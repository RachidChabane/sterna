/**
 * FeatureToggleButton Component
 *
 * Reusable toggle button for global features (Web Search, Reasoning, Connectors)
 * with consistent styling for different states
 */

import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

interface FeatureToggleButtonProps {
  // Feature state
  enabled: number
  total: number
  supported: number

  // UI
  icon: LucideIcon
  label: string
  colors: {
    active: string
    partial: string
    inactive: string
    iconActive: string
    iconPartial: string
    iconInactive: string
  }

  // Behavior
  onClick: () => void
  disabled?: boolean

  // Tooltip content
  tooltipTitle: (state: 'all' | 'some' | 'none') => string
  tooltipDescription: (state: 'all' | 'some' | 'none') => string
}

export function FeatureToggleButton({
  enabled,
  total,
  supported,
  icon: Icon,
  label,
  colors,
  onClick,
  disabled = false,
  tooltipTitle,
  tooltipDescription,
}: FeatureToggleButtonProps) {
  const allEnabled = enabled === supported && supported > 0
  const someEnabled = enabled > 0 && enabled < supported
  const state: 'all' | 'some' | 'none' = allEnabled ? 'all' : someEnabled ? 'some' : 'none'

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            onClick={onClick}
            disabled={disabled || total === 0}
            className={cn(
              "h-9 gap-1.5 px-2.5 border transition-all rounded-full",
              allEnabled
                ? colors.active
                : someEnabled
                ? colors.partial
                : colors.inactive
            )}
          >
            <Icon
              className={cn(
                "h-3.5 w-3.5",
                allEnabled
                  ? colors.iconActive
                  : someEnabled
                  ? colors.iconPartial
                  : colors.iconInactive
              )}
            />
            <span className="text-xs font-medium">{label}</span>
            {allEnabled && (
              <div className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <div>
            <p className="font-medium">{tooltipTitle(state)}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {tooltipDescription(state)}
            </p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
