/**
 * DiscussionsDisplay Component
 *
 * Displays discussion results from Brave Search (Reddit, forums, etc).
 */

import { MessageSquare, ExternalLink } from 'lucide-react'

interface Discussion {
  title: string
  url: string
  description?: string
  forum?: {
    name: string
    url: string
  }
  num_comments?: number
  score?: number
  published_date?: string
}

interface DiscussionsDisplayProps {
  discussions: Discussion[]
}

export function DiscussionsDisplay({ discussions }: DiscussionsDisplayProps) {
  if (!discussions || discussions.length === 0) return null

  return (
    <div className="w-full space-y-2">
        {discussions.map((discussion, index) => (
          <a
            key={index}
            href={discussion.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full border border-border/40 rounded-lg p-3 bg-background/50 hover:bg-muted/50 transition-colors group/discussion"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0 space-y-1">
                {/* Title */}
                <h4
                  className="text-sm font-medium line-clamp-2 group-hover/discussion:text-accent-brand transition-colors [&_strong]:font-bold [&_a]:text-accent-brand [&_a]:hover:underline"
                  dangerouslySetInnerHTML={{ __html: discussion.title }}
                />

                {/* Description */}
                {discussion.description && (
                  <p
                    className="text-xs text-muted-foreground line-clamp-2 [&_strong]:font-semibold [&_a]:text-accent-brand [&_a]:hover:underline"
                    dangerouslySetInnerHTML={{ __html: discussion.description }}
                  />
                )}

                {/* Metadata */}
                <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                  {discussion.forum && (
                    <span className="font-medium">{discussion.forum.name}</span>
                  )}
                  {discussion.num_comments !== undefined && (
                    <span>💬 {discussion.num_comments} comments</span>
                  )}
                  {discussion.score !== undefined && (
                    <span>⬆️ {discussion.score} upvotes</span>
                  )}
                  {discussion.published_date && (
                    <span>{new Date(discussion.published_date).toLocaleDateString()}</span>
                  )}
                </div>
              </div>

              {/* External link icon */}
              <ExternalLink className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0 group-hover/discussion:text-accent-brand transition-colors" />
            </div>
          </a>
        ))}
    </div>
  )
}
