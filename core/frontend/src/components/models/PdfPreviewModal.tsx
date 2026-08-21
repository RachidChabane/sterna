/**
 * PdfPreviewModal Component
 *
 * Premium PDF preview with:
 * - Rendered page thumbnail via pdf.js
 * - Subtle fan spread effect on hover
 * - Page count that transforms to download button on hover
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { X, Download, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type * as PdfjsLib from 'pdfjs-dist'

// pdfjs-dist (~400KB) is only needed once a PDF preview is actually
// rendered, so it's loaded on demand instead of shipping with every chat
// message that might contain an attachment. The module is cached after the
// first load so repeated previews don't re-fetch it.
let pdfjsLibPromise: Promise<typeof PdfjsLib> | null = null
function loadPdfjsLib() {
  if (!pdfjsLibPromise) {
    pdfjsLibPromise = import('pdfjs-dist').then((pdfjsLib) => {
      const version = pdfjsLib.version
      pdfjsLib.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${version}/build/pdf.worker.min.mjs`
      return pdfjsLib
    })
  }
  return pdfjsLibPromise
}

interface PdfPreviewModalProps {
  isOpen: boolean
  onClose: () => void
  pdfSrc: string
  pdfName: string
}

export function PdfPreviewModal({
  isOpen,
  onClose,
  pdfSrc,
  pdfName,
}: PdfPreviewModalProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [pageCount, setPageCount] = useState<number>(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isHovered, setIsHovered] = useState(false)

  // Render PDF first page to canvas
  useEffect(() => {
    if (!isOpen || !pdfSrc) return

    let cancelled = false
    setIsLoading(true)
    setError(null)
    setPageCount(0)

    const loadPdf = async () => {
      try {
        const pdfjsLib = await loadPdfjsLib()
        if (cancelled) return

        // Handle different source types
        let loadingTask

        const standardFontDataUrl = `https://unpkg.com/pdfjs-dist@${pdfjsLib.version}/standard_fonts/`

        if (pdfSrc.startsWith('data:')) {
          // Data URL - extract base64 and convert to Uint8Array
          const base64 = pdfSrc.split(',')[1]
          const binaryString = atob(base64)
          const bytes = new Uint8Array(binaryString.length)
          for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i)
          }
          loadingTask = pdfjsLib.getDocument({
            data: bytes,
            standardFontDataUrl,
          })
        } else {
          // Blob URL or regular URL
          loadingTask = pdfjsLib.getDocument({
            url: pdfSrc,
            disableRange: pdfSrc.startsWith('blob:'),
            disableStream: pdfSrc.startsWith('blob:'),
            standardFontDataUrl,
          })
        }

        const pdf = await loadingTask.promise

        if (cancelled) return

        setPageCount(pdf.numPages)

        // Get first page
        const page = await pdf.getPage(1)

        if (cancelled) return

        const canvas = canvasRef.current
        if (!canvas) return

        const ctx = canvas.getContext('2d')
        if (!ctx) return

        // Calculate scale to fit nicely (max ~320px width)
        const viewport = page.getViewport({ scale: 1 })
        const maxWidth = 320
        const scale = maxWidth / viewport.width
        const scaledViewport = page.getViewport({ scale })

        canvas.width = scaledViewport.width
        canvas.height = scaledViewport.height

        // Render page (pdfjs-dist v5+ takes the canvas directly; the 2d context
        // is derived from it internally)
        await page.render({
          canvas,
          viewport: scaledViewport,
        }).promise

        if (!cancelled) {
          setIsLoading(false)
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[PdfPreviewModal] Failed to render PDF:', err)
          setError('Failed to load PDF preview')
          setIsLoading(false)
        }
      }
    }

    loadPdf()

    return () => {
      cancelled = true
    }
  }, [isOpen, pdfSrc])

  // Download handler
  const handleDownload = useCallback(() => {
    const link = document.createElement('a')
    link.href = pdfSrc
    link.download = pdfName || 'document.pdf'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [pdfSrc, pdfName])

  // Close on escape key
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const modalContent = (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm animate-in fade-in-0 duration-200"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div
          className="relative bg-background rounded-2xl overflow-hidden shadow-2xl border border-border pointer-events-auto animate-in zoom-in-95 fade-in-0 duration-200 max-w-md w-full"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <h2 className="text-base font-semibold text-foreground truncate pr-4">
              {pdfName || 'PDF Preview'}
            </h2>
            <button
              onClick={onClose}
              className="flex-shrink-0 p-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted active:bg-muted active:text-foreground active:scale-95 transition-colors touch-manipulation"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content - hover area includes both preview and button */}
          <div
            className="p-6 flex flex-col items-center"
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
          >
            {/* PDF Preview with fan effect - clickable for download on desktop only */}
            <div
              role="button"
              tabIndex={0}
              onClick={handleDownload}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleDownload() }}
              className="relative focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-lg pointer-events-none [@media(hover:hover)]:pointer-events-auto [@media(hover:hover)]:cursor-pointer"
              aria-label="Click to download PDF"
            >
              {/* Background pages for fan effect */}
              <div
                className={cn(
                  "absolute inset-0 bg-muted rounded-lg transition-all duration-300 ease-out origin-bottom",
                  isHovered ? "opacity-70" : "opacity-0"
                )}
                style={{
                  transform: isHovered ? 'rotate(-3deg) translateX(-4px)' : 'rotate(0deg)',
                }}
              />
              <div
                className={cn(
                  "absolute inset-0 bg-muted rounded-lg transition-all duration-300 ease-out origin-bottom",
                  isHovered ? "opacity-50" : "opacity-0"
                )}
                style={{
                  transform: isHovered ? 'rotate(-6deg) translateX(-8px)' : 'rotate(0deg)',
                  transitionDelay: '30ms',
                }}
              />

              {/* Main page */}
              <div
                className={cn(
                  "relative rounded-lg overflow-hidden transition-all duration-300 ease-out ring-1 ring-border",
                  "shadow-lg",
                  isHovered && "shadow-xl"
                )}
                style={{
                  transform: isHovered ? 'rotate(2deg) translateX(2px)' : 'rotate(0deg)',
                }}
              >
                {/* Loading state */}
                {isLoading && (
                  <div className="w-[320px] h-[420px] bg-muted flex items-center justify-center">
                    <Loader2 className="h-8 w-8 text-muted-foreground animate-spin" />
                  </div>
                )}

                {/* Error state */}
                {error && !isLoading && (
                  <div className="w-[320px] h-[420px] bg-muted flex items-center justify-center">
                    <p className="text-muted-foreground text-sm">{error}</p>
                  </div>
                )}

                {/* Canvas for PDF rendering */}
                <canvas
                  ref={canvasRef}
                  className={cn(
                    "block bg-white",
                    (isLoading || error) && "hidden"
                  )}
                />
              </div>
            </div>

            {/* Page count / Download button */}
            <div className="mt-6 relative h-10 w-36 flex items-center justify-center">
              {/* Page count text - hidden on touch devices, visible on hover-capable when not hovered */}
              <span
                className={cn(
                  "text-sm text-muted-foreground transition-all duration-300 absolute",
                  "hidden [@media(hover:hover)]:block",
                  isHovered ? "opacity-0 scale-95" : "opacity-100 scale-100"
                )}
              >
                {pageCount > 0 ? `${pageCount} page${pageCount !== 1 ? 's' : ''}` : '—'}
              </span>

              {/* Download button - always visible on touch, hover-reveal on desktop */}
              <button
                onClick={handleDownload}
                className={cn(
                  "flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg w-full",
                  "bg-primary hover:bg-primary/90 active:bg-primary/80 active:scale-95 text-primary-foreground text-sm font-medium",
                  "transition-all duration-300 absolute touch-manipulation",
                  // Always visible on touch devices, hover-controlled on desktop
                  "opacity-100 scale-100",
                  "[@media(hover:hover)]:opacity-0 [@media(hover:hover)]:scale-95 [@media(hover:hover)]:pointer-events-none",
                  isHovered && "[@media(hover:hover)]:opacity-100 [@media(hover:hover)]:scale-100 [@media(hover:hover)]:pointer-events-auto"
                )}
              >
                <Download className="h-4 w-4 flex-shrink-0" />
                <span>Download</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )

  // Portal to document.body to escape stacking contexts
  return createPortal(modalContent, document.body)
}
