/**
 * ToolCallApprovalCard Component
 *
 * Compact tool call approval request card.
 * Shows essential info with collapsible details.
 */

import { useState } from 'react'
import { Check, X, ChevronDown, ChevronRight, Wrench, Loader2, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import type { ToolCallApproval } from '@/components/models/types'

interface ToolCallApprovalCardProps {
  approval: ToolCallApproval
  onApprove: (approvalId: string, scope: 'once' | 'session' | 'permanent') => Promise<void>
  onReject: (approvalId: string) => Promise<void>
}

export function ToolCallApprovalCard({ approval, onApprove, onReject }: ToolCallApprovalCardProps) {
  const [showDetails, setShowDetails] = useState(false)
  const [scope, setScope] = useState<'once' | 'session' | 'permanent'>('once')
  const [loading, setLoading] = useState(false)
  const [decided, setDecided] = useState<'approved' | 'rejected' | null>(null)
  const [iconError, setIconError] = useState(false)

  const handleApprove = async () => {
    setLoading(true)
    try {
      await onApprove(approval.id, scope)
      setDecided('approved')
      setShowDetails(false) // Collapse after approval
    } catch (error) {
      console.error('Failed to approve tool:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleReject = async () => {
    setLoading(true)
    try {
      await onReject(approval.id)
      setDecided('rejected')
      setShowDetails(false) // Collapse after rejection
    } catch (error) {
      console.error('Failed to reject tool:', error)
    } finally {
      setLoading(false)
    }
  }

  // Determine icon and colors based on state
  const getHeaderIcon = () => {
    if (loading) {
      return <Loader2 className="h-4 w-4 animate-spin text-brand-600 dark:text-brand-400" />
    }
    if (decided === 'approved') {
      return <Check className="h-4 w-4 text-green-600 dark:text-green-400" />
    }
    if (decided === 'rejected') {
      return <X className="h-4 w-4 text-red-600 dark:text-red-400" />
    }

    // Show server icon if available and not errored, otherwise fallback to Wrench
    if (approval.server_icon_url && !iconError) {
      return (
        <img
          src={approval.server_icon_url}
          alt={approval.server_name}
          className="h-4 w-4 rounded-sm object-contain animate-pulse"
          onError={() => setIconError(true)}
        />
      )
    }

    return <Wrench className="h-4 w-4 text-brand-600 dark:text-brand-400 animate-pulse" />
  }

  const getBadgeContent = () => {
    if (loading) return 'Executing...'
    if (decided === 'approved') return `Approved (${scope})`
    if (decided === 'rejected') return 'Rejected'
    return 'Approval Required'
  }

  const getBadgeClassName = () => {
    const base = "text-xs transition-all duration-200"
    if (loading) {
      return `${base} bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700 animate-pulse`
    }
    if (decided === 'approved') {
      return `${base} bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700`
    }
    if (decided === 'rejected') {
      return `${base} bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700`
    }
    return `${base} bg-brand-100 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 border-brand-300 dark:border-brand-700`
  }

  return (
    <div className="group border rounded-lg bg-card overflow-hidden shadow-sm hover:shadow-md transition-all duration-200 animate-in slide-in-from-top-2">
      {/* Compact Header with dynamic state */}
      <div className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-brand-50/50 to-cyan-50/50 dark:from-brand-950/20 dark:to-cyan-950/20 border-b border-brand-200/50 dark:border-brand-800/50">
        {getHeaderIcon()}
        <div className="flex-1 flex items-center gap-2">
          <span className="text-sm font-semibold text-brand-900 dark:text-brand-100">
            {approval.tool_name}
          </span>
          <Badge variant="secondary" className={cn(getBadgeClassName())}>
            {getBadgeContent()}
          </Badge>
        </div>
      </div>

      {/* Content - hidden after decision */}
      {!decided && (
        <div className="p-3 space-y-3">
        {/* Collapsible Details */}
        <Collapsible open={showDetails} onOpenChange={setShowDetails}>
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-full justify-start text-xs text-muted-foreground hover:text-brand-600 dark:hover:text-brand-400 hover:bg-brand-50/50 dark:hover:bg-brand-950/20 transition-all duration-200"
            >
              <Info className="h-3 w-3 mr-1" />
              {showDetails ? 'Hide' : 'Show'} details
              <ChevronRight
                className={cn(
                  'h-3 w-3 ml-auto transition-transform duration-200',
                  showDetails && 'rotate-90'
                )}
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-2 pt-2 animate-in slide-in-from-top-1">
            {approval.tool_description && (
              <div className="text-xs text-muted-foreground pl-1">
                {approval.tool_description}
              </div>
            )}
            {Object.keys(approval.arguments).length > 0 && (
              <div className="bg-gradient-to-br from-muted/50 to-muted/30 rounded-lg p-2 border border-muted">
                <div className="text-xs font-mono text-muted-foreground">
                  {JSON.stringify(approval.arguments, null, 2)}
                </div>
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>

        {/* Scope Selection with Teal accent */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground whitespace-nowrap">Scope:</span>
          <Select
            value={scope}
            onValueChange={(value: 'once' | 'session' | 'permanent') => setScope(value)}
            disabled={loading}
          >
            <SelectTrigger className="h-8 text-xs flex-1 border-brand-200 dark:border-brand-800 focus:ring-brand-500 dark:focus:ring-brand-400 transition-all duration-200">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="once">Once</SelectItem>
              <SelectItem value="session">Session</SelectItem>
              <SelectItem value="permanent">Always</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <Button
            onClick={handleApprove}
            disabled={loading}
            size="sm"
            className="flex-1 bg-brand-600 hover:bg-brand-500 text-white shadow-sm hover:shadow transition-all duration-200"
          >
            {loading ? (
              <>
                <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
                Executing
              </>
            ) : (
              <>
                <Check className="h-3 w-3 mr-1.5" />
                Approve
              </>
            )}
          </Button>
          <Button
            onClick={handleReject}
            disabled={loading}
            size="sm"
            variant="outline"
            className="flex-1 text-foreground hover:bg-muted transition-all duration-200"
          >
            <X className="h-3 w-3 mr-1.5" />
            Reject
          </Button>
        </div>
        </div>
      )}
    </div>
  )
}
