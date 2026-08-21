import { useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import type { NavigationItem } from '@/store/navigationStore'

/**
 * Registers global Cmd/Ctrl+Shift+1-8 shortcuts that navigate
 * to the corresponding ordered sidebar item.
 */
export function useNavigationShortcuts(orderedNavigation: NavigationItem[]) {
  const navigate = useNavigate()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || !e.shiftKey) return

      const digit = parseInt(e.key, 10)
      if (isNaN(digit) || digit < 1 || digit > 8) return

      // Skip if focus is in an input-like element
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if ((e.target as HTMLElement)?.isContentEditable) return

      const item = orderedNavigation[digit - 1]
      if (!item || item.comingSoon) return

      e.preventDefault()

      const [path, qs] = item.href.split('?')
      const search: Record<string, string | boolean> = {}
      if (qs) {
        new URLSearchParams(qs).forEach((v, k) => {
          search[k] = v === 'true' ? true : v === 'false' ? false : v
        })
      }

      navigate({ to: path, search })
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [orderedNavigation, navigate])
}
