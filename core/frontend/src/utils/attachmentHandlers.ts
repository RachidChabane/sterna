import type { Attachment, ImageAttachment, FileAttachment, VideoAttachment, AudioAttachment } from '@/components/models/types'
import { convertImageToBase64, createImagePreview } from '@/utils/imageUtils'
import { convertFileToBase64, isPDFFile, isOfficeFile, isTextFile, readFileAsText } from '@/utils/fileUtils'
import { saveFromAttachment } from '@/utils/attachmentCache'
import { validateFiles } from '@/utils/fileSecurityValidation'
import apiClient, { getAccessToken, LONG_RUNNING_TIMEOUT_MS } from '@/api/client'
import { generateUUID } from '@/lib/utils'

/**
 * Extract text content from PDF and Office documents using backend API
 * @param file The file to extract content from
 * @returns Extracted text content or null if extraction fails
 */
async function extractDocumentContent(file: File): Promise<string | null> {
  try {
    // Convert file to base64
    const base64 = await convertFileToBase64(file)

    // Get authentication token
    const token = getAccessToken()
    if (!token) {
      console.error('No authentication token available')
      return null
    }

    // Call backend extraction endpoint
    const response = await apiClient.post('/documents/extract/', {
      filename: file.name,
      file_data: base64,
      mime_type: file.type
    }, { timeout: LONG_RUNNING_TIMEOUT_MS }).catch((err) => {
      console.error(`Document extraction failed: ${err instanceof Error ? err.message : err}`)
      return null
    })

    if (!response) {
      return null
    }

    const result = response.data

    if (result.success && result.content) {
      return result.content
    } else {
      console.error(`Document extraction error: ${result.error}`)
      return null
    }
  } catch (error) {
    console.error('Failed to extract document content:', error)
    return null
  }
}

const isVideoFile = (file: File) =>
  file.type.startsWith('video/') ||
  /\.(mp4|webm|ogg|ogv|mov|avi|mkv|m4v)$/i.test(file.name)

const isAudioFile = (file: File) =>
  file.type.startsWith('audio/') ||
  /\.(mp3|wav|m4a|aac|ogg|oga|flac|opus)$/i.test(file.name)

export interface BuildResultCounts {
  imagesAdded: number
  pdfsAdded: number
  officeDocsAdded: number
  textsAdded: number
  videosAdded: number
  audiosAdded: number
  errors: number
  blocked: number
  skippedOverflow: number
  securityWarnings: string[]
}

