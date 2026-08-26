/**
 * The default header, used by every tool that has no id-specific header:
 * icon (or MCP server icon) + display name + a one-line result summary.
 * Also the registry's fallback for tool ids it has never heard of.
 */
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import type { ToolRenderContext } from './types'

// Extract spark ID from spark tool result
const extractSparkId = (result: any): string | null => {
  if (!result) return null
  try {
    let data = result
    if (typeof data === 'string') {
      try { data = JSON.parse(data) } catch { return null }
    }
    // Result structure: { status: 'success', spark: { id, title, ... } }
    if (data?.status === 'success' && data?.spark?.id) {
      return data.spark.id
    }
    return null
  } catch {
    return null
  }
}

// Extract a brief summary from tool results for display
const getToolResultSummary = (toolName: string, result: any): string | null => {
  if (!result) return null

  try {
    // Parse result if string
    let data = result
    if (typeof data === 'string') {
      try { data = JSON.parse(data) } catch { return null }
    }

    // Unwrap nested result structures
    data = data?.result || data
    data = data?.data || data

    // Tool-specific summaries
    switch (toolName) {
      // Brave Search tools
      case 'brave_web_search':
      case 'brave_news_search':
      case 'brave_local_search': {
        const results = data?.results || data?.web?.results || []
        const count = Array.isArray(results) ? results.length : 0
        return count > 0 ? `${count} result${count !== 1 ? 's' : ''}` : 'No results'
      }

      // GitHub tools
      case 'github_list_issues': {
        const issues = Array.isArray(data) ? data : data?.issues || []
        return `${issues.length} issue${issues.length !== 1 ? 's' : ''}`
      }
      case 'github_get_issue':
      case 'github_create_issue':
      case 'github_update_issue': {
        const num = data?.number || data?.issue?.number
        const title = data?.title || data?.issue?.title
        if (num) return `#${num}${title ? `: ${title.slice(0, 40)}${title.length > 40 ? '...' : ''}` : ''}`
        return null
      }
      case 'github_list_pull_requests': {
        const prs = Array.isArray(data) ? data : data?.pull_requests || []
        return `${prs.length} PR${prs.length !== 1 ? 's' : ''}`
      }
      case 'github_get_pull_request':
      case 'github_create_pull_request': {
        const num = data?.number || data?.pull_request?.number
        const title = data?.title || data?.pull_request?.title
        if (num) return `PR #${num}${title ? `: ${title.slice(0, 35)}${title.length > 35 ? '...' : ''}` : ''}`
        return null
      }
      case 'github_list_repos': {
        const repos = Array.isArray(data) ? data : data?.repositories || []
        return `${repos.length} repo${repos.length !== 1 ? 's' : ''}`
      }
      case 'github_search_code': {
        const count = data?.total_count || (Array.isArray(data?.items) ? data.items.length : 0)
        return `${count} match${count !== 1 ? 'es' : ''}`
      }
      case 'github_list_commits': {
        const commits = Array.isArray(data) ? data : data?.commits || []
        return `${commits.length} commit${commits.length !== 1 ? 's' : ''}`
      }
      case 'github_list_branches': {
        const branches = Array.isArray(data) ? data : data?.branches || []
        return `${branches.length} branch${branches.length !== 1 ? 'es' : ''}`
      }

      // Web fetch
      case 'fetch_web_page': {
        if (!data?.success) return data?.error?.slice(0, 50) || 'Failed'
        const title = data?.title
        if (title) return title.slice(0, 50) + (title.length > 50 ? '...' : '')
        const url = data?.url
        if (url) {
          try { return new URL(url).hostname } catch { return null }
        }
        return null
      }

      // Google Maps tools
      case 'geocode_address': {
        const lat = data?.latitude || data?.lat
        const lng = data?.longitude || data?.lng
        if (lat && lng) return `${lat.toFixed(4)}, ${lng.toFixed(4)}`
        return data?.formatted_address?.slice(0, 50) || null
      }
      case 'get_directions': {
        const duration = data?.duration || data?.routes?.[0]?.duration
        const distance = data?.distance || data?.routes?.[0]?.distance
        if (duration) return `${duration}${distance ? ` (${distance})` : ''}`
        return null
      }
      case 'search_nearby_places': {
        const places = Array.isArray(data) ? data : data?.places || data?.results || []
        return `${places.length} place${places.length !== 1 ? 's' : ''}`
      }

      // Spark tools
      case 'create_spark':
      case 'update_spark': {
        if (data?.status === 'success' && data?.spark?.title) {
          return data.spark.title.slice(0, 40) + (data.spark.title.length > 40 ? '...' : '')
        }
        return null
      }

      // Process tools
      case 'list_processes': {
        const procs = data?.processes || []
        if (procs.length === 0) return 'no running processes'
        return `${procs.length} process${procs.length !== 1 ? 'es' : ''} running`
      }
      case 'check_process_health': {
        if (data?.ready) return `port ${data.port} responding`
        return `port ${data?.port || '?'} not responding`
      }

      // Preview tools
      case 'start_preview': {
        if (data?.success) return `server on port ${data.port}`
        return data?.error || 'failed to start'
      }
      case 'stop_preview': {
        if (data?.success) return `port ${data.port} stopped`
        return data?.error || 'failed to stop'
      }

      // Coding agent management tools
      case 'update_coding_agent': {
        if (data?.success && data?.agent?.name) {
          const changeCount = data.changes?.length || 0
          return `${data.agent.name} (${changeCount} change${changeCount !== 1 ? 's' : ''})`
        }
        if (data?.error) return data.error.slice(0, 50)
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
        if (data?.error) return 'Not found'
        const filename = data?.metadata?.filename
        if (filename) return filename.slice(0, 40) + (filename.length > 40 ? '...' : '')
        if (data?.image_base64) return 'Image data retrieved'
        if (data?.url) return 'Image URL generated'
        return null
      }
      case 'get_video': {
        if (data?.error) return 'Not found'
        const filename = data?.metadata?.filename
        const duration = data?.metadata?.duration_formatted
        if (filename) {
          const shortName = filename.slice(0, 30) + (filename.length > 30 ? '...' : '')
          return duration ? `${shortName} (${duration})` : shortName
        }
        return null
      }
      case 'get_spark': {
        if (data?.error) return 'Not found'
        const title = data?.title
        const framework = data?.framework
        if (title) {
          const shortTitle = title.slice(0, 35) + (title.length > 35 ? '...' : '')
          return framework ? `${shortTitle} (${framework})` : shortTitle
        }
        return null
      }
      case 'get_document': {
        if (data?.error) return 'Not found'
        const filename = data?.filename
        const truncated = data?.truncated
        if (filename) {
          const shortName = filename.slice(0, 35) + (filename.length > 35 ? '...' : '')
          return truncated ? `${shortName} (truncated)` : shortName
        }
        return null
      }

      case 'export_asset': {
        if (data?.error) return 'Failed'
        const assetType = data?.asset_type
        const filename = data?.filename
        if (filename) {
          const shortName = filename.slice(0, 30) + (filename.length > 30 ? '...' : '')
          return assetType ? `${assetType}: ${shortName}` : shortName
        }
        return data?.permanent_url ? 'URL generated' : null
      }

      case 'save_asset_to_workspace': {
        if (data?.error) return 'Failed'
        if (data?.success) {
          const path = data?.path
          return path ? path.slice(0, 40) + (path.length > 40 ? '...' : '') : 'Saved'
        }
        return null
      }

      // Generic array results
      default: {
        if (Array.isArray(data)) {
          return `${data.length} item${data.length !== 1 ? 's' : ''}`
        }
        // Check for common count/total fields
        if (typeof data?.count === 'number') return `${data.count} item${data.count !== 1 ? 's' : ''}`
        if (typeof data?.total === 'number') return `${data.total} item${data.total !== 1 ? 's' : ''}`
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
