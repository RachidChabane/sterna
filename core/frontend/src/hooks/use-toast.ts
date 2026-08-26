import { useCallback, useMemo } from 'react'
import { toast as sonnerToast } from 'sonner'

interface ToastAction {
  label: string
  onClick: () => void
}

interface ToastOptions {
  title: string
  description?: string
  variant?: 'default' | 'destructive' | 'success' | 'info'
  action?: ToastAction
  duration?: number
}

function showToast({ title, description, variant, action, duration }: ToastOptions) {
  if (variant === 'destructive') {
    sonnerToast.error(title, { description, action, duration })
  } else if (variant === 'info') {
    sonnerToast.info(title, { description, action, duration })
  } else if (variant === 'success') {
    sonnerToast.success(title, { description, action, duration })
  } else {
    sonnerToast.success(title, { description, action, duration })
  }
}

export function useToast() {
  // Memoize the toast function to prevent re-creating it on every render
  const toast = useCallback(showToast, [])

  // Memoize the returned object to maintain stable reference
  return useMemo(() => ({ toast }), [toast])
}

// Direct export for convenience
export const toast = showToast