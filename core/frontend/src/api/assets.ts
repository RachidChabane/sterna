/**
 * Assets API Client
 *
 * Handles upload, download, and management of conversation attachments.
 * Assets are stored in tiered storage (PostgreSQL for small, R2 for large).
 */

import { api } from './client'

// ============================================================================
// Types
// ============================================================================

/**
 * Asset types supported by the backend
 */
export type AssetType = 'image' | 'video' | 'audio' | 'thumbnail' | 'generated' | 'document'

/**
 * Storage type for the asset
 */
export type StorageType = 'inline' | 'r2'

/**
 * Asset metadata returned from the API
 */
export interface Asset {
  id: string
  asset_type: AssetType
  filename: string
  mime_type: string
  size_bytes: number
  storage_type: StorageType
  width: number | null
  height: number | null
  duration_seconds: number | null
  sha256_hash: string
  created_at: string
  download_url: string
  generation_prompt: string | null
  generation_model: string | null
}

/**
 * Request payload for uploading an asset
 */
export interface AssetUploadRequest {
  chat_id: string
  message_id?: string
  filename: string
  mime_type: string
  asset_type: AssetType
  content_base64: string
  width?: number
  height?: number
  duration_seconds?: number
  generation_prompt?: string
  generation_model?: string
}

/**
 * Response from asset upload
 */
export interface AssetUploadResponse {
  success: boolean
  asset?: Asset
  deduplicated?: boolean
  error?: string
}

/**
 * Response from listing assets
 */
export interface AssetListResponse {
  assets: Asset[]
  count: number
}

/**
 * Gallery asset with chat context
 */
export interface GalleryAsset extends Asset {
  chat_id: string
  chat_name: string | null
  conversation_id: string | null  // Parent conversation ID (for navigation)
  generation_model_display_name: string | null
}

/**
 * Paginated response for gallery images
 */
export interface GalleryListResponse {
  count: number
  next: string | null
  previous: string | null
  results: GalleryAsset[]
}

/**
 * Asset reference to store in message content
 * This is what gets saved in the message instead of inline base64
 */
export interface AssetReference {
  type: 'asset_ref'
  asset_id: string
  filename: string
  mime_type: string
  asset_type: AssetType
  size_bytes: number
  width?: number
  height?: number
  download_url: string
}

// ============================================================================
// Share Link Types
// ============================================================================

/**
 * Share link metadata returned from the API
 */
export interface ShareLink {
  id: string
  token: string
  share_url: string
  asset_id: string
  asset_type: AssetType
  asset_filename: string
  thumbnail_url: string | null
  is_active: boolean
  expires_at: string | null
  view_count: number
  last_viewed_at: string | null
  custom_title: string | null
  created_at: string
  is_expired: boolean
  is_valid: boolean
}

/**
 * Request payload for creating a share link
 */
export interface CreateShareLinkRequest {
  expires_in_hours?: number
  custom_title?: string
  watermark_enabled?: boolean
  watermark_position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left'
}

/**
 * Response from listing share links
 */
export interface ShareLinkListResponse {
  count: number
  page: number
  page_size: number
  results: ShareLink[]
}

/**
 * Response from getting asset share links
 */
export interface AssetShareLinksResponse {
  share_links: ShareLink[]
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Determine asset type from MIME type
 * Note: SVGs are excluded from 'image' as they are XML-based text files
 */
export function getAssetTypeFromMime(mimeType: string): AssetType {
  // SVG files are XML-based and should be treated as documents, not images
  if (mimeType === 'image/svg+xml') return 'document'
  if (mimeType.startsWith('image/')) return 'image'
  if (mimeType.startsWith('video/')) return 'video'
  if (mimeType.startsWith('audio/')) return 'audio'
  return 'document' // Default to document for text-based files
}

/**
 * Convert a File to base64
 */
export async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      // Remove data URL prefix if present
      const base64 = result.includes(',') ? result.split(',')[1] : result
      resolve(base64)
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

/**
 * Get image dimensions from a File
 */
export async function getImageDimensions(file: File): Promise<{ width: number; height: number } | null> {
  if (!file.type.startsWith('image/')) return null

  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      resolve({ width: img.naturalWidth, height: img.naturalHeight })
      URL.revokeObjectURL(img.src)
    }
    img.onerror = () => {
      resolve(null)
      URL.revokeObjectURL(img.src)
    }
    img.src = URL.createObjectURL(file)
  })
}

