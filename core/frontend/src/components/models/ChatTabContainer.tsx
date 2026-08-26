/**
 * ChatTabContainer Component
 *
 * Lightweight tab container for multi-chat comparison mode.
 * Renders a tab bar for switching between chats and wraps multiple
 * ImmersiveChatView instances, showing/hiding them via CSS.
 *
 * Key design decisions:
 * - Tab tracking by ID (not index) for stability
 * - CSS hidden (not unmount) to preserve scroll position and state
 * - Each tab has its own ImmersiveChatView with full feature parity
 */

import { memo, useCallback, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Minimize2, Plus, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ModelIcon } from './ModelIcon'
import { ImmersiveChatView } from './ImmersiveChatView'
import { removeProviderPrefix } from '@/lib/model-utils'
import type { Chat, Model, Message, ModelParameters, Attachment, Filters, ToolExecutedHandler } from './types'
import type { ModelCatalogEntry } from '@/types/models'
import type { FeatureState } from './GlobalFeatureToggles'
import type { NormalizedCostEstimate } from '@/api/llm'
import type { MCPServer } from '@/api/mcp'

/**
 * Props for a single ImmersiveChatView instance.
 * This is the full set of props that ImmersiveChatView expects.
 */
export interface ImmersiveChatViewProps {
  chat: Chat
  models: ModelCatalogEntry[]
  onModelSelect: (model: Model) => void
  onSendMessage: (content: string, attachments?: Attachment[]) => Promise<void>
  onUpdateMessages: (messages: Message[]) => void
  onCancel: () => void
  canCancel: boolean
  onExitImmersive?: () => void
  onParametersChange: (params: ModelParameters) => void
  onToolExecuted?: ToolExecutedHandler
  onAddChat?: () => void
  showFilters?: boolean
  onToggleFilters?: () => void
  hasActiveFilters?: boolean
  filters?: Filters
  onFiltersChange?: (filters: Filters) => void
  providers?: string[]
  recentModelIds?: string[]
  webSearchState?: FeatureState
  onToggleWebSearch?: () => void
  hasWebSearchSupport?: boolean
  reasoningState?: FeatureState
  onToggleReasoning?: () => void
  hasReasoningSupport?: boolean
  mcpToolsState?: FeatureState
  onToggleMCPTools?: () => void
  hasFunctionSupport?: boolean
  fileToolsState?: FeatureState
  onToggleFileTools?: () => void
  imageGenerationState?: FeatureState
  onToggleImageGeneration?: () => void
  videoGenerationState?: FeatureState
  onToggleVideoGeneration?: () => void
  sparksState?: FeatureState
  onToggleSparks?: () => void
  knowledgeBaseState?: FeatureState
  onToggleKnowledgeBase?: () => void
  hasKnowledgeBaseSupport?: boolean
  activeServers?: MCPServer[]
  estimatedCosts?: NormalizedCostEstimate | null
  onEstimateCost?: (text: string) => Promise<void>
  isEstimating?: boolean
  setEstimatedCost?: (cost: NormalizedCostEstimate | null) => void
  attachments: Attachment[]
  onAddAttachment: (attachment: Attachment) => void
  onRemoveAttachment: (id: string) => void
  hasVisionSupport: boolean
  hasPDFSupport: boolean
  onFilterByCapability?: (modality: string) => void
  activeFilters?: string[]
  isDropOver?: boolean
  onDragOver?: (e: React.DragEvent<HTMLDivElement>) => void
  onDragLeave?: (e: React.DragEvent<HTMLDivElement>) => void
  onDrop?: (e: React.DragEvent<HTMLDivElement>) => void | Promise<void>
  onPaste?: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void | Promise<void>
  conversationId: string
  onSuggestionClick?: (suggestion: string) => void
  onClearChat?: (deleteWorkspace?: boolean) => void
  onShowClearDialog?: () => void
  onShowParametersDialog?: () => void
  onCopyResponses?: () => void
  onCopyMetadata?: () => void
  onExportResponses?: () => void
  onExportMetadata?: () => void
  onUpdateChat?: (data: Partial<Chat>) => void
  headerCenterContent?: React.ReactNode
  onRemoveChat?: () => void
  canRemoveChat?: boolean
  // All chats in multi-chat mode (for IDE quick switcher)
  allChats?: Chat[]
  // Spark ignite support (in-chat)
  onIgnite?: (sparkId: string, sparkTitle: string) => void
  // Spark auto-fix support (in-chat)
  sendSparkFixRequest?: (
    content: string,
    sparkFixRequest: { spark_id: string; spark_title: string; error: string }
  ) => Promise<void>
}

interface ChatTabContainerProps {
  chats: Chat[]
  conversationId: string
  activeTabId: string
  onActiveTabChange: (chatId: string) => void
  seenResponseCounts: Record<string, number>
  onAddChat: () => void
  onRemoveChat: (chatId: string) => void
  onExitImmersive: () => void
  /** Factory function to get ImmersiveChatView props for a specific chat */
  getImmersiveChatViewProps: (chatId: string) => ImmersiveChatViewProps
}

