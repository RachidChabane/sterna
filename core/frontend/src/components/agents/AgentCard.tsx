import { useState } from 'react'
import { Pencil, Trash2, FileDown, MoreVertical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { SubAgentSummary } from '@/api/subAgents'

interface AgentCardProps {
  agent: SubAgentSummary
  onEdit: (agent: SubAgentSummary) => void
  onExport: (agent: SubAgentSummary) => void
  onDelete: (agent: SubAgentSummary) => void
  onToggle: (agent: SubAgentSummary) => void
}

const TIER_LABELS: Record<string, string> = {
  fast: 'Fast',
  balanced: 'Balanced',
  powerful: 'Powerful',
  inherit: 'Inherit',
}

export default function AgentCard({ agent, onEdit, onExport, onDelete, onToggle }: AgentCardProps) {
  const [deleteConfirm, setDeleteConfirm] = useState(false)

  const handleDelete = () => {
    if (deleteConfirm) {
      onDelete(agent)
      setDeleteConfirm(false)
    } else {
      setDeleteConfirm(true)
      setTimeout(() => setDeleteConfirm(false), 3000)
    }
  }

  return (
    <div
      className={`group relative rounded-xl border bg-card p-4 transition-all hover:shadow-md ${
        agent.is_active
          ? 'border-border hover:border-accent-brand/50'
          : 'border-border/50 opacity-60'
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-foreground">
              {agent.name}
            </h3>
            <Badge variant="secondary" className="shrink-0 text-[10px]">
              {TIER_LABELS[agent.model_tier] || agent.model_tier}
            </Badge>
          </div>
          {agent.description && (
            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
              {agent.description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {/* Active toggle */}
          <Switch
            checked={agent.is_active}
            onCheckedChange={() => onToggle(agent)}
            className="scale-75"
          />

          {/* Context menu */}
          <DropdownMenu onOpenChange={(open) => { if (!open) setDeleteConfirm(false) }}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 flex-shrink-0"
              >
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onEdit(agent)}>
                <Pencil className="h-4 w-4 mr-2" />
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onExport(agent)}>
                <FileDown className="h-4 w-4 mr-2" />
                Export
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={handleDelete}
                className={deleteConfirm ? 'text-destructive focus:text-destructive' : 'text-destructive'}
              >
                <Trash2 className="h-4 w-4 mr-2" />
                {deleteConfirm ? 'Confirm?' : 'Delete'}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  )
}
