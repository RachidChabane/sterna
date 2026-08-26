import type { Message, Model } from '@/components/models/types'
import { assetsAPI } from '@/api/assets'
import { extractTextFromContent } from '@/utils/chatUtils'
import { isPDFFile, isOfficeFile, formatFileSize } from '@/utils/fileUtils'
import type { ApiMessage } from './types'

export interface AttachmentPreparationResult {
  /** The same array passed in, with the last user entry replaced/updated in place. */
  apiMessages: ApiMessage[]
  hasFileAttachments: boolean
  uploadedFiles: File[]
  workspaceAssets: { asset_id: string; filename: string }[]
  /** False when nothing supported survived filtering — caller should stop loading and bail out. */
  hasSendableContent: boolean
}

function attachmentNeedsBase64Fetch(att: any): boolean {
  const assetId = att.assetId || att.assetRef?.asset_id
  if (!assetId) return false
  if (att.type === 'image' && !att.base64) return true
  if (att.type === 'file' && !att.base64 && !att.textContent) return true
  return false
}

/**
 * Fetch base64 for images/files that only have an assetId or assetRef (no base64
 * data yet) — images loaded from the DB after a page reload, or files pre-uploaded
 * in the new-conversation flow. Mutates each attachment's `base64` field in place.
 */
async function hydrateAttachmentBase64(attachments: any[]): Promise<void> {
  const blobToDataUrl = (blob: Blob): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(reader.result as string)
      reader.onerror = reject
      reader.readAsDataURL(blob)
    })

  for (const att of attachments) {
    if (!attachmentNeedsBase64Fetch(att)) continue
    const assetId = att.assetId || att.assetRef?.asset_id
    try {
      const blob = await assetsAPI.download(assetId)
      if (blob) {
        att.base64 = await blobToDataUrl(blob)
      }
    } catch (error) {
      console.error(`[prepareApiMessagesWithAttachments] Failed to fetch attachment for assetId ${assetId}:`, error)
    }
  }
}