export const ChatTabContainer = memo(function ChatTabContainer({
  chats,
  conversationId,
  activeTabId,
  onActiveTabChange,
  seenResponseCounts,
  onAddChat,
  onRemoveChat,
  onExitImmersive,
  getImmersiveChatViewProps,
}: ChatTabContainerProps) {
  // Calculate unread count for a chat
  const getUnreadCount = useCallback(
    (chat: Chat): number => {
      const responseCount = chat.messages.filter((m) => m.role === 'assistant').length
      const seenCount = seenResponseCounts[chat.id] || 0
      return Math.max(0, responseCount - seenCount)
    },
    [seenResponseCounts]
  )

  // Tab bar component to pass to ImmersiveChatView's header
  const tabBar = useMemo(() => (
    <div className="flex items-center gap-2 min-w-0 max-w-full">
      <div className="flex items-center rounded-full bg-muted/50 min-w-0 max-w-full overflow-hidden">
        <div className="flex items-center gap-1 px-3 py-1 overflow-x-auto scrollbar-none">
          {chats.map((chat) => {
            const isActive = chat.id === activeTabId
            const isLoading = chat.isLoading
            const unreadCount = getUnreadCount(chat)
            const hasUnread = unreadCount > 0 && !isActive
            const responseCount = chat.messages.filter((m) => m.role === 'assistant').length

            return (
              <TooltipProvider key={chat.id}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="relative group flex-shrink-0">
                      <button
                        onClick={() => onActiveTabChange(chat.id)}
                        className={cn(
                          'relative flex items-center justify-center w-8 h-8 rounded-full transition-all',
                          isActive ? 'bg-accent' : 'hover:bg-muted'
                        )}
                      >
                        {chat.model ? (
                          <ModelIcon
                            modelName={chat.model.name}
                            modelId={chat.model.model_id}
                            provider={chat.model.provider}
                            modelIconSlug={chat.model.model_icon_slug}
                            modelIconUrl={chat.model.model_icon_url}
                            providerIconSlug={chat.model.provider_icon_slug}
                            providerIconUrl={chat.model.provider_icon_url}
                            size={18}
                            showTooltip={false}
                          />
                        ) : (
                          <div className="w-[18px] h-[18px] rounded-full bg-muted-foreground/30" />
                        )}

                        {/* Loading indicator - hidden when remove button shows */}
                        {isLoading && (
                          <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-primary rounded-full animate-pulse group-hover:opacity-0 transition-opacity" />
                        )}

                        {/* Unread count badge - hidden when remove button shows */}
                        {hasUnread && !isLoading && (
                          <span className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 bg-primary text-primary-foreground text-[10px] font-medium rounded-full flex items-center justify-center group-hover:opacity-0 transition-opacity">
                            {unreadCount}
                          </span>
                        )}
                      </button>

                      {/* Remove button - appears on hover, top right (desktop only) */}
                      {chats.length > 1 && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            onRemoveChat(chat.id)
                          }}
                          className="hidden md:flex absolute -top-1 -right-1 w-4 h-4 rounded-full bg-muted-foreground/80 hover:bg-destructive text-background items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <X className="h-2.5 w-2.5" />
                        </button>
                      )}
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <div className="text-xs">
                      <div className="font-medium">
                        {chat.model
                          ? removeProviderPrefix(chat.model.name, chat.model.provider)
                          : 'No model'}
                      </div>
                      {isLoading ? (
                        <div className="text-muted-foreground">Generating...</div>
                      ) : hasUnread ? (
                        <div className="text-muted-foreground">
                          {unreadCount} new response{unreadCount !== 1 ? 's' : ''}
                        </div>
                      ) : responseCount > 0 ? (
                        <div className="text-muted-foreground">
                          {responseCount} response{responseCount !== 1 ? 's' : ''}
                        </div>
                      ) : (
                        <div className="text-muted-foreground">No responses yet</div>
                      )}
                    </div>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )
          })}

          {/* Add button inline with tabs */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={onAddChat}
                  className="flex-shrink-0 p-1.5 rounded-full hover:bg-background/80 text-muted-foreground hover:text-foreground transition-colors"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent>Add model to compare</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>

      {/* Exit button */}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={onExitImmersive}
              className="hidden md:flex h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
            >
              <Minimize2 className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Side-by-side view</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  ), [chats, activeTabId, getUnreadCount, onActiveTabChange, onRemoveChat, onAddChat, onExitImmersive])

  return (
    <div className="h-full flex flex-col bg-background relative">
      {/* Tab Content - renders all ImmersiveChatView instances, showing only active */}
      <div className="flex-1 relative overflow-hidden">
        {chats.map((chat) => {
          const isActive = chat.id === activeTabId
          const props = getImmersiveChatViewProps(chat.id)

          return (
            <div
              key={chat.id}
              className={cn(
                'absolute inset-0',
                isActive ? 'visible z-10' : 'invisible z-0'
              )}
            >
              <ImmersiveChatView
                {...props}
                // Don't show exit button on individual chats - it's in the tab bar
                onExitImmersive={undefined}
                // Don't show add chat button on individual chats - it's in the tab bar
                onAddChat={undefined}
                // Pass the tab bar to render in the header center
                headerCenterContent={tabBar}
                // Multi-chat mode: allow removing this chat via mobile menu
                onRemoveChat={() => onRemoveChat(chat.id)}
                canRemoveChat={chats.length > 1}
                // Pass all chats for IDE quick switcher
                allChats={chats}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
})
