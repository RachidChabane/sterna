/**
 * Hook for extracting enrichments from tool execution results
 *
 * Handles extraction of:
 * - Brave Search enrichments (infobox, FAQ, discussions, news, videos)
 * - Brave Search media (images, videos)
 * - Google Maps locations
 */

import { useMemo } from 'react'
import {
  extractEnrichedResults,
  extractBraveSearchMedia,
  extractLocalSearchLocations
} from '@/utils/braveSearchExtractors'
import {
  extractGeocodeLocations,
  extractNearbyPlaces,
  extractDirections
} from '@/utils/googleMapsExtractors'
import type { MediaItem } from '@/components/models/BraveSearchMediaCarousel'

interface ToolExecution {
  tool_call: {
    id: string
    type: 'function'
    function: {
      name: string
      arguments: string
    }
  }
  result: unknown
  success: boolean | null
  isExecuting?: boolean
}

interface Step {
  type: 'text' | 'reasoning' | 'tool_executions'
  content?: string
  isStreaming?: boolean
  executions?: ToolExecution[]
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
interface EnrichedLocation {
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

/** Google Maps directions/route — mirrors DirectionsMap's `directions` prop shape. */
interface DirectionsData {
  summary: string
  distance: string
  duration: string
  start_address: string
  end_address: string
  polyline: string
  steps: Array<{ instruction: string; distance: string; duration: string }>
}

export interface EnrichedResults {
  infobox?: BraveInfobox
  faq?: BraveFaq
  discussions: Discussion[]
  locations: EnrichedLocation[]
  news_results: NewsArticle[]
  videos_results?: MediaItem[]
  web_results: WebResult[]
  directions?: DirectionsData
}

/** One Brave Search media carousel (images or videos) extracted from a step's tool executions. */
export interface BraveMediaGroup {
  items: MediaItem[]
  title: string
}

/**
 * Extract Brave Search media (images/videos) from tool executions
 */
export const useBraveSearchMedia = (steps: Step[]): BraveMediaGroup[] => {
  return useMemo(() => {
    const allMedia: BraveMediaGroup[] = []

    steps.forEach((step) => {
      if (step.type === 'tool_executions' && step.executions) {
        step.executions.forEach((execution) => {
          const toolName = execution.tool_call?.function?.name
          if (
            (toolName === 'brave_image_search' || toolName === 'brave_video_search') &&
            execution.result &&
            !execution.isExecuting &&
            execution.success !== false
          ) {
            const media = extractBraveSearchMedia(toolName, execution)
            if (media) {
              allMedia.push({
                items: media,
                title: toolName === 'brave_image_search' ? 'Images' : 'Videos'
              })
            }
          }
        })
      }
    })

    return allMedia
  }, [steps])
}

/**
 * Google Maps extractors report a missing rating as `null`; the map UI's
 * location shape only accepts `number | undefined`. Normalize at the boundary
 * rather than widening the shared `EnrichedLocation` type to `null` (which
 * the renderer doesn't accept either).
 */
function normalizeLocationRating<T extends { rating?: number | null }>(
  location: T
): Omit<T, 'rating'> & { rating?: number } {
  return { ...location, rating: location.rating ?? undefined }
}

/**
 * Extract enriched Brave Search results (Pro features) and Google Maps locations
 */
export const useEnrichedResults = (steps: Step[]): EnrichedResults | null => {
  return useMemo(() => {
    let enrichments: EnrichedResults | null = null

    steps.forEach((step) => {
      if (step.type === 'tool_executions' && step.executions) {
        step.executions.forEach((execution) => {
          const toolName = execution.tool_call?.function?.name

          // Brave web search enrichments
          if (
            toolName === 'brave_web_search' &&
            execution.result &&
            !execution.isExecuting &&
            execution.success !== false
          ) {
            const extracted = extractEnrichedResults(execution)
            if (extracted) {
              if (!enrichments) {
                enrichments = extracted
              } else {
                // Merge multiple enriched searches
                enrichments.discussions = [...enrichments.discussions, ...extracted.discussions]
                enrichments.locations = [...enrichments.locations, ...extracted.locations]
                enrichments.news_results = [...enrichments.news_results, ...extracted.news_results]
                enrichments.web_results = [...enrichments.web_results, ...extracted.web_results]
                if (extracted.infobox) enrichments.infobox = extracted.infobox
                if (extracted.faq) enrichments.faq = extracted.faq
              }
            }
          }

          // Brave local search locations
          if (
            toolName === 'brave_local_search' &&
            execution.result &&
            !execution.isExecuting &&
            execution.success !== false
          ) {
            const locations = extractLocalSearchLocations(execution)
            if (locations) {
              if (!enrichments) enrichments = { discussions: [], locations: [], news_results: [], web_results: [] }
              enrichments.locations = [...(enrichments.locations || []), ...locations]
            }
          }

          // Google Maps geocode locations
          if (
            toolName === 'geocode_address' &&
            execution.result &&
            !execution.isExecuting &&
            execution.success !== false
          ) {
            const locations = extractGeocodeLocations(execution)
            if (locations) {
              if (!enrichments) enrichments = { discussions: [], locations: [], news_results: [], web_results: [] }
              enrichments.locations = [...(enrichments.locations || []), ...locations.map(normalizeLocationRating)]
            }
          }

          // Google Maps nearby places
          if (
            toolName === 'search_nearby_places' &&
            execution.result &&
            !execution.isExecuting &&
            execution.success !== false
          ) {
            const locations = extractNearbyPlaces(execution)
            if (locations) {
              if (!enrichments) enrichments = { discussions: [], locations: [], news_results: [], web_results: [] }
              enrichments.locations = [...(enrichments.locations || []), ...locations.map(normalizeLocationRating)]
            }
          }

          // Google Maps directions
          if (
            toolName === 'get_directions' &&
            execution.result &&
            !execution.isExecuting &&
            execution.success !== false
          ) {
            const directions = extractDirections(execution)
            if (directions) {
              if (!enrichments) enrichments = { discussions: [], locations: [], news_results: [], web_results: [] }
              enrichments.directions = directions
            }
          }
        })
      }
    })

    return enrichments
  }, [steps])
}
