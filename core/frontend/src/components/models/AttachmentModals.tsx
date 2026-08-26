/**
 * AttachmentModals Component
 *
 * Manages all attachment-related modals/dialogs:
 * - Image gallery with navigation
 * - PDF viewer
 * - All attachments modal (grouped by type)
 * - Text/code file preview
 */

import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  ImagePlus,
  FileType,
  FileCode,
  Loader2,
  Video,
  Music,
  Play,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { FilePreviewModal } from './FilePreviewModal'
import { PdfPreviewModal } from './PdfPreviewModal'
import { ImagePreviewModal } from './ImagePreviewModal'
import { getFileExtension } from '@/utils/fileUtils'
import { TypeBadge } from '@/lib/type-badges'
import { formatFileSize } from '@/utils/imageUtils'
import type { Attachment, ImageAttachment, FileAttachment, VideoAttachment, AudioAttachment } from './types'
import type { CachedAttachment } from '@/utils/attachmentCache'
import { assetsAPI } from '@/api/assets'
import { toast } from 'sonner'

interface AttachmentModalsProps {
  // Image Gallery
  isGalleryOpen: boolean
  setIsGalleryOpen: (open: boolean) => void
  galleryImages: { src: string; alt: string }[]
  selectedImageIndex: number | null
  setSelectedImageIndex: (index: number | null) => void
  selectedAllImage: { src: string; alt: string } | null
  setSelectedAllImage: (image: { src: string; alt: string } | null) => void
  galleryOpenedFromAttachments: boolean
  setGalleryOpenedFromAttachments: (opened: boolean) => void

  // PDF Viewer
  isPdfOpen: boolean
  setIsPdfOpen: (open: boolean) => void
  pdfSrc: string
  pdfName: string

  // All Attachments Modal
  isAllAttachmentsOpen: boolean
  setIsAllAttachmentsOpen: (open: boolean) => void
  allAttachments: Attachment[]

  // Text File Preview
  isTextFileOpen: boolean
  setIsTextFileOpen: (open: boolean) => void
  selectedFile: FileAttachment | null
  fetchedFileContent?: string | null  // Pre-fetched content from parent

  // Cache for hydrating attachments
  cachedAttachments: Record<string, CachedAttachment>

  // Callbacks for opening modals from within
  onOpenPdf: (src: string, name: string) => void
  onOpenTextFile: (file: FileAttachment) => void
  onOpenImageGallery: (images: { src: string; alt: string }[], selectedIndex: number) => void
}

