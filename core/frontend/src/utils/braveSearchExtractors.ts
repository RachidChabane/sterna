/**
 * Brave Search Results Extractors
 *
 * Utilities for extracting enriched results (infobox, FAQ, discussions, news, videos)
 * from Brave Search Pro API responses.
 */
import { isRecord } from '@/components/models/tool-renderers/shared'
import type { MediaItem } from '@/components/models/BraveSearchMediaCarousel'

/** A tool execution's raw payload — the shape every extractor unwraps before reading fields. */
export interface ToolExecutionLike {
  result: unknown
}

/** Brave Search infobox — mirrors InfoboxDisplay's `infobox` prop shape. */
interface BraveInfobox {
  title?: string
  description?: string
  long_desc?: string
  images?: Array<{ url: string; title?: string }>
  data?: Array<{ label: string; value: string }>
  url?: string
  ratings?: Array<{
    ratingValue?: number
    bestRating?: number
    reviewCount?: number
    profile?: string
    is_tripadvisor?: boolean
  }>
  profiles?: Array<{ name: string; url: string; long_name?: string }>
}

/** Brave Search FAQ block — mirrors FAQDisplay's `faq` prop shape. */
interface BraveFaq {
  results?: Array<{ question: string; answer: string; url?: string }>
}

/** A Brave Search discussion result — mirrors DiscussionsDisplay's `discussions` item shape. */
interface Discussion {
  title: string
  url: string
  description?: string
  forum?: { name: string; url: string }
  num_comments?: number
  score?: number
  published_date?: string
}

/** A map location (Brave local search or Google Maps) — mirrors LocationsMap's `locations` item shape. */
export interface EnrichedLocation {
  id?: string
  title: string
  address?: string
  coordinates?: { latitude: number; longitude: number }
  rating?: number
  phone?: string
  opening_hours?: string
  url?: string
  thumbnail?: string
  image?: string
  icon_category?: string
}

/** A Brave Search news article — mirrors NewsClusterDisplay's `news` item shape. */
interface NewsArticle {
  title: string
  url: string
  description?: string
  thumbnail?: { src: string }
  age?: string
  source?: { name: string; favicon?: string }
  published_date?: string
}

/** A Brave Search web result — mirrors WebResultsDisplay's `results` item shape. */
interface WebResult {
  title: string
  url: string
  description?: string
  thumbnail?: { src: string }
}

export interface EnrichedResults {
  infobox?: BraveInfobox
  faq?: BraveFaq
  discussions: Discussion[]
  locations: EnrichedLocation[]
  news_results: NewsArticle[]
  videos_results?: MediaItem[]
  web_results: WebResult[]
}

const isDiscussion = (val: unknown): val is Discussion => isRecord(val)
const isEnrichedLocation = (val: unknown): val is EnrichedLocation => isRecord(val)
const isNewsArticle = (val: unknown): val is NewsArticle => isRecord(val)
const isWebResult = (val: unknown): val is WebResult => isRecord(val)

/**
 * Unwraps a tool execution's possibly-nested, possibly-JSON-string `result`
 * payload into a plain object, or `undefined` if it isn't one.
 */
const unwrapResult = (execution: ToolExecutionLike): Record<string, unknown> | undefined => {
  let result: unknown = execution.result

  // Extract nested result if present - may be double-nested
  if (isRecord(result) && 'result' in result) {
    result = result.result
    // Check for double-nesting
    if (isRecord(result) && 'result' in result && !('results' in result)) {
      result = result.result
    }
  }

  // Parse if string
  if (typeof result === 'string') {
    try {
      result = JSON.parse(result)
    } catch {
      return undefined
    }
  }

  return isRecord(result) ? result : undefined
}

/**
 * Extract enriched results from a Brave web search execution
 */
