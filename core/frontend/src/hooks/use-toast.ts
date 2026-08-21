import { useCallback, useMemo } from 'react'
import { toast as sonnerToast } from 'sonner'

interface ToastAction {
  label: string
  onClick: () => void
}

export function useToast() {
  // Memoize the toast function to prevent re-creating it on every render
  const toast = useCallback(({ title, description, variant, action }: {
    title: string
    description?: string
    variant?: 'default' | 'destructive' | 'success' | 'info'
    action?: ToastAction
  }) => {
    if (variant === 'destructive') {
      sonnerToast.error(title, { description, action })
    } else if (variant === 'info') {
      sonnerToast.info(title, { description, action })
    } else if (variant === 'success') {
      sonnerToast.success(title, { description, action })
    } else {
      sonnerToast.success(title, { description, action })
    }
  }, [])

  // Memoize the returned object to maintain stable reference
  return useMemo(() => ({ toast }), [toast])
}

// Direct export for convenience
export const toast = ({ title, description, variant, action }: {
  title: string
  description?: string
  variant?: 'default' | 'destructive' | 'success' | 'info'
  action?: ToastAction
}) => {
  if (variant === 'destructive') {
    sonnerToast.error(title, { description, action })
  } else if (variant === 'info') {
    sonnerToast.info(title, { description, action })
  } else if (variant === 'success') {
    sonnerToast.success(title, { description, action })
  } else {
    sonnerToast.success(title, { description, action })
  }
}