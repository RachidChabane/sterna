/**
 * ServerDetailModal Component
 *
 * Displays detailed information about an MCP server in a modal dialog.
 * Premium design with visual hierarchy and refined aesthetics.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Globe,
  Key,
  Lock,
  ExternalLink,
  Plus,
  Check,
  Shield,
  Server,
  Wrench,
  Network,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  Loader2,
  Braces,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/store/themeStore'
import { mcpApi } from '@/api/mcp'
import type { MCPPreconfiguredServer, MCPTool } from '@/api/mcp'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'


interface ServerDetailModalProps {
  isOpen: boolean
  onClose: () => void
  server: MCPPreconfiguredServer | null
  onConnect?: (server: MCPPreconfiguredServer) => void
  isConnected?: boolean
}

const AUTH_TYPE_INFO: Record<string, { label: string; description: string; icon: typeof Key; color: string }> = {
  none: {
    label: 'Public Access',
    description: 'No credentials required',
    icon: Globe,
    color: 'text-emerald-500',
  },
  oauth: {
    label: 'OAuth 2.0',
    description: 'Secure authorization flow',
    icon: Lock,
    color: 'text-blue-500',
  },
  api_key: {
    label: 'API Key',
    description: 'Service API key required',
    icon: Key,
    color: 'text-amber-500',
  },
  bearer: {
    label: 'Bearer Token',
    description: 'Access token required',
    icon: Shield,
    color: 'text-purple-500',
  },
}

const CATEGORY_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  productivity: { bg: 'bg-blue-500/10', text: 'text-blue-600 dark:text-blue-400', border: 'border-blue-500/20' },
  developer: { bg: 'bg-purple-500/10', text: 'text-purple-600 dark:text-purple-400', border: 'border-purple-500/20' },
  cloud: { bg: 'bg-orange-500/10', text: 'text-orange-600 dark:text-orange-400', border: 'border-orange-500/20' },
  crm: { bg: 'bg-pink-500/10', text: 'text-pink-600 dark:text-pink-400', border: 'border-pink-500/20' },
  finance: { bg: 'bg-green-500/10', text: 'text-green-600 dark:text-green-400', border: 'border-green-500/20' },
  ai: { bg: 'bg-cyan-500/10', text: 'text-cyan-600 dark:text-cyan-400', border: 'border-cyan-500/20' },
  data: { bg: 'bg-yellow-500/10', text: 'text-yellow-600 dark:text-yellow-400', border: 'border-yellow-500/20' },
  other: { bg: 'bg-gray-500/10', text: 'text-gray-600 dark:text-gray-400', border: 'border-gray-500/20' },
}

/**
 * Format JSON schema property for display
 */
function formatSchemaProperty(name: string, prop: Record<string, unknown>, required: boolean) {
  const type = prop.type as string || 'any'
  const description = prop.description as string
  const enumValues = prop.enum as string[]

  return (
    <div key={name} className="py-1.5 first:pt-0 last:pb-0">
      <div className="flex items-center gap-1.5 mb-0.5">
        <code className="text-[10px] font-mono text-foreground bg-muted/50 px-1 py-0.5 rounded">
          {name}
        </code>
        <Badge variant="outline" className="text-[9px] font-mono h-4 px-1">
          {type}
        </Badge>
        {required && (
          <Badge className="text-[9px] h-4 px-1 bg-amber-500/20 text-amber-600 dark:text-amber-400 border-0">
            required
          </Badge>
        )}
      </div>
      {description && (
        <p className="text-[10px] text-muted-foreground leading-relaxed ml-0.5">{description}</p>
      )}
      {enumValues && enumValues.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1 ml-0.5">
          {enumValues.map((val) => (
            <code key={val} className="text-[9px] bg-secondary px-1 py-0.5 rounded text-muted-foreground">
              {val}
            </code>
          ))}
        </div>
      )}
    </div>
  )
}

