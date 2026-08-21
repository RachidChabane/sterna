import { Button } from '@/components/ui/button'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

export interface BulkAction {
  label: string
  icon: LucideIcon
  onClick: () => void
  variant?: 'primary' | 'secondary' | 'destructive'
}

interface BulkSelectionBarProps {
  selectedCount: number
  actions: BulkAction[]
  onClear: () => void
  className?: string
}

const variantStyles = {
  primary: 'bg-accent-brand text-white border-accent-brand hover:bg-accent-brand/90',
  secondary: 'bg-background text-foreground border-border hover:bg-secondary',
  destructive: 'bg-background text-destructive border-destructive/30 hover:bg-destructive/10',
}

export function BulkSelectionBar({ selectedCount, actions, onClear, className }: BulkSelectionBarProps) {
  if (selectedCount === 0) return null

  return (
    <div className={cn('bg-muted/30 border-l-4 border-accent-brand p-4 rounded-md', className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-accent-brand">
            {selectedCount} item{selectedCount !== 1 ? 's' : ''} selected
          </p>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClear}
            className="h-7 text-xs text-muted-foreground hover:text-foreground"
          >
            <X className="h-3 w-3 mr-1" />
            Clear
          </Button>
        </div>

        <div className="flex items-center gap-2">
          {actions.map((action, index) => (
            <Button
              key={index}
              variant="outline"
              size="sm"
              onClick={action.onClick}
              className={cn(
                'h-8 gap-1.5',
                action.variant ? variantStyles[action.variant] : variantStyles.secondary
              )}
            >
              <action.icon className="h-4 w-4" />
              {action.label}
            </Button>
          ))}
        </div>
      </div>
    </div>
  )
}
