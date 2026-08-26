import type { AttachmentLike } from '@/components/models/types'
import { assetsAPI, assetToReference, getAssetTypeFromMime, type AssetReference } from '@/api/assets'

/**
 * Build a dynamic message for unsupported attachment types
 * @returns Message string or null if all attachments are supported
 */
export function buildUnsupportedAttachmentsMessage(
  hasImages: boolean,
  hasPDFs: boolean,
  hasOfficeFiles: boolean,
  hasText: boolean,
  supportsVision: boolean,
  supportsFiles: boolean
): string | null {
  const unsupportedTypes: string[] = []

  if (hasImages && !supportsVision) {
    unsupportedTypes.push('image')
  }
  if ((hasPDFs || hasOfficeFiles) && !supportsFiles) {
    // If both PDFs and Office files, use generic term
    if (hasPDFs && hasOfficeFiles) {
      unsupportedTypes.push('document file')
    } else if (hasPDFs) {
      unsupportedTypes.push('PDF file')
    } else {
      unsupportedTypes.push('Office document')
    }
  }

  // No unsupported types
  if (unsupportedTypes.length === 0) return null

  // Build first part: what's unsupported
  let typesText: string
  if (unsupportedTypes.length === 1) {
    typesText = `${unsupportedTypes[0]} inputs`
  } else {
    const last = unsupportedTypes.pop()!
    typesText = `${unsupportedTypes.join(', ')} and ${last} inputs`
  }

  // Build second part: what will be processed
  const supportedParts: string[] = []

  if (hasText) {
    supportedParts.push('text')
  }
  if (hasImages && supportsVision) {
    supportedParts.push('images')
  }
  if ((hasPDFs || hasOfficeFiles) && supportsFiles) {
    // If both PDFs and Office files, use generic term
    if (hasPDFs && hasOfficeFiles) {
      supportedParts.push('document files')
    } else if (hasPDFs) {
      supportedParts.push('PDF files')
    } else {
      supportedParts.push('Office documents')
    }
  }

  // If nothing is supported, return a different message
  if (supportedParts.length === 0) {
    return `This model does not support ${typesText}. Your message cannot be processed.`
  }

  // Build the "only X will be processed" part
  let processingText: string
  if (supportedParts.length === 1) {
    processingText = `Only the ${supportedParts[0]}`
  } else if (supportedParts.length === 2) {
    processingText = `Only the ${supportedParts[0]} and ${supportedParts[1]}`
  } else {
    const last = supportedParts.pop()!
    processingText = `Only the ${supportedParts.join(', ')}, and ${last}`
  }

  return `This model does not support ${typesText}. ${processingText} will be processed.`
}

/**
 * Upload attachments as assets and return enriched attachments with asset references
 * This persists files to R2/PostgreSQL for permanent storage
 *
 * Note: If an attachment already has an `assetRef` (e.g., from pre-upload in new conversation flow),
 * it will be used directly without re-uploading.
 */
export async function uploadAttachmentsAsAssets(
  chatId: string,
  attachments: AttachmentLike[]
): Promise<{ enriched: AttachmentLike[], assetRefs: AssetReference[] }> {
  if (attachments.length === 0) {
    return { enriched: [], assetRefs: [] }
  }

  const enriched: AttachmentLike[] = []
  const assetRefs: AssetReference[] = []

  // Upload each attachment in parallel
  const uploadPromises = attachments.map(async (att: AttachmentLike) => {
    // Check if attachment already has an asset reference (from pre-upload)
    const existingAssetRef = att.assetRef
    if (existingAssetRef && existingAssetRef.asset_id) {

      return {
        enriched: att,
        assetRef: existingAssetRef,
      }
    }

    // Check if attachment has assetId but no full assetRef (legacy format)
    const existingAssetId = att.assetId
    if (existingAssetId) {

      // Build a minimal asset reference from available data
      const assetRef: AssetReference = {
        type: 'asset_ref',
        asset_id: existingAssetId,
        filename: att.fileName || att.file?.name || 'unknown',
        mime_type: att.fileType || att.file?.type || 'application/octet-stream',
        asset_type: att.type === 'image' ? 'image' : 'generated',
        size_bytes: att.fileSize || att.file?.size || 0,
        download_url: att.assetUrl || `/api/workspaces/assets/${existingAssetId}/download/`,
      }
      return {
        enriched: att,
        assetRef,
      }
    }

    // No existing asset - need to upload
    // Check if we have a valid File object
    if (!att.file || !(att.file instanceof File)) {
      console.warn(`[uploadAttachmentsAsAssets] No File object for attachment, skipping upload`)
      return { enriched: att, assetRef: null }
    }
    const file = att.file

    try {
      const result = await assetsAPI.uploadFile(chatId, file, {
        assetType: att.type === 'image' ? 'image' : getAssetTypeFromMime(file.type),
      })

      if (result.success && result.asset) {
        // Mutate original attachment to add assetId/assetUrl
        // This ensures the message attachments (which reference the same objects) get updated
        att.assetId = result.asset.id
        att.assetUrl = result.asset.download_url

        // Enrich attachment with asset reference
        const enrichedAtt = {
          ...att,
          assetId: result.asset.id,
          assetUrl: result.asset.download_url,
        }
        return {
          enriched: enrichedAtt,
          assetRef: assetToReference(result.asset),
        }
      } else {
        console.warn(`[uploadAttachmentsAsAssets] Failed to upload ${att.file?.name || 'unknown'}:`, result.error)
        // Return original attachment without asset reference
        return { enriched: att, assetRef: null }
      }
    } catch (error) {
      console.error(`[uploadAttachmentsAsAssets] Error uploading ${att.file?.name || 'unknown'}:`, error)
      return { enriched: att, assetRef: null }
    }
  })

  const results = await Promise.all(uploadPromises)

  for (const result of results) {
    enriched.push(result.enriched)
    if (result.assetRef) {
      assetRefs.push(result.assetRef)
    }
  }


  return { enriched, assetRefs }
}
