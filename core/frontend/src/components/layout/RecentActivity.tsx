/**
 * RecentActivity Component
 *
 * Displays a scrollable list of recent conversations in the sidebar.
 * Uses the conversationStore (PostgreSQL backend) for data.
 */

import { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { MessageSquare, ChevronDown, MoreHorizontal, Pencil, Trash2, Plus, Loader2, BookOpen } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ConfirmDeleteModal } from '@/components/shared'
import { conversationsAPI } from '@/api/conversations'
import { toast } from 'sonner'
import { ModelIcon } from '@/components/models/ModelIcon'
import { useAuthStore } from '@/store/authStore'
import { useActiveConversationStore } from '@/store/activeConversationStore'
import { useConversationStore, type ConversationSummary } from '@/store/conversationStore'
import useModelStore from '@/store/modelStore'
import { removeProviderPrefix } from '@/lib/model-utils'

interface ChatModelEnriched {
  modelId: string
  modelProvider: string | null
  modelName: string | null
  modelIconSlug: string | null
  providerIconSlug: string | null
}

interface ConversationItem {
  id: string
  name: string
  updatedAt: Date
  modelId: string | null
  modelProvider: string | null
  // Enriched model data from model store lookup
  modelName: string | null
  modelIconSlug: string | null
  providerIconSlug: string | null
  // All chat models for hover display
  chatModels: ChatModelEnriched[]
}

interface RecentActivityProps {
  isCollapsed: boolean
  onItemClick?: () => void
}

const CHATS_EXPANDED_KEY = 'sidebar-chats-expanded'

// Typewriter effect hook with erase-then-type animation
// Shows placeholder immediately, then erases it and types the real title
function useTypewriter(
  targetText: string,
  placeholder: string,
  isGenerating: boolean,
  speed: number = 25
) {
  const [displayedText, setDisplayedText] = useState('')
  const [phase, setPhase] = useState<'idle' | 'showing' | 'erasing' | 'typing'>('idle')
  const [finalTarget, setFinalTarget] = useState('')
  const wasGeneratingRef = useRef(false)

  // Detect when generation starts - show placeholder immediately
  useEffect(() => {
    if (isGenerating && !wasGeneratingRef.current) {
      // Just started generating - show placeholder immediately
      setDisplayedText(placeholder)
      setPhase('showing')
      setFinalTarget('')
    }
    wasGeneratingRef.current = isGenerating
  }, [isGenerating, placeholder])

  // Detect when real title arrives (target changes from placeholder)
  useEffect(() => {
    if (phase === 'showing' && targetText && targetText !== placeholder) {
      // Real title arrived - start erasing
      setFinalTarget(targetText)
      setPhase('erasing')
    } else if ((phase === 'erasing' || phase === 'typing') && targetText !== finalTarget) {
      // Target updated while typing - update our final target
      setFinalTarget(targetText)
    }
  }, [targetText, placeholder, phase, finalTarget])

  // Animation loop
  useEffect(() => {
    if (phase === 'erasing') {
      // Erase characters one by one (faster than typing)
      if (displayedText.length > 0) {
        const timeout = setTimeout(() => {
          setDisplayedText(prev => prev.slice(0, -1))
        }, speed * 0.6 + Math.random() * 10) // Faster erasing
        return () => clearTimeout(timeout)
      } else {
        // Done erasing - start typing
        setPhase('typing')
      }
    } else if (phase === 'typing') {
      // Type characters one by one
      if (displayedText.length < finalTarget.length) {
        const timeout = setTimeout(() => {
          setDisplayedText(finalTarget.slice(0, displayedText.length + 1))
        }, speed + Math.random() * 15)
        return () => clearTimeout(timeout)
      } else if (!isGenerating) {
        // Done typing and generation complete
        setPhase('idle')
      }
    }
  }, [displayedText, phase, finalTarget, speed, isGenerating])

  const isAnimating = phase !== 'idle'

  return { displayedText, isAnimating }
}

// Conversation row component with typewriter effect
interface ConversationRowProps {
  item: ConversationItem
  isActive: boolean
  isGenerating: boolean
  targetTitle: string
  onClick: () => void
  onRename: (id: string, name: string) => void
  onDelete: (id: string) => void
  onSaveToKnowledgeBase: (id: string, name: string) => void
}

