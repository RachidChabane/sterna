/**
 * ProcessSection Component
 *
 * A unified, responsive component for displaying collapsible process sections
 * (View process, Web Results, etc.) with consistent styling.
 *
 * - Desktop: Expands inline with smooth animation
 * - Mobile: Opens as a bottom sheet for better touch UX
 */

import { useState, useCallback, type ReactNode } from 'react'
import { ChevronRight, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/store/uiStore'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ScrollArea } from '@/components/ui/scroll-area'

interface ProcessSectionProps {
  /** Icon component to display */
  icon: ReactNode
  /** Section title (e.g., "View process", "Web Results") */
  title: string
  /** Badge content (e.g., "3 steps", count number) */
  badge?: string | number
  /** Optional secondary badge (e.g., "2 failed") */
  secondaryBadge?: { text: string; variant: 'default' | 'error' | 'warning' }
  /** Whether to show loading spinner */
  isLoading?: boolean
  /** Loading text override */
  loadingText?: string
  /** Content to render when expanded */
  children: ReactNode
  /** Optional description for sheet header on mobile */
  description?: string
  /** Additional action button on the right */
  action?: ReactNode
  /** Default expanded state (desktop only) */
  defaultExpanded?: boolean
  /** Controlled expanded state */
  expanded?: boolean
  /** Callback when expanded state changes */
  onExpandedChange?: (expanded: boolean) => void
  /** Custom class name for the container */
  className?: string
  /** Accent color variant */
  variant?: 'teal' | 'blue' | 'purple' | 'amber'
}

const variantStyles = {
  teal: {
    border: 'border-accent-brand/40',
    iconColor: 'text-accent-brand/70',
    badgeBg: 'bg-accent-brand/10',
    badgeText: 'text-accent-brand',
    hoverBg: 'hover:bg-accent-brand/5',
    chevronHover: 'group-hover/section:text-accent-brand',
    sheetAccent: 'border-t-accent-brand',
  },
  blue: {
    border: 'border-blue-500/40',
    iconColor: 'text-blue-500/70',
    badgeBg: 'bg-blue-500/10',
    badgeText: 'text-blue-500',
    hoverBg: 'hover:bg-blue-500/5',
    chevronHover: 'group-hover/section:text-blue-500',
    sheetAccent: 'border-t-blue-500',
  },
  purple: {
    border: 'border-purple-500/40',
    iconColor: 'text-purple-500/70',
    badgeBg: 'bg-purple-500/10',
    badgeText: 'text-purple-500',
    hoverBg: 'hover:bg-purple-500/5',
    chevronHover: 'group-hover/section:text-purple-500',
    sheetAccent: 'border-t-purple-500',
  },
  amber: {
    border: 'border-amber-500/40',
    iconColor: 'text-amber-500/70',
    badgeBg: 'bg-amber-500/10',
    badgeText: 'text-amber-500',
    hoverBg: 'hover:bg-amber-500/5',
    chevronHover: 'group-hover/section:text-amber-500',
    sheetAccent: 'border-t-amber-500',
  },
}

export function ProcessSection({
  icon,
  title,
  badge,
  secondaryBadge,
  isLoading,
  loadingText,
  children,
  description,
  action,
  defaultExpanded = false,
  expanded: controlledExpanded,
  onExpandedChange,
  className,
  variant = 'teal',
}: ProcessSectionProps) {
  const isMobile = useUIStore((state) => state.isMobile)
  const [internalExpanded, setInternalExpanded] = useState(defaultExpanded)
  const [sheetOpen, setSheetOpen] = useState(false)

  const isExpanded = controlledExpanded ?? internalExpanded
  const styles = variantStyles[variant]

  const handleToggle = useCallback(() => {
    if (isMobile) {
      setSheetOpen(true)
    } else {
      const newExpanded = !isExpanded
      setInternalExpanded(newExpanded)
      onExpandedChange?.(newExpanded)
    }
  }, [isMobile, isExpanded, onExpandedChange])

  const handleSheetClose = useCallback(() => {
    setSheetOpen(false)
  }, [])

  // Shared trigger content
  const TriggerContent = (
    <div
      className={cn(
        'flex items-center gap-2 px-2.5 py-2 transition-colors cursor-pointer group/section rounded-md',
        styles.hoverBg,
        className
      )}
      onClick={handleToggle}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          handleToggle()
        }
      }}
    >
      {/* Chevron - rotates on desktop when expanded */}
      <ChevronRight
        className={cn(
          'w-3.5 h-3.5 flex-shrink-0 text-muted-foreground transition-transform duration-200',
          styles.chevronHover,
          !isMobile && isExpanded && 'rotate-90'
        )}
      />

      {/* Icon */}
      <div className={cn('flex-shrink-0', styles.iconColor)}>
        {icon}
      </div>

      {/* Title */}
      <span
        className={cn(
          'text-xs font-medium text-foreground/90 truncate',
          isLoading && 'animate-pulse'
        )}
      >
        {isLoading ? (loadingText || title) : title}
      </span>

      {/* Primary badge */}
      {badge !== undefined && (
        <span
          className={cn(
            'flex-shrink-0 text-xs px-1.5 py-0.5 rounded-full font-medium',
            styles.badgeBg,
            styles.badgeText
          )}
        >
          {badge}
        </span>
      )}

      {/* Secondary badge (e.g., errors) */}
      {secondaryBadge && (
        <span
          className={cn(
            'flex-shrink-0 text-xs px-1.5 py-0.5 rounded-full font-medium',
            secondaryBadge.variant === 'error' && 'bg-red-500/10 text-red-400',
            secondaryBadge.variant === 'warning' && 'bg-amber-500/10 text-amber-400',
            secondaryBadge.variant === 'default' && 'bg-muted text-muted-foreground'
          )}
        >
          {secondaryBadge.text}
        </span>
      )}

      {/* Loading spinner */}
      {isLoading && (
        <div
          className={cn(
            'w-3 h-3 border-2 border-current/30 border-t-current rounded-full animate-spin flex-shrink-0',
            styles.badgeText
          )}
        />
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Action button */}
      {action && (
        <div onClick={(e) => e.stopPropagation()}>
          {action}
        </div>
      )}
    </div>
  )

  // Desktop: Inline collapsible
  if (!isMobile) {
    return (
      <div className={cn('border-l-2 rounded-r overflow-hidden', styles.border)}>
        <Collapsible open={isExpanded} onOpenChange={(open) => {
          setInternalExpanded(open)
          onExpandedChange?.(open)
        }}>
          <CollapsibleTrigger asChild>
            {TriggerContent}
          </CollapsibleTrigger>
          <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
            <div className="px-2.5 pb-2.5">
              <div className="border border-border/40 rounded-lg bg-background/30 overflow-hidden">
                <div className="p-3">
                  {children}
                </div>
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </div>
    )
  }

  // Mobile: Bottom sheet
  return (
    <>
      <div className={cn('border-l-2 rounded-r overflow-hidden', styles.border)}>
        {TriggerContent}
      </div>

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent
          side="bottom"
          className={cn(
            'h-[85vh] rounded-t-2xl border-t-2 p-0',
            styles.sheetAccent
          )}
        >
          {/* Drag handle */}
          <div className="flex justify-center pt-3 pb-2">
            <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
          </div>

          <SheetHeader className="px-4 pb-3 border-b border-border">
            <div className="flex items-center gap-2">
              <div className={styles.iconColor}>{icon}</div>
              <SheetTitle className="text-base">{title}</SheetTitle>
              {badge !== undefined && (
                <span
                  className={cn(
                    'text-xs px-2 py-0.5 rounded-full font-medium',
                    styles.badgeBg,
                    styles.badgeText
                  )}
                >
                  {badge}
                </span>
              )}
            </div>
            {description && (
              <SheetDescription>{description}</SheetDescription>
            )}
          </SheetHeader>

          <ScrollArea className="flex-1 h-[calc(85vh-80px)]">
            <div className="p-4">
              {children}
            </div>
          </ScrollArea>
        </SheetContent>
      </Sheet>
    </>
  )
}
