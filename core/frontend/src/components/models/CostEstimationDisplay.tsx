/**
 * CostEstimationDisplay Component
 *
 * Displays cost estimation results for model comparison:
 * - Token counts (prompt and completion)
 * - Per-model cost breakdown
 * - Total estimated cost
 * - Warning for images/PDFs not included in estimation
 */

import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Calculator, Info, X } from 'lucide-react'
import type { Attachment } from './types'
import type { NormalizedCostEstimate } from '@/api/llm'

interface CostEstimationDisplayProps {
  estimatedCosts: NormalizedCostEstimate | null
  attachments: Attachment[]
  onClose: () => void
}

export function CostEstimationDisplay({
  estimatedCosts,
  attachments,
  onClose,
}: CostEstimationDisplayProps) {
  if (!estimatedCosts) return null

  const hasMediaAttachments = attachments.some((att) =>
    att.type === 'image' || (att.type === 'file' && (
      (att.file?.type === 'application/pdf') ||
      ((att.file?.name || '').toLowerCase().endsWith('.pdf'))
    ))
  )

  return (
    <div className="flex-shrink-0 mx-3 mb-3">
      <Card className="bg-card/50 border-border/50">
        <CardContent className="p-3">
          <div className="space-y-2.5">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Calculator className="h-3.5 w-3.5 text-muted-foreground" />
                <h3 className="text-sm font-medium">Estimated Request Cost</h3>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={onClose}
                className="h-5 w-5 p-0 hover:bg-muted"
              >
                <X className="h-3 w-3" />
              </Button>
            </div>

            {/* Per-Model Details (Tokens + Cost) */}
            {estimatedCosts.costs.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">
                  Per model ({estimatedCosts.costs.length}):
                </p>
                <div className="space-y-1.5">
                  {estimatedCosts.costs.map((cost, index: number) => (
                    <div
                      key={`${cost.model_id}-${index}`}
                      className="px-2 py-1.5 rounded bg-muted/30"
                    >
                      <div className="flex justify-between items-center mb-1">
                        <span className="truncate flex-1 text-xs font-medium">{cost.model_name}</span>
                        <span className="font-mono font-semibold text-xs ml-2">
                          ${cost.cost.toFixed(4)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <span>P:</span>
                          <span className="font-mono font-semibold text-foreground">{(cost.prompt_tokens || 0).toLocaleString()}</span>
                        </span>
                        <span>•</span>
                        <span className="flex items-center gap-1">
                          <span>C:</span>
                          <span className="font-mono font-semibold text-foreground">{(cost.completion_tokens || 0).toLocaleString()}</span>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Total Cost - More compact */}
            <div className="pt-2 border-t border-border/50 flex justify-between items-center">
              <span className="text-sm font-semibold">Total</span>
              <span className="font-mono text-base font-bold">
                ${estimatedCosts.total_cost.toFixed(4)}
              </span>
            </div>

            {/* Warnings - More compact */}
            <div className="flex flex-wrap gap-1.5 text-[10px] text-muted-foreground/80">
              <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 border-muted-foreground/20">
                More accurate in English
              </Badge>
              {hasMediaAttachments && (
                <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 border-muted-foreground/20 flex items-center gap-1">
                  <Info className="h-2.5 w-2.5" />
                  Images/PDFs not included
                </Badge>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
