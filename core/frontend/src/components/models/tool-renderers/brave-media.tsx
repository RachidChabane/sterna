/** brave_image_search / brave_video_search body: the media carousel, when enabled and present. */
import { BraveSearchMediaCarousel, type MediaItem } from '../BraveSearchMediaCarousel'
import { isRecord } from './shared'
import type { ToolRenderContext } from './types'
import type { ToolResult } from '@/api/llm'

/** One entry in a Brave Search `results` array — the fields this renderer reads. */
interface BraveResultItem {
  thumbnail?: { src?: string }
  url?: string
  page_url?: string
  properties?: { url?: string; title?: string; domain?: string; width?: number; height?: number }
  title?: string
  source?: string
  creator?: string
  author?: string
  duration?: string
  view_count?: number
}

const isBraveResultItem = (val: unknown): val is BraveResultItem => isRecord(val)

// Extract media items from Brave Search results
const extractBraveSearchMedia = (toolName: string, executionResult: ToolResult): MediaItem[] | null => {
  // The executionResult is {tool_call, result, success}
  // We need to access result.result or result directly
  let braveResult: unknown = executionResult

  // If executionResult has a nested result property, use that
  if (isRecord(executionResult) && 'result' in executionResult) {
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
  if (!isRecord(braveResult) || !Array.isArray(braveResult.results)) {
    return null
  }
  const results: BraveResultItem[] = braveResult.results.filter(isBraveResultItem)

  const items: MediaItem[] = []

  // Extract images
  if (toolName === 'brave_image_search') {
    results.forEach((item) => {
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
    results.forEach((item) => {
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