export function ServerDetailModal({
  isOpen,
  onClose,
  server,
  onConnect,
  isConnected = false,
}: ServerDetailModalProps) {
  const [showTools, setShowTools] = useState(false)
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set())
  const [fullToolsData, setFullToolsData] = useState<Record<string, MCPTool>>({})
  const [loadingTools, setLoadingTools] = useState<Set<string>>(new Set())
  const theme = useThemeStore((state) => state.theme)
  const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)

  // Toggle tool expansion and fetch full data if needed
  const toggleToolExpansion = useCallback(async (toolId: string) => {
    const isExpanded = expandedTools.has(toolId)

    if (isExpanded) {
      // Collapse
      setExpandedTools(prev => {
        const next = new Set(prev)
        next.delete(toolId)
        return next
      })
    } else {
      // Expand
      setExpandedTools(prev => new Set(prev).add(toolId))

      // Fetch full tool data if not already cached
      if (!fullToolsData[toolId]) {
        setLoadingTools(prev => new Set(prev).add(toolId))
        try {
          const response = await mcpApi.getTool(toolId)
          setFullToolsData(prev => ({ ...prev, [toolId]: response.data }))
        } catch (err) {
          console.error('Failed to fetch tool details:', err)
        } finally {
          setLoadingTools(prev => {
            const next = new Set(prev)
            next.delete(toolId)
            return next
          })
        }
      }
    }
  }, [expandedTools, fullToolsData])

  // Reset tools visibility when modal closes or server changes
  const handleClose = () => {
    setShowTools(false)
    setExpandedTools(new Set())
    onClose()
  }

  if (!server) return null

  const authInfo = AUTH_TYPE_INFO[server.auth_type] || AUTH_TYPE_INFO.none
  const AuthIcon = authInfo.icon
  const categoryStyle = CATEGORY_STYLES[server.category] || CATEGORY_STYLES.other

  const handleConnect = () => {
    if (onConnect) {
      onConnect(server)
      handleClose()
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg p-0 gap-0 overflow-hidden border-border/50">
        {/* Header with gradient background */}
        <div className="relative bg-gradient-to-br from-muted/40 via-muted/20 to-transparent">
          {/* Decorative blur */}
          <div className="absolute top-0 right-0 w-32 h-32 bg-accent-brand/10 rounded-full blur-3xl" />

          <DialogHeader className="relative p-6 pb-4">
            <div className="flex items-start gap-4">
              {/* Icon */}
              <div className="relative">
                <div className="w-14 h-14 rounded-xl bg-background/80 backdrop-blur-sm border border-border/50 flex items-center justify-center shadow-sm">
                  {server.icon_url ? (
                    <img
                      src={server.icon_url}
                      alt=""
                      className={cn(
                        "w-8 h-8 object-contain",
                        isDark && server.icon_invert_in_dark_mode && "invert"
                      )}
                      onError={(e) => {
                        e.currentTarget.style.display = 'none'
                        e.currentTarget.nextElementSibling?.classList.remove('hidden')
                      }}
                    />
                  ) : null}
                  <Globe className={cn("w-6 h-6 text-muted-foreground", server.icon_url && "hidden")} />
                </div>
                {isConnected && (
                  <div className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full bg-accent-brand flex items-center justify-center shadow-sm">
                    <Check className="w-3 h-3 text-white" />
                  </div>
                )}
              </div>

              {/* Title & Badges */}
              <div className="flex-1 min-w-0 pt-1">
                <DialogTitle className="text-xl font-semibold tracking-tight mb-2">
                  {server.name}
                </DialogTitle>
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-[10px] font-medium uppercase tracking-wider",
                      categoryStyle.bg, categoryStyle.text, categoryStyle.border
                    )}
                  >
                    {server.category_display}
                  </Badge>
                  {server.is_official === false && (
                    <Badge
                      variant="outline"
                      className="text-[10px] font-medium uppercase tracking-wider bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
                    >
                      Community
                    </Badge>
                  )}
                </div>
              </div>
            </div>
          </DialogHeader>
        </div>

        {/* Content */}
        <div className="max-h-[50vh] overflow-y-auto">
          <div className="px-6 pb-6 space-y-5">
            {/* Description */}
            <p className="text-sm text-muted-foreground leading-relaxed">
              {server.description || 'No description available'}
            </p>

            {/* Info Cards Grid */}
            <div className="grid grid-cols-2 gap-3">
              {/* Auth Card */}
              <div className="p-3 rounded-lg bg-muted/30 border border-border/40">
                <div className="flex items-center gap-2 mb-1.5">
                  <AuthIcon className={cn("w-3.5 h-3.5", authInfo.color)} />
                  <span className="text-xs font-medium text-foreground">{authInfo.label}</span>
                </div>
                <p className="text-[10px] text-muted-foreground leading-relaxed">
                  {authInfo.description}
                </p>
              </div>

              {/* Transport Card */}
              <div className="p-3 rounded-lg bg-muted/30 border border-border/40">
                <div className="flex items-center gap-2 mb-1.5">
                  <Network className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-xs font-medium text-foreground">
                    {server.transport_type === 'http' ? 'HTTP/SSE' : server.transport_type.toUpperCase()}
                  </span>
                </div>
                <p className="text-[10px] text-muted-foreground leading-relaxed">
                  {server.server_type === 'remote_http' ? 'Remote HTTP endpoint' :
                   server.server_type === 'local' ? 'Sandboxed local server' : 'Network transport'}
                </p>
              </div>

              {/* Tools Card - Expandable */}
              <div
                className={cn(
                  "p-3 rounded-lg bg-muted/30 border border-border/40 transition-colors",
                  server.tools && server.tools.length > 0 && "cursor-pointer hover:bg-muted/50"
                )}
                onClick={() => {
                  if (server.tools && server.tools.length > 0) {
                    setShowTools(!showTools)
                  }
                }}
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <Wrench className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-xs font-medium text-foreground">
                    {server.tools_count || '?'} Tools
                  </span>
                  {server.tools && server.tools.length > 0 && (
                    <span className="ml-auto">
                      {showTools ? (
                        <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                      )}
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-muted-foreground leading-relaxed">
                  {server.tools && server.tools.length > 0
                    ? 'Click to view available tools'
                    : 'Tools discovered on connect'}
                </p>
              </div>

              {/* Server Type Card */}
              <div className="p-3 rounded-lg bg-muted/30 border border-border/40">
                <div className="flex items-center gap-2 mb-1.5">
                  <Server className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-xs font-medium text-foreground">
                    {server.server_type === 'remote_http' ? 'Remote' :
                     server.server_type === 'local' ? 'Local' : 'Server'}
                  </span>
                </div>
                <p className="text-[10px] text-muted-foreground leading-relaxed">
                  {server.npm_package ? 'NPM package' : 'External service'}
                </p>
              </div>
            </div>

            {/* Expandable Tools List */}
            {showTools && server.tools && server.tools.length > 0 && (
              <div className="rounded-lg border border-border/40 bg-muted/20 overflow-hidden">
                <div className="max-h-64 overflow-y-auto">
                  {server.tools.map((tool, index) => {
                    const isExpanded = expandedTools.has(tool.id)
                    const isLoading = loadingTools.has(tool.id)
                    const fullTool = fullToolsData[tool.id]
                    const inputSchema = fullTool?.input_schema || {}
                    const properties = (inputSchema.properties || {}) as Record<string, Record<string, unknown>>
                    const required = (inputSchema.required || []) as string[]
                    const hasParameters = Object.keys(properties).length > 0

                    return (
                      <div
                        key={tool.id}
                        className={cn(
                          "w-full",
                          index !== server.tools!.length - 1 && "border-b border-border/30"
                        )}
                      >
                        {/* Tool header - clickable */}
                        <div
                          className="px-3 py-2.5 cursor-pointer hover:bg-muted/40 transition-colors flex items-start gap-2"
                          onClick={() => toggleToolExpansion(tool.id)}
                        >
                          <div className="flex-shrink-0 mt-0.5">
                            {isLoading ? (
                              <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
                            ) : (
                              <ChevronRight
                                className={cn(
                                  "w-3 h-3 text-muted-foreground transition-transform",
                                  isExpanded && "rotate-90"
                                )}
                              />
                            )}
                          </div>
                          <div className="flex-1 min-w-0 overflow-hidden">
                            <div className="text-xs font-medium text-foreground truncate">
                              {tool.name}
                            </div>
                            {!isExpanded && tool.description && (
                              <p className="text-[10px] text-muted-foreground leading-relaxed mt-0.5 line-clamp-1">
                                {tool.description}
                              </p>
                            )}
                          </div>
                        </div>

                        {/* Expanded content */}
                        {isExpanded && (
                          <div className="pb-3 pt-0 px-3 space-y-3">
                            {/* Full description */}
                            {tool.description && (
                              <div className="text-[11px] text-muted-foreground leading-relaxed prose prose-xs prose-neutral dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-code:text-[10px] prose-code:bg-muted/50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                  {tool.description}
                                </ReactMarkdown>
                              </div>
                            )}

                            {/* Parameters */}
                            {isLoading ? (
                              <div className="flex items-center justify-center py-3">
                                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                              </div>
                            ) : hasParameters ? (
                              <div>
                                <div className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground mb-2">
                                  <Braces className="w-3 h-3" />
                                  Parameters
                                </div>
                                <div className="rounded-md border border-border/30 bg-background/50 p-2 divide-y divide-border/30">
                                  {Object.entries(properties).map(([name, prop]) =>
                                    formatSchemaProperty(name, prop, required.includes(name))
                                  )}
                                </div>
                              </div>
                            ) : fullTool ? (
                              <p className="text-[10px] text-muted-foreground italic">
                                No parameters required
                              </p>
                            ) : null}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Endpoint URL */}
            {server.remote_url && (
              <div className="p-3 rounded-lg bg-muted/20 border border-border/30">
                <div className="flex items-center gap-2 mb-1.5">
                  <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-xs font-medium text-foreground">Endpoint</span>
                </div>
                <code className="text-[10px] text-muted-foreground break-all font-mono">
                  {server.remote_url}
                </code>
              </div>
            )}

            {/* Documentation Link */}
            {server.docs_url && (
              <a
                href={server.docs_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 p-3 rounded-lg bg-blue-500/5 border border-blue-500/20 hover:bg-blue-500/10 transition-colors group"
              >
                <ExternalLink className="w-3.5 h-3.5 text-blue-500" />
                <span className="text-xs font-medium text-blue-600 dark:text-blue-400 group-hover:underline">
                  View Documentation
                </span>
              </a>
            )}
          </div>
        </div>

        {/* Footer */}
        <DialogFooter className="p-4 pt-3 border-t border-border/50 bg-muted/10">
          <div className="flex items-center justify-between w-full">
            <Button variant="ghost" onClick={handleClose} className="text-xs h-9">
              Close
            </Button>
            {isConnected ? (
              <div className="flex items-center gap-1.5 text-xs text-accent-brand px-3 py-1.5 rounded-md bg-accent-brand/10">
                <Check className="h-3.5 w-3.5" />
                <span className="font-medium">Connected</span>
              </div>
            ) : onConnect && (
              <Button
                onClick={handleConnect}
                className="text-xs h-9 px-4 bg-accent-brand hover:bg-accent-brand/90 text-white shadow-sm"
              >
                <Plus className="h-3.5 w-3.5 mr-1.5" />
                Connect
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
