/**
 * ImmersiveChatView Component
 *
 * A fullscreen, focused chat experience similar to ChatGPT/Claude/Gemini.
 * Features:
 * - Centered message container with max-width
 * - Floating input with integrated controls
 * - Clean, distraction-free design
 */

import { memo, useCallback, useMemo, useRef, useEffect, useState } from 'react'
import { useVoiceConversation } from '@/hooks/useVoiceConversation'
import { ImagePreviewModal } from './ImagePreviewModal'
import { VisuallyHidden } from '@radix-ui/react-visually-hidden'
import { cn } from '@/lib/utils'
import { ModelDetailsModal } from './ModelDetailsModal'
import { FilePreviewModal } from './FilePreviewModal'
import { PdfPreviewModal } from './PdfPreviewModal'
import { MessageList } from './MessageList'
import { MessageInput } from './MessageInput'
import type { FeatureState } from './GlobalFeatureToggles'
import { ChatStates } from './ChatStates'
import { SuggestedQuestionsCarousel } from './SuggestedQuestionsCarousel'
import { CostEstimationDisplay } from './CostEstimationDisplay'
import { ProviderGreeting } from './ProviderGreeting'
import { CodeEditorModal } from '@/components/sandbox'
import { ChatInstructionsSheet } from './ChatInstructionsSheet'
import { ChatPanelProvider } from './ChatPanelContext'
import { SparkAutoFixProvider, type SparkFixRequest } from './SparkAutoFixContext'
import { VoiceConversationOverlay } from './VoiceConversationOverlay'
import { useAuthStore } from '@/store/authStore'
import { extractTextFromContent } from '@/utils/chatUtils'
import { useProjectPanelStore } from '@/store/projectPanelStore'
import { ArtifactsSidePanel } from './ArtifactsSidePanel'
import { ProjectStatusSidePanel } from './ProjectStatusSidePanel'
import { PreviewSidePanel } from '@/components/preview/PreviewSidePanel'
import { useUIStore } from '@/store/uiStore'
import { removeProviderPrefix } from '@/lib/model-utils'
import type { Chat, Model, Message, ModelParameters, Attachment, Filters, ToolExecutedHandler } from './types'
import type { NormalizedCostEstimate } from '@/api/llm'
import type { MCPServer } from '@/api/mcp'
import type { ModelCatalogEntry } from '@/types/models'
import type { CachedAttachment } from '@/utils/attachmentCache'
import { useVerificationGuard } from '@/components/auth/VerificationGate'
import { ImmersiveChatHeader } from './ImmersiveChatHeader'
import { MobileModelSheet } from './MobileModelSheet'
import { AllAttachmentsModal } from './AllAttachmentsModal'
import { SaveToKnowledgeBaseDialog } from './SaveToKnowledgeBaseDialog'
import { useChatAutoScroll } from './hooks/useChatAutoScroll'
import { useAttachmentPreviews } from './hooks/useAttachmentPreviews'
import { useWorkspaceDetection } from './hooks/useWorkspaceDetection'
import { useModelDetailsPanel } from './hooks/useModelDetailsPanel'
import { useSaveToKnowledgeBase } from './hooks/useSaveToKnowledgeBase'
import {
  formatCost,
  formatLatency,
  copyMessageContent,
  copyMessageMetadata,
  exportMessageContent,
  exportMessageMetadata,
} from './chatMessageActions'

interface ImmersiveChatViewProps {
  // Chat data
  chat: Chat
  models: ModelCatalogEntry[]

  // Handlers
  onModelSelect: (model: Model) => void
  onSendMessage: (content: string, attachments?: Attachment[]) => Promise<void>
  onUpdateMessages: (messages: Message[]) => void
  onCancel: () => void
  canCancel: boolean
  onExitImmersive?: () => void
  onParametersChange: (params: ModelParameters) => void
  onToolExecuted?: ToolExecutedHandler
  onAddChat?: () => void
  // Model selection
  showFilters?: boolean
  onToggleFilters?: () => void
  hasActiveFilters?: boolean
  filters?: Filters
  onFiltersChange?: (filters: Filters) => void
  providers?: string[]
  recentModelIds?: string[]

