import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { Plus, Server, Grid3X3, ChevronRight, Sparkles, Loader2 } from 'lucide-react'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { mcpApi } from '@/api/mcp'
import type { MCPPreconfiguredServer, MCPDiscoveredServer } from '@/api/mcp'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { AddServerDialog } from '@/components/mcp/AddServerDialog'
import { AIDiscoveryDialog } from '@/components/mcp/AIDiscoveryDialog'
import { CustomServersList } from '@/components/mcp/CustomServersList'
import { PreconfiguredServersList } from '@/components/mcp/PreconfiguredServersList'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'
import { useNavigationStore } from '@/store/navigationStore'
import { useMCPStore } from '@/store/mcpStore'
import { cn } from '@/lib/utils'
import { getApiErrorMessage } from '@/utils/errorMessages'

export const Route = createFileRoute('/connectors')({
  component: () => (
    <ProtectedRoute>
      <MCPPage />
    </ProtectedRoute>
  ),
})

function MCPPage() {
  const navigate = useNavigate()
  const { openMobileSidebar } = useNavigationStore()
  const {
    servers,
    preconfiguredServers,
    serversLoading,
    preconfiguredServersLoading,
    lastServersFetchTime,
    lastPreconfiguredFetchTime,
    fetchAllMCPData,
  } = useMCPStore()
  const search = useSearch({ from: '/connectors' }) as {
    success?: string;
    error?: string;
    message?: string;
    server?: string;
    oauth_success?: string;
    oauth_error?: string;
    server_id?: string;
    server_name?: string;
    search?: string; // Pre-fill search from command palette
  }

  // Smart loading state: show loading if actively fetching OR if data hasn't been fetched yet
  const hasServerData = lastServersFetchTime > 0
  const hasPreconfiguredData = lastPreconfiguredFetchTime > 0
  const isLoading = serversLoading || preconfiguredServersLoading || !hasServerData || !hasPreconfiguredData

  const [addServerDialogOpen, setAddServerDialogOpen] = useState(false)
  const [aiDiscoveryDialogOpen, setAiDiscoveryDialogOpen] = useState(false)
  const [activeSection, setActiveSection] = useState<'connected' | 'browse'>('browse')

  // Pre-fill data for connecting a preconfigured server
  const [prefillServerData, setPrefillServerData] = useState<Partial<MCPPreconfiguredServer> | null>(null)
  const [autoFetchConfigHelp, setAutoFetchConfigHelp] = useState(false)

  // Handle AI-discovered server selection
  const handleAIDiscoveredServer = (server: MCPDiscoveredServer) => {
    setPrefillServerData({
      name: server.name,
      description: server.description,
      npm_package: server.npm_package || undefined,
      remote_url: server.remote_url || undefined,
      transport_type: server.server_type === 'local' ? 'sandboxed' : 'http',
      auth_type: server.auth_type,
      // Include icon data from preconfigured servers
      icon_url: server.icon_url || undefined,
      icon_invert_in_dark_mode: server.icon_invert_in_dark_mode || false,
    })
    setAutoFetchConfigHelp(true)  // Auto-fetch config help for AI-discovered servers
    setAddServerDialogOpen(true)
  }

  // Check for abandoned OAuth on mount (runs once)
  // This handles when user cancels at provider and browser navigates back without callback
  useEffect(() => {
    const pendingServerId = sessionStorage.getItem('mcp_pending_oauth_server_id')

    // Only clean up if we have a pending server AND no OAuth callback params
    // (if there are callback params, the other effect will handle it)
    const hasOAuthParams = window.location.search.includes('oauth_success') ||
                           window.location.search.includes('oauth_error') ||
                           window.location.search.includes('success=connected') ||
                           window.location.search.includes('error=')

    if (pendingServerId && !hasOAuthParams) {
      // Clear sessionStorage first to prevent re-triggering on re-renders
      sessionStorage.removeItem('mcp_pending_oauth_server_id')

      // Before deleting, verify the server is actually in pending OAuth state
      // (OAuth might have succeeded but sessionStorage wasn't cleared due to race condition)
      mcpApi.getServer(pendingServerId)
        .then((response) => {
          const server = response.data
          // Only delete if OAuth is still pending (not connected)
          if (server.oauth_connection_status === 'pending' || server.oauth_connection_status === 'not_configured') {
            return mcpApi.deleteServer(pendingServerId)
              .then(() => {
                toast.info('Authorization cancelled')
                fetchAllMCPData(true)
              })
          } else {
            // OAuth was actually successful, just load the data
            
            fetchAllMCPData()
          }
        })
        .catch((err) => {
          // Server doesn't exist (404) or other error - just load data
          console.error('Failed to check/clean up pending server:', err)
          fetchAllMCPData()
        })
    } else {
      fetchAllMCPData()
    }
  }, [])

  // Switch to browse section when server or search query param is present
  useEffect(() => {
    if (search.server || search.search) {
      setActiveSection('browse')
    }
  }, [search.server, search.search])

  useEffect(() => {
    // Handle OAuth callback results (only when we have callback params)
    if (search.oauth_success === 'true' && search.server_name) {
      // Success! Clear pending server and show success
      sessionStorage.removeItem('mcp_pending_oauth_server_id')
      toast.success(`Successfully connected to ${decodeURIComponent(search.server_name)}!`)
      navigate({ to: '/connectors', search: {} })
      fetchAllMCPData(true)
      setActiveSection('connected') // Switch to My Servers to show the new connection
    } else if (search.success === 'connected' && search.server) {
      // Legacy format - also clear pending
      sessionStorage.removeItem('mcp_pending_oauth_server_id')
      toast.success(`Successfully connected to ${search.server}!`)
      navigate({ to: '/connectors', search: {} })
      fetchAllMCPData(true)
    } else if (search.oauth_error || search.error) {
      // Error callback - clear pending (backend should have deleted it)
      sessionStorage.removeItem('mcp_pending_oauth_server_id')
      const error = search.oauth_error || search.error
      const message = search.message ? decodeURIComponent(search.message) : ''

      // Check if it was just a user cancellation (not a real error)
      const wasCancelled = message.toLowerCase().includes('cancelled') ||
        message.toLowerCase().includes('denied') ||
        error === 'access_denied'

      if (wasCancelled) {
        // User cancelled - just show info toast, not error
        toast.info('Authorization cancelled')
      } else {
        // Real error
        const errorMessage = message ||
          (error === 'invalid_state' || error === 'missing_state'
            ? 'OAuth state validation failed. Please try again.'
            : error === 'oauth_failed' || error === 'callback_failed'
            ? 'OAuth authentication failed. Please try again.'
            : 'An error occurred during connection.')
        toast.error(errorMessage)
      }
      navigate({ to: '/connectors', search: {} })
      fetchAllMCPData(true) // Refresh to reflect any server deletions
    }
  }, [search])

  const [isConnecting, setIsConnecting] = useState(false)

  const handleConnectPreconfigured = async (server: MCPPreconfiguredServer) => {
    // For OAuth servers, try to go directly to OAuth flow
    if (server.auth_type === 'oauth') {
      setIsConnecting(true)
      try {
        // Step 1: Create the server (copying icon_url and other data)
        const createResponse = await mcpApi.createServer({
          name: server.name,
          description: server.description,
          remote_url: server.remote_url,
          auth_type: 'oauth',
          is_active: true,
          icon_url: server.icon_url,
          icon_invert_in_dark_mode: server.icon_invert_in_dark_mode,
        })

        const newServer = createResponse.data

        // Step 2: Start OAuth authorization
        const authResponse = await mcpApi.oauthAuthorize(newServer.id)

        // Step 3: Store pending server ID so we can clean up if OAuth is cancelled
        // (some providers don't redirect to callback on cancel, they just go back)
        sessionStorage.setItem('mcp_pending_oauth_server_id', newServer.id)

        // Step 4: Redirect to OAuth provider
        window.location.href = authResponse.data.authorization_url
      } catch (error) {
        console.error('Failed to start OAuth flow:', error)
        const errorMessage = getApiErrorMessage(error, 'Failed to start authorization')
        toast.error(errorMessage)
        setIsConnecting(false)

        // Fall back to dialog so user can see details and retry
        setPrefillServerData(server)
        setAddServerDialogOpen(true)
      }
      return
    }

    // For non-OAuth servers, open the dialog to collect credentials
    setPrefillServerData(server)
    setAddServerDialogOpen(true)
  }

  // Get IDs of preconfigured servers that the user is already connected to
  // Match by npm_package or remote_url between user's servers and preconfigured servers
  const connectedPreconfiguredIds = preconfiguredServers
    .filter(preconfig =>
      servers.some(userServer =>
        (preconfig.remote_url && userServer.remote_url && preconfig.remote_url === userServer.remote_url) ||
        (preconfig.npm_package && userServer.npm_package && preconfig.npm_package === userServer.npm_package)
      )
    )
    .map(preconfig => preconfig.id)

  return (
    <>
      {/* Loading overlay when starting OAuth flow */}
      {isConnecting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="h-8 w-8 animate-spin text-accent-brand" />
            <p className="text-sm text-muted-foreground">Redirecting to authorization...</p>
          </div>
        </div>
      )}
      <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Mobile header */}
      <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border/50 sticky top-0 z-40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <button
          onClick={openMobileSidebar}
          className="p-2 -ml-2 text-muted-foreground hover:text-foreground transition-colors"
        >
          <PremiumMenuIcon size={18} />
        </button>
        <h1 className="text-base font-medium text-foreground">Connectors</h1>
        <div className="w-10" />
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {/* Sticky desktop header */}
        <div className="sticky top-0 z-30 bg-background hidden md:block">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-8 pb-0">
            {/* Title row */}
            <div className="flex items-center justify-between gap-4">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                Connectors
              </h1>
              <Button
                onClick={() => {
                  setPrefillServerData(null)
                  setAddServerDialogOpen(true)
                }}
                variant="outline"
                className="rounded-full h-9 px-4 flex-shrink-0 text-brand-700 dark:text-brand-400 border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-800 dark:hover:text-brand-300"
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Integration
              </Button>
            </div>

            {/* Tab navigation */}
            <div className="flex items-center -mb-px mt-5">
              <button
                onClick={() => setActiveSection('browse')}
                className={cn(
                  "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all",
                  activeSection === 'browse'
                    ? "border-accent-brand text-accent-brand"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                )}
              >
                <Grid3X3 className="w-4 h-4" />
                <span>Browse</span>
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                  activeSection === 'browse'
                    ? "bg-accent-brand/15 text-accent-brand"
                    : "bg-muted text-muted-foreground"
                )}>
                  {preconfiguredServers.length}
                </span>
              </button>
              <button
                onClick={() => setActiveSection('connected')}
                className={cn(
                  "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all",
                  activeSection === 'connected'
                    ? "border-accent-brand text-accent-brand"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                )}
              >
                <Server className="w-4 h-4" />
                <span>Connected</span>
                {servers.length > 0 && (
                  <span className={cn(
                    "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                    activeSection === 'connected'
                      ? "bg-accent-brand/15 text-accent-brand"
                      : "bg-muted text-muted-foreground"
                  )}>
                    {servers.length}
                  </span>
                )}
              </button>
            </div>
          </div>
          <div className="border-b border-border/50" />
        </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8 pb-24 md:pb-8">
        {activeSection === 'connected' ? (
          <div className="space-y-6">
            {isLoading ? (
              <div className="flex items-center justify-center py-16">
                <div className="flex flex-col items-center gap-4">
                  <div className="relative">
                    <div className="w-10 h-10 rounded-full border-2 border-accent-brand/20 border-t-accent-brand animate-spin" />
                  </div>
                  <p className="text-sm text-muted-foreground">Loading...</p>
                </div>
              </div>
            ) : servers.length === 0 ? (
              <div className="relative overflow-hidden rounded-2xl border border-dashed border-border/60 bg-gradient-to-br from-muted/20 to-muted/5">
                <div className="relative flex flex-col items-center justify-center py-16 px-6">
                  <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-muted/60 to-muted/30 flex items-center justify-center mb-5 shadow-inner">
                    <Sparkles className="w-7 h-7 text-muted-foreground/50" />
                  </div>
                  <h3 className="text-base font-semibold text-foreground mb-2">No connectors enabled</h3>
                  <p className="text-sm text-muted-foreground max-w-sm text-center mb-6">
                    Connect to external tools and services to extend your AI's capabilities
                  </p>
                  <Button
                    onClick={() => setActiveSection('browse')}
                    variant="outline"
                    className="text-sm"
                  >
                    Browse Available
                    <ChevronRight className="w-4 h-4 ml-1" />
                  </Button>
                </div>
              </div>
            ) : (
              <CustomServersList
                servers={servers}
                preconfiguredServers={preconfiguredServers}
                onRefresh={() => fetchAllMCPData(true)}
                isLoading={isLoading}
              />
            )}
          </div>
        ) : (
          <PreconfiguredServersList
            onServerConnect={handleConnectPreconfigured}
            connectedServerIds={connectedPreconfiguredIds}
            highlightServerName={search.server ? decodeURIComponent(search.server) : null}
            onAIDiscover={() => setAiDiscoveryDialogOpen(true)}
            initialSearchQuery={search.search ? decodeURIComponent(search.search) : ''}
          />
        )}
      </div>
      </div>

      {/* Mobile Bottom Navigation */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 z-20 bg-background/95 backdrop-blur-xl border-t border-border/50 safe-area-bottom">
        <div className="flex items-center">
          <button
            onClick={() => setActiveSection('browse')}
            className={cn(
              "flex-1 flex flex-col items-center gap-1 py-3 transition-colors",
              activeSection === 'browse'
                ? "text-accent-brand"
                : "text-muted-foreground"
            )}
          >
            <Grid3X3 className="w-5 h-5" />
            <span className="text-xs font-medium">Browse</span>
          </button>
          <button
            onClick={() => setActiveSection('connected')}
            className={cn(
              "relative flex-1 flex flex-col items-center gap-1 py-3 transition-colors",
              activeSection === 'connected'
                ? "text-accent-brand"
                : "text-muted-foreground"
            )}
          >
            <div className="relative">
              <Server className="w-5 h-5" />
              {servers.length > 0 && (
                <span className="absolute -top-1 -right-3 text-[10px] min-w-[16px] h-4 px-1 rounded-full bg-accent-brand text-white font-medium flex items-center justify-center">
                  {servers.length}
                </span>
              )}
            </div>
            <span className="text-xs font-medium">Connected</span>
          </button>
        </div>
      </div>

      {/* Mobile FAB for Add Integration */}
      <button
        onClick={() => {
          setPrefillServerData(null)
          setAddServerDialogOpen(true)
        }}
        className="md:hidden fixed bottom-20 right-4 z-20 w-14 h-14 rounded-full bg-accent-brand text-white shadow-lg shadow-accent-brand/25 flex items-center justify-center active:scale-95 transition-transform safe-area-bottom"
        aria-label="Add Integration"
      >
        <Plus className="w-6 h-6" />
      </button>

      <AddServerDialog
        open={addServerDialogOpen}
        onOpenChange={(open) => {
          setAddServerDialogOpen(open)
          if (!open) {
            setPrefillServerData(null)
            setAutoFetchConfigHelp(false)
          }
        }}
        onServerCreated={() => fetchAllMCPData(true)}
        prefillData={prefillServerData ? {
          name: prefillServerData.name,
          description: prefillServerData.description,
          npm_package: prefillServerData.npm_package,
          remote_url: prefillServerData.remote_url,
          transport_type: prefillServerData.transport_type,
          auth_type: prefillServerData.auth_type,
          icon_url: prefillServerData.icon_url,
          icon_invert_in_dark_mode: prefillServerData.icon_invert_in_dark_mode,
        } : undefined}
        autoFetchConfigHelp={autoFetchConfigHelp}
      />

      <AIDiscoveryDialog
        open={aiDiscoveryDialogOpen}
        onOpenChange={setAiDiscoveryDialogOpen}
        onServerSelected={handleAIDiscoveredServer}
      />
      </div>
    </>
  )
}
