import { useRouterState } from '@tanstack/react-router'
import { useEffect } from 'react'
import { useAuthStore } from '@/store/authStore'
import { useAuthModalStore } from '@/store/authModalStore'
import { getAuthModalVariant } from '@/lib/sessionDetection'
import { Loader2 } from 'lucide-react'

interface ProtectedRouteProps {
  children: React.ReactNode
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuthStore()
  const { openModal, isRedirecting } = useAuthModalStore()
  const router = useRouterState()
  // `location.href` is the already-stringified pathname + search + hash.
  // `location.search` is a parsed, null-prototype object (TanStack Router's
  // qss decoder) — concatenating it directly (`pathname + search`) throws
  // "Cannot convert object to primitive value" because it has no toString.
  const returnUrl = router.location.href

  // If not authenticated, open auth modal (unless we're redirecting)
  // NOTE: This hook must be called unconditionally (before any early returns)
  // to comply with React's Rules of Hooks
  useEffect(() => {
    if (!isLoading && !isAuthenticated && !isRedirecting) {
      const variant = getAuthModalVariant()

      openModal(variant, returnUrl)
    }
  }, [isAuthenticated, isLoading, isRedirecting, returnUrl, openModal])

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-violet-600" />
      </div>
    )
  }

  // If not authenticated, show loading while modal is open
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-accent-brand" />
      </div>
    )
  }

  // User is authenticated, render children
  return <>{children}</>
}
