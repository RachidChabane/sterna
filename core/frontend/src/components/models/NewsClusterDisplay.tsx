/**
 * NewsClusterDisplay Component
 *
 * Displays news results from Brave Search in a compact grid.
 */

import { Newspaper, ExternalLink } from 'lucide-react'

interface NewsArticle {
  title: string
  url: string
  description?: string
  thumbnail?: {
    src: string
  }
  age?: string
  source?: {
    name: string
    favicon?: string
  }
  published_date?: string
}

interface NewsClusterDisplayProps {
  news: NewsArticle[]
  title?: string
}

export function NewsClusterDisplay({ news, title = 'News' }: NewsClusterDisplayProps) {
  if (!news || news.length === 0) return null

  return (
    <div className="w-full space-y-2">
        {news.map((article, index) => (
          <a
            key={index}
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block border border-border/40 rounded-lg overflow-hidden bg-background/50 hover:bg-muted/50 transition-colors group/article"
          >
            <div className="flex gap-3 p-3">
              {/* Thumbnail */}
              {article.thumbnail && (
                <img
                  src={article.thumbnail.src}
                  alt={article.title}
                  className="w-20 h-20 object-cover rounded flex-shrink-0"
                  loading="lazy"
                  referrerPolicy="no-referrer"
                />
              )}

              {/* Content */}
              <div className="flex-1 min-w-0 flex flex-col">
                {/* Title */}
                <h4
                  className="text-sm font-medium line-clamp-2 group-hover/article:text-accent-brand transition-colors mb-1 [&_strong]:font-bold [&_a]:text-accent-brand [&_a]:hover:underline"
                  dangerouslySetInnerHTML={{ __html: article.title }}
                />

                {/* Description */}
                {article.description && (
                  <p
                    className="text-xs text-muted-foreground line-clamp-2 mb-auto [&_strong]:font-semibold [&_a]:text-accent-brand [&_a]:hover:underline"
                    dangerouslySetInnerHTML={{ __html: article.description }}
                  />
                )}

                {/* Metadata */}
                <div className="flex items-center gap-2 mt-2 text-[10px] text-muted-foreground">
                  {article.source && (
                    <div className="flex items-center gap-1">
                      {article.source.favicon && (
                        <img
                          src={article.source.favicon}
                          alt=""
                          className="w-3 h-3 rounded-sm"
                        />
                      )}
                      <span className="font-medium">{article.source.name}</span>
                    </div>
                  )}
                  {article.age && <span>• {article.age}</span>}
                </div>
              </div>

              {/* External link icon */}
              <ExternalLink className="h-3 w-3 text-muted-foreground flex-shrink-0 self-start group-hover/article:text-accent-brand transition-colors" />
            </div>
          </a>
        ))}
    </div>
  )
}
