import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip'
import { ModelIcon } from './ModelIcon'
import { AlertTriangle, ClockIcon, HashIcon, Info } from 'lucide-react'
import type { Message } from './types'
import { MetricCard, CostDisplay } from '@/components/shared'

interface Props {
  message: Message
  messagesContainer?: HTMLDivElement | null
  formatCost: (cost?: number) => string
  formatLatency: (latency?: number) => string
  disabled?: boolean
}

export function MessageDetailsTooltip({ message, messagesContainer, formatCost, formatLatency, disabled }: Props) {
  const [isOpen, setIsOpen] = useState(false)

  if (message.role !== 'assistant' || message.isError || message.isUnsupported) return null

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <TooltipProvider>
        <Tooltip>
          <PopoverTrigger asChild>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 hover:bg-accent group/btn"
                disabled={disabled}
              >
                <Info className="h-3 w-3 text-muted-foreground group-hover/btn:text-accent-brand transition-colors" />
              </Button>
            </TooltipTrigger>
          </PopoverTrigger>
          <TooltipContent>
            <p>View details</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <PopoverContent
        side="left"
        align="end"
        className="max-w-sm p-3"
        collisionBoundary={messagesContainer ?? undefined}
        collisionPadding={16}
        avoidCollisions={true}
      >
        <div className="space-y-2.5">
            {/* Model header */}
            {message.model && (
              <div className="flex items-center gap-2 pb-2 border-b border-border">
                <ModelIcon
                  modelName={message.model}
                  modelId={message.model_id ?? message.model}
                  provider={message.provider ?? ''}
                  modelIconSlug={message.model_icon_slug}
                  modelIconUrl={message.model_icon_url}
                  providerIconSlug={message.provider_icon_slug}
                  providerIconUrl={message.provider_icon_url}
                  size={20}
                  showTooltip={false}
                />
                <p className="text-xs font-semibold text-foreground">
                  {message.model.split('/').pop()}
                </p>
              </div>
            )}

            {/* Performance section */}
            {message.latency && (
              <MetricCard
                icon={ClockIcon}
                label="Latency"
                value={formatLatency(message.latency)}
              />
            )}

            {/* Tokens section */}
            {message.tokens && message.tokens.prompt !== undefined && message.tokens.completion !== undefined && (
              <MetricCard
                icon={HashIcon}
                label="Tokens"
                value={`${message.tokens.prompt.toLocaleString()} prompt · ${message.tokens.completion.toLocaleString()} completion`}
              />
            )}

            {/* Cost breakdown section */}
            {message.cost !== undefined && (
              <CostDisplay
                variant="detailed"
                cost={message.cost}
                promptCost={message.prompt_cost}
                completionCost={message.completion_cost}
                showBreakdown={message.prompt_cost !== undefined && message.completion_cost !== undefined}
              />
            )}

            {/* Truncation warning */}
            {message.isTruncated && (
              <div className="flex items-start gap-2 p-2 rounded-md border border-destructive/50">
                <AlertTriangle className="h-3.5 w-3.5 text-destructive flex-shrink-0 mt-0.5" />
                <p className="text-xs text-destructive">
                  Response truncated - increase Max Tokens in settings
                </p>
              </div>
            )}
          </div>
      </PopoverContent>
    </Popover>
  )
}
