/**
 * InfoboxDisplay Component
 *
 * Displays Brave Search infobox - rich information panel with structured data.
 */

import { ExternalLink, Star } from 'lucide-react'

interface InfoboxProps {
  infobox: {
    title?: string
    description?: string
    long_desc?: string
    images?: Array<{
      url: string
      title?: string
    }>
    data?: Array<{
      label: string
      value: string
    }>
    url?: string
    ratings?: Array<{
      ratingValue?: number
      bestRating?: number
      reviewCount?: number
      profile?: string
      is_tripadvisor?: boolean
    }>
    profiles?: Array<{
      name: string
      url: string
      long_name?: string
    }>
  }
}

export function InfoboxDisplay({ infobox }: InfoboxProps) {
  if (!infobox) return null

  return (
    <div className="w-full border border-border/40 rounded-lg p-4 bg-background/50 space-y-3">
      {/* Header */}
      <div className="flex items-start gap-3">
        {infobox.images && infobox.images.length > 0 && (
          <img
            src={infobox.images[0].url}
            alt={infobox.title || 'Info'}
            className="w-24 h-24 object-cover rounded-lg flex-shrink-0"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
        )}
        <div className="flex-1 min-w-0">
          {infobox.title && (
            <h3 className="font-semibold text-base mb-1">{infobox.title}</h3>
          )}
          {infobox.description && (
            <p className="text-sm text-muted-foreground">{infobox.description}</p>
          )}
        </div>
      </div>

      {/* Long description */}
      {infobox.long_desc && (
        <p className="text-sm text-foreground/90 leading-relaxed">
          {infobox.long_desc}
        </p>
      )}

      {/* Ratings */}
      {infobox.ratings && infobox.ratings.length > 0 && (
        <div className="flex flex-wrap gap-3 border-t border-border/40 pt-3">
          {infobox.ratings.map((rating, index) => (
            <div key={index} className="flex items-center gap-1.5 text-sm">
              <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />
              <span className="font-medium">{rating.ratingValue}</span>
              {rating.bestRating && <span className="text-muted-foreground">/ {rating.bestRating}</span>}
              {rating.reviewCount && (
                <span className="text-muted-foreground text-xs">({rating.reviewCount} reviews)</span>
              )}
              {rating.profile && (
                <span className="text-xs text-muted-foreground">• {rating.profile}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Data table */}
      {infobox.data && infobox.data.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 border-t border-border/40 pt-3">
          {infobox.data.map((item, index) => (
            <div key={index} className="flex flex-col gap-0.5">
              <span className="text-xs font-medium text-muted-foreground">{item.label}</span>
              <span
                className="text-sm text-foreground [&_a]:text-accent-brand [&_a]:hover:underline"
                dangerouslySetInnerHTML={{ __html: item.value }}
              />
            </div>
          ))}
        </div>
      )}

      {/* Profiles / Social Links */}
      {infobox.profiles && infobox.profiles.length > 0 && (
        <div className="flex flex-wrap gap-2 border-t border-border/40 pt-3">
          {infobox.profiles.map((profile, index) => (
            <a
              key={index}
              href={profile.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs px-2 py-1 rounded-full bg-accent-brand/10 text-accent-brand hover:bg-accent-brand/20 transition-colors"
            >
              {profile.long_name || profile.name}
            </a>
          ))}
        </div>
      )}

      {/* Source link */}
      {infobox.url && (
        <div className="flex items-center gap-2 pt-2 border-t border-border/40">
          <a
            href={infobox.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-accent-brand hover:underline flex items-center gap-1"
          >
            <ExternalLink className="h-3 w-3" />
            <span>View source</span>
          </a>
        </div>
      )}
    </div>
  )
}
