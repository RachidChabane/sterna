import React, { useState, useMemo } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { Badge } from '@/components/ui/badge'
import {
  MessageSquareIcon,
  PencilIcon,
  Trash2Icon,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { RenameModal, ConfirmDeleteModal } from '@/components/shared'
import type { ChatGroupSummary } from './types'

interface ConversationsModalProps {
  isOpen: boolean
  onClose: () => void
  groups: ChatGroupSummary[]
  activeGroupId: string
  onSelectGroup: (groupId: string) => void
  onNewGroup: () => void
  onDeleteGroup: (groupId: string, deleteWorkspace?: boolean) => void
  onRenameGroup: (groupId: string, newName: string) => void
}


export function ConversationsModal({
  isOpen,
  onClose,
  groups,
  activeGroupId,
  onSelectGroup,
  onNewGroup,
  onDeleteGroup,
  onRenameGroup
}: ConversationsModalProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [isKeyboardMode, setIsKeyboardMode] = React.useState(false)
  const [renameDialogOpen, setRenameDialogOpen] = useState(false)
  const [renamingGroup, setRenamingGroup] = useState<ChatGroupSummary | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deletingGroup, setDeletingGroup] = useState<ChatGroupSummary | null>(null)

  // Track keyboard vs mouse usage
  React.useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        setIsKeyboardMode(true)
      }
    }

    const handleMouseMove = () => {
      setIsKeyboardMode(false)
    }

    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('mousemove', handleMouseMove)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('mousemove', handleMouseMove)
    }
  }, [isOpen])

  const formatDate = (date: Date) => {
    // Defensive check for invalid dates
    if (!(date instanceof Date) || isNaN(date.getTime())) {
      return 'Unknown'
    }
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const hours = Math.floor(diff / (1000 * 60 * 60))
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (hours < 1) return 'Just now'
    if (hours < 24) return `${hours}h ago`
    if (days === 1) return 'Yesterday'
    if (days < 7) return `${days}d ago`
    if (days < 30) return `${Math.floor(days / 7)}w ago`
    if (days < 365) return `${Math.floor(days / 30)}mo ago`
    return date.toLocaleDateString()
  }

  // Filter groups by search query
  const filteredGroups = useMemo(() => {
    if (!searchQuery.trim()) return groups
    const query = searchQuery.toLowerCase()
    return groups.filter(g =>
      g.name.toLowerCase().includes(query) ||
      g.fullName.toLowerCase().includes(query)
    )
  }, [groups, searchQuery])

  // Group conversations by date
  const groupedConversations = useMemo(() => {
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000)
    const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000)
    const monthAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000)

    return {
      today: filteredGroups.filter(g => g.updatedAt >= today),
      yesterday: filteredGroups.filter(g => g.updatedAt >= yesterday && g.updatedAt < today),
      thisWeek: filteredGroups.filter(g => g.updatedAt >= weekAgo && g.updatedAt < yesterday),
      thisMonth: filteredGroups.filter(g => g.updatedAt >= monthAgo && g.updatedAt < weekAgo),
      older: filteredGroups.filter(g => g.updatedAt < monthAgo)
    }
  }, [filteredGroups])

  // Handle item selection
  const handleSelect = (groupId: string) => {
    onSelectGroup(groupId)
    onClose()
  }

  // Handle rename
  const handleRenameClick = (e: React.MouseEvent, groupId: string) => {
    e.stopPropagation()
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

  // Handle delete
  const handleDeleteClick = (e: React.MouseEvent, groupId: string) => {
    e.stopPropagation()
    const group = groups.find(g => g.id === groupId)
    if (group) {
      setDeletingGroup(group)
      setDeleteDialogOpen(true)
    }
  }

  const handleDeleteConfirm = (deleteWorkspace?: boolean) => {
    if (deletingGroup) {
      onDeleteGroup(deletingGroup.id, deleteWorkspace)
      setDeletingGroup(null)
    }
  }

  const totalCount = filteredGroups.length

  // Render conversation item
  const renderConversationItem = (group: ChatGroupSummary) => {
    const isActive = activeGroupId === group.id

    const handleClick = (e: React.MouseEvent) => {
      e.preventDefault()
      e.stopPropagation()
      handleSelect(group.id)
    }

    return (
      <div key={group.id} onClick={handleClick} className="w-full">
        <CommandItem
          value={group.id}
          onSelect={() => handleSelect(group.id)}
          className="flex items-center gap-2.5 px-2.5 py-2 cursor-pointer group"
        >
          {/* Icon */}
          <div className={cn(
            "p-1.5 rounded-md transition-all duration-200",
            isActive
              ? "bg-accent-brand/20 text-accent-brand"
              : "bg-muted group-hover:bg-accent-brand/10 group-hover:text-accent-brand group-aria-selected:bg-accent-brand/20 group-aria-selected:text-accent-brand"
          )}>
            <MessageSquareIcon className="h-4 w-4 shrink-0" />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <div className="text-sm font-medium truncate group-aria-selected:text-accent-brand">
                {group.name}
              </div>
              {isActive && (
                <Badge variant="secondary" className="text-xs shrink-0 bg-accent-brand/20 text-accent-brand border-accent-brand/30">
                  Active
                </Badge>
              )}
            </div>
            <div className="text-xs text-muted-foreground truncate mt-0.5">
              {formatDate(group.updatedAt)}
            </div>
          </div>

          {/* Quick actions */}
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={(e) => handleRenameClick(e, group.id)}
              className="p-1 hover:bg-accent-brand/20 rounded-full transition-colors"
              title="Rename"
            >
              <PencilIcon className="h-3 w-3" />
            </button>
            <button
              onClick={(e) => handleDeleteClick(e, group.id)}
              className="p-1 hover:bg-destructive/20 text-destructive rounded-full transition-colors"
              title="Delete"
            >
              <Trash2Icon className="h-3 w-3" />
            </button>
          </div>
        </CommandItem>
      </div>
    )
  }

  return (
    <>
      <style>{`
        .keyboard-mode [cmdk-item]:hover {
          background: transparent !important;
          box-shadow: none !important;
        }
        .keyboard-mode [cmdk-item]:hover > * {
          background: transparent !important;
        }
        .keyboard-mode [cmdk-item]:hover .group-hover\\:bg-accent-brand\\/10,
        .keyboard-mode [cmdk-item]:hover .group-hover\\:bg-accent-brand\\/20,
        .keyboard-mode [cmdk-item]:hover .group-hover\\:text-accent-brand {
          background-color: inherit !important;
          color: inherit !important;
        }
        .keyboard-mode [cmdk-item]:hover .bg-muted,
        .keyboard-mode [cmdk-item]:hover .rounded-md {
          background-color: hsl(var(--muted)) !important;
          color: inherit !important;
        }
        .keyboard-mode [cmdk-item]:hover .opacity-0 {
          opacity: 0 !important;
        }
      `}</style>
      <Dialog open={isOpen} onOpenChange={onClose}>
        <DialogContent className="max-w-2xl p-0 gap-0 overflow-hidden">
          <DialogTitle className="sr-only">Conversations</DialogTitle>
          <DialogDescription className="sr-only">
            Browse and select your model comparison conversations. Use arrow keys to navigate and Enter to select.
          </DialogDescription>
          <Command shouldFilter={false} className={cn("rounded-lg border-0", isKeyboardMode && "keyboard-mode")}>
            {/* Search Input */}
            <div className="border-b border-border px-3">
              <CommandInput
                placeholder="Search conversations..."
                value={searchQuery}
                onValueChange={setSearchQuery}
                className="border-0 focus:ring-0"
              />
            </div>

            <CommandList className="max-h-[500px]">
              {/* Empty State */}
              <CommandEmpty>
                <div className="py-6 text-center">
                  <p className="text-sm text-muted-foreground">No conversations found.</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Try a different search term
                  </p>
                </div>
              </CommandEmpty>

              {/* Today */}
              {groupedConversations.today.length > 0 && (
                <>
                  <CommandGroup heading={
                    <div className="flex items-center gap-2">
                      <span>Today</span>
                      <Badge variant="secondary" className="text-[10px] font-normal">
                        {groupedConversations.today.length}
                      </Badge>
                    </div>
                  }>
                    {groupedConversations.today.map(renderConversationItem)}
                  </CommandGroup>
                  {(groupedConversations.yesterday.length > 0 || groupedConversations.thisWeek.length > 0 || groupedConversations.thisMonth.length > 0 || groupedConversations.older.length > 0) && (
                    <CommandSeparator />
                  )}
                </>
              )}

              {/* Yesterday */}
              {groupedConversations.yesterday.length > 0 && (
                <>
                  <CommandGroup heading={
                    <div className="flex items-center gap-2">
                      <span>Yesterday</span>
                      <Badge variant="secondary" className="text-[10px] font-normal">
                        {groupedConversations.yesterday.length}
                      </Badge>
                    </div>
                  }>
                    {groupedConversations.yesterday.map(renderConversationItem)}
                  </CommandGroup>
                  {(groupedConversations.thisWeek.length > 0 || groupedConversations.thisMonth.length > 0 || groupedConversations.older.length > 0) && (
                    <CommandSeparator />
                  )}
                </>
              )}

              {/* This Week */}
              {groupedConversations.thisWeek.length > 0 && (
                <>
                  <CommandGroup heading={
                    <div className="flex items-center gap-2">
                      <span>This Week</span>
                      <Badge variant="secondary" className="text-[10px] font-normal">
                        {groupedConversations.thisWeek.length}
                      </Badge>
                    </div>
                  }>
                    {groupedConversations.thisWeek.map(renderConversationItem)}
                  </CommandGroup>
                  {(groupedConversations.thisMonth.length > 0 || groupedConversations.older.length > 0) && (
                    <CommandSeparator />
                  )}
                </>
              )}

              {/* This Month */}
              {groupedConversations.thisMonth.length > 0 && (
                <>
                  <CommandGroup heading={
                    <div className="flex items-center gap-2">
                      <span>This Month</span>
                      <Badge variant="secondary" className="text-[10px] font-normal">
                        {groupedConversations.thisMonth.length}
                      </Badge>
                    </div>
                  }>
                    {groupedConversations.thisMonth.map(renderConversationItem)}
                  </CommandGroup>
                  {groupedConversations.older.length > 0 && <CommandSeparator />}
                </>
              )}

              {/* Older */}
              {groupedConversations.older.length > 0 && (
                <CommandGroup heading={
                  <div className="flex items-center gap-2">
                    <span>Older</span>
                    <Badge variant="secondary" className="text-[10px] font-normal">
                      {groupedConversations.older.length}
                    </Badge>
                  </div>
                }>
                  {groupedConversations.older.map(renderConversationItem)}
                </CommandGroup>
              )}
            </CommandList>

            {/* Footer with keyboard shortcuts */}
            <div className="border-t border-accent-brand/20 px-3 py-2 bg-accent-brand/5">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <div className="flex items-center gap-4">
                  <span>
                    <kbd className="px-1.5 py-0.5 bg-background border border-border rounded text-[10px]">
                      ↑↓
                    </kbd>{' '}
                    Navigate
                  </span>
                  <span>
                    <kbd className="px-1.5 py-0.5 bg-background border border-border rounded text-[10px]">
                      Enter
                    </kbd>{' '}
                    Select
                  </span>
                  <span>
                    <kbd className="px-1.5 py-0.5 bg-background border border-border rounded text-[10px]">
                      Esc
                    </kbd>{' '}
                    Close
                  </span>
                </div>
                {totalCount > 0 && (
                  <span className="text-[10px] font-medium text-accent-brand bg-accent-brand/10 px-2 py-1 rounded">
                    {totalCount} conversation{totalCount !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            </div>
          </Command>
        </DialogContent>
      </Dialog>

      {/* Rename Dialog */}
      {renamingGroup && (
        <RenameModal
          isOpen={renameDialogOpen}
          onClose={() => {
            setRenameDialogOpen(false)
            setRenamingGroup(null)
          }}
          onConfirm={handleRenameConfirm}
          currentName={renamingGroup.name}
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
          showWorkspaceCheckbox={true}
          workspaceCheckboxLabel="Also delete all workspace files"
        />
      )}
    </>
  )
}
