/**
 * AttachmentPreviews Component
 *
 * Displays compact previews of attached files and images.
 * Clean, uniform card design matching the message list carousel.
 * Uses carousel when more than 4 attachments.
 */

import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { X, ChevronLeft, ChevronRight, Play, Music } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Attachment, FileAttachment, ImageAttachment, VideoAttachment, AudioAttachment } from './types'
import { getFileExtension, isPDFFile } from '@/utils/fileUtils'
import { TypeBadge } from '@/lib/type-badges'
import { formatFileSize } from '@/utils/imageUtils'
import { FilePreviewModal } from './FilePreviewModal'
import { PdfPreviewModal } from './PdfPreviewModal'
import useEmblaCarousel from 'embla-carousel-react'

interface AttachmentPreviewsProps {
  attachments: Attachment[]
  onRemove: (attachmentId: string) => void
  onImageClick?: (attachment: Attachment) => void
}

export function AttachmentPreviews({
  attachments,
  onRemove,
  onImageClick
}: AttachmentPreviewsProps) {
  const [selectedFile, setSelectedFile] = useState<FileAttachment | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  // PDF preview state
  const [isPdfOpen, setIsPdfOpen] = useState(false)
  const [pdfSrc, setPdfSrc] = useState('')
  const [pdfName, setPdfName] = useState('')

  // Carousel setup - use when > 4 attachments
  const useCarousel = attachments.length > 4
  const [emblaRef, emblaApi] = useEmblaCarousel({
    loop: false,
    align: 'start',
    slidesToScroll: 1,
    containScroll: 'trimSnaps',
    active: useCarousel,
  })

  const [canScrollPrev, setCanScrollPrev] = useState(false)
  const [canScrollNext, setCanScrollNext] = useState(false)

  const scrollPrev = useCallback(() => emblaApi?.scrollPrev(), [emblaApi])
  const scrollNext = useCallback(() => emblaApi?.scrollNext(), [emblaApi])

  const onSelect = useCallback(() => {
    if (!emblaApi) return
    setCanScrollPrev(emblaApi.canScrollPrev())
    setCanScrollNext(emblaApi.canScrollNext())
  }, [emblaApi])

  useEffect(() => {
    if (!emblaApi || !useCarousel) return
    onSelect()
    emblaApi.on('select', onSelect)
    emblaApi.on('reInit', onSelect)
    return () => {
      emblaApi.off('select', onSelect)
      emblaApi.off('reInit', onSelect)
    }
  }, [emblaApi, onSelect, useCarousel])

  const handleFileClick = (file: FileAttachment) => {
    // Check if it's a PDF
    if (isPDFFile(file.file)) {
      if (file.base64) {
        setPdfSrc(file.base64)
        setPdfName(file.file.name)
        setIsPdfOpen(true)
      }
      return
    }
    // Text/code files
    if (file.textContent) {
      setSelectedFile(file)
      setIsModalOpen(true)
    }
  }

  // Render image attachment card
  const renderImageCard = (attachment: ImageAttachment) => (
    <Tooltip key={attachment.id}>
      <TooltipTrigger asChild>
        <div
          role="button"
          tabIndex={0}
          className="group relative w-[120px] h-[75px] rounded-lg overflow-hidden bg-muted/50 ring-1 ring-border/50 hover:ring-primary/50 active:ring-primary/70 active:scale-[0.98] transition-all duration-200 shadow-sm hover:shadow-md cursor-pointer touch-manipulation flex-shrink-0"
          onClick={(e) => {
            if (!(e.target as HTMLElement).closest('[data-remove]')) {
              onImageClick?.(attachment)
            }
          }}
          onKeyDown={(e) => {
            if ((e.key === 'Enter' || e.key === ' ') && !(e.target as HTMLElement).closest('[data-remove]')) {
              e.preventDefault()
              onImageClick?.(attachment)
            }
          }}
        >
          <img
            src={attachment.preview}
            alt={attachment.file.name}
            className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-[1.02]"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
          <Button
            data-remove
            type="button"
            variant="ghost"
            size="icon"
            className="absolute top-1 right-1 h-6 w-6 transition-all bg-black/60 hover:bg-destructive active:bg-destructive text-white rounded-full opacity-80 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
            onClick={(e) => {
              e.stopPropagation()
              onRemove(attachment.id)
            }}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs">
        <p className="text-xs">{attachment.file.name}</p>
      </TooltipContent>
    </Tooltip>
  )

  // Render file attachment card
  const renderFileCard = (attachment: FileAttachment) => {
    const extension = getFileExtension(attachment.file.name)
    const isPdf = isPDFFile(attachment.file)
    const isClickable = isPdf ? !!attachment.base64 : !!attachment.textContent

    return (
      <Tooltip key={attachment.id}>
        <TooltipTrigger asChild>
          <div
            role="button"
            tabIndex={0}
            className={cn(
              "group relative w-[120px] h-[75px] rounded-lg bg-muted/30 ring-1 ring-border/50 hover:ring-primary/50 hover:bg-muted/50 active:ring-primary/70 active:scale-[0.98] transition-all duration-200 shadow-sm hover:shadow-md p-2 flex flex-col text-left touch-manipulation flex-shrink-0",
              isClickable && "cursor-pointer"
            )}
            onClick={() => isClickable && handleFileClick(attachment)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                isClickable && handleFileClick(attachment)
              }
            }}
          >
            {/* Extension badge - top left */}
            <TypeBadge type={extension} className="absolute top-1.5 left-1.5" />

            {/* File info - bottom aligned */}
            <div className="mt-auto">
              <p className="text-[10px] font-medium truncate leading-tight text-foreground/90">
                {attachment.file.name}
              </p>
              <p className="text-[9px] text-muted-foreground mt-0.5">
                {formatFileSize(attachment.file.size)}
              </p>
            </div>

            {/* Remove button - visible on touch, hover-reveal on desktop */}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute top-1 right-1 h-6 w-6 transition-all text-muted-foreground hover:bg-destructive/10 hover:text-destructive active:bg-destructive/20 active:text-destructive rounded-full opacity-70 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation()
                onRemove(attachment.id)
              }}
            >
              <X className="h-3 w-3" />
            </Button>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs">
          <p className="text-xs">{attachment.file.name}</p>
        </TooltipContent>
      </Tooltip>
    )
  }

  // Render video attachment card
  const renderVideoCard = (attachment: VideoAttachment) => (
    <Tooltip key={attachment.id}>
      <TooltipTrigger asChild>
        <div
          className="group relative w-[160px] h-[90px] rounded-lg overflow-hidden bg-muted/50 ring-1 ring-border/50 hover:ring-primary/50 transition-all duration-200 shadow-sm hover:shadow-md flex-shrink-0"
        >
          <video
            src={attachment.preview}
            preload="metadata"
            className="w-full h-full object-cover"
            muted
          />
          {/* Play icon overlay */}
          <div className="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/30 transition-colors pointer-events-none">
            <div className="h-8 w-8 rounded-full bg-black/60 flex items-center justify-center">
              <Play className="h-4 w-4 text-white ml-0.5" fill="white" />
            </div>
          </div>
          {/* Size badge */}
          <TypeBadge type={getFileExtension(attachment.file.name)} className="absolute bottom-1.5 left-1.5" />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute top-1 right-1 h-6 w-6 transition-all bg-black/60 hover:bg-destructive active:bg-destructive text-white rounded-full opacity-80 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
            onClick={(e) => {
              e.stopPropagation()
              onRemove(attachment.id)
            }}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs">
        <p className="text-xs">{attachment.file.name}</p>
        <p className="text-[10px] text-muted-foreground">{formatFileSize(attachment.file.size)}</p>
      </TooltipContent>
    </Tooltip>
  )

  // Render audio attachment card
  const renderAudioCard = (attachment: AudioAttachment) => (
    <Tooltip key={attachment.id}>
      <TooltipTrigger asChild>
        <div
          className="group relative w-[120px] h-[75px] rounded-lg overflow-hidden ring-1 ring-border/50 hover:ring-primary/50 transition-all duration-200 shadow-sm hover:shadow-md p-2 flex flex-col text-left flex-shrink-0 bg-gradient-to-br from-purple-500/20 to-pink-500/20"
        >
          {/* Music icon */}
          <div className="flex items-center gap-1.5 mb-auto">
            <Music className="h-4 w-4 text-purple-400 flex-shrink-0" />
            <TypeBadge type={getFileExtension(attachment.file.name)} />
          </div>
          {/* File info */}
          <div className="mt-auto">
            <p className="text-[10px] font-medium truncate leading-tight text-foreground/90">
              {attachment.file.name}
            </p>
            <p className="text-[9px] text-muted-foreground mt-0.5">
              {formatFileSize(attachment.file.size)}
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute top-1 right-1 h-6 w-6 transition-all text-muted-foreground hover:bg-destructive/10 hover:text-destructive active:bg-destructive/20 active:text-destructive rounded-full opacity-70 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
            onClick={(e) => {
              e.stopPropagation()
              onRemove(attachment.id)
            }}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs">
        <p className="text-xs">{attachment.file.name}</p>
        <p className="text-[10px] text-muted-foreground">{formatFileSize(attachment.file.size)}</p>
      </TooltipContent>
    </Tooltip>
  )

  if (attachments.length === 0) return null

  // Simple flex layout for <= 4 items
  if (!useCarousel) {
    return (
      <TooltipProvider>
        <div className="pb-3 flex-shrink-0">
          <div className="flex flex-wrap items-center gap-2">
            {attachments.map((attachment) =>
              attachment.type === 'image'
                ? renderImageCard(attachment as ImageAttachment)
                : attachment.type === 'video'
                ? renderVideoCard(attachment as VideoAttachment)
                : attachment.type === 'audio'
                ? renderAudioCard(attachment as AudioAttachment)
                : renderFileCard(attachment as FileAttachment)
            )}
          </div>
        </div>

        {/* File Preview Modal */}
        {selectedFile && (
          <FilePreviewModal
            isOpen={isModalOpen}
            onClose={() => setIsModalOpen(false)}
            fileName={selectedFile.file.name}
            fileSize={selectedFile.file.size}
            textContent={selectedFile.textContent || ''}
          />
        )}

        {/* PDF Preview Modal */}
        <PdfPreviewModal
          isOpen={isPdfOpen}
          onClose={() => setIsPdfOpen(false)}
          pdfSrc={pdfSrc}
          pdfName={pdfName}
        />
      </TooltipProvider>
    )
  }

  // Carousel layout for > 4 items
  return (
    <TooltipProvider>
      <div className="pb-3 flex-shrink-0">
        <div className="relative">
          {/* Carousel viewport */}
          <div className="overflow-hidden rounded-lg" ref={emblaRef}>
            <div className="flex gap-2">
              {attachments.map((attachment) =>
                attachment.type === 'image'
                  ? renderImageCard(attachment as ImageAttachment)
                  : renderFileCard(attachment as FileAttachment)
              )}
            </div>
          </div>

          {/* Fade overlays */}
          {canScrollPrev && (
            <div className="absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-background via-background/80 to-transparent pointer-events-none z-[5] rounded-l-lg" />
          )}
          {canScrollNext && (
            <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-background via-background/80 to-transparent pointer-events-none z-[5] rounded-r-lg" />
          )}

          {/* Navigation buttons - larger touch targets, always visible on mobile */}
          {canScrollPrev && (
            <Button
              variant="ghost"
              size="sm"
              onClick={scrollPrev}
              className="absolute -left-3 top-1/2 -translate-y-1/2 h-8 w-8 p-0 z-10 rounded-full bg-background hover:bg-muted active:bg-muted/80 active:scale-95 border border-border shadow-md hover:shadow-lg transition-all touch-manipulation"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
          )}
          {canScrollNext && (
            <Button
              variant="ghost"
              size="sm"
              onClick={scrollNext}
              className="absolute -right-3 top-1/2 -translate-y-1/2 h-8 w-8 p-0 z-10 rounded-full bg-background hover:bg-muted active:bg-muted/80 active:scale-95 border border-border shadow-md hover:shadow-lg transition-all touch-manipulation"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* File Preview Modal */}
      {selectedFile && (
        <FilePreviewModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          fileName={selectedFile.file.name}
          fileSize={selectedFile.file.size}
          textContent={selectedFile.textContent || ''}
        />
      )}

      {/* PDF Preview Modal */}
      <PdfPreviewModal
        isOpen={isPdfOpen}
        onClose={() => setIsPdfOpen(false)}
        pdfSrc={pdfSrc}
        pdfName={pdfName}
      />
    </TooltipProvider>
  )
}
