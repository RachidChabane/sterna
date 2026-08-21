/**
 * WebResultsDisplay Component
 *
 * Displays web search results from Brave Search in a compact vertical list.
 */

import { ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'

interface WebResult {
  title: string
  url: string
  description?: string
  thumbnail?: {
    src: string
  }
}

interface WebResultsDisplayProps {
  results: WebResult[]
}

export function WebResultsDisplay({ results }: WebResultsDisplayProps) {
  if (!results || results.length === 0) return null

  return (
    <div className="space-y-1">
      {results.map((result, index) => {
        // Extract domain from URL
        let domain = ''
        try {
          domain = new URL(result.url).hostname.replace('www.', '')
        } catch {
          domain = result.url
        }

        return (
          <a
            key={index}
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              "group flex items-start gap-3 p-2.5 rounded-lg",
              "hover:bg-muted/50 active:bg-muted/70 transition-colors"
            )}
          >
            {/* Favicon */}
            <div className="flex-shrink-0 h-8 w-8 rounded-md bg-muted/50 border border-border/40 flex items-center justify-center overflow-hidden mt-0.5">
              <img
                src={`https://www.google.com/s2/favicons?domain=${domain}&sz=32`}
                alt=""
                className="w-5 h-5"
                onError={(e) => {
                  const img = e.target as HTMLImageElement
                  if (!img.src.includes('duckduckgo')) {
                    img.src = `https://icons.duckduckgo.com/ip3/${domain}.ico`
                  }
                }}
              />
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              {/* Title */}
              <h4
                className="text-sm font-medium text-foreground line-clamp-2 leading-snug group-hover:text-accent-brand transition-colors [&_strong]:font-bold"
                dangerouslySetInnerHTML={{ __html: result.title }}
              />

              {/* Domain */}
              <div className="text-xs text-muted-foreground/60 truncate mt-1">
                {domain}
              </div>

              {/* Description */}
              {result.description && (
                <p
                  className="text-xs text-muted-foreground/50 line-clamp-2 leading-snug mt-1 [&_strong]:font-medium [&_strong]:text-muted-foreground/70"
                  dangerouslySetInnerHTML={{ __html: result.description }}
                />
              )}
            </div>

            {/* External link */}
            <div className="flex-shrink-0 self-center opacity-0 group-hover:opacity-100 transition-opacity">
              <ExternalLink className="h-3.5 w-3.5 text-muted-foreground/50" />
            </div>
          </a>
        )
      })}
    </div>
  )
}
