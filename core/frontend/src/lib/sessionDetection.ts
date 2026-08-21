/**
 * Detects if the user had a previous authenticated session.
 * This helps distinguish between:
 * - Session expired (user was logged in before)
 * - No account (new user who never logged in)
 *
 * @returns true if evidence of a previous session exists
 */
export function hadPreviousSession(): boolean {
  try {
    // Check for auth tokens in localStorage
    const hasAccessToken = localStorage.getItem('access_token') !== null
    const hasRefreshToken = localStorage.getItem('refresh_token') !== null

    if (hasAccessToken || hasRefreshToken) {
      
      return true
    }

    // Check for persisted auth storage
    const authStorage = localStorage.getItem('auth-storage')
    if (authStorage) {
      try {
        const parsed = JSON.parse(authStorage)
        // If auth storage exists and has state with user data, it indicates previous login
        if (parsed?.state?.user) {
          
          return true
        }
      } catch (e) {
        console.warn('[SessionDetection] Failed to parse auth-storage:', e)
      }
    }

    // Check for user-scoped storage keys (these are created on login)
    // Pattern: model-storage-{userId}, navigation-storage-{userId}, etc.
    const storageKeys = Object.keys(localStorage)
    const hasUserScopedKeys = storageKeys.some(
      key =>
        key.startsWith('model-storage-') ||
        key.startsWith('navigation-storage-') ||
        key.startsWith('onboarding-storage-') ||
        key.startsWith('ui-storage-')
    )

    if (hasUserScopedKeys) {
      
      return true
    }

    // Check for project storage (created after login)
    const hasProjectStorage = localStorage.getItem('project-storage') !== null
    const hasCurrentProjectId = localStorage.getItem('current_project_id') !== null

    if (hasProjectStorage || hasCurrentProjectId) {
      
      return true
    }

    
    return false
  } catch (error) {
    console.error('[SessionDetection] Error checking session:', error)
    // Default to showing session expired to be safe
    return true
  }
}

/**
 * Gets the appropriate auth modal variant based on session history
 * @returns 'session-expired' if user had a previous session, 'sign-up-prompt' if new user
 */
export function getAuthModalVariant(): 'session-expired' | 'sign-up-prompt' {
  return hadPreviousSession() ? 'session-expired' : 'sign-up-prompt'
}
