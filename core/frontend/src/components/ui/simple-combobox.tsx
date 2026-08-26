import * as React from "react"
import { Check, ChevronDown, Search, Star, Filter } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Collapsible, CollapsibleContent } from "@/components/ui/collapsible"
import { ModelDetailsPopover } from "@/components/models/ModelDetailsPopover"
import type { Model } from "@/api/llm"

export interface SimpleComboboxOption {
  value: string
  label: string
  group?: string
  description?: string
  metadata?: Model
  isFavorite?: boolean
  icon?: React.ReactNode
  groupIcon?: React.ReactNode
}

interface SimpleComboboxProps {
  options: SimpleComboboxOption[]
  value?: string
  onValueChange?: (value: string) => void
  onToggleFavorite?: (value: string, isFavorite: boolean) => void
  placeholder?: string
  searchPlaceholder?: string
  emptyMessage?: string
  className?: string
  disabled?: boolean
  showFilters?: boolean
  onToggleFilters?: () => void
  hasActiveFilters?: boolean
  filterContent?: React.ReactNode
  side?: "top" | "right" | "bottom" | "left"
  sideOffset?: number
  recentModelIds?: string[]
  /** Compact mode - show only icon in trigger button */
  compact?: boolean
  /** Hide the chevron icon in the trigger button */
  hideChevron?: boolean
  /** Button variant for the trigger */
  variant?: "default" | "outline" | "ghost" | "secondary"
}

