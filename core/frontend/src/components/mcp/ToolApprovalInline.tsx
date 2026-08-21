/**
 * ToolApprovalInline Component
 *
 * Displays an inline approval request for an MCP tool execution.
 * Shows tool name, arguments, and approve/reject buttons.
 * Similar to citation display but for tool approvals.
 */

import { useState } from 'react'
import { Check, X, Loader2, Wrench, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { useMCPStore } from '@/store/mcpStore'
import { cn } from '@/lib/utils'
import type { MCPToolApproval } from '@/api/mcp'

interface ToolApprovalInlineProps {
  approval: MCPToolApproval
  onApproved?: () => void
  onRejected?: () => void
}

export function ToolApprovalInline({
  approval,
  onApproved,
  onRejected,
}: ToolApprovalInlineProps) {
  const { toast } = useToast()
  const { approveTool, rejectTool } = useMCPStore()

  const [approving, setApproving] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [scope, setScope] = useState<'once' | 'session' | 'permanent'>('once')
  const [showArgs, setShowArgs] = useState(false)

  const handleApprove = async () => {
    setApproving(true)
    try {
      const result = await approveTool(approval.id, scope)
      if (result) {
        toast({
          title: 'Tool Approved',
          description: `${approval.tool_name || 'Tool'} can now execute`,
        })
        onApproved?.()
      }
    } catch (error: any) {
      toast({
        title: 'Approval Failed',
        description: error.message || 'Could not approve tool execution',
        variant: 'destructive',
      })
    } finally {
      setApproving(false)
    }
  }

  const handleReject = async () => {
    setRejecting(true)
    try {
      const result = await rejectTool(approval.id)
      if (result) {
        toast({
          title: 'Tool Rejected',
          description: `${approval.tool_name || 'Tool'} execution was cancelled`,
        })
        onRejected?.()
      }
    } catch (error: any) {
      toast({
        title: 'Rejection Failed',
        description: error.message || 'Could not reject tool execution',
        variant: 'destructive',
      })
    } finally {
      setRejecting(false)
    }
  }

  return (
    <div className="my-3 rounded-lg border border-blue-500/30 bg-blue-500/5 p-3 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-1">
          <Wrench className="h-4 w-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-blue-700 dark:text-blue-300 truncate">
              {approval.tool_name || 'Unknown Tool'}
            </p>
            <p className="text-xs text-muted-foreground">Requesting permission to execute</p>
          </div>
        </div>
        <Badge
          variant="outline"
          className="bg-amber-500/10 border-amber-500/50 text-amber-700 dark:text-amber-400"
        >
          Pending
        </Badge>
      </div>

      {/* Arguments Preview */}
      {approval.proposed_arguments && Object.keys(approval.proposed_arguments).length > 0 && (
        <div className="space-y-1.5">
          <button
            onClick={() => setShowArgs(!showArgs)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {showArgs ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
            <span>
              {showArgs ? 'Hide' : 'Show'} arguments (
              {Object.keys(approval.proposed_arguments).length})
            </span>
          </button>

          {showArgs && (
            <div className="rounded bg-muted/50 p-2 text-xs font-mono space-y-1">
              {Object.entries(approval.proposed_arguments).map(([key, value]) => (
                <div key={key} className="flex gap-2">
                  <span className="text-muted-foreground">{key}:</span>
                  <span className="flex-1 break-all">
                    {typeof value === 'string'
                      ? value
                      : JSON.stringify(value, null, 2)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Approval Controls */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={scope} onValueChange={(v: any) => setScope(v)}>
          <SelectTrigger className="w-[140px] h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="once">Once</SelectItem>
            <SelectItem value="session">This session</SelectItem>
            <SelectItem value="permanent">Always</SelectItem>
          </SelectContent>
        </Select>

        <Button
          size="sm"
          onClick={handleApprove}
          disabled={approving || rejecting}
          className={cn(
            "h-8 gap-1.5",
            "bg-green-600 hover:bg-green-700 text-white"
          )}
        >
          {approving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5" />
          )}
          <span>Approve</span>
        </Button>

        <Button
          size="sm"
          variant="outline"
          onClick={handleReject}
          disabled={approving || rejecting}
          className="h-8 gap-1.5 border-destructive/50 text-destructive hover:bg-destructive/10"
        >
          {rejecting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <X className="h-3.5 w-3.5" />
          )}
          <span>Reject</span>
        </Button>
      </div>

      {/* Scope explanation */}
      <p className="text-xs text-muted-foreground">
        {scope === 'once' && 'Will ask again for next execution'}
        {scope === 'session' && 'Valid for this conversation (24h)'}
        {scope === 'permanent' && 'Always allow this tool to execute'}
      </p>
    </div>
  )
}
