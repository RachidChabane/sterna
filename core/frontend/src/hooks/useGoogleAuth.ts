import { useGoogleLogin, useGoogleOneTapLogin } from '@react-oauth/google'
import { useAuthStore } from '@/store/authStore'
import { useNavigate } from '@tanstack/react-router'
import { useToast } from '@/hooks/use-toast'
import apiClient, { setTokens } from '@/api/client'
import { migrateToUserScopedStorage, cleanupLegacyStorage } from '@/lib/userScopedStorage'

interface GoogleAuthResponse {
  access: string
  refresh: string
  user: any
  created: boolean
  message: string
}

export function useGoogleAuth() {
  const { toast } = useToast()
  const navigate = useNavigate()
  const setUser = useAuthStore((state) => state.setUser)

  const handleGoogleSuccess = async (credential: string) => {
    try {
      // Send the Google credential to our backend
      const response = await apiClient.post<GoogleAuthResponse>('/auth/google/', {
        credential
      })

      const data = response.data

      // Store tokens (backend returns 'access' / 'refresh' - see authentication/oauth_views.py)
      setTokens(data.access, data.refresh)

      // Migrate old non-scoped storage to user-scoped storage
      if (data.user?.id) {
        const storeNames = ['model-storage', 'navigation-storage', 'onboarding-storage', 'ui-storage', 'settings-storage']

        // Migrate any existing data from old keys to user-scoped keys
        migrateToUserScopedStorage(data.user.id, storeNames)

        // Clean up legacy non-scoped keys after migration
        cleanupLegacyStorage(storeNames)
      }

      // Update auth store
      setUser(data.user)

      // Rehydrate user-scoped stores now that user is authenticated
      // This ensures settings (code theme, etc.) are loaded from user-scoped localStorage
      import('@/store/modelStore').then(({ default: useModelStore }) => {
        useModelStore.persist.rehydrate()
      })
      import('@/store/settingsStore').then(({ useSettingsStore }) => {
        useSettingsStore.persist.rehydrate()
      })

      // Load preferences from backend after successful login
      // This runs async in background - don't await to avoid blocking login
      import('@/hooks/usePreferencesLoader').then(({ loadPreferencesFromBackend }) => {
        loadPreferencesFromBackend().catch((err) => {
          console.error('[GoogleAuth] Failed to load preferences after login:', err)
        })
      })

      // Show success message
      toast({
        title: data.created ? 'Account created!' : 'Welcome back!',
        description: data.message,
      })

      // Navigate to return URL or home
      const searchParams = new URLSearchParams(window.location.search)
      const returnUrl = searchParams.get('from') || '/voice-rooms'
      // Ensure returnUrl is a valid internal path
      if (typeof returnUrl === 'string' && returnUrl.startsWith('/')) {
        navigate({ to: returnUrl })
      } else {
        navigate({ to: '/voice-rooms' })
      }

    } catch (error: any) {
      console.error('Google auth error:', error)
      toast({
        title: 'Authentication failed',
        description: error.response?.data?.error || 'Could not authenticate with Google. Please try again.',
        variant: 'destructive',
      })
    }
  }

  // Google One Tap login
  useGoogleOneTapLogin({
    onSuccess: (credentialResponse) => {
      if (credentialResponse.credential) {
        handleGoogleSuccess(credentialResponse.credential)
      }
    },
    onError: () => {
      
    },
    // Only show One Tap if user is not already logged in
    auto_select: false,
    cancel_on_tap_outside: true,
  })

  // Standard Google login (for button click)
  const googleLogin = useGoogleLogin({
    flow: 'implicit',
    onSuccess: async (tokenResponse) => {
      // For implicit flow, we get an access_token
      // We need to get user info first, then send to backend
      try {
        // Get user info from Google
        const userInfoResponse = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
          headers: {
            'Authorization': `Bearer ${tokenResponse.access_token}`,
          },
        })

        const userInfo = await userInfoResponse.json()

        // Create a credential-like object for our backend
        // Note: This is a workaround since we're using implicit flow
        // In production, consider using authorization code flow
        const credential = tokenResponse.access_token

        await handleGoogleSuccess(credential)
      } catch (error) {
        console.error('Failed to get user info:', error)
        toast({
          title: 'Authentication failed',
          description: 'Could not retrieve user information from Google.',
          variant: 'destructive',
        })
      }
    },
    onError: (error) => {
      console.error('Google login error:', error)
      toast({
        title: 'Google login failed',
        description: 'Please try again or use email/password login.',
        variant: 'destructive',
      })
    }
  })

  return {
    googleLogin,
    handleGoogleSuccess
  }
}

// Alternative: Direct credential response handler for Google Sign-In button
export function useGoogleCredentialResponse() {
  const { handleGoogleSuccess } = useGoogleAuth()

  return {
    handleCredentialResponse: (response: any) => {
      if (response.credential) {
        handleGoogleSuccess(response.credential)
      }
    }
  }
}