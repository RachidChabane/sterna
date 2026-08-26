/**
 * Unified OAuth Callback Router
 *
 * Handles OAuth callbacks for:
 * 1. User authentication (normal flow)
 * 2. MCP server OAuth (state prefixed with "mcp:")
 * 3. Code feature GitHub connection (state prefixed with "code:")
 *
 * GitHub OAuth App Configuration:
 * - Callback URL: http://localhost:5173/oauth/callback
 * - Same app used for all flows
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'
import { Loader2 } from 'lucide-react'
import { authApi } from '@/api/endpoints'
import apiClient, { setTokens } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { SternaLogo } from '@/components/icons/SternaLogo'

export const Route = createFileRoute('/oauth/callback')({
  component: OAuthCallback,
})

// Track last processed callback to prevent double execution in React Strict Mode
// Uses URL + timestamp to allow re-processing on new OAuth flows
let lastProcessedCallback: { url: string; time: number } | null = null
const CALLBACK_DEBOUNCE_MS = 2000 // 2 seconds debounce

function OAuthCallback() {
  const navigate = useNavigate()

  useEffect(() => {
    const componentMountTime = performance.now()
    const mountTimestamp = new Date().toISOString()
    

    // Prevent double execution in React Strict Mode using URL + time-based debounce
    const currentUrl = window.location.href
    const now = Date.now()
    if (lastProcessedCallback &&
        lastProcessedCallback.url === currentUrl &&
        now - lastProcessedCallback.time < CALLBACK_DEBOUNCE_MS) {
      
      return
    }
    lastProcessedCallback = { url: currentUrl, time: now }
    

    // Parse URL search params
    const urlParams = new URLSearchParams(window.location.search)
    const code = urlParams.get('code')
    const state = urlParams.get('state')
    const error = urlParams.get('error')

    // Handle OAuth errors
    if (error) {
      console.error('OAuth error:', error)
      const errorDescription = urlParams.get('error_description')
      navigate({
        to: '/login',
        search: {
          error,
          message: errorDescription || 'OAuth failed'
        }
      })
      return
    }

    // Validate required parameters
    if (!code || !state) {
      console.error('Missing code or state parameter')
      navigate({
        to: '/login',
        search: { error: 'missing_params' }
      })
      return
    }

    // Route based on state parameter
    if (state.startsWith('mcp:')) {
      // MCP Server OAuth Flow
      handleMCPCallback(code, state)
    } else if (state.startsWith('code:')) {
      // Code Feature GitHub Connection Flow
      handleCodeCallback(code, state)
    } else {
      // Authentication Flow
      handleAuthCallback(code, state)
    }
  }, [navigate])

  /**
   * Handle MCP server OAuth callback
   * Redirects to backend MCP callback handler
   */
  const handleMCPCallback = (code: string, state: string) => {
    
    
    
    

    // Redirect to backend MCP callback handler
    // The backend will:
    // 1. Validate the state
    // 2. Exchange code for token
    // 3. Store OAuth tokens in MCPServer
    // 4. Auto-discover tools
    // 5. Redirect to /connectors?success=connected

    // IMPORTANT: Must use full backend URL, not relative path
    // Relative paths don't go through Vite proxy when using window.location.href
    // Dev: VITE_BACKEND_URL = http://localhost:8000
    // Prod: VITE_BACKEND_URL = empty (uses same origin as frontend)
    const backendUrl = import.meta.env.VITE_BACKEND_URL || window.location.origin
    const callbackUrl = `${backendUrl}/api/mcp/connections/github/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`

    
    

    // Use setTimeout + replace for more reliable redirect
    // This ensures the redirect happens after React's render cycle completes
    // and won't be interrupted by component unmounting
    setTimeout(() => {
      
      try {
        window.location.replace(callbackUrl)
      } catch (error) {
        console.error('[OAuth] Redirect failed:', error)
        // Fallback to href if replace fails
        window.location.href = callbackUrl
      }
    }, 100)
  }

  /**
   * Handle Code Feature GitHub connection callback
   * Connects GitHub account for repository access in Code feature
   */
  const handleCodeCallback = async (code: string, state: string) => {
    
    

    // Verify state to prevent CSRF
    const storedState = sessionStorage.getItem('github_oauth_state')
    

    if (state !== storedState) {
      console.error('[OAuth] State mismatch for Code feature!')
      navigate({
        to: '/chats',
        search: { error: 'invalid_state' }
      })
      return
    }

    // Get return URL
    const returnUrl = sessionStorage.getItem('github_auth_return_url') || '/chats'

    // Clean up session storage
    sessionStorage.removeItem('github_oauth_state')
    sessionStorage.removeItem('github_auth_return_url')

    try {
      // Call Code feature's backend callback
      await apiClient.get('/code-sessions/github/callback/', {
        params: { code, state },
      })

      // Redirect to Code page
      navigate({ to: returnUrl as any })

    } catch (error: any) {
      console.error('[OAuth] Code feature GitHub connection failed:', error)
      navigate({
        to: '/chats',
        search: { error: 'github_connect_failed' }
      })
    }
  }

  /**
   * Handle authentication OAuth callback
   * Exchanges code for JWT token directly
   */
  const handleAuthCallback = async (code: string, state: string) => {
    const startTime = performance.now()
    const timestamp = new Date().toISOString()
    
    
    
    
    

    // Verify state to prevent CSRF
    const storedState = sessionStorage.getItem('github_oauth_state')
    
    
    

    if (state !== storedState) {
      console.error('[OAuth] State mismatch!')
      console.error('[OAuth] Expected:', storedState)
      console.error('[OAuth] Received:', state)
      console.error('[OAuth] sessionStorage contents:', {
        state: sessionStorage.getItem('github_oauth_state'),
        returnUrl: sessionStorage.getItem('github_auth_return_url')
      })
      navigate({
        to: '/login',
        search: {
          error: 'invalid_state',
          message: 'Security validation failed. Please try again.'
        }
      })
      return
    }

    // Get return URL from sessionStorage (set by AuthModal)
    const returnUrl = sessionStorage.getItem('github_auth_return_url') || '/chats'

    // Clean up session storage
    sessionStorage.removeItem('github_oauth_state')
    sessionStorage.removeItem('github_auth_return_url')
    

    try {
      // Exchange code for tokens via backend.
      // `state` is the backend-issued nonce (task 19) — the backend
      // validates it against Redis and consumes it.
      const apiCallStart = performance.now()
      const response = await authApi.githubAuth(code, state)
      
      const data = response.data

      // Store tokens (normalize key names)
      const accessTokenValue = data.access || data.access_token
      const refreshTokenValue = data.refresh || data.refresh_token
      if (!accessTokenValue || !refreshTokenValue) {
        // Without this guard we would persist the string "undefined" in
        // localStorage; fail into the existing catch → /login?error=auth_failed
        throw new Error('OAuth token exchange returned no tokens')
      }
      setTokens(accessTokenValue, refreshTokenValue)

      // Update auth store
      useAuthStore.setState({
        user: data.user,
        isAuthenticated: true,
      })

      
      
      

      // Redirect to return URL or home
      if (typeof returnUrl === 'string' && returnUrl.startsWith('/')) {
        navigate({ to: returnUrl })
      } else {
        navigate({ to: '/chats' })
      }

    } catch (error: any) {
      console.error('[OAuth] Authentication callback failed!')
      console.error('[OAuth] Total time elapsed:', (performance.now() - startTime).toFixed(2), 'ms')
      console.error('[OAuth] Error details:', error)
      navigate({
        to: '/login',
        search: {
          error: 'auth_failed',
          message: error.response?.data?.error || 'Authentication failed. Please try again.'
        }
      })
    }
  }

  return (
    <div className="flex items-center justify-center min-h-dvh bg-background p-6">
      <div className="text-center max-w-sm">
        <div className="flex justify-center mb-6">
          <SternaLogo size={40} className="text-accent-brand" />
        </div>
        <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-accent-brand" />
        <h2 className="text-lg font-medium mb-2 text-foreground">Processing sign-in…</h2>
        <p className="text-sm text-muted-foreground">
          Please wait while we complete the authorization.
        </p>
      </div>
    </div>
  )
}
