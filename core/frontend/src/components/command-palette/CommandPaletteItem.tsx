import React from 'react'
import { CommandItem } from '@/components/ui/command'
import { Badge } from '@/components/ui/badge'
import { highlightMatches } from './utils/search'
import { ModelIcon } from '@/components/models/ModelIcon'
import type { CommandItem as CommandItemType } from './types'
import type { LucideIcon } from 'lucide-react'

interface CommandPaletteItemProps {
  item: CommandItemType
  query: string
  onSelect: () => void
}

/**
 * Command Palette Item Component
 *
 * Renders individual command items with icons, highlighting, badges, and actions
 */
export function CommandPaletteItem({ item, query, onSelect }: CommandPaletteItemProps) {
  const { title, subtitle, icon, badge } = item

  // Render icon
  const renderIcon = () => {
    // For model items, use ModelIcon with actual model data
    if (item.type === 'model' && '_modelData' in item && item._modelData) {
      const model = item._modelData
      return (
        <div className="p-1.5 rounded-md bg-muted group-hover:bg-accent-brand/10 group-aria-selected:bg-accent-brand/20 transition-colors duration-200">
          <ModelIcon
            modelName={model.name}
            modelId={model.model_id}
            provider={model.provider}
            modelIconSlug={model.model_icon_slug}
            modelIconUrl={model.model_icon_url}
            providerIconSlug={model.provider_icon_slug}
            providerIconUrl={model.provider_icon_url}
            size={14}
            showTooltip={false}
          />
        </div>
      )
    }

    // For integration items, use server icon if available
    if (item.type === 'integration' && '_serverData' in item && item._serverData) {
      const server = item._serverData
      if (server.icon_url) {
        return (
          <div className="p-1.5 rounded-md bg-muted group-hover:bg-accent-brand/10 group-aria-selected:bg-accent-brand/20 transition-colors duration-200">
            <img
              src={server.icon_url}
              alt={server.name}
              className="h-4 w-4 shrink-0 object-contain"
              onError={(e) => {
                // Hide image on error, will fall through to default icon
                e.currentTarget.style.display = 'none'
              }}
            />
          </div>
        )
      }
    }

    // If icon is already a rendered React element, return it as-is wrapped
    if (React.isValidElement(icon)) {
      return (
        <div className="p-1.5 rounded-md bg-muted group-hover:bg-accent-brand/10 group-hover:text-accent-brand group-aria-selected:bg-accent-brand/20 group-aria-selected:text-accent-brand transition-all duration-200">
          {icon}
        </div>
      )
    }

    // Otherwise, treat icon as a component (function or ForwardRef) and render it
    // ForwardRef components are objects with $$typeof or render properties
    const isValidComponent =
      typeof icon === 'function' ||
      (typeof icon === 'object' && icon !== null && ('$$typeof' in icon || 'render' in icon))

    if (icon && isValidComponent) {
      const Icon = icon as LucideIcon
      return (
        <div className="p-1.5 rounded-md bg-muted group-hover:bg-accent-brand/10 group-hover:text-accent-brand group-aria-selected:bg-accent-brand/20 group-aria-selected:text-accent-brand transition-all duration-200">
          <Icon className="h-4 w-4 shrink-0" />
        </div>
      )
    }

    // No icon
    return null
  }

  // Highlight title matches
  const titleParts = highlightMatches(title, query)

  // Handle item selection
  const handleSelect = () => {
    item.onSelect()
    onSelect() // Close palette
  }

  // Handle mouse click - bypass cmdk's keyboard-only mode
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    handleSelect()
  }

  return (
    <div onClick={handleClick} className="w-full">
      <CommandItem
        value={item.id}
        onSelect={handleSelect}
        className="flex items-center gap-2.5 px-2.5 py-2 cursor-pointer group"
      >
      {/* Icon */}
      {renderIcon()}

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {/* Title with highlighting */}
          <div className="text-sm font-medium truncate group-aria-selected:text-accent-brand">
            {titleParts.map((part, i) => (
              <span
                key={i}
                className={part.highlighted ? 'text-accent-brand font-semibold' : ''}
              >
                {part.text}
              </span>
            ))}
          </div>

          {/* Badge */}
          {badge && (
            <Badge variant="secondary" className="text-xs shrink-0 group-aria-selected:bg-accent-brand/20 group-aria-selected:text-accent-brand group-aria-selected:border-accent-brand/30">
              {badge}
            </Badge>
          )}
        </div>

        {/* Subtitle */}
        {subtitle && (
          <div className="text-xs text-muted-foreground truncate mt-0.5">
            {subtitle}
          </div>
        )}
      </div>
    </CommandItem>
    </div>
  )
}
