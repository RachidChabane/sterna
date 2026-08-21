import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

export type StatusBadgeVariant = 'warning' | 'success' | 'error' | 'info' | 'pending' | 'running' | 'default'

interface StatusBadgeProps {
  variant?: StatusBadgeVariant
  icon?: LucideIcon
  children: React.ReactNode
  tooltip?: {
    title: string
    description: string | React.ReactNode
  }
  className?: string
}

const variantStyles: Record<StatusBadgeVariant, string> = {
  warning: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30',
  success: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30',
  error: 'bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/30',
  info: 'bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30',
  pending: 'bg-gray-500/10 text-gray-700 dark:text-gray-400 border-gray-500/30',
  running: 'bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30',
  default: 'bg-muted text-foreground border-border',
}

export function StatusBadge({ variant = 'default', icon: Icon, children, tooltip, className }: StatusBadgeProps) {
  const badge = (
    <Badge variant="outline" className={cn('gap-1.5', variantStyles[variant], className)}>
      {Icon && <Icon className="h-3.5 w-3.5" />}
      {children}
    </Badge>
  )

  if (!tooltip) {
    return badge
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {badge}
        </TooltipTrigger>
        <TooltipContent className="max-w-sm">
          <p className="font-medium">{tooltip.title}</p>
          {typeof tooltip.description === 'string' ? (
            <p className="text-xs text-muted-foreground mt-1">{tooltip.description}</p>
          ) : (
            <div className="text-xs text-muted-foreground mt-1">{tooltip.description}</div>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
