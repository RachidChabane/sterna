/**
 * Suggested Questions Carousel Component
 *
 * Horizontal infinite scrolling carousel of suggested prompts for model comparison.
 * Appears above the shared input in sync mode when all chats are empty.
 * Redesigned with compact layout and animated borders matching the input style.
 */

import { useCallback } from 'react'
import useEmblaCarousel from 'embla-carousel-react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SUGGESTED_QUESTIONS } from './constants/suggestedQuestions'

interface SuggestedQuestionsCarouselProps {
  onSuggestionClick: (prompt: string) => void
}

export function SuggestedQuestionsCarousel({ onSuggestionClick }: SuggestedQuestionsCarouselProps) {
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: true, align: 'start', slidesToScroll: 1 })

  const scrollPrev = useCallback(() => {
    if (emblaApi) emblaApi.scrollPrev()
  }, [emblaApi])

  const scrollNext = useCallback(() => {
    if (emblaApi) emblaApi.scrollNext()
  }, [emblaApi])

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

        .carousel-suggestion-card {
          position: relative;
          transition: background-color 0.3s ease;
        }

        .carousel-suggestion-card::before {
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

        .carousel-suggestion-card:hover::before {
          opacity: 1;
          background: linear-gradient(135deg,
            rgba(59, 130, 246, 0.5),
            rgba(61, 92, 228, 0.5),
            rgba(59, 130, 246, 0.5)
          );
          background-size: 200% 200%;
          animation: gradientShift 3s ease infinite;
        }

        /* Light mode: better contrast */
        .light .carousel-suggestion-card {
          background: hsl(var(--card) / 0.8);
        }
      `}</style>
      <div className="pb-2 flex-shrink-0">
        <div className="relative">
          {/* Carousel */}
          <div className="overflow-hidden" ref={emblaRef}>
            <div className="flex">
              {SUGGESTED_QUESTIONS.map((question, index) => {
                const Icon = question.icon
                return (
                  <button
                    key={index}
                    onClick={() => onSuggestionClick(question.prompt)}
                    className="carousel-suggestion-card group relative flex-shrink-0 w-[240px] flex items-center gap-2.5 p-2.5 mr-3 rounded-xl
                             bg-background/50 border border-border/40
                             text-left
                             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand focus-visible:ring-offset-2"
                  >
                    {/* Icon - More compact */}
                    <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg
                                  bg-accent-brand/10 group-hover:bg-accent-brand/20
                                  transition-all duration-300">
                      <Icon className="h-4 w-4 text-accent-brand" />
                    </div>

                    {/* Content - Side by side with icon */}
                    <div className="flex-1 min-w-0">
                      <h4 className="font-semibold text-xs mb-0.5 group-hover:text-accent-brand transition-colors duration-300 truncate">
                        {question.title}
                      </h4>
                      <p className="text-[10px] text-muted-foreground line-clamp-1">
                        {question.description}
                      </p>
                    </div>

                    {/* Hover indicator - Smaller */}
                    <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                      <div className="w-1.5 h-1.5 rounded-full bg-accent-brand" />
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Fade overlays - Slightly smaller */}
          <div className="absolute left-0 top-0 bottom-0 w-20 bg-gradient-to-r from-background to-transparent pointer-events-none z-[5]" />
          <div className="absolute right-0 top-0 bottom-0 w-20 bg-gradient-to-l from-background to-transparent pointer-events-none z-[5]" />

          {/* Navigation buttons - Overlaid with teal hover */}
          <Button
            variant="ghost"
            size="sm"
            onClick={scrollPrev}
            className="absolute left-2 top-1/2 -translate-y-1/2 h-8 w-8 p-0 z-10 rounded-full
                     bg-background/80 hover:bg-accent-brand/10 hover:shadow-[0_0_15px_rgba(61,92,228,0.3)]
                     border border-border/40 hover:border-accent-brand/50
                     transition-colors duration-300"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={scrollNext}
            className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 p-0 z-10 rounded-full
                     bg-background/80 hover:bg-accent-brand/10 hover:shadow-[0_0_15px_rgba(61,92,228,0.3)]
                     border border-border/40 hover:border-accent-brand/50
                     transition-colors duration-300"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </>
  )
}
