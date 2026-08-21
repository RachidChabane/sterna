import React from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { useCommandPalette } from '@/hooks/useCommandPalette'
import { CommandPaletteItem } from './CommandPaletteItem'
import useCommandPaletteStore from '@/store/commandPaletteStore'
import { useNavigationStore } from '@/store/navigationStore'
import { useUIStore } from '@/store/uiStore'
import type { CommandItem } from './types'
import { cn } from '@/lib/utils'

/**
 * Global Command Palette
 *
 * Accessible via Cmd+K (Mac) or Ctrl+K (Windows/Linux)
 *
 * Features:
 * - Search pages (Models, Chats, etc.)
 * - Search conversations by title
 * - Search models by name/provider
 * - Recent items when empty
 * - Keyboard navigation
 * - Provider-based extensibility
 */
export function GlobalCommandPalette() {
  const navigate = useNavigate()
  const { open, setOpen, query, setQuery, results, loading } = useCommandPalette()
  const { recentItems, addToRecent } = useCommandPaletteStore()
  const { setMobileSidebarOpen } = useNavigationStore()
  const isMobile = useUIStore((state) => state.isMobile)
  const [isKeyboardMode, setIsKeyboardMode] = React.useState(false)

  // Handle open change
  const handleOpenChange = React.useCallback((isOpen: boolean) => {
    setOpen(isOpen)
    if (!isOpen) {
      setMobileSidebarOpen(false)
    }
  }, [setOpen, setMobileSidebarOpen])

  // Close mobile sidebar when command palette opens (handles keyboard shortcut too)
  React.useEffect(() => {
    if (open) {
      setMobileSidebarOpen(false)
    }
  }, [open, setMobileSidebarOpen])

  // Track keyboard vs mouse usage
  React.useEffect(() => {
    if (!open) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        setIsKeyboardMode(true)
      }
    }

    const handleMouseMove = () => {
      setIsKeyboardMode(false)
    }

    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('mousemove', handleMouseMove)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('mousemove', handleMouseMove)
    }
  }, [open])

  // Handle item selection
  const handleSelect = (item: CommandItem) => {
    // Add to recent items
    addToRecent(item)

    // Navigate if it's a page
    if (item.type === 'page') {
      navigate({ to: item.href })
    }

    // Navigate if it's a conversation
    if (item.type === 'conversation') {
      navigate({ to: '/chats' })
    }

    // Navigate if it's a voice room action
    if (item.type === 'action' && item.id.startsWith('voice-room-')) {
      navigate({ to: '/voice-rooms' })
    }

    // Navigate to search page for full-text search action
    if (item.type === 'action' && item.id === 'search-all-conversations') {
      navigate({ to: '/search', search: { q: query } })
    }

    // Navigate if it's an image
    if (item.type === 'image') {
      navigate({ to: '/creations', search: { tab: 'images' } })
    }

    // Navigate if it's a video
    if (item.type === 'video') {
      navigate({ to: '/creations', search: { tab: 'videos' } })
    }

    // Navigate if it's a spark
    if (item.type === 'spark') {
      navigate({ to: '/creations', search: { tab: 'sparks' } })
    }

    // Close palette and mobile sidebar
    handleOpenChange(false)
  }

  // Calculate total items for footer
  const totalItems = results.reduce((sum, group) => sum + group.items.length, 0)

  // Show recent items when query is empty
  const showRecent = !query && recentItems.length > 0 && results.length === 0

  // Common command content used by both desktop and mobile
  const commandContent = (
    <Command shouldFilter={false} className={cn("rounded-lg border-0", isKeyboardMode && "keyboard-mode")}>
      {/* Search Input */}
      <div className="border-b border-border px-3">
        <CommandInput
          placeholder={isMobile ? "Search..." : "Search pages, conversations, models..."}
          value={query}
          onValueChange={setQuery}
          className="border-0 focus:ring-0"
        />
      </div>

      <CommandList className={cn(isMobile ? "max-h-[60vh]" : "max-h-[500px]")}>
        {/* Empty State */}
        <CommandEmpty>
          {loading ? (
            <div className="py-6 text-center">
              <p className="text-sm text-muted-foreground">Searching...</p>
            </div>
          ) : (
            <div className="py-6 text-center">
              <p className="text-sm text-muted-foreground">No results found.</p>
              <p className="text-xs text-muted-foreground mt-1">
                Try a different search term
              </p>
            </div>
          )}
        </CommandEmpty>

        {/* Recent Items */}
        {showRecent && (
          <CommandGroup heading="Recent">
            {recentItems.map((item) => (
              <CommandPaletteItem
                key={item.id}
                item={item}
                query=""
                onSelect={() => handleSelect(item)}
              />
            ))}
          </CommandGroup>
        )}

        {/* Search Results Grouped by Provider */}
        {results.map((group, index) => (
          <div key={group.provider.id}>
            {index > 0 && <CommandSeparator />}
            <CommandGroup heading={group.provider.name}>
              {group.items.map((item) => (
                <CommandPaletteItem
                  key={item.id}
                  item={item}
                  query={query}
                  onSelect={() => handleSelect(item)}
                />
              ))}
            </CommandGroup>
          </div>
        ))}
      </CommandList>

      {/* Footer with keyboard shortcuts - hidden on mobile */}
      {!isMobile && (
        <div className="border-t border-accent-brand/20 px-3 py-2 bg-accent-brand/5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <div className="flex items-center gap-4">
              <span>
                <kbd className="px-1.5 py-0.5 bg-background border border-border rounded text-[10px]">
                  ↑↓
                </kbd>{' '}
                Navigate
              </span>
              <span>
                <kbd className="px-1.5 py-0.5 bg-background border border-border rounded text-[10px]">
                  Enter
                </kbd>{' '}
                Select
              </span>
              <span>
                <kbd className="px-1.5 py-0.5 bg-background border border-border rounded text-[10px]">
                  Esc
                </kbd>{' '}
                Close
              </span>
            </div>
            {totalItems > 0 && (
              <span className="text-[10px] font-medium text-accent-brand bg-accent-brand/10 px-2 py-1 rounded">
                {totalItems} result{totalItems !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Mobile footer - just show result count */}
      {isMobile && totalItems > 0 && (
        <div className="border-t border-accent-brand/20 px-3 py-2 bg-accent-brand/5 flex justify-center">
          <span className="text-[10px] font-medium text-accent-brand bg-accent-brand/10 px-2 py-1 rounded">
            {totalItems} result{totalItems !== 1 ? 's' : ''}
          </span>
        </div>
      )}
    </Command>
  )

  // Keyboard mode styles
  const keyboardStyles = (
    <style>{`
      .keyboard-mode [cmdk-item]:hover {
        background: transparent !important;
        box-shadow: none !important;
      }
      .keyboard-mode [cmdk-item]:hover > * {
        background: transparent !important;
      }
      .keyboard-mode [cmdk-item]:hover .group-hover\\:bg-accent-brand\\/10,
      .keyboard-mode [cmdk-item]:hover .group-hover\\:bg-accent-brand\\/20,
      .keyboard-mode [cmdk-item]:hover .group-hover\\:text-accent-brand {
        background-color: inherit !important;
        color: inherit !important;
      }
      .keyboard-mode [cmdk-item]:hover .bg-muted,
      .keyboard-mode [cmdk-item]:hover .rounded-md {
        background-color: hsl(var(--muted)) !important;
        color: inherit !important;
      }
    `}</style>
  )

  // Mobile: Use bottom sheet
  if (isMobile) {
    return (
      <>
        {keyboardStyles}
        <Sheet open={open} onOpenChange={handleOpenChange}>
          <SheetContent side="bottom" className="p-0 rounded-t-2xl h-[80vh]">
            <SheetTitle className="sr-only">Search</SheetTitle>
            <SheetDescription className="sr-only">
              Search for pages, conversations, models, and more.
            </SheetDescription>
            {/* Drag handle */}
            <div className="flex justify-center pt-3 pb-2">
              <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
            </div>
            {commandContent}
          </SheetContent>
        </Sheet>
      </>
    )
  }

  // Desktop: Use dialog
  return (
    <>
      {keyboardStyles}
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="max-w-2xl p-0 gap-0 overflow-hidden">
          <DialogTitle className="sr-only">Command Palette</DialogTitle>
          <DialogDescription className="sr-only">
            Search for pages, conversations, models, and more. Use arrow keys to navigate and Enter to select.
          </DialogDescription>
          {commandContent}
        </DialogContent>
      </Dialog>
    </>
  )
}
