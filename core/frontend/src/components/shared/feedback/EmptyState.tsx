import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string | React.ReactNode
  action?: {
    label: string
    onClick: () => void
    variant?: 'default' | 'outline' | 'secondary'
  }
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-12 px-4 text-center', className)}>
      <div className="rounded-full bg-muted/50 p-4 mb-4">
        <Icon className="h-8 w-8 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      {typeof description === 'string' ? (
        <p className="text-sm text-muted-foreground mb-6 max-w-md">{description}</p>
      ) : (
        <div className="text-sm text-muted-foreground mb-6 max-w-md">{description}</div>
      )}
      {action && (
        <Button variant={action.variant || 'default'} onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}
