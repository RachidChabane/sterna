import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

type MetricCardVariant = 'default' | 'highlight' | 'warning'

interface MetricCardProps {
  icon: LucideIcon
  label: string
  value: string | React.ReactNode
  variant?: MetricCardVariant
  className?: string
}

const variantStyles: Record<MetricCardVariant, { container: string; icon: string }> = {
  default: {
    container: 'border-border',
    icon: 'text-muted-foreground',
  },
  highlight: {
    container: 'border-accent-brand/30 bg-accent-brand/5',
    icon: 'text-accent-brand',
  },
  warning: {
    container: 'border-amber-500/30 bg-amber-500/5',
    icon: 'text-amber-600 dark:text-amber-400',
  },
}

export function MetricCard({ icon: Icon, label, value, variant = 'default', className }: MetricCardProps) {
  const styles = variantStyles[variant]

  return (
    <div className={cn('flex items-center gap-2.5 p-2 rounded-md border', styles.container, className)}>
      <Icon className={cn('h-3.5 w-3.5 flex-shrink-0', styles.icon)} />
      <div className="flex-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        {typeof value === 'string' ? (
          <p className="text-xs font-medium text-foreground">{value}</p>
        ) : (
          <div className="text-xs font-medium text-foreground">{value}</div>
        )}
      </div>
    </div>
  )
}
