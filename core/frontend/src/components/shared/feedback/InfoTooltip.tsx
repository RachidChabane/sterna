import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { LucideIcon } from 'lucide-react'

interface InfoTooltipProps {
  title: string
  description: string | React.ReactNode
  icon?: LucideIcon
  side?: 'top' | 'bottom' | 'left' | 'right'
  children: React.ReactNode
  className?: string
}

export function InfoTooltip({
  title,
  description,
  icon: Icon,
  side = 'bottom',
  children,
  className,
}: InfoTooltipProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {children}
        </TooltipTrigger>
        <TooltipContent side={side} className={className}>
          <div className="text-sm">
            {Icon && (
              <div className="flex items-center gap-2 mb-1">
                <Icon className="h-4 w-4" />
                <p className="font-medium">{title}</p>
              </div>
            )}
            {!Icon && <p className="font-medium">{title}</p>}
            {typeof description === 'string' ? (
              <p className="text-xs text-muted-foreground mt-1">{description}</p>
            ) : (
              <div className="text-xs text-muted-foreground mt-1">{description}</div>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
