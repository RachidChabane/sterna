/**
 * ProviderIcon component
 *
 * Displays the appropriate icon for a model provider with intelligent fallback:
 * 1. Colored React component (for common providers, ~37 supported — see
 *    `lib/provider-icons.tsx`, vendored locally as static SVGs)
 * 2. CDN URL (for rare providers, monochrome but acceptable)
 * 3. Building2 icon (generic fallback, represents a company/organization)
 */

import { memo } from 'react'
import { Building2 } from 'lucide-react'
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

interface ProviderIconProps {
  provider: string
  providerIconSlug?: string
  providerIconUrl?: string
  size?: number
  className?: string
  showTooltip?: boolean
  tooltipContent?: string
}

export const ProviderIcon = memo(function ProviderIcon({
  provider,
  providerIconSlug,
  providerIconUrl,
  size = 24,
  className,
  showTooltip = true,
  tooltipContent,
}: ProviderIconProps) {
  const { isDark } = useTheme()

  // Priority 1: Try colored React component (for common providers)
  const iconComponent = getColoredIconComponent(providerIconSlug)

  // Get the render component (.Color variant if available, otherwise Mono)
  const RenderIcon = getIconRenderComponent(iconComponent)

  // Determine if we need to apply adaptive color
  // Only apply color to monochrome icons (no .Color variant)
  const isMonochrome = iconComponent && !iconComponent.Color
  const adaptiveColor = isMonochrome ? getAdaptiveIconColor(providerIconSlug, isDark, iconComponent) : undefined

  const iconElement = (
    <div className={cn('flex items-center justify-center', className)}>
      {RenderIcon ? (
        // Render icon: .Color uses native colors, Mono uses adaptive color
        <RenderIcon
          size={size}
          {...(adaptiveColor && { style: { color: adaptiveColor } })}
          className="shrink-0"
        />
      ) : providerIconUrl ? (
        // CDN URL for rare providers (monochrome but acceptable)
        <img
          src={providerIconUrl}
          alt={`${provider} logo`}
          width={size}
          height={size}
          className="object-contain"
          loading="lazy"
          onError={(e) => {
            // If CDN image fails, replace with fallback SVG
            const target = e.currentTarget
            target.style.display = 'none'
            if (target.nextSibling) {
              (target.nextSibling as HTMLElement).style.display = 'inline-block'
            }
          }}
        />
      ) : null}
      {/* Fallback icon: Building2 (represents company/organization) */}
      <Building2
        size={size}
        className={cn(
          'shrink-0 text-muted-foreground opacity-50',
          (RenderIcon || providerIconUrl) && 'hidden'
        )}
      />
    </div>
  )

  if (!showTooltip) {
    return iconElement
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{iconElement}</TooltipTrigger>
        <TooltipContent>
          <p>{tooltipContent || normalizeProviderName(provider)}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
})
