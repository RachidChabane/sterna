/**
 * The default header, used by every tool that has no id-specific header:
 * icon (or MCP server icon) + display name + a one-line result summary.
 * Also the registry's fallback for tool ids it has never heard of.
 */
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import { isRecord, asString, asNumber, getPath } from './shared'
import type { ToolRenderContext } from './types'
import type { ToolResult } from '@/api/llm'

const truncate = (text: string, max: number): string => text.slice(0, max) + (text.length > max ? '...' : '')

const arrayLength = (val: unknown): number | undefined => (Array.isArray(val) ? val.length : undefined)
const arrayAt = (val: unknown, i: number): unknown => (Array.isArray(val) ? val[i] : undefined)

// Extract spark ID from spark tool result
const extractSparkId = (result: ToolResult): string | null => {
  if (!result) return null
  try {
    const data: unknown = typeof result === 'string' ? JSON.parse(result) : result
    // Result structure: { status: 'success', spark: { id, title, ... } }
    if (getPath(data, 'status') === 'success') {
      const id = getPath(data, 'spark', 'id')
      if (typeof id === 'string') return id
    }
    return null
  } catch {
    return null
  }
}

// Extract a brief summary from tool results for display
const getToolResultSummary = (toolName: string, result: ToolResult): string | null => {
  if (!result) return null

  try {
    // Parse result if string
    let data: unknown = typeof result === 'string' ? (() => { try { return JSON.parse(result) } catch { return null } })() : result
    if (data === null) return null

    // Unwrap nested result structures
    data = getPath(data, 'result') ?? data
    data = getPath(data, 'data') ?? data

    // Tool-specific summaries
    switch (toolName) {
      // Brave Search tools
      case 'brave_web_search':
      case 'brave_news_search':
      case 'brave_local_search': {
        const results = getPath(data, 'results') ?? getPath(data, 'web', 'results')
        const count = Array.isArray(results) ? results.length : 0
        return count > 0 ? `${count} result${count !== 1 ? 's' : ''}` : 'No results'
      }

      // GitHub tools
      case 'github_list_issues': {
        const count = arrayLength(data) ?? arrayLength(getPath(data, 'issues')) ?? 0
        return `${count} issue${count !== 1 ? 's' : ''}`
      }
      case 'github_get_issue':
      case 'github_create_issue':
      case 'github_update_issue': {
        const num = asNumber(getPath(data, 'number')) ?? asNumber(getPath(data, 'issue', 'number'))
        const title = asString(getPath(data, 'title')) ?? asString(getPath(data, 'issue', 'title'))
        if (num) return `#${num}${title ? `: ${truncate(title, 40)}` : ''}`
        return null
      }
      case 'github_list_pull_requests': {
        const count = arrayLength(data) ?? arrayLength(getPath(data, 'pull_requests')) ?? 0
        return `${count} PR${count !== 1 ? 's' : ''}`
      }
      case 'github_get_pull_request':
      case 'github_create_pull_request': {
        const num = asNumber(getPath(data, 'number')) ?? asNumber(getPath(data, 'pull_request', 'number'))
        const title = asString(getPath(data, 'title')) ?? asString(getPath(data, 'pull_request', 'title'))
        if (num) return `PR #${num}${title ? `: ${truncate(title, 35)}` : ''}`
        return null
      }
      case 'github_list_repos': {
        const count = arrayLength(data) ?? arrayLength(getPath(data, 'repositories')) ?? 0
        return `${count} repo${count !== 1 ? 's' : ''}`
      }
      case 'github_search_code': {
        const count = asNumber(getPath(data, 'total_count')) ?? arrayLength(getPath(data, 'items')) ?? 0
        return `${count} match${count !== 1 ? 'es' : ''}`
      }
      case 'github_list_commits': {
        const count = arrayLength(data) ?? arrayLength(getPath(data, 'commits')) ?? 0
        return `${count} commit${count !== 1 ? 's' : ''}`
      }
      case 'github_list_branches': {
        const count = arrayLength(data) ?? arrayLength(getPath(data, 'branches')) ?? 0
        return `${count} branch${count !== 1 ? 'es' : ''}`
      }

      // Web fetch
      case 'fetch_web_page': {
        if (getPath(data, 'success') !== true) {
          const error = asString(getPath(data, 'error'))
          return error ? truncate(error, 50) : 'Failed'
        }
        const title = asString(getPath(data, 'title'))
        if (title) return truncate(title, 50)
        const url = asString(getPath(data, 'url'))
        if (url) {
          try { return new URL(url).hostname } catch { return null }
        }
        return null
      }

      // Google Maps tools
      case 'geocode_address': {
        const lat = asNumber(getPath(data, 'latitude')) ?? asNumber(getPath(data, 'lat'))
        const lng = asNumber(getPath(data, 'longitude')) ?? asNumber(getPath(data, 'lng'))
        if (lat && lng) return `${lat.toFixed(4)}, ${lng.toFixed(4)}`
        const address = asString(getPath(data, 'formatted_address'))
        return address ? truncate(address, 50) : null
      }
      case 'get_directions': {
        const firstRoute = arrayAt(getPath(data, 'routes'), 0)
        const duration = asString(getPath(data, 'duration')) ?? asString(getPath(firstRoute, 'duration'))
        const distance = asString(getPath(data, 'distance')) ?? asString(getPath(firstRoute, 'distance'))
        if (duration) return `${duration}${distance ? ` (${distance})` : ''}`
        return null
      }
      case 'search_nearby_places': {
        const count = arrayLength(data) ?? arrayLength(getPath(data, 'places')) ?? arrayLength(getPath(data, 'results')) ?? 0
        return `${count} place${count !== 1 ? 's' : ''}`
      }

      // Spark tools
      case 'create_spark':
      case 'update_spark': {
        const title = asString(getPath(data, 'spark', 'title'))
        if (getPath(data, 'status') === 'success' && title) {
          return truncate(title, 40)
        }
        return null
      }

      // Process tools
      case 'list_processes': {
        const count = arrayLength(getPath(data, 'processes')) ?? 0
        if (count === 0) return 'no running processes'
        return `${count} process${count !== 1 ? 'es' : ''} running`
      }
      case 'check_process_health': {
        const port = getPath(data, 'port')
        if (getPath(data, 'ready') === true) return `port ${port} responding`
        return `port ${port ?? '?'} not responding`
      }

      // Preview tools
      case 'start_preview': {
        if (getPath(data, 'success') === true) return `server on port ${getPath(data, 'port')}`
        return asString(getPath(data, 'error')) ?? 'failed to start'
      }
      case 'stop_preview': {
        if (getPath(data, 'success') === true) return `port ${getPath(data, 'port')} stopped`
        return asString(getPath(data, 'error')) ?? 'failed to stop'
      }

      // Coding agent management tools
      case 'update_coding_agent': {
        const agentName = asString(getPath(data, 'agent', 'name'))
        if (getPath(data, 'success') === true && agentName) {
          const changeCount = arrayLength(getPath(data, 'changes')) ?? 0
          return `${agentName} (${changeCount} change${changeCount !== 1 ? 's' : ''})`
        }
        const error = asString(getPath(data, 'error'))
        if (error) return truncate(error, 50)
        return null
      }

      // List tools - no summary here, shown in ListToolResultsDisplay
      case 'list_sparks':
      case 'list_generated_images':
      case 'list_generated_videos':
      case 'list_voice_rooms':
      case 'list_mcp_servers':
      case 'list_available_models':
      case 'list_knowledge_base_documents':
      case 'list_coding_agents':
        return null

      // Asset access tools
      case 'get_image': {
        if (getPath(data, 'error')) return 'Not found'
        const filename = asString(getPath(data, 'metadata', 'filename'))
        if (filename) return truncate(filename, 40)
        if (getPath(data, 'image_base64')) return 'Image data retrieved'
        if (getPath(data, 'url')) return 'Image URL generated'
        return null
      }
      case 'get_video': {
        if (getPath(data, 'error')) return 'Not found'
        const filename = asString(getPath(data, 'metadata', 'filename'))
        const duration = asString(getPath(data, 'metadata', 'duration_formatted'))
        if (filename) {
          const shortName = truncate(filename, 30)
          return duration ? `${shortName} (${duration})` : shortName
        }
        return null
      }
      case 'get_spark': {
        if (getPath(data, 'error')) return 'Not found'
        const title = asString(getPath(data, 'title'))
        const framework = asString(getPath(data, 'framework'))
        if (title) {
          const shortTitle = truncate(title, 35)
          return framework ? `${shortTitle} (${framework})` : shortTitle
        }
        return null
      }
      case 'get_document': {
        if (getPath(data, 'error')) return 'Not found'
        const filename = asString(getPath(data, 'filename'))
        const truncated = getPath(data, 'truncated')
        if (filename) {
          const shortName = truncate(filename, 35)
          return truncated ? `${shortName} (truncated)` : shortName
        }
        return null
      }

      case 'export_asset': {
        if (getPath(data, 'error')) return 'Failed'
        const assetType = asString(getPath(data, 'asset_type'))
        const filename = asString(getPath(data, 'filename'))
        if (filename) {
          const shortName = truncate(filename, 30)
          return assetType ? `${assetType}: ${shortName}` : shortName
        }
        return getPath(data, 'permanent_url') ? 'URL generated' : null
      }

      case 'save_asset_to_workspace': {
        if (getPath(data, 'error')) return 'Failed'
        if (getPath(data, 'success')) {
          const path = asString(getPath(data, 'path'))
          return path ? truncate(path, 40) : 'Saved'
        }
        return null
      }

      // Generic array results
      default: {
        if (Array.isArray(data)) {
          return `${data.length} item${data.length !== 1 ? 's' : ''}`
        }
        // Check for common count/total fields
        const count = asNumber(getPath(data, 'count'))
        if (count !== undefined) return `${count} item${count !== 1 ? 's' : ''}`
        const total = asNumber(getPath(data, 'total'))
        if (total !== undefined) return `${total} item${total !== 1 ? 's' : ''}`
        return null
      }
    }
  } catch {
    return null
  }
}

