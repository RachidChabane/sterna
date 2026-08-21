/**
 * AttachmentMenu Component
 *
 * Provides a simplified attachment button with unified file upload.
 * Accepts all file types (images, PDFs, DOCX, text/code files) in a single menu.
 * Applies comprehensive security validation using magic byte detection.
 */

import { useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Paperclip } from 'lucide-react'
import { cn, generateUUID } from '@/lib/utils'
import { useToast } from '@/hooks/use-toast'
import type { Attachment, ImageAttachment, FileAttachment, VideoAttachment, AudioAttachment } from './types'
import { saveFromAttachment } from '@/utils/attachmentCache'
import {
  convertImageToBase64,
  createImagePreview,
} from '@/utils/imageUtils'
import {
  convertFileToBase64,
  isPDFFile,
  isOfficeFile,
  isTextFile,
  readFileAsText
} from '@/utils/fileUtils'
import { validateFiles } from '@/utils/fileSecurityValidation'
import { getAccessToken } from '@/api/client'

/**
 * Extract text content from PDF and Office documents using backend API
 */
async function extractDocumentContent(file: File): Promise<string | null> {
  try {
    const base64 = await convertFileToBase64(file)
    const token = getAccessToken()

    if (!token) {
      console.error('[AttachmentMenu] No authentication token available')
      return null
    }

    const response = await fetch('/api/documents/extract/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        filename: file.name,
        file_data: base64,
        mime_type: file.type
      }),
    })

    if (!response.ok) {
      console.error(`[AttachmentMenu] Extraction failed: ${response.status}`)
      return null
    }

    const result = await response.json()
    if (result.success && result.content) {
      return result.content
    } else {
      console.error(`[AttachmentMenu] Extraction error: ${result.error}`)
      return null
    }
  } catch (error) {
    console.error('[AttachmentMenu] Failed to extract document:', error)
    return null
  }
}
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface AttachmentMenuProps {
  attachments: Attachment[]
  onAttach: (attachment: Attachment) => void
  onRemove: (attachmentId: string) => void
  disabled?: boolean
}

const MAX_ATTACHMENTS = 8