  // Feature toggles
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
  // Cost estimation
  estimatedCosts?: NormalizedCostEstimate | null
  onEstimateCost?: (text: string) => Promise<void>
  isEstimating?: boolean
  setEstimatedCost?: (cost: NormalizedCostEstimate | null) => void

  // Attachments
  attachments: Attachment[]
  onAddAttachment: (attachment: Attachment) => void
  onRemoveAttachment: (id: string) => void
  hasVisionSupport: boolean
  hasPDFSupport: boolean
  onFilterByCapability?: (modality: string) => void
  activeFilters?: string[]

  // Drag and drop
  isDropOver?: boolean
  onDragOver?: (e: React.DragEvent<HTMLDivElement>) => void
  onDragLeave?: (e: React.DragEvent<HTMLDivElement>) => void
  onDrop?: (e: React.DragEvent<HTMLDivElement>) => void | Promise<void>
  onPaste?: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void

  // Conversation
  conversationId: string

  // Suggestion click
  onSuggestionClick?: (suggestion: string) => void

  // Options menu handlers
  onClearChat?: (deleteWorkspace?: boolean) => void
  onShowClearDialog?: () => void
  onShowParametersDialog?: () => void
  onCopyResponses?: () => void
  onCopyMetadata?: () => void
  onExportResponses?: () => void
  onExportMetadata?: () => void

  // Chat update handler (for instructions, etc.)
  onUpdateChat?: (data: Partial<Chat>) => void

  // Optional content to render in the center of the header (e.g., multi-chat tab bar)
  headerCenterContent?: React.ReactNode

  // Multi-chat mode: remove current chat (shown in mobile menu)
  onRemoveChat?: () => void
  canRemoveChat?: boolean

  // All chats in multi-chat mode (for IDE quick switcher)
  allChats?: Chat[]

  // Spark auto-fix support
  sendSparkFixRequest?: (content: string, sparkFixRequest: SparkFixRequest) => Promise<void>
  // Spark ignite support (in-chat)
  onIgnite?: (sparkId: string, sparkTitle: string) => void
}