const SPARK_TOOL_NAMES = new Set(['create_spark', 'update_spark'])

export function GenericHeader(context: ToolRenderContext) {
  const { execution, toolName, displayName, Icon, isCodeVariant, effectiveSuccess } = context
  const { isDark } = useTheme()
  const serverIconUrl = execution.tool_call.server_icon_url
  const serverIconInvert = execution.tool_call.server_icon_invert

  const getClickHandler = (): (() => void) | undefined => {
    if (execution.isExecuting || effectiveSuccess === false) return undefined
    if (SPARK_TOOL_NAMES.has(toolName)) {
      const sparkId = extractSparkId(execution.result)
      if (sparkId) return () => useArtifactsPanelStore.getState().openSparkInPanel(sparkId)
    }
    return undefined
  }
  const clickHandler = getClickHandler()
  const isClickable = !!clickHandler

  return (
    <div
      className={cn(
        "flex items-center gap-1.5",
        isClickable && "cursor-pointer hover:text-foreground transition-colors"
      )}
      onClick={clickHandler}
      role={isClickable ? "button" : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={isClickable ? (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          clickHandler!()
        }
      } : undefined}
    >
      {serverIconUrl ? (
        <img
          src={serverIconUrl}
          alt=""
          className={cn(
            "w-3.5 h-3.5 shrink-0 object-contain",
            isDark && serverIconInvert && "invert"
          )}
          onError={(e) => {
            // Hide broken image, fallback icon will be shown via CSS
            e.currentTarget.style.display = 'none'
          }}
        />
      ) : (
        <Icon className={cn("w-3.5 h-3.5 shrink-0", isCodeVariant ? "text-foreground/50" : "text-muted-foreground")} />
      )}
      <span className={cn(
        isCodeVariant ? "text-foreground/70 font-medium" : "text-foreground font-medium",
        isClickable && "hover:underline"
      )}>{displayName}</span>
      {/* Brief summary for completed tools */}
      {execution.result && !execution.isExecuting && effectiveSuccess !== false && (() => {
        const summary = getToolResultSummary(toolName, execution.result)
        return summary ? (
          <span className="text-muted-foreground/60 text-xs">
            → {summary}
          </span>
        ) : null
      })()}
    </div>
  )
}
