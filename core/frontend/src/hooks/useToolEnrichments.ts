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

interface ToolExecution {
  tool_call: {
    id: string
    type: 'function'
    function: {
      name: string
      arguments: string
    }
  }
  result: any
  success: boolean | null
  isExecuting?: boolean
}

interface Step {
  type: 'text' | 'reasoning' | 'tool_executions'
  content?: string
  isStreaming?: boolean
  executions?: ToolExecution[]
}

interface EnrichedResults {
  infobox?: any
  faq?: any
  discussions: any[]
  locations: any[]
  news_results: any[]
  videos_results?: any[]
  web_results: any[]
  directions?: any
}

/**
 * Extract Brave Search media (images/videos) from tool executions
 */
export const useBraveSearchMedia = (steps: Step[]) => {
  return useMemo(() => {
    const allMedia: { items: any[]; title: string }[] = []

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
              enrichments.locations = [...(enrichments.locations || []), ...locations]
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
              enrichments.locations = [...(enrichments.locations || []), ...locations]
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
