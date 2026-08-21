import { useEffect } from 'react'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { GoogleOAuthProvider } from '@react-oauth/google'
import { routeTree } from './routeTree.gen'

// Create router instance with SPA optimizations
const router = createRouter({
  routeTree,
  // Preload routes on hover/touch for instant navigation
  defaultPreload: 'intent',
  // No delay - start preloading immediately on hover
  defaultPreloadDelay: 0,
})

// Register router for type safety
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

// Google OAuth Client ID from environment variable
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

function App() {
  // Hide splash screen after app loads
  useEffect(() => {
    // Mark app as loaded for this session (prevents splash on navigation/HMR)
    sessionStorage.setItem('sterna-loaded', 'true')

    // Wait for initial animations to complete, then start fade out
    const timer = setTimeout(() => {
      const splash = document.getElementById('splash-screen')
      if (splash && splash.style.display !== 'none') {
        splash.classList.add('fade-out')
        // Remove from DOM after fade out animation completes
        setTimeout(() => {
          splash.remove()
        }, 600)
      }
    }, 1000)

    return () => clearTimeout(timer)
  }, [])

  // Only wrap with GoogleOAuthProvider if client ID is configured
  if (GOOGLE_CLIENT_ID) {
    return (
      <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
        <RouterProvider router={router} />
      </GoogleOAuthProvider>
    )
  }

  // Fallback without Google OAuth if not configured
  return <RouterProvider router={router} />
}

export default App