// Memoize to prevent re-rendering when parent updates but props haven't changed
// Critical: prevents expensive renderOption calls for all options
export const SimpleCombobox = React.memo(function SimpleCombobox({
  options,
  value,
  onValueChange,
  onToggleFavorite,
  placeholder = "Select option...",
  searchPlaceholder = "Search...",
  emptyMessage = "No results found.",
  className,
  disabled = false,
  showFilters = false,
  onToggleFilters,
  hasActiveFilters = false,
  filterContent,
  side = "bottom",
  sideOffset = 4,
  recentModelIds = [],
  compact = false,
  hideChevron = false,
  variant = "outline",
}: SimpleComboboxProps) {
  const [open, setOpen] = React.useState(false)
  const [search, setSearch] = React.useState("")
  const [hoveredOptionValue, setHoveredOptionValue] = React.useState<string | null>(null)
  const [isMobile, setIsMobile] = React.useState(false)

  // Detect mobile via media query
  React.useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 768px)')
    setIsMobile(mediaQuery.matches)

    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  // Reset hover state when popover closes
  React.useEffect(() => {
    if (!open) {
      setHoveredOptionValue(null)
    }
  }, [open])

  // Filter options based on search
  // CRITICAL: Only calculate when dropdown is open to avoid blocking main thread during typing
  const filteredOptions = React.useMemo(() => {
    // Skip expensive calculation if dropdown is closed
    if (!open) return []

    if (!search) return options

    const searchLower = search.toLowerCase()
    return options.filter(option =>
      option.label.toLowerCase().includes(searchLower) ||
      (option.group && option.group.toLowerCase().includes(searchLower)) ||
      (option.description && option.description.toLowerCase().includes(searchLower))
    )
  }, [options, search, open])

  // Group filtered options with recent and favorites
  // CRITICAL: Only calculate when dropdown is open to avoid blocking main thread during typing
  const groupedOptions = React.useMemo(() => {
    // Skip expensive calculation if dropdown is closed
    if (!open) return { groups: {}, ungrouped: [], favorites: [], recent: [] }

    const groups: Record<string, SimpleComboboxOption[]> = {}
    const ungrouped: SimpleComboboxOption[] = []
    const favorites: SimpleComboboxOption[] = []
    const recent: SimpleComboboxOption[] = []

    filteredOptions.forEach((option) => {
      // Separate recent models first - they ONLY go in recent section
      if (recentModelIds.includes(option.value)) {
        recent.push(option)
      } else if (option.isFavorite) {
        // Separate favorites - they ONLY go in favorites section
        favorites.push(option)
      } else {
        // Only add to regular groups if NOT a favorite or recent
        if (option.group) {
          if (!groups[option.group]) {
            groups[option.group] = []
          }
          groups[option.group].push(option)
        } else {
          ungrouped.push(option)
        }
      }
    })

    // Sort recent models by their order in recentModelIds (most recently used first)
    // This ensures the display order matches the actual recency order
    recent.sort((a, b) => {
      const indexA = recentModelIds.indexOf(a.value)
      const indexB = recentModelIds.indexOf(b.value)
      return indexA - indexB
    })

    return { groups, ungrouped, favorites, recent }
  }, [filteredOptions, recentModelIds, open])

  const selectedOption = options.find((option) => option.value === value)

  const handleSelect = (optionValue: string) => {
    onValueChange?.(optionValue)
    setOpen(false)
    setSearch("")
  }

  const handleToggleFavorite = (e: React.MouseEvent, option: SimpleComboboxOption) => {
    e.stopPropagation()
    onToggleFavorite?.(option.value, !option.isFavorite)
  }

  const renderOption = (option: SimpleComboboxOption) => {
    const isSelected = value === option.value
    const isHovered = hoveredOptionValue === option.value
    const hasTooltip = option.metadata && isHovered && !isMobile

    const optionContent = (
      <div
        className={
          isSelected
            ? "relative flex cursor-pointer select-none items-center rounded-sm py-1.5 pr-7 px-1.5 text-sm outline-none transition-all duration-200 bg-accent-brand/10 text-foreground border-l-4 border-accent-brand shadow-[0_1px_3px_0_hsl(var(--accent-brand)/0.4)] hover:bg-accent-brand/20 hover:shadow-[0_4px_8px_-2px_hsl(var(--accent-brand)/0.5)]"
            : "relative flex cursor-pointer select-none items-center rounded-sm py-1.5 pr-7 px-1.5 text-sm outline-none transition-all duration-200 hover:bg-accent hover:text-accent-foreground"
        }
        onClick={() => handleSelect(option.value)}
        onMouseEnter={() => option.metadata && setHoveredOptionValue(option.value)}
        onMouseLeave={() => setHoveredOptionValue(null)}
      >
        <Check
          className={cn(
            "mr-2 h-4 w-4 flex-shrink-0 transition-colors duration-200",
            isSelected ? "opacity-100 text-accent-brand" : "opacity-0"
          )}
        />
        {option.icon && (
          <div className="mr-2 flex-shrink-0">
            {option.icon}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className={cn("font-medium flex items-center gap-1.5", isSelected && "font-semibold")}>
            {option.label}
            {option.metadata?.is_new && (
              <Badge variant="default" className="h-4 px-1 text-xs font-medium bg-accent-brand text-white">
                New
              </Badge>
            )}
          </div>
          {option.description && (
            <div className="text-xs text-muted-foreground">
              {option.description}
            </div>
          )}
        </div>
        {onToggleFavorite && (
          <button
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-accent-foreground/10 rounded"
            onClick={(e) => handleToggleFavorite(e, option)}
          >
            <Star
              className={cn(
                "h-4 w-4",
                option.isFavorite ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground"
              )}
            />
          </button>
        )}
      </div>
    )

    // Only create tooltip if metadata exists AND option is hovered (and not on mobile)
    if (!hasTooltip) {
      return <React.Fragment key={option.value}>{optionContent}</React.Fragment>
    }

    return (
      <Tooltip key={option.value} delayDuration={200} open={true}>
        <TooltipTrigger asChild>
          {optionContent}
        </TooltipTrigger>
        <TooltipContent
          side="right"
          align="start"
          className="p-0 bg-background text-foreground border-2 shadow-xl max-w-none rounded-lg"
          sideOffset={8}
        >
          {/* hasTooltip (checked above) already guarantees metadata is set */}
          <ModelDetailsPopover model={option.metadata!} />
        </TooltipContent>
      </Tooltip>
    )
  }

  // Shared content for both Popover and Sheet
  const comboboxContent = (
    <>
      <div className={cn(
        "flex items-center border-b px-3",
        isMobile && "mx-3 rounded-lg bg-muted/30 border mb-2"
      )}>
        <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
        <Input
          placeholder={searchPlaceholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-11 border-0 focus:ring-0 focus-visible:ring-0 focus-visible:ring-offset-0 bg-transparent"
          autoFocus
        />
      </div>

      {/* Filter toggle button */}
      {onToggleFilters && (
        <div className="border-b px-2 py-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleFilters}
            className={cn(
              "w-full justify-start relative",
              showFilters && "bg-secondary"
            )}
          >
            <Filter className="mr-2 h-4 w-4" />
            Filters
            {hasActiveFilters && (
              <span className="ml-auto h-2 w-2 bg-accent-brand rounded-full" />
            )}
          </Button>
        </div>
      )}

      {/* Filter content (expandable) */}
      {filterContent && (
        <Collapsible open={showFilters}>
          <CollapsibleContent className="border-b">
            <div className="p-3 bg-accent-brand/5">
              {filterContent}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}

      <ScrollArea className={cn(
        isMobile
          ? showFilters ? "h-[calc(100vh-450px)]" : "h-[calc(100vh-180px)]"
          : showFilters ? "h-[min(300px,50vh)]" : "h-[min(500px,60vh)]"
      )}>
        <TooltipProvider>
          <div className={cn("p-1", isMobile && "pb-8")}>
            {filteredOptions.length === 0 ? (
              <div className="py-6 text-center text-sm">{emptyMessage}</div>
            ) : (
              <>
                  {/* Render recent models section */}
                  {groupedOptions.recent.length > 0 && (
                <div>
                  <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
                    Recent Chat Models
                  </div>
                  <div className="px-2 space-y-0.5">
                    {groupedOptions.recent.map((option) => renderOption(option))}
                  </div>
                </div>
              )}

                  {/* Render favorites section */}
                  {groupedOptions.favorites.length > 0 && (
                <div>
                  <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
                    Favorite Models
                  </div>
                  <div className="px-2 space-y-0.5">
                    {groupedOptions.favorites.map((option) => renderOption(option))}
                  </div>
                </div>
              )}

              {/* Render ungrouped items */}
              {groupedOptions.ungrouped.length > 0 && (
                <div className="px-2 py-1.5 space-y-0.5">
                  {groupedOptions.ungrouped.map((option) => renderOption(option))}
                </div>
              )}

              {/* Render grouped items */}
              {Object.entries(groupedOptions.groups).map(([group, groupOptions]) => {
                const groupIcon = groupOptions[0]?.groupIcon
                return (
                  <div key={group}>
                    <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                      {groupIcon && (
                        <div className="flex-shrink-0">
                          {groupIcon}
                        </div>
                      )}
                      <span>{group}</span>
                    </div>
                    <div className="px-2 space-y-0.5">
                      {groupOptions.map((option) => renderOption(option))}
                    </div>
                  </div>
                )
              })}
              </>
            )}
          </div>
        </TooltipProvider>
      </ScrollArea>
    </>
  )

  // Trigger button - shared between both modes
  const triggerButton = (
    <Button
      variant={variant}
      role="combobox"
      aria-expanded={open}
      className={cn(
        "transition-all duration-200",
        compact ? "w-10 h-10 p-0 justify-center" : "w-full justify-between",
        selectedOption && "border-accent-brand/30 hover:border-accent-brand/50",
        className
      )}
      disabled={disabled}
      onClick={isMobile ? () => setOpen(true) : undefined}
    >
      {compact ? (
        // Compact mode - icon only
        // Use [&_svg]:!size-auto to override button's [&_svg]:size-4
        selectedOption?.icon ? (
          <div className="flex-shrink-0 [&_svg]:!size-auto">{selectedOption.icon}</div>
        ) : (
          <ChevronDown className="h-4 w-4 opacity-50" />
        )
      ) : (
        // Full mode - icon + label + optional chevron
        <>
          <div className="flex items-center gap-2 truncate">
            {selectedOption?.icon && (
              <div className="flex-shrink-0 [&_svg]:!size-auto">
                {selectedOption.icon}
              </div>
            )}
            <span className={cn("truncate", selectedOption && "font-semibold")}>
              {selectedOption ? selectedOption.label : placeholder}
            </span>
          </div>
          {!hideChevron && <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />}
        </>
      )}
    </Button>
  )

  // Mobile: use Sheet (full screen from bottom)
  if (isMobile) {
    return (
      <>
        {triggerButton}
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent side="bottom" className="h-[85vh] px-0 pb-0">
            <SheetHeader className="px-4 pt-2 pb-4">
              <SheetTitle>{placeholder}</SheetTitle>
            </SheetHeader>
            <div className="flex flex-col gap-2">
              {comboboxContent}
            </div>
          </SheetContent>
        </Sheet>
      </>
    )
  }

  // Desktop: use Popover
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        {triggerButton}
      </PopoverTrigger>
      <PopoverContent className="w-[350px] md:w-[400px] p-0" align="start" side={side} sideOffset={sideOffset} collisionPadding={16}>
        {comboboxContent}
      </PopoverContent>
    </Popover>
  )
})
