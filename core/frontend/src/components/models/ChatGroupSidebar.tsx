import { useState } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { PlusIcon, Trash2Icon, MessageSquareIcon, ChevronLeftIcon, ChevronRightIcon, MoreVerticalIcon, PencilIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { RenameModal, ConfirmDeleteModal } from '@/components/shared'
import type { ChatGroupSummary } from './types'

interface ChatGroupSidebarProps {
  groups: ChatGroupSummary[]
  activeGroupId: string
  onSelectGroup: (groupId: string) => void
  onNewGroup: () => void
  onDeleteGroup: (groupId: string) => void
  onRenameGroup: (groupId: string, newName: string) => void
  isCollapsed: boolean
  onToggleCollapse: () => void
}

interface ConversationItemProps {
  group: ChatGroupSummary
  activeGroupId: string
  onSelectGroup: (id: string) => void
  onRenameClick: (id: string, name: string) => void
  onDeleteClick: (id: string) => void
  formatDate: (date: Date) => string
}

function ConversationItem({
  group,
  activeGroupId,
  onSelectGroup,
  onRenameClick,
  onDeleteClick,
  formatDate
}: ConversationItemProps) {
  // Show tooltip if displayed name is different from full name (truncated)
  const isTruncated = group.name !== group.fullName

  const content = (
    <div
      className={cn(
        "group relative rounded-lg p-2 pr-8 cursor-pointer transition-colors hover:bg-secondary hover:text-foreground",
        activeGroupId === group.id && "bg-secondary text-foreground"
      )}
      onClick={() => onSelectGroup(group.id)}
    >
      <div className="flex items-start gap-1.5">
        <MessageSquareIcon className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-muted-foreground" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-xs line-clamp-2 whitespace-pre-line">
            {group.name}
          </div>
          <div className="text-xs text-muted-foreground">
            {formatDate(group.updatedAt)}
          </div>
        </div>
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-1.5 right-1.5 h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
            onClick={(e) => {
              e.stopPropagation()
            }}
          >
            <MoreVerticalIcon className="h-3.5 w-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
          <DropdownMenuItem
            onClick={(e) => {
              e.stopPropagation()
              onRenameClick(group.id, group.fullName)
            }}
          >
            <PencilIcon className="h-3.5 w-3.5 mr-2" />
            Rename
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={(e) => {
              e.stopPropagation()
              onDeleteClick(group.id)
            }}
            className="text-destructive focus:text-destructive"
          >
            <Trash2Icon className="h-3.5 w-3.5 mr-2" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )

  if (isTruncated) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          {content}
        </TooltipTrigger>
        <TooltipContent side="right" className="whitespace-pre-line">
          {group.fullName}
        </TooltipContent>
      </Tooltip>
    )
  }

  return content
}