export const extractEnrichedResults = (execution: ToolExecutionLike): EnrichedResults | null => {
  const result = unwrapResult(execution)
  if (!result) return null

  // Check if this is an enriched web search result (ONLY with real enrichments, not just web results)
  const hasEnrichments = Boolean(
    result.infobox ||
    result.faq ||
    (Array.isArray(result.discussions) && result.discussions.length > 0) ||
    (Array.isArray(result.locations) && result.locations.length > 0) ||
    (Array.isArray(result.news_results) && result.news_results.length > 0)
  )

  if (!hasEnrichments) {
    return null
  }

  // Normalize videos_results to match MediaItem format using shared normalizer
  const rawVideos = Array.isArray(result.videos_results) ? result.videos_results.filter(isRawVideoItem) : []
  const normalizedVideos = rawVideos
    .map(normalizeVideoItem)
    .filter((item) => item.thumbnail) // Only include videos with valid thumbnails

  return {
    infobox: isRecord(result.infobox) ? (result.infobox as BraveInfobox) : undefined,
    faq: isRecord(result.faq) ? (result.faq as BraveFaq) : undefined,
    discussions: Array.isArray(result.discussions) ? result.discussions.filter(isDiscussion) : [],
    locations: Array.isArray(result.locations) ? result.locations.filter(isEnrichedLocation) : [],
    news_results: Array.isArray(result.news_results) ? result.news_results.filter(isNewsArticle) : [],
    videos_results: normalizedVideos,
    web_results: Array.isArray(result.results) ? result.results.filter(isWebResult) : []  // Standard web search results
  }
}

/** One item in a Brave `videos_results` array — the fields this extractor reads. */
interface RawVideoItem {
  thumbnail?: { src?: string }
  url?: string
  page_url?: string
  title?: string
  creator?: string
  author?: string
  duration?: string
  view_count?: number
}

const isRawVideoItem = (val: unknown): val is RawVideoItem => isRecord(val)

/**
 * Normalize a single video item to MediaItem format
 */
const normalizeVideoItem = (item: RawVideoItem): MediaItem => ({
  type: 'video' as const,
  thumbnail: item.thumbnail?.src || '',
  url: item.url || item.page_url || '',
  title: item.title,
  source: item.creator || item.author,
  duration: item.duration,
  views: item.view_count ? `${item.view_count} views` : undefined
})

/** One item in a Brave image-search `results` array — the fields this extractor reads. */
interface RawImageItem {
  thumbnail?: { src?: string; original?: string }
  image?: { url?: string; width?: number; height?: number }
  properties?: { url?: string; title?: string; domain?: string; width?: number; height?: number }
  url?: string
  title?: string
  source?: string
}

const isRawImageItem = (val: unknown): val is RawImageItem => isRecord(val)

/**
 * Extract media items (images/videos) from Brave Search results
 */
export const extractBraveSearchMedia = (toolName: string, execution: ToolExecutionLike): MediaItem[] | null => {
  const braveResult = unwrapResult(execution)

  // Check if this is a Brave Search result with media
  if (!braveResult || !Array.isArray(braveResult.results)) {
    return null
  }

  const items: MediaItem[] = []

  // Extract images
  if (toolName === 'brave_image_search') {
    braveResult.results.filter(isRawImageItem).forEach((item) => {
      // Try multiple thumbnail locations (Brave API structure may vary)
      const thumbnailSrc = item.thumbnail?.src || item.thumbnail?.original || item.image?.url || item.properties?.url
      if (thumbnailSrc) {
        items.push({
          type: 'image',
          thumbnail: thumbnailSrc,
          url: item.url || item.properties?.url || thumbnailSrc,
          title: item.title || item.properties?.title,
          source: item.source || item.properties?.domain,
          width: item.properties?.width || item.image?.width,
          height: item.properties?.height || item.image?.height
        })
      }
    })
  }

  // Extract videos
  if (toolName === 'brave_video_search') {
    braveResult.results.filter(isRawVideoItem).forEach((item) => {
      if (item.thumbnail?.src) {
        items.push(normalizeVideoItem(item))
      }
    })
  }

  return items.length > 0 ? items : null
}

/**
 * Extract locations from Brave local search
 */
export const extractLocalSearchLocations = (execution: ToolExecutionLike): EnrichedLocation[] | null => {
  const result = unwrapResult(execution)
  if (!result || !Array.isArray(result.results)) return null

  const locationsWithGPS = result.results.filter(isEnrichedLocation).filter((loc) => loc.coordinates)
  return locationsWithGPS.length > 0 ? locationsWithGPS : null
}
