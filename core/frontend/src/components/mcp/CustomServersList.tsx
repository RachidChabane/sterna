/**
 * CustomServersList Component
 *
 * Displays a list of custom (npm-based) MCP servers with refined UI.
 */

import { useState } from 'react'
import {
  Package,
  Trash2,
  RefreshCw,
  RotateCw,
  Wrench,
  Key,
  Globe,
  AlertCircle,
  Loader2,
  LogIn,
  ChevronRight,
  Terminal,
  MoreHorizontal,
  Pencil,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ScrollArea } from '@/components/ui/scroll-area'
import { toast } from 'sonner'
import { mcpApi, type MCPServer, type MCPPreconfiguredServer } from '@/api/mcp'
import { getApiErrorMessage } from '@/utils/errorMessages'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/store/themeStore'
import { AddServerDialog } from './AddServerDialog'


interface CustomServersListProps {
  servers: MCPServer[]
  preconfiguredServers?: MCPPreconfiguredServer[]
  onRefresh: () => void
  isLoading?: boolean
}

type ServerStatus = 'connected' | 'stale' | 'error' | 'inactive' | 'never_connected' | 'ready'

const statusConfig: Record<ServerStatus, { color: string; bgColor: string; label: string }> = {
  connected: { color: 'text-emerald-500', bgColor: 'bg-emerald-500', label: 'Connected' },
  ready: { color: 'text-emerald-500', bgColor: 'bg-emerald-500', label: 'Ready' },
  stale: { color: 'text-amber-500', bgColor: 'bg-amber-500', label: 'Stale' },
  error: { color: 'text-red-500', bgColor: 'bg-red-500', label: 'Error' },
  inactive: { color: 'text-muted-foreground', bgColor: 'bg-muted-foreground', label: 'Inactive' },
  never_connected: { color: 'text-muted-foreground', bgColor: 'bg-muted-foreground/50', label: 'Not Connected' },
}

