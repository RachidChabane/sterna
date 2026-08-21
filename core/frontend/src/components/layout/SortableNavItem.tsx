import { useMemo } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Link } from '@tanstack/react-router'
import { ArrowBigUp, Command } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from '@/components/ui/tooltip'

function ShortcutBadge({ number, isMac }: { number: number; isMac: boolean }) {
  return (
    <kbd className="inline-flex items-center gap-px rounded border border-border/80 bg-background/60 px-1 py-px shadow-[0_1px_0_0_theme(colors.border)]">
      {!isMac && <span className="text-[9px] font-medium leading-none">Ctrl</span>}
      <ArrowBigUp className="h-2.5 w-2.5" />
      {isMac && <Command className="h-2.5 w-2.5" />}
      <span className="text-[10px] font-semibold leading-none">{number}</span>
    </kbd>
  )
}

interface SortableNavItemProps {
  id: string
  name: string
  href: string
  icon: LucideIcon
  isActive: boolean
  isCollapsed: boolean
  onClick?: () => void
  comingSoon?: boolean
  beta?: boolean
  shortcutNumber?: number
  isMac?: boolean
}

export function SortableNavItem({
  id,
  name,
  href,
  icon: Icon,
  isActive,
  isCollapsed,
  onClick,
  comingSoon,
  beta,
  shortcutNumber,
  isMac = false,
}: SortableNavItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id })

  // Parse href to separate path from search params for TanStack Router
  const { toPath, searchParams } = useMemo(() => {
    const [path, qs] = href.split('?')
    if (!qs) return { toPath: path, searchParams: {} }
    const params: Record<string, string | boolean> = {}
    new URLSearchParams(qs).forEach((v, k) => {
      // Coerce "true"/"false" to booleans so TanStack Router won't JSON-quote them
      params[k] = v === 'true' ? true : v === 'false' ? false : v
    })
    return { toPath: path, searchParams: params }
  }, [href])

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  const content = (
    <>
      <Icon className={cn(
        "h-4 w-4 flex-shrink-0",
        isActive && !comingSoon && "text-accent-brand",
        comingSoon && "opacity-50"
      )} />
      <div className={cn(
        "flex items-center gap-2 flex-1 min-w-0 overflow-hidden transition-all duration-300",
        isCollapsed ? "w-0 opacity-0" : "opacity-100"
      )}>
        <span className="truncate whitespace-nowrap">{name}</span>
        {beta && (
          <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 font-medium text-accent-brand/80 border-accent-brand/30 bg-accent-brand/10 flex-shrink-0">
            Beta
          </Badge>
        )}
        {comingSoon && (
          <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 font-medium text-muted-foreground/70 border-muted-foreground/20 bg-transparent flex-shrink-0">
            Coming Soon
          </Badge>
        )}
        {shortcutNumber != null && !comingSoon && (
          <span className="ml-auto opacity-0 group-hover/item:opacity-60 transition-opacity duration-200 flex-shrink-0">
            <ShortcutBadge number={shortcutNumber} isMac={isMac} />
          </span>
        )}
      </div>
    </>
  )

  // Collapsed state: wrap in Radix Tooltip
  if (isCollapsed) {
    const tooltipLabel = comingSoon ? `${name} (Coming Soon)` : name

    return (
      <div
        ref={setNodeRef}
        style={style}
        className={cn(
          "relative group/item cursor-grab hover:cursor-grab active:cursor-grabbing",
          isDragging && "z-50 opacity-50",
        )}
        {...attributes}
        {...listeners}
      >
        <Tooltip>
          <TooltipTrigger asChild>
            {comingSoon ? (
              <div
                className={cn(
                  "flex items-center rounded-md text-[12.5px] font-medium transition-all duration-300 group cursor-not-allowed",
                  "text-muted-foreground/60",
                  "justify-center p-1.5 w-fit"
                )}
              >
                {content}
              </div>
            ) : (
              <Link
                to={toPath}
                search={searchParams}
                onClick={onClick}
                onPointerDown={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
                className={cn(
                  "relative flex items-center rounded-md text-[12.5px] font-medium transition-all duration-300 group",
                  "justify-center p-1.5 w-fit",
                  isActive
                    ? "bg-accent-brand/10 text-accent-brand before:absolute before:inset-y-1 before:left-0 before:w-[3px] before:rounded-full before:bg-accent-brand"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                {content}
              </Link>
            )}
          </TooltipTrigger>
          <TooltipContent side="right" className="flex items-center gap-2.5">
            <span>{tooltipLabel}</span>
            {shortcutNumber != null && !comingSoon && (
              <ShortcutBadge number={shortcutNumber} isMac={isMac} />
            )}
          </TooltipContent>
        </Tooltip>
      </div>
    )
  }

  // Expanded state
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "relative group/item cursor-grab hover:cursor-grab active:cursor-grabbing",
        isDragging && "z-50 opacity-50",
        "w-full"
      )}
      {...attributes}
      {...listeners}
    >
      {comingSoon ? (
        <div
          className={cn(
            "flex items-center rounded-md text-[12.5px] font-medium transition-all duration-300 group cursor-not-allowed",
            "text-muted-foreground/60",
            "gap-2 px-2.5 py-[7px] w-full"
          )}
        >
          {content}
        </div>
      ) : (
        <Link
          to={toPath}
          search={searchParams}
          onClick={onClick}
          onPointerDown={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
          className={cn(
            "relative flex items-center rounded-md text-[12.5px] font-medium transition-all duration-300 group",
            "gap-2 px-2.5 py-[7px] w-full",
            isActive
              ? "bg-accent-brand/10 text-accent-brand before:absolute before:inset-y-1 before:left-0 before:w-[3px] before:rounded-full before:bg-accent-brand"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          {content}
        </Link>
      )}
    </div>
  )
}
