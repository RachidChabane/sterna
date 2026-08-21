import { Badge } from '@/components/ui/badge'
import { DollarSign } from 'lucide-react'
import { cn } from '@/lib/utils'

export type CostDisplayVariant = 'inline' | 'badge' | 'detailed'

interface CostDisplayProps {
  cost?: number
  promptCost?: number
  completionCost?: number
  variant?: CostDisplayVariant
  showBreakdown?: boolean
  className?: string
}

function formatCost(cost?: number): string {
  if (cost === undefined || cost === null) return '$0.0000'
  return `$${cost.toFixed(4)}`
}

export function CostDisplay({
  cost,
  promptCost,
  completionCost,
  variant = 'inline',
  showBreakdown = false,
  className,
}: CostDisplayProps) {
  // Inline variant - simple text with icon
  if (variant === 'inline') {
    return (
      <span className={cn('inline-flex items-center gap-1 text-sm text-accent-brand', className)}>
        <DollarSign className="h-3.5 w-3.5" />
        {formatCost(cost)}
      </span>
    )
  }

  // Badge variant - compact badge
  if (variant === 'badge') {
    return (
      <Badge variant="outline" className={cn('gap-1 bg-accent-brand/10 text-accent-brand border-accent-brand/30', className)}>
        <DollarSign className="h-3 w-3" />
        {formatCost(cost)}
      </Badge>
    )
  }

  // Detailed variant - full breakdown
  return (
    <div className={cn('flex items-center gap-2.5 p-2 rounded-md border border-border', className)}>
      <DollarSign className="h-3.5 w-3.5 text-accent-brand flex-shrink-0" />
      <div className="flex-1 space-y-1">
        <p className="text-xs text-muted-foreground">Cost Breakdown</p>
        {showBreakdown && (promptCost !== undefined || completionCost !== undefined) ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
            <span className="text-muted-foreground">Prompt:</span>
            <span className="font-medium text-foreground text-right">{formatCost(promptCost)}</span>
            <span className="text-muted-foreground">Completion:</span>
            <span className="font-medium text-foreground text-right">{formatCost(completionCost)}</span>
            <span className="text-muted-foreground font-semibold">Total:</span>
            <span className="font-semibold text-accent-brand text-right">{formatCost(cost)}</span>
          </div>
        ) : (
          <p className="text-xs font-medium text-accent-brand">{formatCost(cost)}</p>
        )}
      </div>
    </div>
  )
}
