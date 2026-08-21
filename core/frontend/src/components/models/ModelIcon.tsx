/**
 * ModelIcon component
 *
 * Displays the appropriate icon for a model using intelligent fallback logic:
 * 1. Model-specific icon (e.g., Claude for anthropic/claude-3-opus)
 * 2. Provider icon (e.g., Anthropic)
 * 3. Generic Package icon (represents a product)
 *
 * Performance optimized: Uses CDN URLs, lazy loading.
 * Handles SVG gradient ID collisions when multiple identical icons are on the page.
 */

import { useId, useRef, useLayoutEffect, memo, type ComponentType, type SVGProps } from 'react'
import { Package } from 'lucide-react'
import { cn } from '@/lib/utils'
import { normalizeProviderName } from '@/lib/icon-utils'
import { getColoredIconComponent, getAdaptiveIconColor, getIconRenderComponent } from '@/lib/provider-icons'
import { useTheme } from '@/hooks/useTheme'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface ModelIconProps {
  modelName: string
  modelId: string
  provider: string
  modelIconSlug?: string
  modelIconUrl?: string
  providerIconSlug?: string
  providerIconUrl?: string
  size?: number
  className?: string
  showTooltip?: boolean
  tooltipContent?: string
}

export const ModelIcon = memo(function ModelIcon({
  modelName,
  modelId,
  provider,
  modelIconSlug,
  modelIconUrl,
  providerIconSlug,
  providerIconUrl,
  size = 24,
  className,
  showTooltip = true,
  tooltipContent,
}: ModelIconProps) {
  const { isDark } = useTheme()
  const uniqueId = useId()
  const containerRef = useRef<HTMLDivElement>(null)

  // Determine which icon to use with colored components first:
  // Priority 1: Model icon component (e.g., Claude)
  // Priority 2: Provider icon component (e.g., Anthropic)
  // Priority 3: CDN URL (model or provider, monochrome)
  // Priority 4: Package fallback
  const modelIconComponent = getColoredIconComponent(modelIconSlug)
  const providerIconComponent = modelIconComponent ? null : getColoredIconComponent(providerIconSlug)
  const iconComponent = modelIconComponent || providerIconComponent

  // Get the render component (.Color variant if available, otherwise Mono).
  // lib/provider-icons declares IconComponent with plain SVG props; restore
  // the `title` prop here explicitly for the `title=""` passed below (see
  // that file's JSDoc for how these SVGs are vendored).
  const RenderIcon = getIconRenderComponent(iconComponent) as
    | ComponentType<SVGProps<SVGSVGElement> & { size?: number; title?: string }>
    | null

  // Determine if we need to apply adaptive color
  // Only apply color to monochrome icons (no .Color variant)
  const isMonochrome = iconComponent && !iconComponent.Color
  const iconSlug = modelIconSlug || providerIconSlug
  const adaptiveColor = isMonochrome ? getAdaptiveIconColor(iconSlug, isDark, iconComponent) : undefined

  const iconUrl = !iconComponent ? (modelIconUrl || providerIconUrl) : null
  const iconLabel = modelIconSlug && modelIconSlug !== providerIconSlug
    ? `${modelName} (model icon)`
    : `${provider} (provider icon)`

  // Fix SVG gradient ID collisions when multiple identical icons are on the page
  // Some icons (like Gemini) use linearGradient with fixed IDs that conflict
  useLayoutEffect(() => {
    if (!containerRef.current || !RenderIcon) return

    const svg = containerRef.current.querySelector('svg')
    if (!svg) return

    // Find all elements with IDs in defs (gradients, patterns, etc.)
    const defs = svg.querySelector('defs')
    if (!defs) return

    const elementsWithId = defs.querySelectorAll('[id]')
    if (elementsWithId.length === 0) return

    // Create a mapping of old IDs to new unique IDs
    const idMap = new Map<string, string>()
    elementsWithId.forEach((el) => {
      const oldId = el.getAttribute('id')
      if (oldId) {
        // Create unique ID by appending React's useId value (already unique)
        const newId = `${oldId}-${uniqueId.replace(/:/g, '')}`
        idMap.set(oldId, newId)
        el.setAttribute('id', newId)
      }
    })

    // Update all references to these IDs (url(#id) in fill, stroke, etc.)
    const allElements = svg.querySelectorAll('*')
    allElements.forEach((el) => {
      ;['fill', 'stroke', 'clip-path', 'mask'].forEach((attr) => {
        const value = el.getAttribute(attr)
        if (value) {
          idMap.forEach((newId, oldId) => {
            if (value === `url(#${oldId})`) {
              el.setAttribute(attr, `url(#${newId})`)
            }
          })
        }
      })
    })
  }, [RenderIcon, uniqueId])

  const iconElement = (
    <div ref={containerRef} className={cn('flex items-center justify-center', className)}>
      {RenderIcon ? (
        // Render icon: .Color uses native colors, Mono uses adaptive color
        // title="" suppresses native SVG tooltip
        <RenderIcon
          size={size}
          title=""
          {...(adaptiveColor && { style: { color: adaptiveColor } })}
          className="shrink-0"
        />
      ) : iconUrl ? (
        // CDN URL for rare models/providers (monochrome but acceptable)
        <img
          src={iconUrl}
          alt={iconLabel}
          title=""
          width={size}
          height={size}
          className="object-contain"
          loading="lazy"
          onError={(e) => {
            // If CDN image fails, replace with fallback
            const target = e.currentTarget
            target.style.display = 'none'
            if (target.nextSibling) {
              (target.nextSibling as HTMLElement).style.display = 'inline-block'
            }
          }}
        />
      ) : null}
      {/* Fallback icon: Package (represents a product/model) */}
      <Package
        size={size}
        className={cn(
          'shrink-0 text-muted-foreground opacity-50',
          (RenderIcon || iconUrl) && 'hidden'
        )}
      />
    </div>
  )

  if (!showTooltip) {
    return iconElement
  }

  // Tooltip shows model name and provider
  const defaultTooltip = modelIconSlug && modelIconSlug !== providerIconSlug
    ? `${modelName} by ${normalizeProviderName(provider)}`
    : modelName

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{iconElement}</TooltipTrigger>
        <TooltipContent>
          <p>{tooltipContent || defaultTooltip}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
})
