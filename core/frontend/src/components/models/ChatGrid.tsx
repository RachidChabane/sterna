/**
 * ChatGrid Component
 *
 * A clean, responsive grid layout for multi-chat comparison.
 * Features:
 * - 2 columns on desktop, 1 on tablet/mobile
 * - Simple header with title, options menu, and add button
 * - Creations panel toggle for sparks/images/videos
 * - Single shared floating input at bottom
 * - "Add Chat" card when below MAX_CHATS
 */

import { memo, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Plus,
  Maximize2,
  GalleryVerticalEnd,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import { ChatGridCard } from './ChatGridCard'
import type { ChatGridCardProps } from './ChatGridCard'
import { MessageInput } from './MessageInput'
import { MAX_CHATS } from './constants'
import type { Chat, Model, Attachment } from './types'
import type { FeatureState } from './GlobalFeatureToggles'
import { useVerificationGuard } from '@/components/auth/VerificationGate'

interface ChatGridProps {
  chats: Chat[]
  maxChats?: number
  onAddChat: () => void
  onRemoveChat: (chatId: string) => void
  onEnterImmersive: () => void
  /** Factory function to get ChatGridCard props for a specific chat */
  getChatGridCardProps: (chatId: string) => ChatGridCardProps

  // Shared input props
  onSendMessage: (content: string, attachments?: Attachment[]) => Promise<void>
  onCancel: () => void
  canCancel: boolean
  isAnyLoading: boolean
  hasAnyModel: boolean
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
  onPaste?: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void

  // Feature toggles for shared input
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
  activeServers?: any[]

}

export const ChatGrid = memo(function ChatGrid({
  chats,
  maxChats = MAX_CHATS,
  onAddChat,
  onRemoveChat,
  onEnterImmersive,
  getChatGridCardProps,
  // Shared input props
  onSendMessage,
  onCancel,
  canCancel,
  isAnyLoading,
  hasAnyModel,
  attachments,
  onAddAttachment,
  onRemoveAttachment,
  hasVisionSupport,
  hasPDFSupport,
  onFilterByCapability,
  activeFilters,
  isDropOver,
  onDragOver,
  onDragLeave,
  onDrop,
  onPaste,
  webSearchState,
  onToggleWebSearch,
  hasWebSearchSupport,
  reasoningState,
  onToggleReasoning,
  hasReasoningSupport,
  mcpToolsState,
  onToggleMCPTools,
  hasFunctionSupport,
  fileToolsState,
  onToggleFileTools,
  imageGenerationState,
  onToggleImageGeneration,
  videoGenerationState,
  onToggleVideoGeneration,
  sparksState,
  onToggleSparks,
  knowledgeBaseState,
  onToggleKnowledgeBase,
  hasKnowledgeBaseSupport,
  activeServers,
}: ChatGridProps) {
  const canAddChat = chats.length < maxChats
  const { isPanelOpen: isArtifactsPanelOpen, imageCount, videoCount } = useArtifactsPanelStore()

  const { guard } = useVerificationGuard()
  const guardedSendMessage = useMemo(
    () => guard(onSendMessage, 'send messages'),
    [guard, onSendMessage],
  )

  // Count total sparks across all chats
  const totalSparks = useMemo(() => {
    return chats.reduce((acc, chat) => {
      const messageSparks = (chat.messages || [])
        .filter((m) => m.sparks && m.sparks.length > 0)
        .flatMap((m) => m.sparks || [])
      const chatSparks = chat.sparks || []
      return acc + messageSparks.length + chatSparks.length
    }, 0)
  }, [chats])

  const totalArtifacts = totalSparks + imageCount + videoCount

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background relative">
      {/* Header - compact */}
      <header className="flex-shrink-0 flex items-center justify-between px-3 py-2 border-b">
        <div className="flex items-center gap-2">
          <h1 className="text-base font-semibold">Compare</h1>
          <span className="text-xs text-muted-foreground">
            {chats.length} model{chats.length !== 1 ? 's' : ''}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {/* Creations/Artifacts panel toggle */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => useArtifactsPanelStore.getState().setPanelOpen(!isArtifactsPanelOpen)}
                  className={cn(
                    "h-7 px-2 gap-1.5",
                    isArtifactsPanelOpen
                      ? "text-brand-500 hover:text-brand-600"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <GalleryVerticalEnd className="h-3.5 w-3.5" />
                  {totalArtifacts > 0 && (
                    <span className="text-xs">{totalArtifacts}</span>
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {isArtifactsPanelOpen ? 'Hide Creations' : 'Show Creations'}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onEnterImmersive}
                  className="h-7 px-2 gap-1.5"
                >
                  <Maximize2 className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline text-xs">Focus</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Focus mode with tabs</TooltipContent>
            </Tooltip>
          </TooltipProvider>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="default"
                  size="sm"
                  onClick={onAddChat}
                  disabled={!canAddChat}
                  className="h-7 px-2 gap-1.5"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline text-xs">Add</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {canAddChat ? 'Add model' : `Max ${maxChats} reached`}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </header>

      {/* Grid container - with bottom padding for floating input */}
      <div className="flex-1 overflow-auto p-2 pb-20">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
          {chats.map((chat) => {
            const props = getChatGridCardProps(chat.id)
            return (
              <div
                key={chat.id}
                className="h-[calc(50vh-5rem)] min-h-[220px]"
              >
                <ChatGridCard
                  {...props}
                  onRemove={() => onRemoveChat(chat.id)}
                  showRemove={chats.length > 1}
                />
              </div>
            )
          })}

          {canAddChat && (
            <div className="h-[calc(50vh-5rem)] min-h-[220px]">
              <button
                onClick={onAddChat}
                className={cn(
                  "w-full h-full rounded-xl border-2 border-dashed border-muted-foreground/20",
                  "flex flex-col items-center justify-center gap-2",
                  "text-muted-foreground hover:text-foreground",
                  "hover:border-muted-foreground/40 hover:bg-muted/20",
                  "transition-all duration-200"
                )}
              >
                <div className="w-10 h-10 rounded-full bg-muted/50 flex items-center justify-center">
                  <Plus className="h-5 w-5" />
                </div>
                <p className="text-sm font-medium">Add Model</p>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Shared floating input - positioned at bottom */}
      <div className="absolute bottom-0 left-0 right-0 p-3 pointer-events-none bg-gradient-to-t from-background via-background to-transparent">
        <div className="max-w-3xl mx-auto pointer-events-auto">
          <div className="rounded-2xl bg-card/95 backdrop-blur-md border border-border/50 shadow-lg">
            <MessageInput
              mode="synced"
              chats={chats}
              chatsWithModels={chats.filter(c => c.model !== null).length}
              disabled={isAnyLoading}
              attachments={attachments}
              onRemoveAttachment={onRemoveAttachment}
              onAddAttachment={onAddAttachment}
              hasVisionSupport={hasVisionSupport}
              hasPDFSupport={hasPDFSupport}
              onFilterByCapability={onFilterByCapability}
              activeFilters={activeFilters}
              isDropOver={isDropOver ?? false}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onPaste={onPaste}
              onSend={(content) => guardedSendMessage(content, attachments)}
              onCancel={onCancel}
              canCancel={canCancel}
              webSearchState={webSearchState}
              onToggleWebSearch={onToggleWebSearch}
              hasWebSearchSupport={hasWebSearchSupport}
              reasoningState={reasoningState}
              onToggleReasoning={onToggleReasoning}
              hasReasoningSupport={hasReasoningSupport}
              mcpToolsState={mcpToolsState}
              onToggleMCPTools={onToggleMCPTools}
              hasFunctionSupport={hasFunctionSupport}
              fileToolsState={fileToolsState}
              onToggleFileTools={onToggleFileTools}
              imageGenerationState={imageGenerationState}
              onToggleImageGeneration={onToggleImageGeneration}
              videoGenerationState={videoGenerationState}
              onToggleVideoGeneration={onToggleVideoGeneration}
              sparksState={sparksState}
              onToggleSparks={onToggleSparks}
              knowledgeBaseState={knowledgeBaseState}
              onToggleKnowledgeBase={onToggleKnowledgeBase}
              hasKnowledgeBaseSupport={hasKnowledgeBaseSupport}
              activeServers={activeServers}
              floatingMode
            />
          </div>
        </div>
      </div>
    </div>
  )
})

// Re-export ChatGridCardProps for use by ModelComparisonPage
export type { ChatGridCardProps }