export function AttachmentMenu({
  attachments,
  onAttach,
  onRemove,
  disabled = false,
}: AttachmentMenuProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()
  const isAtLimit = attachments.length >= MAX_ATTACHMENTS

  /**
   * Unified file handler with comprehensive security validation
   * Supports: Images (PNG, JPG, GIF, WebP, SVG), PDFs, DOCX, and text/code files
   */
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    // Enforce global attachments cap
    const remainingSlots = MAX_ATTACHMENTS - attachments.length
    if (remainingSlots <= 0) {
      toast({
        title: 'Attachment limit reached',
        description: `You can attach up to ${MAX_ATTACHMENTS} items per message`,
        variant: 'destructive'
      })
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    const filesToProcess = Array.from(files).slice(0, remainingSlots)
    const skippedOverflow = files.length - filesToProcess.length

    // Apply comprehensive security validation (magic byte detection)
    // Use higher size limit if any media files are present
    const hasMedia = filesToProcess.some(f =>
      f.type.startsWith('video/') || f.type.startsWith('audio/') ||
      /\.(mp4|webm|ogg|ogv|mov|avi|mkv|m4v|mp3|wav|m4a|aac|flac|opus)$/i.test(f.name)
    )
    const validation = await validateFiles(filesToProcess, hasMedia ? 100 : 10)

    // Show security warnings for blocked files
    if (validation.blockedFiles.length > 0) {
      for (const { file, reason } of validation.blockedFiles) {
        toast({
          title: 'Security Warning',
          description: reason,
          variant: 'destructive'
        })
      }
    }

    // Show errors for invalid files
    if (validation.invalidFiles.length > 0) {
      for (const { file, reason } of validation.invalidFiles) {
        toast({
          title: 'Invalid File',
          description: reason,
          variant: 'destructive'
        })
      }
    }

    // Show non-blocking warnings
    if (validation.warnings.length > 0) {
      for (const { file, message } of validation.warnings) {
        toast({
          title: 'File Type Warning',
          description: message,
          variant: 'default'
        })
      }
    }

    // Process valid files
    let successCount = 0
    let errorCount = 0

    for (const file of validation.validFiles) {
      try {
        // SVG files are XML-based and should be treated as text/code, not images
        const isSVG = file.type === 'image/svg+xml' || file.name.toLowerCase().endsWith('.svg')
        const isImage = file.type.startsWith('image/') && !isSVG
        const isPDF = isPDFFile(file)
        const isOffice = isOfficeFile(file)
        const isText = isTextFile(file) || isSVG

        if (isImage) {
          // Process image attachment
          const base64 = await convertImageToBase64(file)
          const preview = createImagePreview(file)

          const attachment: ImageAttachment = {
            id: generateUUID(),
            type: 'image',
            file,
            preview,
            base64
          }

          onAttach(attachment)
          saveFromAttachment(attachment)
          successCount += 1
        } else if (isPDF) {
          // Process PDF attachment - convert to base64 for preview and extract text for sending
          const base64 = await convertFileToBase64(file)
          const textContent = await extractDocumentContent(file)

          // PDFs always get attached (base64 for preview), text extraction is optional
          const attachment: FileAttachment = {
            id: generateUUID(),
            type: 'file',
            file,
            base64,
            textContent: textContent || undefined
          }

          onAttach(attachment)
          saveFromAttachment(attachment)
          successCount += 1

          // Show warning if text extraction failed (preview still works)
          if (!textContent) {
            toast({
              title: 'PDF attached',
              description: `Text extraction failed for ${file.name}. The PDF can still be previewed.`,
              variant: 'default'
            })
          }
        } else if (isOffice) {
          // Process Office document attachment - extract text content using backend
          const textContent = await extractDocumentContent(file)

          if (textContent) {
            const attachment: FileAttachment = {
              id: generateUUID(),
              type: 'file',
              file,
              base64: undefined,
              textContent
            }

            onAttach(attachment)
            saveFromAttachment(attachment)
            successCount += 1
          } else {
            // Extraction failed
            toast({
              title: 'Extraction Failed',
              description: `Could not extract content from ${file.name}. The file may be encrypted or corrupted.`,
              variant: 'destructive'
            })
            errorCount += 1
          }
        } else if (isText) {
          // Process text/code file attachment
          const textContent = await readFileAsText(file)

          const attachment: FileAttachment = {
            id: generateUUID(),
            type: 'file',
            file,
            base64: undefined,
            textContent
          }

          onAttach(attachment)
          saveFromAttachment(attachment)
          successCount += 1
        } else if (file.type.startsWith('video/') || /\.(mp4|webm|mov|avi|mkv|m4v)$/i.test(file.name)) {
          // Process video attachment - lightweight reference only, no base64
          const preview = URL.createObjectURL(file)
          const attachment: VideoAttachment = {
            id: generateUUID(),
            type: 'video',
            file,
            preview,
          }
          onAttach(attachment)
          saveFromAttachment(attachment)
          successCount += 1
        } else if (file.type.startsWith('audio/') || /\.(mp3|wav|m4a|aac|flac|opus|ogg|oga)$/i.test(file.name)) {
          // Process audio attachment - lightweight reference only, no base64
          const preview = URL.createObjectURL(file)
          const attachment: AudioAttachment = {
            id: generateUUID(),
            type: 'audio',
            file,
            preview,
          }
          onAttach(attachment)
          saveFromAttachment(attachment)
          successCount += 1
        } else {
          // Unknown file type - try as text
          try {
            const textContent = await readFileAsText(file)

            const attachment: FileAttachment = {
              id: generateUUID(),
              type: 'file',
              file,
              base64: undefined,
              textContent
            }

            onAttach(attachment)
            saveFromAttachment(attachment)
            successCount += 1
          } catch {
            errorCount += 1
          }
        }
      } catch (error) {
        errorCount += 1
      }
    }

    // Show summary toast
    const totalFailed = validation.blockedFiles.length + validation.invalidFiles.length + errorCount

    if (successCount > 0) {
      toast({
        title: successCount === 1 ? 'File attached' : 'Files attached',
        description: successCount === 1
          ? '1 file added'
          : `${successCount} file${successCount > 1 ? 's' : ''} added${totalFailed ? ` • ${totalFailed} failed` : ''}${skippedOverflow ? ` • ${skippedOverflow} skipped (limit)` : ''}`
      })
    } else if (totalFailed > 0) {
      toast({
        title: 'Failed to attach files',
        description: `${totalFailed} file${totalFailed > 1 ? 's' : ''} could not be added`,
        variant: 'destructive'
      })
    }

    // Reset input so same file(s) can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const hasAttachments = attachments.length > 0

  return (
    <div className="flex items-center">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className={cn(
                "relative h-10 w-10 rounded-full transition-all duration-400 ease-bounce hover:scale-110 hover:shadow-[0_0_20px_rgba(59,130,246,0.3)] hover:border-primary/50 active:scale-95 active:border-primary active:bg-primary/10 disabled:opacity-50 disabled:hover:scale-100 disabled:hover:shadow-none touch-manipulation",
                hasAttachments && "border-primary/50"
              )}
              disabled={disabled || isAtLimit}
              onClick={() => fileInputRef.current?.click()}
            >
              <Paperclip className="h-4 w-4" />
              {/* Badge counter on button */}
              {hasAttachments && (
                <span className="absolute -top-1 -right-1 h-4 min-w-4 px-1 rounded-full bg-primary text-[10px] font-bold text-primary-foreground flex items-center justify-center shadow-sm">
                  {attachments.length}
                </span>
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p className="font-medium">Attach Files</p>
            <p className="text-xs text-muted-foreground mt-1">
              {hasAttachments
                ? `${attachments.length}/${MAX_ATTACHMENTS} attached`
                : 'Images, videos, audio, PDFs, Office docs, text/code'
              }
            </p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,video/*,audio/*,.pdf,.rtf,.docx,.doc,.xlsx,.xls,.xlsm,.xlsb,.pptx,.ppt,.odt,.ods,.odp,.odg,.txt,.csv,.json,.md,.html,.xml,.js,.jsx,.ts,.tsx,.py,.java,.c,.cpp,.cs,.php,.rb,.go,.rs,.swift,.kt,.scala,.sql,.sh,.bash,.zsh,.yaml,.yml,.toml,.ini,.env,.log,.gitignore,.dockerfile,.vue,.svelte,.astro,.mp4,.webm,.mov,.avi,.mkv,.m4v,.mp3,.wav,.m4a,.aac,.flac,.opus,.ogg"
        multiple
        onChange={handleFileSelect}
        className="hidden"
      />
    </div>
  )
}