function ConversationRow({
  item,
  isActive,
  isGenerating,
  targetTitle,
  onClick,
  onRename,
  onDelete,
  onSaveToKnowledgeBase,
}: ConversationRowProps) {
  // Use typewriter effect when generating title
  // Shows "New Conversation" immediately, erases it, then types the real title
  const { displayedText, isAnimating } = useTypewriter(
    targetTitle,
    'New Conversation',
    isGenerating,
    25
  )

  // Determine what to show - use typewriter output while animating
  const displayTitle = isAnimating ? displayedText : item.name
  // Show cursor while animating
  const showCursor = isAnimating

  return (
    <div
      onClick={onClick}
      className={cn(
        "relative flex items-center gap-1 px-3 py-[9px] rounded-md cursor-pointer",
        "hover:bg-muted transition-colors",
        "group",
        isActive && "bg-muted before:absolute before:inset-y-1.5 before:left-0 before:w-[2px] before:rounded-full before:bg-accent-brand"
      )}
    >
      <div className="w-0 grow text-left">
        <span className="block text-[12px] font-medium truncate text-foreground/95">
          {displayTitle}
          {/* Show typing cursor when generating */}
          {showCursor && (
            <span className="inline-block w-[2px] h-[12px] bg-accent-brand ml-0.5 animate-pulse" />
          )}
        </span>
      </div>
      {/* Model icons - show all chat model icons on hover */}
      {item.chatModels.length > 0 && !isActive && (
        <div className="flex-shrink-0 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="relative flex-shrink-0 flex items-center">
                  {/* Show up to 3 model icons, stacked with overlap */}
                  {item.chatModels.slice(0, 3).map((cm, idx) => (
                    <div
                      key={cm.modelId + idx}
                      className="relative flex-shrink-0"
                      style={{ marginLeft: idx > 0 ? '-4px' : 0, zIndex: 3 - idx }}
                    >
                      <ModelIcon
                        modelName={cm.modelName || cm.modelId}
                        modelId={cm.modelId}
                        provider={cm.modelProvider || 'unknown'}
                        modelIconSlug={cm.modelIconSlug || undefined}
                        providerIconSlug={cm.providerIconSlug || undefined}
                        size={16}
                        showTooltip={false}
                      />
                    </div>
                  ))}
                  {/* Show +N if more than 3 models */}
                  {item.chatModels.length > 3 && (
                    <span className="ml-0.5 text-[10px] text-muted-foreground">
                      +{item.chatModels.length - 3}
                    </span>
                  )}
                </div>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                <div className="flex flex-col gap-0.5">
                  {item.chatModels.map((cm, idx) => (
                    <span key={cm.modelId + idx}>{cm.modelName || cm.modelId}</span>
                  ))}
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      )}
      {/* Three-dot menu - show on hover */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className={cn(
              "flex-shrink-0 p-0.5 rounded hover:bg-muted-foreground/10 transition-opacity",
              isActive ? "opacity-100" : "opacity-100 md:opacity-0 md:group-hover:opacity-100"
            )}
            onClick={(e) => e.stopPropagation()}
          >
            <MoreHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-36">
          <DropdownMenuItem
            onClick={(e) => {
              e.stopPropagation()
              onRename(item.id, item.name)
            }}
          >
            <Pencil className="h-3.5 w-3.5 mr-2" />
            Rename
          </DropdownMenuItem>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onSaveToKnowledgeBase(item.id, item.name)
                }}
              >
                <BookOpen className="h-3.5 w-3.5 mr-2" />
                Save to KB
              </DropdownMenuItem>
            </TooltipTrigger>
            <TooltipContent side="left">
              <p>Save to Knowledge Base</p>
            </TooltipContent>
          </Tooltip>
          <DropdownMenuItem
            onClick={(e) => {
              e.stopPropagation()
              onDelete(item.id)
            }}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="h-3.5 w-3.5 mr-2" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

export function RecentActivity({ isCollapsed, onItemClick }: RecentActivityProps) {
  const navigate = useNavigate()
  const { isAuthenticated } = useAuthStore()

  // Get the active conversation ID and title generation state from global store
  const activeConversationId = useActiveConversationStore((state) => state.activeConversationId)
  const generatingTitleForId = useActiveConversationStore((state) => state.generatingTitleForId)
  const newConversation = useActiveConversationStore((state) => state.newConversation)

  // Get conversations from the database-backed store
  const storeConversations = useConversationStore((state) => state.conversations)
  const storeIsLoading = useConversationStore((state) => state.isLoading)
  const storeIsLoadingMore = useConversationStore((state) => state.isLoadingMore)
  const storeHasMore = useConversationStore((state) => state.hasMore)
  const fetchConversations = useConversationStore((state) => state.fetchConversations)
  const fetchMoreConversations = useConversationStore((state) => state.fetchMoreConversations)
  const renameConversation = useConversationStore((state) => state.renameConversation)
  const deleteConversation = useConversationStore((state) => state.deleteConversation)

  // Get models from store for enriching conversation items with icon data
  const allModels = useModelStore((state) => state.allModels)
  const fetchAllModels = useModelStore((state) => state.fetchAllModels)
  const allModelsLoaded = useModelStore((state) => state.allModelsLoaded)

  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [isChatsExpanded, setIsChatsExpanded] = useState(() => {
    const stored = localStorage.getItem(CHATS_EXPANDED_KEY)
    return stored !== 'false' // Default to expanded
  })

  // Rename modal state
  const [renameModalOpen, setRenameModalOpen] = useState(false)
  const [renameTarget, setRenameTarget] = useState<{ id: string; name: string } | null>(null)
  const [newName, setNewName] = useState('')

  // Delete modal state
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null)

  // Save to Knowledge Base modal state
  const [saveToKBModalOpen, setSaveToKBModalOpen] = useState(false)
  const [saveToKBTarget, setSaveToKBTarget] = useState<{ id: string; name: string } | null>(null)
  const [isSavingToKB, setIsSavingToKB] = useState(false)

  // Track if we've loaded conversations
  const hasLoadedRef = useRef(false)

  const toggleChatsExpanded = useCallback((open: boolean) => {
    setIsChatsExpanded(open)
    localStorage.setItem(CHATS_EXPANDED_KEY, String(open))
  }, [])

  // Load conversations from the store on mount
  useEffect(() => {
    if (isAuthenticated && !hasLoadedRef.current) {
      hasLoadedRef.current = true
      fetchConversations()
    }
  }, [isAuthenticated, fetchConversations])

  // Fetch all models to get icon data for conversation items
  useEffect(() => {
    if (isAuthenticated && !allModelsLoaded) {
      fetchAllModels()
    }
  }, [isAuthenticated, allModelsLoaded, fetchAllModels])

  // Process conversations from the store
  const conversationItems = useMemo(() => {
    const items: ConversationItem[] = storeConversations.map((conv: ConversationSummary) => {
      // Look up model details from the model store
      const model = conv.modelId
        ? allModels.find(m => m.model_id === conv.modelId)
        : null

      // Extract display name (remove provider prefix like "Anthropic: Claude 3.5 Sonnet" -> "Claude 3.5 Sonnet")
      const modelName = model?.name
        ? removeProviderPrefix(model.name, conv.modelProvider || undefined)
        : null

      // Enrich all chat models with store data
      const chatModels: ChatModelEnriched[] = (conv.chatModels || []).map(cm => {
        const chatModel = allModels.find(m => m.model_id === cm.modelId)
        return {
          modelId: cm.modelId,
          modelProvider: cm.modelProvider,
          modelName: chatModel?.name
            ? removeProviderPrefix(chatModel.name, cm.modelProvider || undefined)
            : cm.modelId,
          modelIconSlug: chatModel?.model_icon_slug || null,
          providerIconSlug: chatModel?.provider_icon_slug || null,
        }
      })

      return {
        id: conv.id,
        name: conv.name,
        updatedAt: new Date(conv.updatedAt),
        modelId: conv.modelId,
        modelProvider: conv.modelProvider,
        // Enriched model data
        modelName,
        modelIconSlug: model?.model_icon_slug || null,
        providerIconSlug: model?.provider_icon_slug || null,
        chatModels,
      }
    })

    // Sort by updatedAt (newest first)
    items.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime())

    // If there's a newConversation in the store, ensure it's shown correctly
    if (newConversation) {
      const existingIndex = items.findIndex(item => item.id === newConversation.id)
      if (existingIndex === -1) {
        // Not in list yet, add it at the top
        items.unshift({
          id: newConversation.id,
          name: newConversation.name,
          updatedAt: new Date(),
          modelId: null,
          modelProvider: null,
          modelName: null,
          modelIconSlug: null,
          providerIconSlug: null,
          chatModels: [],
        })
      } else {
        // Already in list but might have stale name - update it
        items[existingIndex] = {
          ...items[existingIndex],
          name: newConversation.name,
        }
        // Move to top if it's a new conversation being generated
        if (existingIndex > 0) {
          const [item] = items.splice(existingIndex, 1)
          items.unshift(item)
        }
      }
    }

    return items
  }, [storeConversations, newConversation, allModels])

  // Handle scroll to load more from backend
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const target = e.target as HTMLDivElement
    const { scrollTop, scrollHeight, clientHeight } = target

    // Load more when within 50px of the bottom
    if (scrollHeight - scrollTop - clientHeight < 50 && storeHasMore && !storeIsLoadingMore) {
      fetchMoreConversations()
    }
  }, [storeHasMore, storeIsLoadingMore, fetchMoreConversations])

  // Return spacer if not authenticated
  if (!isAuthenticated) {
    return <div className="flex-1 mt-4" />
  }

  // In collapsed mode, just return a spacer - nav already has chat link
  if (isCollapsed) {
    return <div className="flex-1" />
  }

  // Show loading state
  if (storeIsLoading && storeConversations.length === 0) {
    return (
      <div className="flex-1 flex flex-col min-h-0 mt-4">
        <div className="mx-2 px-2.5 py-1.5 flex items-center gap-2">
          <MessageSquare className="h-3.5 w-3.5 text-muted-foreground/70" />
          <span className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider">Chats</span>
        </div>
        <div className="flex-1 flex items-center justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground/50" />
        </div>
      </div>
    )
  }

  // Return spacer if no items
  if (conversationItems.length === 0) {
    return <div className="flex-1 mt-4" />
  }

  const handleConversationClick = (id: string) => {
    navigate({ to: '/chats', search: { conversation: id } })
    onItemClick?.()
  }

  const handleNewConversation = (e: React.MouseEvent) => {
    e.stopPropagation() // Don't toggle the collapsible
    navigate({ to: '/chats', search: { new: true } })
    onItemClick?.()
  }

  const handleRenameConversation = (id: string, currentName: string) => {
    setRenameTarget({ id, name: currentName })
    setNewName(currentName)
    setRenameModalOpen(true)
  }

  const handleDeleteConversation = (id: string) => {
    setDeleteTargetId(id)
    setDeleteModalOpen(true)
  }

  const handleSaveToKnowledgeBase = (id: string, name: string) => {
    setSaveToKBTarget({ id, name })
    setSaveToKBModalOpen(true)
  }

  const confirmRename = async () => {
    if (!renameTarget || !newName.trim()) return

    try {
      // Use the store's rename method (calls the API)
      await renameConversation(renameTarget.id, newName.trim())

      setRenameModalOpen(false)
      setRenameTarget(null)
      setNewName('')
    } catch (error) {
      console.error('Failed to rename conversation:', error)
    }
  }

  const confirmDelete = async () => {
    if (!deleteTargetId) return

    try {
      // Navigate to new conversation page if we're on the deleted conversation
      const wasViewingDeleted = deleteTargetId === activeConversationId

      // Use the store's delete method (calls the API)
      await deleteConversation(deleteTargetId)

      setDeleteModalOpen(false)
      setDeleteTargetId(null)

      // Navigate to new conversation page only if viewing the deleted one
      if (wasViewingDeleted) {
        navigate({ to: '/chats', search: { new: true } })
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error)
    }
  }

  const confirmSaveToKB = async () => {
    if (!saveToKBTarget) return

    setIsSavingToKB(true)
    try {
      const result = await conversationsAPI.saveToKnowledgeBase(saveToKBTarget.id)
      toast.success('Saved to knowledge base', {
        description: result.filename,
      })
      setSaveToKBModalOpen(false)
      setSaveToKBTarget(null)
    } catch (error: unknown) {
      const err = error as { response?: { status?: number; data?: { existing_filename?: string } } }
      if (err.response?.status === 409) {
        toast.error('Already saved', {
          description: `This conversation was already saved as ${err.response?.data?.existing_filename}`,
        })
      } else {
        toast.error('Failed to save', {
          description: 'Could not save conversation to knowledge base',
        })
      }
    } finally {
      setIsSavingToKB(false)
    }
  }

  return (
    <TooltipProvider>
      <div className="flex-1 flex flex-col min-h-0 mt-4 overflow-hidden border-t border-border/50">
        {/* Chats Section */}
        <Collapsible
          open={isChatsExpanded}
          onOpenChange={toggleChatsExpanded}
          className="flex flex-col min-h-0 flex-1"
        >
          <div className="flex-shrink-0 mx-2 flex items-center gap-1 pt-2">
            <CollapsibleTrigger asChild>
              <button
                className="flex-1 px-3 py-2 flex items-center gap-2 hover:bg-muted transition-colors rounded-md"
              >
                <MessageSquare className="h-3.5 w-3.5 text-muted-foreground/70" />
                <span className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider flex-1 text-left">Chats</span>
                <ChevronDown className={cn(
                  "h-3 w-3 text-muted-foreground/50 transition-transform duration-200",
                  !isChatsExpanded && "-rotate-90"
                )} />
              </button>
            </CollapsibleTrigger>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={handleNewConversation}
                  className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground/70 hover:text-foreground"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">New conversation</TooltipContent>
            </Tooltip>
          </div>
          <CollapsibleContent className="flex-1 min-h-0 overflow-hidden">
            <ScrollArea className="h-full" onScrollCapture={handleScroll}>
              <div className="px-2 pt-0.5 pb-2" ref={scrollContainerRef}>
                {conversationItems.map((item) => {
                  const isActive = item.id === activeConversationId
                  const isGenerating = generatingTitleForId === item.id
                  // Use newConversation.name as the target for typewriter when generating
                  const targetTitle = isGenerating && newConversation?.name
                    ? newConversation.name
                    : item.name

                  return (
                    <ConversationRow
                      key={item.id}
                      item={item}
                      isActive={isActive}
                      isGenerating={isGenerating}
                      targetTitle={targetTitle}
                      onClick={() => handleConversationClick(item.id)}
                      onRename={handleRenameConversation}
                      onDelete={handleDeleteConversation}
                      onSaveToKnowledgeBase={handleSaveToKnowledgeBase}
                    />
                  )
                })}
                {/* Load more indicator */}
                {(storeHasMore || storeIsLoadingMore) && (
                  <div className="flex items-center justify-center py-2">
                    {storeIsLoadingMore ? (
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground/40" />
                    ) : (
                      <button
                        onClick={() => fetchMoreConversations()}
                        className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                      >
                        Load more
                      </button>
                    )}
                  </div>
                )}
              </div>
            </ScrollArea>
          </CollapsibleContent>
        </Collapsible>

        {/* Rename Modal */}
        <Dialog open={renameModalOpen} onOpenChange={setRenameModalOpen}>
          <DialogContent className="sm:max-w-[400px]">
            <DialogHeader>
              <DialogTitle>Rename Conversation</DialogTitle>
              <DialogDescription>
                Enter a new name for this conversation.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Conversation name"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    confirmRename()
                  }
                }}
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRenameModalOpen(false)}>
                Cancel
              </Button>
              <Button onClick={confirmRename} disabled={!newName.trim()}>
                Rename
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Delete Confirmation Modal */}
        <ConfirmDeleteModal
          isOpen={deleteModalOpen}
          onClose={() => setDeleteModalOpen(false)}
          onConfirm={confirmDelete}
          title="Delete Conversation"
          description="Are you sure you want to delete this conversation? This action cannot be undone."
        />

        {/* Save to Knowledge Base Confirmation Modal */}
        <Dialog open={saveToKBModalOpen} onOpenChange={setSaveToKBModalOpen}>
          <DialogContent className="sm:max-w-[400px]">
            <DialogHeader>
              <DialogTitle>Save to Knowledge Base</DialogTitle>
              <DialogDescription>
                Save "{saveToKBTarget?.name}" to your knowledge base? This will make the conversation content searchable by AI.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setSaveToKBModalOpen(false)} disabled={isSavingToKB}>
                Cancel
              </Button>
              <Button onClick={confirmSaveToKB} disabled={isSavingToKB}>
                {isSavingToKB ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <BookOpen className="h-4 w-4 mr-2" />
                    Save
                  </>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </TooltipProvider>
  )
}