/**
 * Convert Asset to AssetReference for storing in messages
 */
export function assetToReference(asset: Asset): AssetReference {
  return {
    type: 'asset_ref',
    asset_id: asset.id,
    filename: asset.filename,
    mime_type: asset.mime_type,
    asset_type: asset.asset_type,
    size_bytes: asset.size_bytes,
    width: asset.width ?? undefined,
    height: asset.height ?? undefined,
    download_url: asset.download_url,
  }
}

// ============================================================================
// API Client
// ============================================================================

export const assetsAPI = {
  /**
   * Upload a new asset
   */
  async upload(request: AssetUploadRequest): Promise<AssetUploadResponse> {
    try {
      const response = await api.post('/workspaces/assets/upload/', request)
      return response.data
    } catch (error: any) {
      console.error('[assetsAPI] Upload failed:', error)
      return {
        success: false,
        error: error.response?.data?.error || error.message || 'Upload failed',
      }
    }
  },

  /**
   * Upload a File object as an asset
   * Convenience method that handles base64 conversion
   */
  async uploadFile(
    chatId: string,
    file: File,
    options?: {
      messageId?: string
      assetType?: AssetType
    }
  ): Promise<AssetUploadResponse> {
    try {
      // Convert file to base64
      const base64 = await fileToBase64(file)

      // Get image dimensions if applicable
      const dimensions = await getImageDimensions(file)

      const request: AssetUploadRequest = {
        chat_id: chatId,
        message_id: options?.messageId,
        filename: file.name,
        mime_type: file.type || 'application/octet-stream',
        asset_type: options?.assetType || getAssetTypeFromMime(file.type),
        content_base64: base64,
        width: dimensions?.width,
        height: dimensions?.height,
      }

      return await this.upload(request)
    } catch (error: any) {
      console.error('[assetsAPI] uploadFile failed:', error)
      return {
        success: false,
        error: error.message || 'Failed to process file',
      }
    }
  },

  /**
   * Upload multiple files in parallel
   * Returns results in the same order as input files
   */
  async uploadFiles(
    chatId: string,
    files: File[],
    options?: {
      messageId?: string
      onProgress?: (completed: number, total: number) => void
    }
  ): Promise<AssetUploadResponse[]> {
    const results: AssetUploadResponse[] = []
    let completed = 0

    // Upload in parallel with concurrency limit
    const CONCURRENCY = 3
    const chunks: File[][] = []
    for (let i = 0; i < files.length; i += CONCURRENCY) {
      chunks.push(files.slice(i, i + CONCURRENCY))
    }

    for (const chunk of chunks) {
      const chunkResults = await Promise.all(
        chunk.map(file => this.uploadFile(chatId, file, {
          messageId: options?.messageId,
        }))
      )
      results.push(...chunkResults)
      completed += chunk.length
      options?.onProgress?.(completed, files.length)
    }

    return results
  },

  /**
   * Get asset metadata
   */
  async get(assetId: string): Promise<Asset | null> {
    try {
      const response = await api.get(`/workspaces/assets/${assetId}/`)
      return response.data
    } catch (error) {
      console.error('[assetsAPI] Get failed:', error)
      return null
    }
  },

  /**
   * Get asset download URL
   * For inline display, use this URL directly in <img> tags
   */
  getDownloadUrl(assetId: string): string {
    return `/api/workspaces/assets/${assetId}/download/`
  },

  /**
   * Download asset content as Blob
   * @param assetId - The asset ID to download
   * @param options - Optional watermark settings
   */
  async download(
    assetId: string,
    options?: {
      watermark?: boolean
      watermark_position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left'
    }
  ): Promise<Blob | null> {
    try {
      const params: Record<string, string> = {}
      if (options?.watermark) {
        params.watermark = 'true'
        if (options.watermark_position) {
          params.watermark_position = options.watermark_position
        }
      }
      const response = await api.get(`/workspaces/assets/${assetId}/download/`, {
        responseType: 'blob',
        params,
      })
      return response.data
    } catch (error) {
      console.error('[assetsAPI] Download failed:', error)
      return null
    }
  },

  /**
   * Delete an asset
   */
  async delete(assetId: string): Promise<boolean> {
    try {
      await api.delete(`/workspaces/assets/${assetId}/delete/`)
      return true
    } catch (error) {
      console.error('[assetsAPI] Delete failed:', error)
      return false
    }
  },

  /**
   * List all assets in a chat
   */
  async listByChat(chatId: string): Promise<Asset[]> {
    try {
      const response = await api.get(`/workspaces/assets/chat/${chatId}/`)
      return response.data.assets || []
    } catch (error) {
      console.error('[assetsAPI] List by chat failed:', error)
      return []
    }
  },

  /**
   * List all assets attached to a specific message
   */
  async listByMessage(messageId: string): Promise<Asset[]> {
    try {
      const response = await api.get(`/workspaces/assets/message/${messageId}/`)
      return response.data.assets || []
    } catch (error) {
      console.error('[assetsAPI] List by message failed:', error)
      return []
    }
  },

  /**
   * List all AI-generated images for the current user
   */
  async listUserGeneratedImages(params?: {
    page?: number
    page_size?: number
    ordering?: string
    search?: string
  }): Promise<GalleryListResponse> {
    try {
      const response = await api.get('/workspaces/assets/user/images/', { params })
      return response.data
    } catch (error) {
      console.error('[assetsAPI] List user generated images failed:', error)
      return {
        count: 0,
        next: null,
        previous: null,
        results: [],
      }
    }
  },

  /**
   * List all AI-generated videos for the current user
   */
  async listUserGeneratedVideos(params?: {
    page?: number
    page_size?: number
    ordering?: string
    search?: string
  }): Promise<GalleryListResponse> {
    try {
      const response = await api.get('/workspaces/assets/user/videos/', { params })
      return response.data
    } catch (error) {
      console.error('[assetsAPI] List user generated videos failed:', error)
      return {
        count: 0,
        next: null,
        previous: null,
        results: [],
      }
    }
  },

  /**
   * Get a presigned URL for direct access to an asset
   * Useful for video players that need direct access to media
   */
  async getPresignedUrl(assetId: string, expiration?: number): Promise<{
    presigned_url: string
    expires_in: number
    mime_type: string
    filename: string
    size_bytes: number
  } | null> {
    try {
      const params = expiration ? { expiration } : undefined
      const response = await api.get(`/workspaces/assets/${assetId}/presigned-url/`, { params })
      return response.data
    } catch (error) {
      console.error('[assetsAPI] Get presigned URL failed:', error)
      return null
    }
  },

  // ============================================================================
  // Share Link Methods
  // ============================================================================

  /**
   * Create a public share link for an asset
   */
  async createShareLink(
    assetId: string,
    options?: CreateShareLinkRequest
  ): Promise<ShareLink | null> {
    try {
      const response = await api.post(`/workspaces/assets/${assetId}/share/`, options || {})
      return response.data
    } catch (error: any) {
      console.error('[assetsAPI] Create share link failed:', error)
      throw new Error(error.response?.data?.error || 'Failed to create share link')
    }
  },

  /**
   * Revoke (soft delete) a share link
   */
  async revokeShareLink(token: string): Promise<boolean> {
    try {
      await api.delete(`/workspaces/assets/share/${token}/revoke/`)
      return true
    } catch (error) {
      console.error('[assetsAPI] Revoke share link failed:', error)
      return false
    }
  },

  /**
   * Get all share links for a specific asset
   */
  async getAssetShareLinks(assetId: string): Promise<ShareLink[]> {
    try {
      const response = await api.get(`/workspaces/assets/${assetId}/shares/`)
      return response.data.share_links || []
    } catch (error) {
      console.error('[assetsAPI] Get asset share links failed:', error)
      return []
    }
  },

  /**
   * List all share links created by the current user
   */
  async listShareLinks(params?: {
    page?: number
    page_size?: number
    active?: boolean
    asset_id?: string
  }): Promise<ShareLinkListResponse> {
    try {
      const queryParams: Record<string, string | number> = {}
      if (params?.page) queryParams.page = params.page
      if (params?.page_size) queryParams.page_size = params.page_size
      if (params?.active !== undefined) queryParams.active = params.active ? 'true' : 'false'
      if (params?.asset_id) queryParams.asset_id = params.asset_id

      const response = await api.get('/workspaces/assets/shares/', { params: queryParams })
      return response.data
    } catch (error) {
      console.error('[assetsAPI] List share links failed:', error)
      return {
        count: 0,
        page: 1,
        page_size: 20,
        results: [],
      }
    }
  },
}

export default assetsAPI