export async function buildAttachmentsFromFiles(
  filesLike: FileList | File[],
  options: { currentCount: number; maxCount?: number }
): Promise<{ attachments: Attachment[]; counts: BuildResultCounts }> {
  const maxCount = options.maxCount ?? 8
  const existing = options.currentCount
  const files = Array.from(filesLike)
  const remainingSlots = Math.max(0, maxCount - existing)
  const filesToProcess = files.slice(0, remainingSlots)
  const skippedOverflow = files.length > remainingSlots ? files.length - remainingSlots : 0

  const results: Attachment[] = []
  let imagesAdded = 0
  let pdfsAdded = 0
  let officeDocsAdded = 0
  let textsAdded = 0
  let videosAdded = 0
  let audiosAdded = 0
  let errors = 0
  const securityWarnings: string[] = []

  // Apply comprehensive security validation (magic byte detection)
  // Use higher size limit if any media files are present
  const hasMedia = filesToProcess.some(f => isVideoFile(f) || isAudioFile(f))
  const validation = await validateFiles(filesToProcess, hasMedia ? 100 : 10)

  // Track blocked files
  const blocked = validation.blockedFiles.length + validation.invalidFiles.length

  // Collect security warnings
  for (const { file, reason } of validation.blockedFiles) {
    securityWarnings.push(`BLOCKED: ${file.name} - ${reason}`)
  }

  for (const { file, reason } of validation.invalidFiles) {
    securityWarnings.push(`INVALID: ${file.name} - ${reason}`)
  }

  for (const { file, message } of validation.warnings) {
    securityWarnings.push(`WARNING: ${file.name} - ${message}`)
  }

  // Process only validated files
  for (const file of validation.validFiles) {
    try {
      // SVG files are XML-based and should be treated as text/code, not images
      const isSVG = file.type === 'image/svg+xml' || file.name.toLowerCase().endsWith('.svg')
      const isImage = file.type.startsWith('image/') && !isSVG
      const isPDF = isPDFFile(file)
      const isText = isTextFile(file) || isSVG

      if (isImage) {
        // Process image attachment
        const base64 = await convertImageToBase64(file)
        const preview = createImagePreview(file)
        const att: ImageAttachment = {
          id: generateUUID(),
          type: 'image',
          file,
          preview,
          base64,
        }
        results.push(att)
        saveFromAttachment(att)
        imagesAdded++
      } else if (isPDF) {
        // Process PDF attachment - extract text content using backend
        
        const textContent = await extractDocumentContent(file)
        
        if (textContent) {
          const att: FileAttachment = {
            id: generateUUID(),
            type: 'file',
            file,
            base64: undefined,
            textContent,
          }
          results.push(att)
          saveFromAttachment(att)
          pdfsAdded++
        } else {
          // Extraction failed, count as error
          securityWarnings.push(`WARNING: ${file.name} - Could not extract PDF content. The file may be encrypted or corrupted.`)
          errors++
        }
      } else if (isOfficeFile(file)) {
        // Process Office document attachment - extract text content using backend
        const textContent = await extractDocumentContent(file)
        if (textContent) {
          const att: FileAttachment = {
            id: generateUUID(),
            type: 'file',
            file,
            base64: undefined,
            textContent,
          }
          results.push(att)
          saveFromAttachment(att)
          officeDocsAdded++
        } else {
          // Extraction failed, count as error
          securityWarnings.push(`WARNING: ${file.name} - Could not extract document content. The file may be encrypted or corrupted.`)
          errors++
        }
      } else if (isText) {
        // Process text/code file attachment
        const text = await readFileAsText(file)
        const att: FileAttachment = {
          id: generateUUID(),
          type: 'file',
          file,
          base64: undefined,
          textContent: text,
        }
        results.push(att)
        saveFromAttachment(att)
        textsAdded++
      } else if (isVideoFile(file)) {
        // Process video attachment - lightweight reference only, no base64
        const preview = URL.createObjectURL(file)
        const att: VideoAttachment = {
          id: generateUUID(),
          type: 'video',
          file,
          preview,
        }
        results.push(att)
        saveFromAttachment(att)
        videosAdded++
      } else if (isAudioFile(file)) {
        // Process audio attachment - lightweight reference only, no base64
        const preview = URL.createObjectURL(file)
        const att: AudioAttachment = {
          id: generateUUID(),
          type: 'audio',
          file,
          preview,
        }
        results.push(att)
        saveFromAttachment(att)
        audiosAdded++
      } else {
        // Unknown file type - try as text
        try {
          const text = await readFileAsText(file)
          const att: FileAttachment = {
            id: generateUUID(),
            type: 'file',
            file,
            base64: undefined,
            textContent: text,
          }
          results.push(att)
          saveFromAttachment(att)
          textsAdded++
        } catch {
          errors++
        }
      }
    } catch {
      errors++
    }
  }

  return {
    attachments: results,
    counts: {
      imagesAdded,
      pdfsAdded,
      officeDocsAdded,
      textsAdded,
      videosAdded,
      audiosAdded,
      errors,
      blocked,
      skippedOverflow,
      securityWarnings
    },
  }
}

export function extractFilesFromDataTransfer(dt: DataTransfer): File[] {
  const files: File[] = []
  if (dt.items && dt.items.length) {
    for (const item of Array.from(dt.items)) {
      if (item.kind === 'file') {
        const f = item.getAsFile()
        if (f) files.push(f)
      }
    }
  } else if (dt.files && dt.files.length) {
    for (const f of Array.from(dt.files)) files.push(f)
  }
  return files
}

export function extractFilesFromClipboard(e: React.ClipboardEvent): File[] {
  const files: File[] = []
  const dt = e.clipboardData
  if (!dt) return files
  if (dt.items && dt.items.length) {
    for (const item of Array.from(dt.items)) {
      if (item.kind === 'file') {
        const f = item.getAsFile()
        if (f) files.push(f)
      }
    }
  } else if (dt.files && dt.files.length) {
    for (const f of Array.from(dt.files)) files.push(f)
  }
  return files
}