export default function ChatGroupSidebar({
  groups,
  activeGroupId,
  onSelectGroup,
  onNewGroup,
  onDeleteGroup,
  onRenameGroup,
  isCollapsed,
  onToggleCollapse
}: ChatGroupSidebarProps) {
  const [renameDialogOpen, setRenameDialogOpen] = useState(false)
  const [renamingGroup, setRenamingGroup] = useState<ChatGroupSummary | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deletingGroup, setDeletingGroup] = useState<ChatGroupSummary | null>(null)
  const formatDate = (date: Date) => {
    // Defensive check for invalid dates
    if (!(date instanceof Date) || isNaN(date.getTime())) {
      return 'Unknown'
    }
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return 'Today'
    if (days === 1) return 'Yesterday'
    if (days < 7) return `${days} days ago`
    if (days < 30) return `${Math.floor(days / 7)} weeks ago`
    if (days < 365) return `${Math.floor(days / 30)} months ago`
    return date.toLocaleDateString()
  }

  const handleRenameClick = (groupId: string, currentName: string) => {
    const group = groups.find(g => g.id === groupId)
    if (group) {
      setRenamingGroup(group)
      setRenameDialogOpen(true)
    }
  }

  const handleRenameConfirm = (newName: string) => {
    if (renamingGroup) {
      onRenameGroup(renamingGroup.id, newName)
      setRenamingGroup(null)
    }
  }

  const handleDeleteClick = (groupId: string) => {
    const group = groups.find(g => g.id === groupId)
    if (group) {
      setDeletingGroup(group)
      setDeleteDialogOpen(true)
    }
  }

  const handleDeleteConfirm = () => {
    if (deletingGroup) {
      onDeleteGroup(deletingGroup.id)
      setDeletingGroup(null)
    }
  }

  if (isCollapsed) {
    // Collapsed view - just icons
    return (
      <div className="w-[60px] border-r bg-muted/10 flex flex-col h-full transition-all duration-300">
        {/* Toggle button */}
        <div className="p-2 border-b flex justify-center">
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleCollapse}
            title="Expand sidebar"
          >
            <ChevronRightIcon className="h-5 w-5" />
          </Button>
        </div>

        {/* New conversation button */}
        <div className="p-2 border-b flex justify-center">
          <Button
            variant="ghost"
            size="icon"
            onClick={onNewGroup}
            title="New Conversation"
          >
            <PlusIcon className="h-5 w-5" />
          </Button>
        </div>

        {/* Groups list - just icons */}
        <ScrollArea className="flex-1">
          <div className="w-full p-2 space-y-1">
            {groups.map((group) => (
              <Button
                key={group.id}
                variant="ghost"
                size="icon"
                className={cn(
                  "w-full",
                  activeGroupId === group.id && "bg-secondary text-foreground"
                )}
                onClick={() => onSelectGroup(group.id)}
                title={group.fullName}
              >
                <MessageSquareIcon className="h-5 w-5" />
              </Button>
            ))}
          </div>
        </ScrollArea>
      </div>
    )
  }

  // Expanded view
  return (
    <div className="w-[340px] border-r bg-muted/10 flex flex-col h-full transition-all duration-300">
      {/* Toggle button */}
      <div className="p-2 border-b flex justify-end">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          title="Collapse sidebar"
        >
          <ChevronLeftIcon className="h-5 w-5" />
        </Button>
      </div>

      {/* Header */}
      <div className="px-4 pb-4 border-b">
        <Button
          onClick={onNewGroup}
          variant="outline"
          size="sm"
          className="w-full rounded-full text-brand-700 dark:text-brand-400 border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-800 dark:hover:text-brand-300"
        >
          <PlusIcon className="h-4 w-4 mr-2" />
          New Conversation
        </Button>
      </div>

      {/* Groups List */}
      <ScrollArea className="flex-1">
        <TooltipProvider>
          <div className="w-full p-2 space-y-1">
            {groups.length === 0 ? (
              <div className="text-center text-muted-foreground text-sm py-8">
                No conversations yet
              </div>
            ) : (
              groups.map((group) => (
                <ConversationItem
                  key={group.id}
                  group={group}
                  activeGroupId={activeGroupId}
                  onSelectGroup={onSelectGroup}
                  onRenameClick={handleRenameClick}
                  onDeleteClick={handleDeleteClick}
                  formatDate={formatDate}
                />
              ))
            )}
          </div>
        </TooltipProvider>
      </ScrollArea>

      {/* Footer with count */}
      <div className="p-4 border-t text-xs text-muted-foreground text-center">
        {groups.length} conversation{groups.length !== 1 ? 's' : ''}
      </div>

      {/* Rename Dialog */}
      {renamingGroup && (
        <RenameModal
          isOpen={renameDialogOpen}
          onClose={() => {
            setRenameDialogOpen(false)
            setRenamingGroup(null)
          }}
          onConfirm={handleRenameConfirm}
          currentName={renamingGroup.fullName}
          title="Rename Conversation"
          description="Enter a new name for this conversation"
          inputPlaceholder="Conversation name"
        />
      )}

      {/* Delete Confirmation Dialog */}
      {deletingGroup && (
        <ConfirmDeleteModal
          isOpen={deleteDialogOpen}
          onClose={() => {
            setDeleteDialogOpen(false)
            setDeletingGroup(null)
          }}
          onConfirm={handleDeleteConfirm}
          title="Delete Conversation"
          itemName={deletingGroup.name}
        />
      )}
    </div>
  )
}