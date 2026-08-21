import { useEffect, useState, useCallback, useRef } from 'react'
import { commandRegistry } from '@/components/command-palette/providers'
import useCommandPaletteStore from '@/store/commandPaletteStore'
import type { GroupedCommandItems } from '@/components/command-palette/types'

const DEBOUNCE_DELAY = 150 // ms

/**
 * Command Palette Hook
 *
 * Manages global command palette state, keyboard shortcuts, and debounced search
 */
export function useCommandPalette() {
  const { open, query, setOpen, setQuery } = useCommandPaletteStore()
  const [results, setResults] = useState<GroupedCommandItems[]>([])
  const [loading, setLoading] = useState(false)
  const searchTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined)
  const searchIdRef = useRef(0)

  // Handle keyboard shortcut: Cmd+K (Mac) or Ctrl+K (Windows/Linux)
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen(!open)
      }
    }

    document.addEventListener('keydown', down)
    return () => document.removeEventListener('keydown', down)
  }, [open, setOpen])

  // Debounced search
  const performSearch = useCallback(
    async (searchQuery: string, searchId: number) => {
      try {
        setLoading(true)
        const searchResults = await commandRegistry.search(searchQuery)

        // Only update if this is still the latest search
        if (searchId === searchIdRef.current) {
          setResults(searchResults)
        }
      } catch (error) {
        console.error('[useCommandPalette] Search error:', error)
        if (searchId === searchIdRef.current) {
          setResults([])
        }
      } finally {
        if (searchId === searchIdRef.current) {
          setLoading(false)
        }
      }
    },
    []
  )

  // Trigger search when query changes
  useEffect(() => {
    // Clear previous timeout
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }

    // Don't search if palette is closed
    if (!open) {
      setResults([])
      setLoading(false)
      return
    }

    // Increment search ID to invalidate previous searches
    searchIdRef.current += 1
    const currentSearchId = searchIdRef.current

    // Debounce search
    searchTimeoutRef.current = setTimeout(() => {
      performSearch(query, currentSearchId)
    }, DEBOUNCE_DELAY)

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [query, open, performSearch])

  // Clear query when closing
  useEffect(() => {
    if (!open) {
      setQuery('')
    }
  }, [open, setQuery])

  return {
    open,
    setOpen,
    query,
    setQuery,
    results,
    loading,
  }
}
