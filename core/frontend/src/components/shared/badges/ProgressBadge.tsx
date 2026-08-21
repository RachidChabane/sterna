import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { Loader2 } from 'lucide-react'

interface ProgressBadgeProps {
  current: number
  total: number
  label?: string
  variant?: 'default' | 'animated'
  className?: string
}

export function ProgressBadge({ current, total, label, variant = 'default', className }: ProgressBadgeProps) {
  const percentage = total > 0 ? Math.round((current / total) * 100) : 0
  const isComplete = current >= total && total > 0
  const isInProgress = current > 0 && current < total

  return (
    <Badge
      variant="outline"
      className={cn(
        'gap-1.5',
        isComplete && 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30',
        isInProgress && 'bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30',
        !isComplete && !isInProgress && 'bg-gray-500/10 text-gray-700 dark:text-gray-400 border-gray-500/30',
        className
      )}
    >
      {variant === 'animated' && isInProgress && (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      )}
      {label ? `${label}: ` : ''}
      {current}/{total} ({percentage}%)
    </Badge>
  )
}