export function CustomServersList({
  servers,
  preconfiguredServers = [],
  onRefresh,
}: CustomServersListProps) {
  const theme = useThemeStore((state) => state.theme)
  const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)

  const [expandedServer, setExpandedServer] = useState<string | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [serverToDelete, setServerToDelete] = useState<MCPServer | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [discoveringTools, setDiscoveringTools] = useState<string | null>(null)
  const [authorizingServer, setAuthorizingServer] = useState<string | null>(null)
  const [reconnectingServer, setReconnectingServer] = useState<string | null>(null)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [serverToEdit, setServerToEdit] = useState<MCPServer | null>(null)

  // Find matching preconfigured server info by URL
  const getServerInfo = (server: MCPServer): { iconUrl?: string; invertInDarkMode?: boolean } => {
    const matchingPreconfig = preconfiguredServers.find(p =>
      (server.remote_url && p.remote_url && server.remote_url === p.remote_url) ||
      (server.npm_package && p.npm_package && server.npm_package === p.npm_package)
    )
    return {
      iconUrl: matchingPreconfig?.icon_url,
      invertInDarkMode: matchingPreconfig?.icon_invert_in_dark_mode,
    }
  }

  if (servers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="w-12 h-12 rounded-2xl bg-muted/30 flex items-center justify-center mb-4">
          <Terminal className="w-5 h-5 text-muted-foreground/60" />
        </div>
        <p className="text-sm text-muted-foreground">No custom connectors</p>
        <p className="text-xs text-muted-foreground/60 mt-1">
          Add a custom connector to connect to external services
        </p>
      </div>
    )
  }

  const handleDeleteClick = (server: MCPServer, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setServerToDelete(server)
    setDeleteDialogOpen(true)
  }

  const handleEditClick = (server: MCPServer, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setServerToEdit(server)
    setEditDialogOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!serverToDelete) return
    setIsDeleting(true)
    try {
      await mcpApi.deleteServer(serverToDelete.id)
      toast.success(`"${serverToDelete.name}" removed`)
      setDeleteDialogOpen(false)
      setServerToDelete(null)
      onRefresh()
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'Failed to delete server'))
    } finally {
      setIsDeleting(false)
    }
  }

  const handleDiscoverTools = async (server: MCPServer, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setDiscoveringTools(server.id)
    try {
      const response = await mcpApi.discoverTools(server.id, true)
      const toolCount = response.data.tools?.length || 0
      toast.success(`Discovered ${toolCount} tool${toolCount !== 1 ? 's' : ''} from ${server.name}`)
      onRefresh()
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'Failed to discover tools'))
    } finally {
      setDiscoveringTools(null)
    }
  }

  const handleOAuthAuthorize = async (server: MCPServer, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setAuthorizingServer(server.id)
    try {
      toast.info('Discovering OAuth configuration...')
      const discoverResponse = await mcpApi.oauthDiscover(server.id)
      if (discoverResponse.data.status !== 'success') {
        throw new Error('Failed to discover OAuth configuration')
      }
      toast.info('Redirecting to authorization...')
      const authResponse = await mcpApi.oauthAuthorize(server.id)
      if (authResponse.data.authorization_url) {
        window.location.href = authResponse.data.authorization_url
      } else {
        throw new Error('No authorization URL received')
      }
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'Failed to initiate OAuth authorization'))
    } finally {
      setAuthorizingServer(null)
    }
  }

  const handleReconnect = async (server: MCPServer, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setReconnectingServer(server.id)
    try {
      const response = await mcpApi.healthCheck(server.id)
      if (response.data.is_healthy) {
        toast.success(`Successfully reconnected to ${server.name}`)
      } else {
        toast.error(`Failed to connect to ${server.name}`)
      }
      onRefresh()
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'Failed to reconnect'))
    } finally {
      setReconnectingServer(null)
    }
  }

  const getStatus = (server: MCPServer): ServerStatus => {
    const rawStatus = (server.connection_status as ServerStatus) || 'never_connected'
    // For servers that don't require auth, treat 'never_connected' as 'ready'
    // They can be used immediately - no health check needed
    if (rawStatus === 'never_connected' && server.auth_type === 'none') {
      return 'ready'
    }
    return rawStatus
  }

  return (
    <>
      <div className="space-y-2">
        {servers.map((server, idx) => {
          const status = getStatus(server)
          const config = statusConfig[status]
          const isExpanded = expandedServer === server.id
          const isRemote = !!server.remote_url
          const needsAuth = server.auth_type === 'oauth' && server.oauth_connection_status !== 'connected' && status !== 'connected'

          const serverInfo = getServerInfo(server)

          return (
            <div
              key={server.id}
              className={cn(
                "group rounded-xl border transition-colors",
                isExpanded
                  ? "bg-card border-border"
                  : "bg-card/30 border-border/50 hover:bg-card/60 hover:border-border/80"
              )}
            >
              {/* Header Row */}
              <div
                className="flex items-center gap-3 p-3 sm:p-4 cursor-pointer"
                onClick={() => setExpandedServer(isExpanded ? null : server.id)}
              >
                {/* Icon & Status */}
                <div className="relative flex-shrink-0">
                  <div className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center",
                    serverInfo.iconUrl ? "bg-muted/30" : isRemote ? "bg-blue-500/10" : "bg-accent-brand/10"
                  )}>
                    {serverInfo.iconUrl ? (
                      <img
                        src={serverInfo.iconUrl}
                        alt=""
                        className={cn(
                          "w-5 h-5 object-contain",
                          isDark && serverInfo.invertInDarkMode && "invert"
                        )}
                      />
                    ) : isRemote ? (
                      <Globe className="w-4 h-4 text-blue-500" />
                    ) : (
                      <Package className="w-4 h-4 text-accent-brand" />
                    )}
                  </div>
                  {/* Status dot */}
                  <div className={cn(
                    "absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-background",
                    config.bgColor
                  )} />
                </div>

                {/* Name & Meta */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-medium text-sm text-foreground truncate max-w-[140px] sm:max-w-none">
                      {server.name}
                    </h3>
                    {needsAuth && (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 whitespace-nowrap">
                        Auth Required
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 sm:gap-3 mt-0.5">
                    <span className="text-[11px] sm:text-xs text-muted-foreground font-mono truncate">
                      {server.npm_package || server.remote_url}
                    </span>
                    {(server.tools_count ?? 0) > 0 && (
                      <span className="text-[11px] sm:text-xs text-muted-foreground/70 flex items-center gap-1 flex-shrink-0">
                        <Wrench className="w-3 h-3" />
                        {server.tools_count}
                      </span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                  {needsAuth ? (
                    <Button
                      size="sm"
                      onClick={(e) => handleOAuthAuthorize(server, e)}
                      disabled={authorizingServer === server.id}
                      className="h-7 sm:h-8 text-[11px] sm:text-xs btn-premium px-2 sm:px-3"
                    >
                      {authorizingServer === server.id ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <>
                          <LogIn className="w-3 h-3 sm:mr-1.5" />
                          <span className="hidden sm:inline">Authorize</span>
                        </>
                      )}
                    </Button>
                  ) : (status === 'stale' || status === 'error' || status === 'never_connected') && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={(e) => handleReconnect(server, e)}
                      disabled={reconnectingServer === server.id}
                      className="h-7 sm:h-8 text-[11px] sm:text-xs px-2 sm:px-3"
                    >
                      {reconnectingServer === server.id ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <>
                          <RotateCw className="w-3 h-3 sm:mr-1.5" />
                          <span className="hidden sm:inline">Reconnect</span>
                        </>
                      )}
                    </Button>
                  )}

                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="sm" className="h-7 w-7 sm:h-8 sm:w-8 p-0">
                        <MoreHorizontal className="w-4 h-4 text-muted-foreground" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-40">
                      <DropdownMenuItem onClick={(e) => handleDiscoverTools(server, e as any)}>
                        <RefreshCw className="w-3.5 h-3.5 mr-2" />
                        Refresh Tools
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={(e) => handleEditClick(server, e as any)}>
                        <Pencil className="w-3.5 h-3.5 mr-2" />
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={(e) => handleDeleteClick(server, e as any)}
                        className="text-red-500 focus:text-red-500"
                      >
                        <Trash2 className="w-3.5 h-3.5 mr-2" />
                        Remove
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>

                  <ChevronRight className={cn(
                    "w-4 h-4 text-muted-foreground/50 transition-transform duration-200",
                    isExpanded && "rotate-90"
                  )} />
                </div>
              </div>

              {/* Expanded Content */}
              {isExpanded && (
                <div className="px-4 pb-4 pt-0 border-t border-border/50">
                  <div className="pt-4 space-y-4">
                    {/* Details Grid */}
                    <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Status</span>
                        <span className={cn("font-medium", config.color)}>{config.label}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Transport</span>
                        <span className="text-foreground">{server.transport_type}</span>
                      </div>
                      {server.env_var_keys && server.env_var_keys.length > 0 && (
                        <div className="col-span-2 flex items-start justify-between">
                          <span className="text-muted-foreground flex items-center gap-1">
                            <Key className="w-3 h-3" />
                            Env Variables
                          </span>
                          <div className="flex flex-wrap gap-1 justify-end">
                            {server.env_var_keys.map((key) => (
                              <code key={key} className="px-1.5 py-0.5 rounded bg-muted/50 text-[10px] font-mono">
                                {key}
                              </code>
                            ))}
                          </div>
                        </div>
                      )}
                      {server.allowed_domains && server.allowed_domains.length > 0 && (
                        <div className="col-span-2 flex items-start justify-between">
                          <span className="text-muted-foreground flex items-center gap-1">
                            <Globe className="w-3 h-3" />
                            Allowed Domains
                          </span>
                          <div className="flex flex-wrap gap-1 justify-end">
                            {server.allowed_domains.map((domain) => (
                              <code key={domain} className="px-1.5 py-0.5 rounded bg-muted/50 text-[10px] font-mono">
                                {domain}
                              </code>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Tools List */}
                    {server.tools && server.tools.length > 0 && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <Wrench className="w-3 h-3 text-muted-foreground" />
                          <span className="text-xs font-medium text-muted-foreground">
                            Available Tools ({server.tools.length})
                          </span>
                        </div>
                        <ScrollArea className="h-[120px] rounded-lg bg-muted/20 p-2">
                          <div className="space-y-1">
                            {server.tools.map((tool) => (
                              <div
                                key={tool.id}
                                className="flex items-start gap-2 p-2 rounded-md hover:bg-muted/30 transition-colors"
                              >
                                <code className="text-xs font-medium text-accent-brand whitespace-nowrap">
                                  {tool.name}
                                </code>
                                {tool.description && (
                                  <span className="text-[11px] text-muted-foreground line-clamp-1">
                                    {tool.description}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </ScrollArea>
                      </div>
                    )}

                    {/* Error Message */}
                    {server.last_error && (
                      <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/5 border border-red-500/10">
                        <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                        <p className="text-xs text-red-400">{server.last_error}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Delete Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove Integration</DialogTitle>
            <DialogDescription>
              {serverToDelete &&
                `Are you sure you want to remove "${serverToDelete.name}"? This will disconnect the integration and remove all associated tools.`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteConfirm}
              disabled={isDeleting}
            >
              {isDeleting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      {serverToEdit && (
        <AddServerDialog
          open={editDialogOpen}
          onOpenChange={(open) => {
            setEditDialogOpen(open)
            if (!open) setServerToEdit(null)
          }}
          onServerCreated={() => {
            setEditDialogOpen(false)
            setServerToEdit(null)
            onRefresh()
          }}
          editServer={{
            id: serverToEdit.id,
            name: serverToEdit.name,
            description: serverToEdit.description,
            npm_package: serverToEdit.npm_package,
            remote_url: serverToEdit.remote_url,
            transport_type: serverToEdit.transport_type,
            auth_type: serverToEdit.auth_type,
            env_var_keys: serverToEdit.env_var_keys,
            allowed_domains: serverToEdit.allowed_domains,
          }}
        />
      )}
    </>
  )
}