export const ImmersiveChatView = memo(function ImmersiveChatView({
  chat,
  models,
  onModelSelect,
  onSendMessage,
  onUpdateMessages,
  onCancel,
  canCancel,
  onExitImmersive,
  onParametersChange,
  onToolExecuted,
  onAddChat,
  showFilters,
  onToggleFilters,
  hasActiveFilters,
  filters,
  onFiltersChange,
  providers,
  recentModelIds,
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
  hasKnowledgeBaseSupport = false,
  activeServers,
  estimatedCosts,
  onEstimateCost,
  isEstimating,
  setEstimatedCost,
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
  conversationId,
  onSuggestionClick,
  onClearChat,
  onShowClearDialog,
  onShowParametersDialog,
  onCopyResponses,
  onCopyMetadata,
  onExportResponses,
  onExportMetadata,
  onUpdateChat,
  headerCenterContent,
  onRemoveChat,
  canRemoveChat,
  allChats,
  sendSparkFixRequest,
  onIgnite,
}: ImmersiveChatViewProps) {
  // Debug logging to trace re-renders
  

  const { user } = useAuthStore()
  const { clonedRepo } = useProjectPanelStore()
  const isMobile = useUIStore((state) => state.isMobile)

  // Aggregate sparks from all messages and chat-level sparks
  const currentChatSparks = useMemo(() => {
    // Collect sparks from messages
    const messageSparks = (chat.messages || [])
      .filter((m) => m.sparks && m.sparks.length > 0)
      .flatMap((m) => m.sparks || [])

    // Include chat-level sparks (for sparks not linked to specific messages)
    const chatSparks = chat.sparks || []

    // Combine and deduplicate by ID
    const allSparks = [...messageSparks, ...chatSparks]
    const uniqueSparks = allSparks.filter((spark, index, self) =>
      index === self.findIndex((s) => s.id === spark.id)
    )

    // Filter out older versions - only show sparks that don't have a newer version
    // A spark has a newer version if another spark has it as parent_id
    const parentIds = new Set(uniqueSparks.map((s) => s.parent_id).filter(Boolean))
    const latestSparks = uniqueSparks.filter((spark) => !parentIds.has(spark.id))

    return latestSparks
  }, [chat.messages, chat.sparks])
  const [codeEditorOpen, setCodeEditorOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')

  // Detect whether this chat has workspace files (for "Open IDE" button)
  const hasWorkspace = useWorkspaceDetection({
    messages: chat.messages,
    clonedRepo,
    userId: user?.id,
    chatId: chat?.id,
  })

  // Listen for setInputMessage events from the Project panel (e.g., "Implement" button)
  useEffect(() => {
    const handleSetInputMessage = (event: CustomEvent<{ message: string }>) => {
      setInputValue(event.detail.message)
    }
    const handleOpenCodeEditor = () => setCodeEditorOpen(true)
    window.addEventListener('setInputMessage', handleSetInputMessage as EventListener)
    window.addEventListener('openCodeEditor', handleOpenCodeEditor)
    return () => {
      window.removeEventListener('setInputMessage', handleSetInputMessage as EventListener)
      window.removeEventListener('openCodeEditor', handleOpenCodeEditor)
    }
  }, [])

  const {
    isModelDetailsOpen,
    setIsModelDetailsOpen,
    selectedModelDetails,
    handleOpenModelDetails,
  } = useModelDetailsPanel(chat.model)
  const [mobileModelSheetOpen, setMobileModelSheetOpen] = useState(false)
  const [voiceOverlayOpen, setVoiceOverlayOpen] = useState(false)
  const [instructionsSheetOpen, setInstructionsSheetOpen] = useState(false)
  const {
    isSavingToKnowledgeBase,
    showSaveToKBDialog,
    setShowSaveToKBDialog,
    handleSaveToKnowledgeBase,
    confirmSaveToKnowledgeBase,
  } = useSaveToKnowledgeBase(conversationId)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const hasMessages = chat.messages.length > 0

  // Detect streaming: last assistant message exists with no cost/tokens yet
  const lastAssistantMsg = useMemo(() => {
    for (let i = chat.messages.length - 1; i >= 0; i--) {
      if (chat.messages[i].role === 'assistant') return chat.messages[i]
    }
    return null
  }, [chat.messages])

  const isStreaming = !!(
    lastAssistantMsg &&
    !lastAssistantMsg.isError &&
    !lastAssistantMsg.isUnsupported &&
    !lastAssistantMsg.cost &&
    !lastAssistantMsg.tokens &&
    !lastAssistantMsg.is_stopped
  )

  // Text reveal state: typewriter continues after API streaming ends
  const [isTextRevealing, setIsTextRevealing] = useState(false)
  const stopRevealRef = useRef(false)

  // Reset stopReveal when a new message starts streaming
  useEffect(() => {
    if (isStreaming) stopRevealRef.current = false
  }, [isStreaming])

  const handleTextRevealChange = useCallback((revealing: boolean) => {
    setIsTextRevealing(revealing)
  }, [])

  const isGenerating = chat.isLoading || isStreaming || isTextRevealing

  // Voice conversation callback for auto-sending transcribed messages
  const handleVoiceSend = useCallback(async (content: string) => {
    
    
    
    
    

    try {
      // Send the raw transcript - no prefix needed
      
      await onSendMessage(content, []) // No attachments for voice messages
      
    } catch (error) {
      console.error('[ImmersiveChatView] 📤 Error sending voice message:', error)
    }
  }, [onSendMessage, chat.model])

  // Voice Conversation hook - used for message-level TTS (read aloud in message list)
  const {
    isSpeaking,
    isTTSLoading,
    speakText: speak,
    stopSpeaking,
  } = useVoiceConversation({
    messages: chat.messages,
    isGenerating: chat.isLoading,
  })

  // TTS is always supported with browser fallback
  const isTTSSupported = true

  // Handler to open voice conversation overlay (used by voice button in MessageInput)
  const handleActivateVoice = useCallback(async () => {
    // Open the fullscreen voice conversation overlay
    setVoiceOverlayOpen(true)
  }, [])

  // Handle suggestion click - fill the input
  const handleSuggestionClick = useCallback((suggestion: string) => {
    setInputValue(suggestion)
    // Also call the parent handler if provided
    onSuggestionClick?.(suggestion)
  }, [onSuggestionClick])

  // Ctrl+L scroll behaviour (pin the last user message to the top while its
  // response streams in, then follow the bottom) — see useChatAutoScroll.
  const { scrollContainerRef, contentEndRef, spacerRef } = useChatAutoScroll({
    messages: chat.messages,
    isGenerating,
    conversationId,
  })

  // Verification guard intercepts send for unverified users
  const { guard } = useVerificationGuard()

  // Handle send
  const handleSend = useCallback(async (content: string) => {

    try {
      await onSendMessage(content, attachments)

    } catch (error) {
      console.error('[ImmersiveChatView] Error in onSendMessage:', error)
    }
    setInputValue('') // Clear external value after sending
  }, [onSendMessage, attachments])

  const guardedSend = useMemo(
    () => guard(handleSend, 'send messages'),
    [guard, handleSend],
  )

  // Extended cancel: also stops the typewriter reveal
  const handleCancel = useCallback(() => {
    if (canCancel) {
      onCancel()
    }
    // Also stop the typewriter
    stopRevealRef.current = true
    setIsTextRevealing(false)
  }, [canCancel, onCancel])

  // Show stop button during API streaming OR typewriter reveal
  const showCancel = canCancel || isTextRevealing

  // Message container ref for context
  const messagesContainerRef = useRef<HTMLDivElement>(null)

  // Context handlers
  const handleRetry = useCallback(async (assistantMessageIndex: number) => {
    // Find the user message before this assistant message and resend
    const messages = chat.messages
    let userMessageIndex = assistantMessageIndex - 1
    while (userMessageIndex >= 0 && messages[userMessageIndex].role !== 'user') {
      userMessageIndex--
    }
    if (userMessageIndex >= 0) {
      const userMessage = messages[userMessageIndex]
      const userMessageText = extractTextFromContent(userMessage.content)
      const userAttachments = (userMessage.attachments || []) as Attachment[]

      // Remove BOTH the user message and assistant message (and any notices in between)
      const toRemove = new Set<number>([userMessageIndex, assistantMessageIndex])
      for (let i = userMessageIndex + 1; i < assistantMessageIndex; i++) {
        const m = messages[i]
        if (m.role === 'assistant' && m.isUnsupported) toRemove.add(i)
      }
      const updatedMessages = messages.filter((_, idx) => !toRemove.has(idx))

      // Update messages first
      onUpdateMessages(updatedMessages)

      // Wait for React to apply the state update before resending
      await new Promise(resolve => setTimeout(resolve, 0))

      // Resend the user message
      await onSendMessage(userMessageText, userAttachments.length ? userAttachments : undefined)
    }
  }, [chat.messages, onUpdateMessages, onSendMessage])

  const handleEditMessage = useCallback(async (messageIndex: number, newContent: string) => {
    // Get the message being edited
    const editedMessage = chat.messages[messageIndex]
    if (!editedMessage || editedMessage.role !== 'user') return

    // Get attachments from the message being edited
    const userAttachments = (editedMessage.attachments || []) as Attachment[]

    // Delete ALL messages after the edited message (complete rewind)
    const updatedMessages = chat.messages.slice(0, messageIndex)

    // Update messages to remove everything from the edited message onwards
    onUpdateMessages(updatedMessages)

    // Wait for React to apply the state update
    await new Promise(resolve => setTimeout(resolve, 0))

    // Send the edited message as a new message
    await onSendMessage(newContent, userAttachments)
  }, [chat.messages, onUpdateMessages, onSendMessage])

  const {
    imageGalleryOpen,
    setImageGalleryOpen,
    galleryImages,
    gallerySelectedIndex,
    setGallerySelectedIndex,
    isAllAttachmentsOpen,
    setIsAllAttachmentsOpen,
    allAttachments,
    isFilePreviewOpen,
    setIsFilePreviewOpen,
    previewFile,
    loadingFileId,
    isPdfOpen,
    setIsPdfOpen,
    pdfSrc,
    pdfName,
    loadedBlobUrls,
    loadingAssetIds,
    loadAssetAsBlobUrl,
    handleOpenImageGallery,
    handleOpenPdf,
    handleOpenTextFile,
    handleOpenAllAttachments,
  } = useAttachmentPreviews()

  // Check for issue context from ProjectStatusSidePanel (when implementing an issue)
  useEffect(() => {
    if (!conversationId) return

    const issueContextRaw = sessionStorage.getItem(`issue_context_${conversationId}`)
    if (issueContextRaw) {
      try {
        // Parse the structured context from the backend
        const context = JSON.parse(issueContextRaw)
        if (context.type === 'github_issue') {
          // Create a simple message referencing the issue
          // The LLM will use tools to fetch details and plan the implementation
          setInputValue(`Implement GitHub issue #${context.issue_number}: ${context.issue_title}`)
        }
      } catch {
        // Fallback for old format (plain text) - should not happen with new API
        setInputValue(issueContextRaw)
      }
      // Remove after use to prevent re-filling on refresh
      sessionStorage.removeItem(`issue_context_${conversationId}`)
    }
  }, [conversationId])

  // Pick up pending secondary picker after clone-and-navigate (repo picker flow)
  useEffect(() => {
    const pendingRaw = sessionStorage.getItem('mention_pending_secondary')
    if (!pendingRaw) return
    sessionStorage.removeItem('mention_pending_secondary')
    try {
      const { toolName, pickerType } = JSON.parse(pendingRaw)
      if (toolName) {
        setInputValue(`@${toolName} `)
        requestAnimationFrame(() => {
          window.dispatchEvent(new CustomEvent('triggerSecondaryPicker', {
            detail: { toolName, pickerType }
          }))
        })
      }
    } catch { /* ignore malformed data */ }
  }, [conversationId])

  // Create context value
  const chatPanelContextValue = useMemo(() => ({
    model: chat.model,
    messages: chat.messages,
    isLoading: chat.isLoading,
    isGenerating: chat.isLoading,
    user,
    conversationId,
    chatId: chat.id,
    syncMode: false,
    messagesContainer: messagesContainerRef.current,
    cachedAttachments: {},
    disabledChat: false,
    onUpdateMessages,
    onToolExecuted,
    onRetry: handleRetry,
    onEditMessage: handleEditMessage,
    onCopyContent: copyMessageContent,
    onCopyMetadata: copyMessageMetadata,
    onExportContent: exportMessageContent,
    onExportMetadata: exportMessageMetadata,
    onOpenModelDetails: handleOpenModelDetails,
    formatCost,
    formatLatency,
    onOpenImageGallery: handleOpenImageGallery,
    onOpenPdf: handleOpenPdf,
    onOpenTextFile: handleOpenTextFile,
    onOpenAllAttachments: handleOpenAllAttachments,
    // Text reveal state
    onTextRevealChange: handleTextRevealChange,
    stopRevealRef,
    // TTS props
    onSpeak: speak,
    onStopSpeaking: stopSpeaking,
    isSpeaking,
    isTTSLoading,
    isTTSSupported,
  }), [
    // copyMessageContent, copyMessageMetadata, exportMessageContent, exportMessageMetadata,
    // formatCost and formatLatency are module-level imports (chatMessageActions.ts) — stable
    // by construction, not reactive dependencies.
    chat.model, chat.messages, chat.isLoading, chat.id, user, conversationId,
    onUpdateMessages, onToolExecuted, handleRetry, handleEditMessage,
    handleOpenModelDetails, handleOpenImageGallery,
    handleOpenPdf, handleOpenTextFile, handleOpenAllAttachments,
    handleTextRevealChange,
    speak, stopSpeaking, isSpeaking, isTTSLoading, isTTSSupported
  ])

  // Consistent content width for visual harmony (832px = 52rem)
  // - Wide enough for code blocks without excessive wrapping (~90 chars)
  // - Comfortable for prose reading (~70-80 chars per line)
  // - Aligns with modern chat interfaces (Gemini-style)
  const contentWidthClass = "max-w-[52rem]"

  return (
    <div className="h-full flex flex-col bg-background relative">
      <ImmersiveChatHeader
        model={chat.model}
        models={models}
        onModelSelect={onModelSelect}
        showFilters={showFilters}
        onToggleFilters={onToggleFilters}
        hasActiveFilters={hasActiveFilters}
        filters={filters}
        onFiltersChange={onFiltersChange}
        providers={providers}
        recentModelIds={recentModelIds}
        headerCenterContent={headerCenterContent}
        onAddChat={onAddChat}
        hasWorkspace={hasWorkspace}
        onOpenCodeEditor={() => setCodeEditorOpen(true)}
        sparksCount={currentChatSparks.length}
        onRemoveChat={onRemoveChat}
        canRemoveChat={canRemoveChat}
        onOpenMobileModelSheet={() => setMobileModelSheetOpen(true)}
        onOpenInstructions={() => setInstructionsSheetOpen(true)}
        hasMessages={hasMessages}
        onSaveToKnowledgeBase={handleSaveToKnowledgeBase}
        isSavingToKnowledgeBase={isSavingToKnowledgeBase}
        onCopyResponses={onCopyResponses}
        onCopyMetadata={onCopyMetadata}
        onExportResponses={onExportResponses}
        onExportMetadata={onExportMetadata}
        onExitImmersive={onExitImmersive}
      />

      {/* Content wrapper - flex row for chat + artifacts panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main chat area - shrinks when artifacts panel opens */}
        <div className="flex-1 flex flex-col overflow-hidden relative">
          <div ref={scrollContainerRef} className="flex-1 overflow-y-auto pb-44">
            <div className={cn(contentWidthClass, "mx-auto px-6 py-8")}>
          {/* Empty state with provider-specific greeting */}
          {!hasMessages && !chat.isLoading && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
              {/* Provider-specific greeting */}
              <div className="mb-8">
                <ProviderGreeting
                  model={chat.model}
                  userName={user?.first_name || user?.full_name}
                  onModelClick={() => handleOpenModelDetails()}
                />
              </div>

              {/* Suggestions - same width as content for visual alignment */}
              {onSuggestionClick && attachments.length === 0 && (
                <div className="w-full">
                  <SuggestedQuestionsCarousel onSuggestionClick={handleSuggestionClick} />
                </div>
              )}
            </div>
          )}

          {/* Messages */}
          {hasMessages && (
            <ChatPanelProvider value={chatPanelContextValue}>
              {sendSparkFixRequest ? (
                <SparkAutoFixProvider
                  sendSparkFixRequest={sendSparkFixRequest}
                  sparksEnabled={sparksState?.enabled !== undefined && sparksState.enabled > 0}
                  isLoading={chat.isLoading}
                >
                  <MessageList />
                </SparkAutoFixProvider>
              ) : (
                <MessageList />
              )}
            </ChatPanelProvider>
          )}

          {/* Loading state and interrupted response warning */}
          <ChatStates
            messages={chat.messages}
            isLoading={chat.isLoading}
            canCancel={showCancel}
            onCancel={handleCancel}
            model={chat.model}
            syncMode={false}
            onOpenModelDetails={() => {}}
            suppressInterruptedWarning={false}
            emptyStateContent={<></>}  // Suppress duplicate suggested questions (we have carousel above)
            onResend={(message) => {
              // Resend the last user message
              onSendMessage(message, [])
            }}
          />

          {/* Marker for real content bottom (before spacer) — used for overflow detection */}
          <div ref={contentEndRef} style={{ overflowAnchor: 'none' }} />

          {/* Spacer: dynamically sized so the user can pin-scroll to the last user message
              but never into empty space. Height = max(0, visibleH - contentBelowUserMsg). */}
          <div ref={spacerRef} aria-hidden style={{ height: 0 }} />

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Floating input area - fixed on mobile (above nav), absolute on desktop */}
      <div
        className="fixed md:absolute left-0 right-0 bottom-0 pointer-events-none z-20"
        style={{
          bottom: 'var(--mobile-bottom-nav-height, 0px)',
        }}
      >
        <div className="bg-background pb-3 md:pb-5 px-4 md:px-6 pointer-events-auto">
          <div className={cn(contentWidthClass, "mx-auto")}>
            {/* Cost estimation */}
            {estimatedCosts && (
              <div className="mb-3">
                <CostEstimationDisplay
                  estimatedCosts={estimatedCosts}
                  attachments={attachments}
                  onClose={() => setEstimatedCost?.(null)}
                />
              </div>
            )}

            {/* Floating input container - elevated with subtle shadow */}
            <div className="rounded-2xl bg-card/98 backdrop-blur-md border border-border/40 shadow-lg shadow-black/5 dark:shadow-black/20">
              {/* Input */}
              <MessageInput
                mode="independent"
                model={chat.model}
                disabled={chat.isLoading || !chat.model}
                externalValue={inputValue}
                attachments={attachments}
                onRemoveAttachment={onRemoveAttachment}
                onAddAttachment={onAddAttachment}
                hasVisionSupport={hasVisionSupport}
                hasPDFSupport={hasPDFSupport}
                onFilterByCapability={onFilterByCapability}
                activeFilters={activeFilters}
                isDropOver={isDropOver}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
                onPaste={onPaste}
                onSend={guardedSend}
                onCancel={handleCancel}
                canCancel={showCancel}
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
                estimatedCost={estimatedCosts}
                setEstimatedCost={setEstimatedCost}
                chats={[chat]}
                chatsWithModels={chat.model ? 1 : 0}
                floatingMode={true}
                // Voice conversation - opens fullscreen overlay
                onActivateVoice={handleActivateVoice}
              />
            </div>
          </div>
        </div>
      </div>
    </div>

        {/* Artifacts Side Panel - right side, hidden on mobile (uses sheet instead) */}
        {!isMobile && <ArtifactsSidePanel chatId={chat.id} conversationId={conversationId} sparks={currentChatSparks} sendSparkFixRequest={sendSparkFixRequest} sparksEnabled={sparksState?.enabled !== undefined && sparksState.enabled > 0} isLoading={chat.isLoading} onIgnite={onIgnite} />}

        {/* Project Status Side Panel - right side */}
        {!isMobile && <ProjectStatusSidePanel conversationId={conversationId} chatId={chat.id} />}

        {/* Preview Side Panel - right side */}
        {!isMobile && <PreviewSidePanel conversationId={conversationId} chatId={chat.id} />}
      </div>

      {/* Mobile Artifacts Panel (Sheet) */}
      {isMobile && <ArtifactsSidePanel chatId={chat.id} conversationId={conversationId} sparks={currentChatSparks} sendSparkFixRequest={sendSparkFixRequest} sparksEnabled={sparksState?.enabled !== undefined && sparksState.enabled > 0} isLoading={chat.isLoading} onIgnite={onIgnite} />}

      {/* Mobile Project Panel (Sheet) */}
      {isMobile && <ProjectStatusSidePanel conversationId={conversationId} chatId={chat.id} />}

      {/* Mobile Preview Panel (Sheet) */}
      {isMobile && <PreviewSidePanel conversationId={conversationId} chatId={chat.id} />}

      {/* Code Editor Modal */}
      <CodeEditorModal
        userId={user?.id.toString()}
        chatId={chat.id}
        conversationId={conversationId}
        model={chat.model}
        open={codeEditorOpen}
        onOpenChange={setCodeEditorOpen}
        messages={chat.messages}
        chats={allChats}
      />

      {/* Save to Knowledge Base Confirmation Dialog */}
      <SaveToKnowledgeBaseDialog
        open={showSaveToKBDialog}
        onOpenChange={setShowSaveToKBDialog}
        isSaving={isSavingToKnowledgeBase}
        onConfirm={confirmSaveToKnowledgeBase}
      />

      {/* Model Details Modal */}
      <ModelDetailsModal
        isOpen={isModelDetailsOpen}
        onClose={() => setIsModelDetailsOpen(false)}
        model={selectedModelDetails}
        onSelectModel={(entry) => {
          const selected = models.find(m => m.model_id === entry.model_id)
          if (selected) {
            onModelSelect(selected)
          }
        }}
        selectedModelId={chat.model?.model_id}
      />

      {/* File Preview Modal */}
      {previewFile && (
        <FilePreviewModal
          isOpen={isFilePreviewOpen}
          onClose={() => setIsFilePreviewOpen(false)}
          fileName={previewFile.name}
          fileSize={previewFile.size}
          textContent={previewFile.content}
        />
      )}

      {/* PDF Preview Modal */}
      <PdfPreviewModal
        isOpen={isPdfOpen}
        onClose={() => setIsPdfOpen(false)}
        pdfSrc={pdfSrc}
        pdfName={pdfName}
      />

      {/* Image Gallery Modal */}
      <ImagePreviewModal
        isOpen={imageGalleryOpen}
        onClose={() => setImageGalleryOpen(false)}
        images={galleryImages}
        selectedIndex={gallerySelectedIndex}
        onIndexChange={setGallerySelectedIndex}
      />

      {/* All Attachments Modal */}
      <AllAttachmentsModal
        open={isAllAttachmentsOpen}
        onOpenChange={setIsAllAttachmentsOpen}
        attachments={allAttachments}
        loadedBlobUrls={loadedBlobUrls}
        loadingAssetIds={loadingAssetIds}
        loadingFileId={loadingFileId}
        onLoadAsset={loadAssetAsBlobUrl}
        onOpenImageGallery={handleOpenImageGallery}
        onOpenTextFile={handleOpenTextFile}
        onOpenPdf={handleOpenPdf}
      />

      {/* Mobile Model Selection Sheet */}
      <MobileModelSheet
        open={mobileModelSheetOpen}
        onOpenChange={setMobileModelSheetOpen}
        models={models}
        selectedModelId={chat.model?.model_id}
        onSelectModel={onModelSelect}
      />

      {/* Voice Conversation Overlay - fullscreen voice mode like Voice Sessions */}
      <VoiceConversationOverlay
        isOpen={voiceOverlayOpen}
        onClose={() => setVoiceOverlayOpen(false)}
        onSendMessage={handleVoiceSend}
        messages={chat.messages}
        isGenerating={chat.isLoading}
        model={chat.model}
        modelName={chat.model ? removeProviderPrefix(chat.model.name, chat.model.provider) : 'AI'}
      />

      {/* Chat Instructions Sheet */}
      <ChatInstructionsSheet
        isOpen={instructionsSheetOpen}
        onClose={() => setInstructionsSheetOpen(false)}
        instructions={chat.instructions}
        onSave={(instructions) => {
          onUpdateChat?.({ instructions })
        }}
      />

    </div>
  )
})