export function AttachmentModals({
  isGalleryOpen,
  setIsGalleryOpen,
  galleryImages,
  selectedImageIndex,
  setSelectedImageIndex,
  selectedAllImage,
  setSelectedAllImage,
  galleryOpenedFromAttachments,
  setGalleryOpenedFromAttachments,
  isPdfOpen,
  setIsPdfOpen,
  pdfSrc,
  pdfName,
  isAllAttachmentsOpen,
  setIsAllAttachmentsOpen,
  allAttachments,
  isTextFileOpen,
  setIsTextFileOpen,
  selectedFile,
  fetchedFileContent,
  cachedAttachments,
  onOpenPdf,
  onOpenTextFile,
  onOpenImageGallery,
}: AttachmentModalsProps) {
  // State for loading file content from asset storage
  const [loadingFileId, setLoadingFileId] = useState<string | null>(null)
  // Cache fetched content to avoid re-fetching
  const [fetchedContent, setFetchedContent] = useState<Record<string, string>>({})
  // Cache blob URLs for images/PDFs loaded from asset storage (authentication requires API fetch)
  const [loadedBlobUrls, setLoadedBlobUrls] = useState<Record<string, string>>({})
  const [loadingAssetIds, setLoadingAssetIds] = useState<Set<string>>(new Set())

  // Load image/PDF from asset storage via API (includes auth headers)
  // Returns the blob URL so it can be used immediately
  const loadAssetAsBlobUrl = useCallback(async (assetId: string): Promise<string | null> => {
    // Return existing URL if already loaded
    if (loadedBlobUrls[assetId]) return loadedBlobUrls[assetId]
    // Don't start duplicate loads
    if (loadingAssetIds.has(assetId)) return null

    setLoadingAssetIds(prev => new Set(prev).add(assetId))
    try {
      const blob = await assetsAPI.download(assetId)
      if (blob) {
        const blobUrl = URL.createObjectURL(blob)
        setLoadedBlobUrls(prev => ({ ...prev, [assetId]: blobUrl }))
        return blobUrl
      }
      return null
    } catch (error) {
      console.error('[AttachmentModals] Failed to load asset:', assetId, error)
      return null
    } finally {
      setLoadingAssetIds(prev => {
        const next = new Set(prev)
        next.delete(assetId)
        return next
      })
    }
  }, [loadedBlobUrls, loadingAssetIds])

  // Cleanup blob URLs on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      Object.values(loadedBlobUrls).forEach(url => {
        URL.revokeObjectURL(url)
      })
    }
  }, []) // Only on unmount

  // Helper to handle file click - fetches content from API if needed
  const handleFileClick = async (f: FileAttachment, cached?: CachedAttachment) => {
    const existingContent = f.textContent || cached?.textContent || fetchedContent[f.id]

    if (existingContent) {
      // Content available, open preview directly
      onOpenTextFile({
        id: f.id,
        type: 'file',
        file: f.file || new File([], 'file'),
        base64: undefined,
        textContent: existingContent
      })
      return
    }

    // Need to fetch from asset storage
    if (f.assetId) {
      setLoadingFileId(f.id)
      try {
        const blob = await assetsAPI.download(f.assetId)
        if (blob) {
          const text = await blob.text()
          // Cache the fetched content
          setFetchedContent(prev => ({ ...prev, [f.id]: text }))
          // Open preview with fetched content
          onOpenTextFile({
            id: f.id,
            type: 'file',
            file: f.file || new File([], 'file'),
            base64: undefined,
            textContent: text
          })
        } else {
          toast.error('Failed to load file content')
        }
      } catch (error) {
        console.error('Failed to fetch file content:', error)
        toast.error('Failed to load file content')
      } finally {
        setLoadingFileId(null)
      }
      return
    }

    toast.error('File content not available')
  }

  return (
    <>
      {/* Premium Image Gallery Modal */}
      <ImagePreviewModal
        isOpen={isGalleryOpen}
        onClose={() => {
          setIsGalleryOpen(false)
          setSelectedImageIndex(null)
          // Reopen all attachments modal if it was opened from there
          if (galleryOpenedFromAttachments) {
            setIsAllAttachmentsOpen(true)
            setGalleryOpenedFromAttachments(false)
          }
        }}
        images={galleryImages}
        selectedIndex={selectedImageIndex ?? 0}
        onIndexChange={(index) => setSelectedImageIndex(index)}
      />

      {/* Premium PDF Preview Modal */}
      <PdfPreviewModal
        isOpen={isPdfOpen}
        onClose={() => setIsPdfOpen(false)}
        pdfSrc={pdfSrc}
        pdfName={pdfName}
      />

      {/* All Attachments Modal */}
      <Dialog open={isAllAttachmentsOpen} onOpenChange={setIsAllAttachmentsOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Attachments</DialogTitle>
            <DialogDescription>
              {allAttachments.length} item{allAttachments.length !== 1 ? 's' : ''}
            </DialogDescription>
          </DialogHeader>

          {/* Group attachments into sections */}
          {(() => {
            const imageAtts = allAttachments.filter(a => a.type === 'image') as ImageAttachment[]
            const videoAtts = allAttachments.filter(a => a.type === 'video') as VideoAttachment[]
            const audioAtts = allAttachments.filter(a => a.type === 'audio') as AudioAttachment[]
            const fileAtts = allAttachments.filter(a => a.type === 'file') as FileAttachment[]
            const textCodeAtts = fileAtts.filter(f => {
              const cached = cachedAttachments[f.id]
              return !!(f.textContent || cached?.textContent)
            })
            const pdfDocxAtts = fileAtts.filter(f => {
              const cached = cachedAttachments[f.id]
              const name = f.file?.name || cached?.name || ''
              const ext = getFileExtension(name).toLowerCase()
              return ['pdf', 'doc', 'docx'].includes(ext) || (!!(f.base64 || cached?.base64) && !(f.textContent || cached?.textContent))
            })

            return (
              <div className="space-y-6">
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
                        const cached = cachedAttachments[img.id]
                        // Priority: base64 (local) > loaded blob URL (from API) > cached
                        // Note: Direct download URLs don't work because browser doesn't send auth headers
                        const assetId = img.assetId || img.id  // id is set to asset_id during reconstruction
                        const blobUrl = assetId ? loadedBlobUrls[assetId] : null
                        const src = img.base64 || blobUrl || cached?.base64
                        const alt = img.file?.name || cached?.name || 'image'
                        const isLoading = assetId ? loadingAssetIds.has(assetId) : false
                        const needsLoad = !src && assetId && !isLoading

                        // Trigger loading if needed
                        if (needsLoad) {
                          loadAssetAsBlobUrl(assetId)
                        }

                        return (
                          <button
                            key={img.id}
                            type="button"
                            className="w-full h-48 rounded-md overflow-hidden cursor-zoom-in hover:opacity-90 transition-opacity"
                            onClick={() => {
                              if (!src) return
                              // Hydrate images with priority: base64 > loaded blob URL > cached
                              const hydrated = imageAtts.map((img) => {
                                const c = cachedAttachments[img.id]
                                const imgAssetId = img.assetId || img.id
                                const imgBlobUrl = imgAssetId ? loadedBlobUrls[imgAssetId] : null
                                const imgSrc = img.base64 || imgBlobUrl || c?.base64 || ''
                                const imgAlt = img.file?.name || c?.name || 'image'
                                return { src: imgSrc, alt: imgAlt }
                              }).filter(it => it.src)
                              onOpenImageGallery(hydrated, i)
                              setIsAllAttachmentsOpen(false)
                              setGalleryOpenedFromAttachments(true)
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
                          loadAssetAsBlobUrl(assetId)
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
                        const cached = cachedAttachments[f.id]
                        const name = f.file?.name || cached?.name || 'file'
                        const extension = getFileExtension(name)
                        const sizeStr = formatFileSize((f.file?.size ?? cached?.size) || 0)
                        // Content is available if we have it locally, in cache, fetched, or can fetch via assetId
                        const isAvailable = Boolean(f.textContent || cached?.textContent || fetchedContent[f.id] || f.assetId)
                        const isLoading = loadingFileId === f.id
                        return (
                          <button
                            key={f.id}
                            type="button"
                            onClick={() => handleFileClick(f, cached)}
                            disabled={!isAvailable || isLoading}
                            className={cn(
                              "relative group rounded-lg border border-border bg-secondary/30 transition-colors p-2.5 text-left w-full",
                              isAvailable && !isLoading ? "hover:bg-secondary/50" : "opacity-60 cursor-not-allowed"
                            )}
                            style={{ maxWidth: '100%' }}
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
                                  <TypeBadge type={extension} />
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
                      <span>PDF/Docx</span>
                      <span className="text-xs text-muted-foreground/70">({pdfDocxAtts.length})</span>
                    </div>
                    <div className="flex flex-col gap-2">
                      {pdfDocxAtts.map((f) => {
                        const cached = cachedAttachments[f.id]
                        const name = f.file?.name || cached?.name || 'file'
                        const extension = getFileExtension(name)
                        const sizeStr = formatFileSize((f.file?.size ?? cached?.size) || 0)
                        // Use loaded blob URL from API (direct URLs don't work due to auth)
                        const assetId = f.assetId || f.id
                        const blobUrl = assetId ? loadedBlobUrls[assetId] : null
                        const isPdf = extension.toLowerCase() === 'pdf' || (!!(f.base64 || cached?.base64) && !(f.textContent || cached?.textContent))
                        const isAssetLoading = assetId ? loadingAssetIds.has(assetId) : false
                        // For PDFs we need base64 or blob URL, for DOCX we can fetch text content from asset storage
                        const isAvailable = isPdf
                          ? Boolean(f.base64 || cached?.base64 || blobUrl || assetId)  // assetId means we can load it
                          : Boolean(f.textContent || cached?.textContent || fetchedContent[f.id] || assetId)
                        const isLoading = loadingFileId === f.id || isAssetLoading
                        return (
                          <button
                            key={f.id}
                            type="button"
                            onClick={async () => {
                              if (isPdf) {
                                // Priority: base64 > cached base64 > loaded blob URL > fetch from API
                                let pdfSource = f.base64 || cached?.base64 || blobUrl
                                if (!pdfSource && assetId) {
                                  // Need to fetch from API first - use returned URL directly
                                  pdfSource = await loadAssetAsBlobUrl(assetId)
                                }
                                if (pdfSource) {
                                  onOpenPdf(pdfSource, name)
                                } else {
                                  toast.error('Failed to load PDF')
                                }
                              } else {
                                // For non-PDF documents, use the async file click handler
                                handleFileClick(f, cached)
                              }
                            }}
                            disabled={!isAvailable || isLoading}
                            className={cn(
                              "relative group rounded-lg border border-border bg-secondary/30 transition-colors p-2.5 text-left w-full",
                              isAvailable && !isLoading ? "hover:bg-secondary/50" : "opacity-60 cursor-not-allowed"
                            )}
                            style={{ maxWidth: '100%' }}
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
                                  <TypeBadge type={extension} />
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
            )
          })()}

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAllAttachmentsOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Text/Code File Preview Modal (re-use existing component) */}
      {selectedFile && (
        <FilePreviewModal
          isOpen={isTextFileOpen}
          onClose={() => setIsTextFileOpen(false)}
          fileName={selectedFile.file?.name || cachedAttachments[selectedFile.id]?.name || 'file'}
          fileSize={selectedFile.file?.size || cachedAttachments[selectedFile.id]?.size || 0}
          textContent={selectedFile.textContent || fetchedFileContent || fetchedContent[selectedFile.id] || ''}
        />
      )}
    </>
  )
}