function buildResult(
  apiMessages: ApiMessage[],
  lastApiUserIndex: number,
  lastUserStateMsg: Message,
  model: Model,
  attachments: any[],
): AttachmentPreparationResult {
  // Helper to check if attachment is a PDF (handles both File object and extracted properties)
  const isPDF = (a: any): boolean => {
    if (a.file && isPDFFile(a.file)) return true
    // Fallback: check extracted properties or assetRef
    const filename = a.fileName || a.file?.name || a.assetRef?.filename || ''
    const mimeType = a.fileType || a.file?.type || a.assetRef?.mime_type || ''
    return mimeType === 'application/pdf' || filename.toLowerCase().endsWith('.pdf')
  }

  // Helper to check if attachment is an Office file
  const isOffice = (a: any): boolean => {
    if (a.file && isOfficeFile(a.file)) return true
    // Fallback: check extracted properties or assetRef
    const filename = a.fileName || a.file?.name || a.assetRef?.filename || ''
    const mimeType = a.fileType || a.file?.type || a.assetRef?.mime_type || ''
    const officeExtensions = ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp']
    const officeMimes = [
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-powerpoint',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    ]
    return officeMimes.includes(mimeType) || officeExtensions.some(ext => filename.toLowerCase().endsWith(ext))
  }

  const imageAtts = attachments.filter((a: any) => a.type === 'image' && a.base64)
  const pdfAtts = attachments.filter((a: any) => a.type === 'file' && a.base64 && !a.textContent && isPDF(a))
  const officeAtts = attachments.filter((a: any) => a.type === 'file' && a.base64 && !a.textContent && isOffice(a))
  const otherBinaryAtts = attachments.filter((a: any) => a.type === 'file' && a.base64 && !a.textContent && !isPDF(a) && !isOffice(a))
  const textFileAtts = attachments.filter((a: any) => a.type === 'file' && a.textContent)
  const videoAtts = attachments.filter((a: any) => a.type === 'video')
  const audioAtts = attachments.filter((a: any) => a.type === 'audio')
  const mediaToolAtts = [...videoAtts, ...audioAtts]

  // Extract File objects for file tools (workspace upload)
  // This includes ALL file attachments (PDFs, text files, video, audio) for workspace access
  const allFileAtts = attachments.filter((a: any) =>
    (a.type === 'file' && a.file) ||
    (a.type === 'video' && a.file) ||
    (a.type === 'audio' && a.file)
  )
  const uploadedFiles: File[] = allFileAtts.map((a: any) => a.file).filter((f: any) => f instanceof File)

  // Collect asset IDs for workspace upload — only for assets WITHOUT a real File object
  // (assets with real File objects are sent via FormData and copied by the request.FILES path)
  const workspaceAssets: { asset_id: string; filename: string }[] = attachments
    .filter((a: any) => {
      const assetId = a.assetId || a.assetRef?.asset_id
      const hasRealFile = a.file instanceof File
      return assetId && !hasRealFile && (a.type === 'file' || a.type === 'video' || a.type === 'audio')
    })
    .map((a: any) => ({
      asset_id: a.assetId || a.assetRef?.asset_id,
      filename: a.fileName || a.assetRef?.filename || 'unknown',
    }))

  // Model capabilities
  const supportsVision = model.input_modalities?.includes('image')
  const supportsFiles = model.input_modalities?.includes('file')

  // Only include attachments supported by the target model
  const includeImages = supportsVision ? imageAtts : []
  const includePDFs = supportsFiles ? pdfAtts : []
  const includeOfficeFiles = supportsFiles ? officeAtts : []
  const includeOtherBinaryFiles = supportsFiles ? otherBinaryAtts : []
  const allIncludeFiles = [...includePDFs, ...includeOfficeFiles, ...includeOtherBinaryFiles]
  const hasFileAttachments = allIncludeFiles.length > 0

  // Extract original typed text from the message content
  const originalText = extractTextFromContent(lastUserStateMsg.content as any)

  // Append text file contents for API only
  let apiText = originalText
  if (textFileAtts.length > 0) {
    for (const file of textFileAtts) {
      // Handle both normal attachments (file.file.name) and serialized ones (file.fileName)
      const fileName = file.file?.name || (file as any).fileName || 'file'
      apiText += `\n\n--- Fichier attaché: ${fileName} ---\n${file.textContent}\n--- Fin du fichier ---`
    }
  }

  // Build media text references for video/audio (lightweight URL references, not base64)
  const buildMediaTextRef = (text: string): string => {
    if (mediaToolAtts.length === 0) return text
    const lines = mediaToolAtts.map((media: any) => {
      const filename = media.fileName || media.file?.name || media.assetRef?.filename
      const assetId = media.assetId || media.assetRef?.asset_id
      const assetUrl = media.assetUrl || media.assetRef?.download_url
        || (assetId ? `/api/workspaces/assets/${assetId}/download/` : '')
      const mime = media.fileType || media.file?.type || media.assetRef?.mime_type || ''
      const size = media.fileSize || media.file?.size || media.assetRef?.size_bytes || 0
      const sizeStr = size > 0 ? `, ${formatFileSize(size)}` : ''
      return assetUrl ? `- ${filename}: asset_url="${assetUrl}" (${mime}${sizeStr})` : null
    }).filter(Boolean)

    if (lines.length > 0) {
      text += `\n\n[Attached media files (use asset_url with video tools like animate_image, animate_character):\n${lines.join('\n')}\n]`
    }
    return text
  }

  // Reconstruct the last user message content for API
  // Note: OpenRouter's file-parser plugin expects files (PDFs, Office docs) in the same format as images
  // Using image_url with the data URI scheme allows the plugin to detect and parse the file type
  if (includeImages.length > 0 || allIncludeFiles.length > 0) {
    // Build image metadata text for edit_image tool support
    // This lets the LLM know the asset_url to use when editing user-uploaded images
    let textWithImageMetadata = apiText
    if (includeImages.length > 0) {
      const imageMetadataLines = includeImages.map((img: any, idx: number) => {
        const filename = img.fileName || img.file?.name || img.assetRef?.filename || `image_${idx + 1}`
        // Get asset URL from various sources, or construct from asset ID
        const assetId = img.assetId || img.assetRef?.asset_id
        const assetUrl = img.assetUrl || img.assetRef?.download_url || (assetId ? `/api/workspaces/assets/${assetId}/download/` : '')
        return assetUrl ? `- ${filename}: asset_url="${assetUrl}"` : `- ${filename}`
      }).filter((line: string) => line.includes('asset_url'))

      if (imageMetadataLines.length > 0) {
        textWithImageMetadata += `\n\n[Attached images (for use with edit_image tool):\n${imageMetadataLines.join('\n')}\n]`
      }
    }

    // Append media (video/audio) text references
    textWithImageMetadata = buildMediaTextRef(textWithImageMetadata)

    const parts = [
      { type: 'text' as const, text: textWithImageMetadata },
      ...includeImages.map((img: any) => ({ type: 'image_url' as const, image_url: { url: img.base64 } })),
      ...allIncludeFiles.map((f: any) => ({ type: 'image_url' as const, image_url: { url: f.base64 } })),
    ]
    apiMessages[lastApiUserIndex] = { role: 'user', content: parts }
  } else {
    // Append media (video/audio) text references even when no images/files
    apiMessages[lastApiUserIndex] = { role: 'user', content: buildMediaTextRef(apiText) }
  }

  // If after filtering nothing is left to send (no text and no supported parts), cancel early
  const hasTextToSend = (apiText || '').trim().length > 0
  const hasPartsToSend = includeImages.length > 0 || allIncludeFiles.length > 0
  const hasMediaRefs = mediaToolAtts.length > 0
  const hasSendableContent = hasTextToSend || hasPartsToSend || hasMediaRefs

  return { apiMessages, hasFileAttachments, uploadedFiles, workspaceAssets, hasSendableContent }
}

/**
 * Build the API-bound version of the last user message by incorporating attachments
 * (images/PDFs/Office docs) and text-file contents, filtering parts down to what the
 * target model's `input_modalities` actually support. Mutates `apiMessages` in place
 * at `lastApiUserIndex`.
 *
 * Returns a plain result (not a Promise) when no attachment needs a base64 fetch —
 * the overwhelmingly common case (no attachments, or attachments already carrying
 * base64) — so callers that don't need to await keep sendToModel's dispatch to
 * llmApi.completeStream fully synchronous, matching the pre-extraction call graph.
 * Only attachments referencing an assetId without base64 data (reload / pre-upload)
 * force the async path.
 */
export function prepareApiMessagesWithAttachments(
  apiMessages: ApiMessage[],
  lastApiUserIndex: number,
  lastUserStateMsg: Message,
  model: Model,
): AttachmentPreparationResult | Promise<AttachmentPreparationResult> {
  const attachments = (lastUserStateMsg as any).attachments || []

  if (!attachments.some(attachmentNeedsBase64Fetch)) {
    return buildResult(apiMessages, lastApiUserIndex, lastUserStateMsg, model, attachments)
  }

  return hydrateAttachmentBase64(attachments).then(() =>
    buildResult(apiMessages, lastApiUserIndex, lastUserStateMsg, model, attachments)
  )
}
