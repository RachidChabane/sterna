/**
 * BraveSearchMediaCarousel Component
 *
 * Displays images and videos from Brave Search results in a horizontal carousel.
 * Shows thumbnails with metadata like dimensions, source, and duration.
 * Styled to match SuggestedQuestionsCarousel with compact layout and animated borders.
 */

import { useCallback, useEffect, useState } from 'react'
import useEmblaCarousel from 'embla-carousel-react'
import { ChevronLeft, ChevronRight, ExternalLink, Play, Image as ImageIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface MediaItem {
  type: 'image' | 'video'
  thumbnail: string
  url: string
  title?: string
  source?: string
  width?: number
  height?: number
  duration?: string
  views?: string
}

interface BraveSearchMediaCarouselProps {
  items: MediaItem[]
  title?: string
}

export function BraveSearchMediaCarousel({ items, title }: BraveSearchMediaCarouselProps) {
  const [emblaRef, emblaApi] = useEmblaCarousel({
    loop: false,
    align: 'start',
    slidesToScroll: 1,
    containScroll: 'trimSnaps'
  })

  const [canScrollPrev, setCanScrollPrev] = useState(false)
  const [canScrollNext, setCanScrollNext] = useState(false)

  const scrollPrev = useCallback(() => {
    if (emblaApi) emblaApi.scrollPrev()
  }, [emblaApi])

  const scrollNext = useCallback(() => {
    if (emblaApi) emblaApi.scrollNext()
  }, [emblaApi])

  const onSelect = useCallback(() => {
    if (!emblaApi) return
    setCanScrollPrev(emblaApi.canScrollPrev())
    setCanScrollNext(emblaApi.canScrollNext())
  }, [emblaApi])

  useEffect(() => {
    if (!emblaApi) return

    onSelect()
    emblaApi.on('select', onSelect)
    emblaApi.on('reInit', onSelect)

    return () => {
      emblaApi.off('select', onSelect)
      emblaApi.off('reInit', onSelect)
    }
  }, [emblaApi, onSelect])

  if (!items || items.length === 0) return null

  return (
    <>
      <style>{`
        @keyframes gradientShift {
          0% {
            background-position: 0% 50%;
          }
          50% {
            background-position: 100% 50%;
          }
          100% {
            background-position: 0% 50%;
          }
        }

        .media-carousel-card {
          position: relative;
          transition: background-color 0.3s ease;
        }

        .media-carousel-card::before {
          content: '';
          position: absolute;
          inset: -1px;
          border-radius: inherit;
          padding: 1px;
          background: linear-gradient(135deg, transparent, transparent);
          -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
          -webkit-mask-composite: xor;
          mask-composite: exclude;
          opacity: 0;
          transition: opacity 0.3s ease;
          pointer-events: none;
        }

        .media-carousel-card:hover::before {
          opacity: 1;
          background: linear-gradient(135deg,
            hsl(var(--accent-brand) / 0.5),
            hsl(var(--accent-brand) / 0.7),
            hsl(var(--accent-brand) / 0.5)
          );
          background-size: 200% 200%;
          animation: gradientShift 3s ease infinite;
        }

        /* Light mode: better contrast */
        .light .media-carousel-card {
          background: hsl(var(--card) / 0.8);
        }
      `}</style>
      <div className="pb-2 w-full max-w-full min-w-0">
        {title && (
          <div className="flex items-center gap-2 mb-2 px-1">
            <div className="flex items-center gap-1.5">
              {items[0].type === 'image' ? (
                <ImageIcon className="h-3.5 w-3.5 text-accent-brand" />
              ) : (
                <Play className="h-3.5 w-3.5 text-accent-brand" />
              )}
              <span className="text-xs font-medium text-muted-foreground">
                {title}
              </span>
            </div>
            <span className="text-[10px] text-muted-foreground">
              ({items.length} result{items.length > 1 ? 's' : ''})
            </span>
          </div>
        )}

        <div className="relative group w-full max-w-full min-w-0">
          {/* Carousel viewport - takes full width of parent, Embla handles internal scrolling */}
          <div
            className="overflow-hidden rounded-lg w-full min-w-0"
            ref={emblaRef}
          >
            <div className="flex gap-3">
              {items.map((item, index) => (
                <a
                  key={index}
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="media-carousel-card flex-shrink-0 w-[200px] flex flex-col rounded-xl overflow-hidden
                           bg-background/50 border border-border/40
                           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand focus-visible:ring-offset-2
                           group/card"
                >
                  {/* Thumbnail */}
                  <div className="relative aspect-video bg-muted/50 flex items-center justify-center overflow-hidden">
                    <img
                      src={item.thumbnail}
                      alt={item.title || 'Media result'}
                      className="w-full h-full object-cover"
                      loading="lazy"
                      referrerPolicy="no-referrer"
                      crossOrigin="anonymous"
                      onError={(e) => {
                        // Fallback if image fails to load
                        const parent = e.currentTarget.parentElement
                        if (parent) {
                          e.currentTarget.style.display = 'none'
                          const fallback = document.createElement('div')
                          fallback.className = 'flex flex-col items-center justify-center w-full h-full bg-muted gap-1 p-2'
                          fallback.innerHTML = `
                            <span class="text-muted-foreground text-xs text-center">Image unavailable</span>
                            <span class="text-muted-foreground text-[10px] text-center opacity-70">Click to view on source</span>
                          `
                          parent.insertBefore(fallback, e.currentTarget)
                        }
                      }}
                    />

                    {/* Video duration badge */}
                    {item.type === 'video' && item.duration && (
                      <div className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded bg-black/80 text-white text-[10px] font-medium">
                        {item.duration}
                      </div>
                    )}

                    {/* Play icon for videos */}
                    {item.type === 'video' && (
                      <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover/card:opacity-100 transition-opacity">
                        <div className="w-10 h-10 rounded-full bg-accent-brand/90 flex items-center justify-center">
                          <Play className="h-5 w-5 text-white fill-white" />
                        </div>
                      </div>
                    )}

                    {/* External link icon */}
                    <div className="absolute top-2 right-2 opacity-0 group-hover/card:opacity-100 transition-opacity">
                      <div className="p-1 rounded bg-background/90 border border-border">
                        <ExternalLink className="h-2.5 w-2.5" />
                      </div>
                    </div>
                  </div>

                  {/* Metadata */}
                  <div className="p-2 flex-1 flex flex-col gap-0.5">
                    {item.title && (
                      <p className="text-[11px] font-medium line-clamp-2 leading-tight">
                        {item.title}
                      </p>
                    )}

                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground mt-auto">
                      {item.source && (
                        <span className="truncate">{item.source}</span>
                      )}
                      {item.width && item.height && (
                        <span className="flex-shrink-0">
                          {item.width}×{item.height}
                        </span>
                      )}
                      {item.views && (
                        <span className="flex-shrink-0">{item.views}</span>
                      )}
                    </div>
                  </div>
                </a>
              ))}
            </div>
          </div>

          {/* Fade overlays for scroll indication */}
          {canScrollPrev && (
            <div className="absolute left-0 top-0 bottom-0 w-20 bg-gradient-to-r from-background to-transparent pointer-events-none z-[5]" />
          )}
          {canScrollNext && (
            <div className="absolute right-0 top-0 bottom-0 w-20 bg-gradient-to-l from-background to-transparent pointer-events-none z-[5]" />
          )}

          {/* Navigation buttons - Overlaid with orange hover */}
          {canScrollPrev && (
            <Button
              variant="ghost"
              size="sm"
              onClick={scrollPrev}
              className="absolute left-2 top-1/2 -translate-y-1/2 h-8 w-8 p-0 z-10 rounded-full
                       bg-background/80 hover:bg-accent-brand/10 hover:shadow-[0_0_15px_hsl(var(--accent-brand)/0.3)]
                       border border-border/40 hover:border-accent-brand/50
                       transition-colors duration-300"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
          )}
          {canScrollNext && (
            <Button
              variant="ghost"
              size="sm"
              onClick={scrollNext}
              className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 p-0 z-10 rounded-full
                       bg-background/80 hover:bg-accent-brand/10 hover:shadow-[0_0_15px_hsl(var(--accent-brand)/0.3)]
                       border border-border/40 hover:border-accent-brand/50
                       transition-colors duration-300"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </>
  )
}
