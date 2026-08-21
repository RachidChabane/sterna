/**
 * Brave Search Results Extractors
 *
 * Utilities for extracting enriched results (infobox, FAQ, discussions, news, videos)
 * from Brave Search Pro API responses.
 */

interface EnrichedResults {
  infobox?: any
  faq?: any
  discussions: any[]
  locations: any[]
  news_results: any[]
  videos_results: any[]
  web_results: any[]
}

/**
 * Extract enriched results from a Brave web search execution
 */
export const extractEnrichedResults = (execution: any): EnrichedResults | null => {
  let result = execution.result

  // Extract nested result if present - may be double-nested
  if (result && typeof result === 'object' && 'result' in result) {
    result = result.result
    // Check for double-nesting
    if (result && typeof result === 'object' && 'result' in result && !('results' in result)) {
      result = result.result
    }
  }

  // Parse if string
  if (typeof result === 'string') {
    try {
      result = JSON.parse(result)
    } catch (e) {
      return null
    }
  }

  // Check if this is an enriched web search result (ONLY with real enrichments, not just web results)
  const hasEnrichments = result && (
    result.infobox ||
    result.faq ||
    (result.discussions && result.discussions.length > 0) ||
    (result.locations && result.locations.length > 0) ||
    (result.news_results && result.news_results.length > 0)
  )

  if (!hasEnrichments) {
    return null
  }

  // Normalize videos_results to match MediaItem format using shared normalizer
  const normalizedVideos = (result.videos_results || [])
    .map(normalizeVideoItem)
    .filter((item: any) => item.thumbnail) // Only include videos with valid thumbnails

  return {
    infobox: result.infobox,
    faq: result.faq,
    discussions: result.discussions || [],
    locations: result.locations || [],
    news_results: result.news_results || [],
    videos_results: normalizedVideos,
    web_results: result.results || []  // Standard web search results
  }
}

/**
 * Normalize a single video item to MediaItem format
 */
const normalizeVideoItem = (item: any) => ({
  type: 'video' as const,
  thumbnail: item.thumbnail?.src || '',
  url: item.url || item.page_url || '',
  title: item.title,
  source: item.creator || item.author,
  duration: item.duration,
  views: item.view_count ? `${item.view_count} views` : undefined
})

/**
 * Extract media items (images/videos) from Brave Search results
 */
export const extractBraveSearchMedia = (toolName: string, executionResult: any) => {
  // The executionResult is {tool_call, result, success}
  let braveResult = executionResult

  // Extract nested result if present - may be double-nested
  if (executionResult && typeof executionResult === 'object' && 'result' in executionResult) {
    braveResult = executionResult.result

    // Check for double-nesting: result.result contains the actual data
    if (braveResult && typeof braveResult === 'object' && 'result' in braveResult && !('results' in braveResult)) {
      braveResult = braveResult.result
    }
  }

  // Parse result if it's a JSON string
  if (typeof braveResult === 'string') {
    try {
      braveResult = JSON.parse(braveResult)
    } catch (e) {
      return null
    }
  }

  // Check if this is a Brave Search result with media
  if (!braveResult || !braveResult.results || !Array.isArray(braveResult.results)) {
    return null
  }

  const items: any[] = []

  // Extract images
  if (toolName === 'brave_image_search') {
    braveResult.results.forEach((item: any) => {
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
    braveResult.results.forEach((item: any) => {
      if (item.thumbnail && item.thumbnail.src) {
        items.push(normalizeVideoItem(item))
      }
    })
  }

  return items.length > 0 ? items : null
}

/**
 * Extract locations from Brave local search
 */
export const extractLocalSearchLocations = (execution: any) => {
  let result = execution.result

  // Extract nested result - may be double-nested
  if (result && typeof result === 'object' && 'result' in result) {
    result = result.result
    // Check for double-nesting
    if (result && typeof result === 'object' && 'result' in result && !('results' in result)) {
      result = result.result
    }
  }

  // Parse if string
  if (typeof result === 'string') {
    try {
      result = JSON.parse(result)
    } catch (e) {
      return null
    }
  }

  if (result && result.results) {
    const locationsWithGPS = result.results.filter((loc: any) => loc.coordinates)
    return locationsWithGPS.length > 0 ? locationsWithGPS : null
  }

  return null
}
