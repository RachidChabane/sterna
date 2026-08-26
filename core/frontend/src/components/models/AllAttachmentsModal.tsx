import { FileCode, FileType, ImagePlus, Loader2, Music, Play, Video } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { getFileExtension } from '@/utils/fileUtils'
import { formatFileSize } from '@/utils/imageUtils'
import { TypeBadge } from '@/lib/type-badges'
import type { Attachment, AudioAttachment, FileAttachment, ImageAttachment, VideoAttachment } from './types'

interface AllAttachmentsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  attachments: Attachment[]
  loadedBlobUrls: Record<string, string>
  loadingAssetIds: Set<string>
  loadingFileId: string | null
  onLoadAsset: (assetId: string) => Promise<string | null>
  onOpenImageGallery: (images: { src: string; alt: string }[], selectedIndex: number) => void
  onOpenTextFile: (file: FileAttachment) => void
  onOpenPdf: (src: string, name: string) => void
}

export function AllAttachmentsModal({
  open,
  onOpenChange,
  attachments,
  loadedBlobUrls,
  loadingAssetIds,
  loadingFileId,
  onLoadAsset,
  onOpenImageGallery,
  onOpenTextFile,
  onOpenPdf,
}: AllAttachmentsModalProps) {
  const imageAtts = attachments.filter((a): a is ImageAttachment => a.type === 'image')
  const videoAtts = attachments.filter((a): a is VideoAttachment => a.type === 'video')
  const audioAtts = attachments.filter((a): a is AudioAttachment => a.type === 'audio')
  const fileAtts = attachments.filter((a): a is FileAttachment => a.type === 'file')

  // Categorize files by mime type or extension
  const textCodeAtts = fileAtts.filter(f => {
    const mimeType = f.file?.type || ''
    const name = f.file?.name || ''
    const ext = getFileExtension(name).toLowerCase()
    // Text-based mime types or common text file extensions
    return mimeType.startsWith('text/') ||
      mimeType === 'application/json' ||
      mimeType === 'application/xml' ||
      mimeType === 'application/javascript' ||
      ['txt', 'json', 'xml', 'csv', 'md', 'js', 'ts', 'jsx', 'tsx', 'py', 'html', 'css', 'yaml', 'yml', 'sh', 'sql'].includes(ext)
  })

  const pdfDocxAtts = fileAtts.filter(f => {
    const mimeType = f.file?.type || ''
    const name = f.file?.name || ''
    const ext = getFileExtension(name).toLowerCase()
    return ['pdf', 'doc', 'docx'].includes(ext) ||
      mimeType === 'application/pdf' ||
      mimeType === 'application/msword' ||
      mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Attachments</DialogTitle>
          <DialogDescription>
            {attachments.length} item{attachments.length !== 1 ? 's' : ''}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 max-h-[60vh] overflow-y-auto">
          {/* Images Section */}
          {imageAtts.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <ImagePlus className="h-4 w-4" />
                <span>Images</span>
                <span className="text-xs text-muted-foreground/70">({imageAtts.length})</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {imageAtts.map((img, i) => {
                  // Use assetId to load via API (direct URLs don't work due to auth)
                  const assetId = img.assetId || img.id
                  const blobUrl = assetId ? loadedBlobUrls[assetId] : null
                  const src = img.base64 || blobUrl || ''
                  const alt = img.file?.name || 'image'
                  const isLoading = assetId ? loadingAssetIds.has(assetId) : false
                  const needsLoad = !src && assetId && !isLoading

                  // Trigger loading if needed
                  if (needsLoad) {
                    onLoadAsset(assetId)
                  }

                  return (
                    <button
                      key={img.id}
                      type="button"
                      className="w-full h-48 rounded-md overflow-hidden cursor-zoom-in hover:opacity-90 transition-opacity"
                      onClick={() => {
                        if (!src) return
                        // Hydrate images with blob URLs
                        const imgs = imageAtts
                          .map(a => {
                            const aAssetId = a.assetId || a.id
                            const aBlobUrl = aAssetId ? loadedBlobUrls[aAssetId] : null
                            return { src: a.base64 || aBlobUrl || '', alt: a.file?.name || 'image' }
                          })
                          .filter(it => it.src)
                        onOpenImageGallery(imgs, i)
                        onOpenChange(false)
                      }}
                    >
                      {isLoading ? (
                        <div className="w-full h-full flex items-center justify-center bg-muted/40">
                          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                        </div>
                      ) : src ? (
                        <img src={src} alt={alt} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground bg-muted/40">
                          {alt}
                        </div>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Videos Section */}
          {videoAtts.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <Video className="h-4 w-4" />
                <span>Videos</span>
                <span className="text-xs text-muted-foreground/70">({videoAtts.length})</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {videoAtts.map((vid) => {
                  const name = vid.file?.name || 'video'
                  const ext = getFileExtension(name).toUpperCase()
                  const sizeStr = formatFileSize(vid.file?.size || 0)
                  const assetId = vid.assetId || vid.id
                  const blobUrl = assetId ? loadedBlobUrls[assetId] : null
                  const src = vid.preview || blobUrl || ''
                  const isLoading = assetId ? loadingAssetIds.has(assetId) : false

                  if (!src && assetId && !isLoading) {
                    onLoadAsset(assetId)
                  }

                  return (
                    <div
                      key={vid.id}
                      className="relative w-full h-48 rounded-md overflow-hidden bg-muted/40 group"
                    >
                      {isLoading ? (
                        <div className="w-full h-full flex items-center justify-center">
                          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                        </div>
                      ) : src ? (
                        <video
                          src={src}
                          preload="metadata"
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <Video className="h-8 w-8 text-muted-foreground" />
                        </div>
                      )}
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <div className="w-10 h-10 rounded-full bg-black/50 flex items-center justify-center">
                          <Play className="h-5 w-5 text-white ml-0.5" fill="white" />
                        </div>
                      </div>
                      <div className="absolute bottom-1 left-1 flex items-center gap-1">
                        <TypeBadge type={ext} />
                        <span className="text-[10px] px-1.5 py-0 rounded bg-black/60 text-white">{sizeStr}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Audio Section */}
          {audioAtts.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <Music className="h-4 w-4" />
                <span>Audio</span>
                <span className="text-xs text-muted-foreground/70">({audioAtts.length})</span>
              </div>
              <div className="flex flex-col gap-2">
                {audioAtts.map((aud) => {
                  const name = aud.file?.name || 'audio'
                  const ext = getFileExtension(name).toUpperCase()
                  const sizeStr = formatFileSize(aud.file?.size || 0)
                  return (
                    <div
                      key={aud.id}
                      className="relative rounded-lg border border-border bg-secondary/30 p-2.5 w-full"
                    >
                      <div className="flex items-center gap-2">
                        <div className="flex-shrink-0 p-1.5 rounded bg-gradient-to-br from-purple-500/20 to-pink-500/20">
                          <Music className="h-4 w-4 text-purple-500" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium truncate leading-tight mb-1">{name}</p>
                          <div className="flex items-center gap-1.5">
                            <TypeBadge type={ext} />
                            <span className="text-[10px] text-muted-foreground">{sizeStr}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Text/Code Section */}
          {textCodeAtts.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <FileCode className="h-4 w-4" />
                <span>Text/Code</span>
                <span className="text-xs text-muted-foreground/70">({textCodeAtts.length})</span>
              </div>
              <div className="flex flex-col gap-2">
                {textCodeAtts.map((f) => {
                  const name = f.file?.name || 'file'
                  const extension = getFileExtension(name)
                  const sizeStr = formatFileSize(f.file?.size || 0)
                  const isAvailable = Boolean(f.textContent || f.assetId)
                  const isLoading = loadingFileId === f.id
                  return (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => onOpenTextFile(f)}
                      disabled={!isAvailable || isLoading}
                      className={cn(
                        "relative group rounded-lg border border-border bg-secondary/30 transition-colors p-2.5 text-left w-full",
                        isAvailable && !isLoading ? "hover:bg-secondary/50" : "opacity-60 cursor-not-allowed"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <div className="flex-shrink-0 p-1.5 rounded bg-primary/10">
                          {isLoading ? (
                            <Loader2 className="h-4 w-4 text-primary animate-spin" />
                          ) : (
                            <FileCode className="h-4 w-4 text-primary" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium truncate leading-tight mb-1">{name}</p>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] px-1.5 py-0 rounded bg-muted font-medium">{extension}</span>
                            <span className="text-[10px] text-muted-foreground">{sizeStr}</span>
                          </div>
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* PDF/Docx Section */}
          {pdfDocxAtts.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <FileType className="h-4 w-4" />
                <span>PDF/Documents</span>
                <span className="text-xs text-muted-foreground/70">({pdfDocxAtts.length})</span>
              </div>
              <div className="flex flex-col gap-2">
                {pdfDocxAtts.map((f) => {
                  const name = f.file?.name || 'file'
                  const extension = getFileExtension(name)
                  const sizeStr = formatFileSize(f.file?.size || 0)
                  const assetId = f.assetId || f.id
                  const blobUrl = assetId ? loadedBlobUrls[assetId] : null
                  const isPdf = extension.toLowerCase() === 'pdf' || (!!f.base64 && !f.textContent)
                  const isAssetLoading = assetId ? loadingAssetIds.has(assetId) : false
                  // For PDFs we can use base64 or fetch via assetId; for DOCX we fetch text content
                  const isAvailable = isPdf
                    ? Boolean(f.base64 || blobUrl || assetId)
                    : Boolean(f.textContent || f.assetId)
                  const isLoading = loadingFileId === f.id || isAssetLoading
                  return (
                    <button
                      key={f.id}
                      type="button"
                      onClick={async () => {
                        if (isPdf) {
                          // Priority: base64 > loaded blob URL > fetch from API
                          let pdfSource = f.base64 || blobUrl
                          if (!pdfSource && assetId) {
                            pdfSource = await onLoadAsset(assetId)
                          }
                          if (pdfSource) {
                            onOpenPdf(pdfSource, name)
                          } else {
                            toast.error('Failed to load PDF')
                          }
                        } else {
                          // For non-PDF documents, use the async file handler
                          onOpenTextFile(f)
                        }
                      }}
                      disabled={!isAvailable || isLoading}
                      className={cn(
                        "relative group rounded-lg border border-border bg-secondary/30 transition-colors p-2.5 text-left w-full",
                        isAvailable && !isLoading ? "hover:bg-secondary/50" : "opacity-60 cursor-not-allowed"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <div className="flex-shrink-0 p-1.5 rounded bg-primary/10">
                          {isLoading ? (
                            <Loader2 className="h-4 w-4 text-primary animate-spin" />
                          ) : (
                            <FileType className="h-4 w-4 text-primary" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium truncate leading-tight mb-1">{name}</p>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] px-1.5 py-0 rounded bg-muted font-medium">{extension}</span>
                            <span className="text-[10px] text-muted-foreground">{sizeStr}</span>
                          </div>
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
