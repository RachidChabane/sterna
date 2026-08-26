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
  extractLocalSearchLocations,
  type EnrichedResults as BraveEnrichedResults
} from '@/utils/braveSearchExtractors'
import {
  extractGeocodeLocations,
  extractNearbyPlaces,
  extractDirections,
  type DirectionsData
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

/**
 * Enrichments extracted from a step's tool executions: the Brave Search shape
 * (infobox/faq/discussions/locations/news/web results) plus the Google Maps
 * directions field only this hook's `get_directions` handling populates.
 */
export interface EnrichedResults extends BraveEnrichedResults {
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
