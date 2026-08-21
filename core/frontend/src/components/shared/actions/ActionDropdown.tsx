import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { MoreVertical } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

export interface Action {
  label: string
  icon: LucideIcon
  onClick: () => void
  variant?: 'default' | 'destructive' | 'warning'
  disabled?: boolean
  separator?: boolean
}

interface ActionDropdownProps {
  actions: Action[]
  trigger?: React.ReactNode
  align?: 'start' | 'center' | 'end'
  className?: string
}

const variantStyles = {
  default: '',
  destructive: 'text-destructive hover:text-destructive',
  warning: 'text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300',
}

export function ActionDropdown({ actions, trigger, align = 'end', className }: ActionDropdownProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {trigger || (
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <MoreVertical className="h-4 w-4" />
            <span className="sr-only">Open menu</span>
          </Button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} className={className}>
        {actions.map((action, index) => (
          <div key={index}>
            {action.separator && index > 0 && <DropdownMenuSeparator />}
            <DropdownMenuItem
              onClick={action.onClick}
              disabled={action.disabled}
              className={cn(action.variant && variantStyles[action.variant])}
            >
              <action.icon className="h-4 w-4 mr-2" />
              {action.label}
            </DropdownMenuItem>
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
