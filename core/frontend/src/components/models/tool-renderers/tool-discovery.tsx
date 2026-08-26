/** search_available_tools: header shows a found/disabled count, body lists the tools found. */
import { memo, useState } from 'react'
import { cn } from '@/lib/utils'
import { ChevronRight } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { ToolRenderContext } from './types'

// Helper to parse tool discovery result
const parseToolDiscoveryResult = (result: any) => {
  // Recursively parse JSON strings
  const parseJson = (val: any): any => {
    if (typeof val === 'string') {
      try { return parseJson(JSON.parse(val)) } catch { return val }
    }
    return val
  }

  // Unwrap nested result structures
  const unwrap = (obj: any): any => {
    if (!obj || typeof obj !== 'object') return obj
    // Try common wrapper patterns
    if (obj.result) return unwrap(obj.result)
    if (obj.data) return unwrap(obj.data)
    return obj
  }

  const parsed = parseJson(result)
  const toolsData = unwrap(parsed)

  // Extract found count - check multiple possible field names
  const foundCount = toolsData?.found || toolsData?.total || (toolsData?.tools?.length ?? 0)
  const availableCount = toolsData?.available ?? foundCount
  const tools = toolsData?.tools || []
  const disabledCount = foundCount - availableCount

  return { foundCount, availableCount, tools, disabledCount }
}

export function ToolDiscoveryHeader({ execution, displayName, Icon, isCodeVariant }: ToolRenderContext) {
  return (
    <div className="flex items-center gap-1.5">
      <Icon className={cn("w-3.5 h-3.5 shrink-0", isCodeVariant ? "text-foreground/50" : "text-muted-foreground")} />
      <span className={isCodeVariant ? "text-foreground/70 font-medium" : "text-foreground font-medium"}>{displayName}</span>
      {execution.result && !execution.isExecuting && (() => {
        const { foundCount, disabledCount } = parseToolDiscoveryResult(execution.result)
        return foundCount > 0 ? (
          <span className="text-muted-foreground/60">
            {foundCount} tool{foundCount !== 1 ? 's' : ''} found
            {disabledCount > 0 && <span className="text-amber-400 ml-1">({disabledCount} disabled)</span>}
          </span>
        ) : (
          <span className="text-muted-foreground/60">none found</span>
        )
      })()}
    </div>
  )
}

export function ToolDiscoveryBody({ execution }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting) return null
  return <ToolDiscoveryResult result={execution.result} />
}

// Component for displaying discovered tools list (expandable)
const ToolDiscoveryResult = memo(({ result }: { result: any }) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const { tools } = parseToolDiscoveryResult(result)

  if (tools.length === 0) return null

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="ml-5">
      <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
        <ChevronRight className={cn(
          "h-3 w-3 transition-transform duration-200",
          isExpanded && "rotate-90"
        )} />
        <span>{isExpanded ? 'Hide' : 'Show'} tools</span>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="mt-1.5 space-y-1.5 pl-3 border-l border-border/40 max-h-[300px] overflow-y-auto">
          {tools.map((tool: any, index: number) => {
            const isDisabled = tool.status === 'disabled'
            const isNotConnected = tool.status === 'not_connected'
            const isUnavailable = isDisabled || isNotConnected
            return (
              <div key={index} className="text-xs">
                <div className="flex items-center gap-1.5 flex-wrap">
                  {tool.server_icon && (
                    <img
                      src={tool.server_icon}
                      alt=""
                      className={`w-3.5 h-3.5 object-contain flex-shrink-0 ${tool.server_icon_invert ? 'dark:invert' : ''}`}
                    />
                  )}
                  <span className={`font-mono ${isUnavailable ? 'text-muted-foreground/50' : 'text-accent-brand'}`}>
                    {tool.display_name || tool.name}
                  </span>
                  {isDisabled && tool.requires && (
                    <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 text-[10px]">
                      Requires: {tool.requires}
                    </span>
                  )}
                  {isNotConnected && tool.requires_connection && (
                    <a
                      href={`/connectors?server=${encodeURIComponent(tool.requires_connection)}`}
                      className="px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 text-[10px] hover:bg-blue-500/30 transition-colors cursor-pointer"
                      onClick={(e) => {
                        e.preventDefault()
                        window.location.href = `/connectors?server=${encodeURIComponent(tool.requires_connection)}`
                      }}
                    >
                      Connect: {tool.requires_connection}
                    </a>
                  )}
                </div>
                {tool.description && (
                  <div className={`ml-0 mt-0.5 ${isUnavailable ? 'text-muted-foreground/40' : 'text-muted-foreground/60'}`}>
                    {tool.description.slice(0, 80)}{tool.description.length > 80 ? '...' : ''}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})
