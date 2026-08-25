import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

type BetaVariant = 'beta' | 'experimental' | 'preview'

interface BetaBadgeProps {
  variant?: BetaVariant
  className?: string
}

const VARIANT_STYLES: Record<BetaVariant, string> = {
  beta:         'bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/30',
  experimental: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30',
  preview:      'bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30',
}

const TOOLTIP_TEXT: Record<BetaVariant, string> = {
  beta:         "Some deploys may fail; we're improving the experience. Reports welcome.",
  experimental: 'This feature is experimental. Behavior may change or be unstable.',
  preview:      'Preview feature — available early for feedback.',
}

const LABELS: Record<BetaVariant, string> = {
  beta:         'Beta',
  experimental: 'Experimental',
  preview:      'Preview',
}

export function BetaBadge({ variant = 'beta', className }: BetaBadgeProps) {
  const badge = (
    <Badge
      variant="outline"
      className={cn('text-[10px] font-semibold px-1.5 py-0 h-4 cursor-default', VARIANT_STYLES[variant], className)}
    >
      {LABELS[variant]}
    </Badge>
  )

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent className="max-w-xs text-xs">
          {TOOLTIP_TEXT[variant]}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
