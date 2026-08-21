import { Search } from 'lucide-react'
import { useOS } from '@/hooks/useOS'
import useCommandPaletteStore from '@/store/commandPaletteStore'
import { cn } from '@/lib/utils'

interface CommandPaletteSearchBarProps {
  /**
   * Whether the sidebar is in collapsed state
   */
  isCollapsed?: boolean

  /**
   * Additional className for the container
   */
  className?: string
}

/**
 * Command Palette Search Bar
 *
 * A prominent, modern search bar component that triggers the command palette.
 * Displays a search icon, placeholder text, and keyboard shortcut badge.
 *
 * Features:
 * - Full-width clickable button styled as a search input
 * - Responsive design for collapsed sidebar
 * - Platform-aware keyboard shortcut (⌘K for Mac, Ctrl+K for others)
 * - Interactive hover and focus states
 */
export function CommandPaletteSearchBar({
  isCollapsed = false,
  className
}: CommandPaletteSearchBarProps) {
  const { setOpen } = useCommandPaletteStore()
  const { isMac } = useOS()

  const handleClick = () => {
    setOpen(true)
  }

  return (
    <button
      onClick={handleClick}
      className={cn(
        "group flex items-center transition-all duration-300 overflow-hidden",
        isCollapsed
          ? "justify-center p-2 rounded-md hover:bg-muted hover:text-accent-brand"
          : "w-full gap-3 px-3 py-2.5 rounded-lg bg-secondary/20 border border-border/50 hover:border-accent-brand/60 cursor-text justify-between focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        className
      )}
      aria-label="Open command palette"
    >
      {/* Search Icon - always visible, centered when collapsed */}
      <Search className={cn(
        "flex-shrink-0 text-accent-brand/80 group-hover:text-accent-brand transition-all duration-300",
        isCollapsed ? "h-[18px] w-[18px]" : "h-4 w-4"
      )} />

      {/* Expanded content - hidden when collapsed */}
      {!isCollapsed && (
        <div className="flex items-center justify-between flex-1 min-w-0 overflow-hidden gap-3">
        {/* Placeholder text */}
        <span className="text-sm text-muted-foreground/60 group-hover:text-muted-foreground transition-colors duration-300 truncate whitespace-nowrap">
          Search...
        </span>

        {/* Keyboard Shortcut Badge - hidden on mobile */}
        <div className={cn(
          "hidden md:flex items-center gap-1 px-2 py-0.5 rounded",
          "bg-muted/20 text-muted-foreground/70 border border-muted/30",
          "group-hover:bg-muted/30 group-hover:text-muted-foreground group-hover:border-accent-brand/30",
          "transition-all duration-300 ease-out",
          "font-medium text-[11px] flex-shrink-0 whitespace-nowrap"
        )}>
          <span>
            {isMac ? '⌘K' : 'Ctrl+K'}
          </span>
        </div>
        </div>
      )}
    </button>
  )
}
