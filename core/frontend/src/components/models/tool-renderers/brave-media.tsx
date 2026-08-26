/** brave_image_search / brave_video_search body: the media carousel, when enabled and present. */
import { BraveSearchMediaCarousel } from '../BraveSearchMediaCarousel'
import type { ToolRenderContext } from './types'

// Extract media items from Brave Search results
const extractBraveSearchMedia = (toolName: string, executionResult: any) => {
  // The executionResult is {tool_call, result, success}
  // We need to access result.result or result directly
  let braveResult = executionResult

  // If executionResult has a nested result property, use that
  if (executionResult && typeof executionResult === 'object' && 'result' in executionResult) {
    braveResult = executionResult.result
  }

  // Parse result if it's a JSON string
  if (typeof braveResult === 'string') {
    try {
      braveResult = JSON.parse(braveResult)
    } catch (e) {
      console.error('[BraveSearchMedia] Failed to parse result:', e)
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
      if (item.thumbnail && item.thumbnail.src) {
        items.push({
          type: 'image',
          thumbnail: item.thumbnail.src,
          url: item.url || item.properties?.url || '',
          title: item.title || item.properties?.title,
          source: item.source || item.properties?.domain,
          width: item.properties?.width,
          height: item.properties?.height
        })
      }
    })
  }

  // Extract videos
  if (toolName === 'brave_video_search') {
    braveResult.results.forEach((item: any) => {
      if (item.thumbnail && item.thumbnail.src) {
        items.push({
          type: 'video',
          thumbnail: item.thumbnail.src,
          url: item.url || item.page_url || '',
          title: item.title,
          source: item.creator || item.author,
          duration: item.duration,
          views: item.view_count ? `${item.view_count} views` : undefined
        })
      }
    })
  }

  return items.length > 0 ? items : null
}

export function BraveMediaBody({ execution, toolName, showBraveSearchMedia }: ToolRenderContext) {
  const shouldExtract = showBraveSearchMedia && execution.result && !execution.isExecuting && execution.success !== false
  const media = shouldExtract ? extractBraveSearchMedia(toolName, execution.result) : null
  if (!media) return null

  return (
    <BraveSearchMediaCarousel
      items={media}
      title={toolName === 'brave_image_search' ? 'Images' : 'Videos'}
    />
  )
}
