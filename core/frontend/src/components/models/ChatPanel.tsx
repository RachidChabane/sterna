import { useState, useRef, useEffect, useCallback, useMemo, memo, type HTMLAttributes } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useToast } from '@/hooks/use-toast'
import { useAttachmentManagement } from '@/hooks/useAttachmentManagement'
import { useChatCosts } from '@/hooks/useChatCosts'
import { useTTS } from '@/hooks/useTTS'
import { useAuthStore } from '@/store/authStore'
import { useAuthModalStore } from '@/store/authModalStore'
import { getAuthModalVariant } from '@/lib/sessionDetection'
import { revokeImagePreview } from '@/utils/imageUtils'
import type { Model, Message, Filters, ModelParameters, Chat, Attachment, FileAttachment, CostEstimate, ToolExecutedHandler } from './types'

import { ChatHeader } from './ChatHeader'
import { MessageInput } from './MessageInput'
import { MessageList } from './MessageList'
import { AttachmentModals } from './AttachmentModals'
import { ChatStates } from './ChatStates'
import { ChatModals } from './ChatModals'
import { ChatPanelProvider } from './ChatPanelContext'
import { useChatPanelScroll } from './hooks/useChatPanelScroll'
import { useChatFeatureToggles } from './hooks/useChatFeatureToggles'
import { useMessageMutations } from './hooks/useMessageMutations'
import { useMessageExportActions } from './hooks/useMessageExportActions'
import { useAttachmentDragAndPaste } from './hooks/useAttachmentDragAndPaste'
import { useChatPanelModelDetails } from './hooks/useChatPanelModelDetails'
import { useAttachmentViewerState } from './hooks/useAttachmentViewerState'
import { useAttachmentCacheHydration } from './hooks/useAttachmentCacheHydration'
interface ChatPanelProps {
  model: Model | null
  models: Model[]
  messages: Message[]
  isLoading: boolean
  onModelSelect: (model: Model) => void
  onSendMessage: (content: string, attachments?: Attachment[]) => void
  onUpdateMessages?: (messages: Message[]) => void
  onRemove?: () => void
  showRemove?: boolean
  syncMode: boolean
  onToggleSyncMode?: () => void
  conversationId?: string  // For sandbox isolation
  onMoveLeft?: () => void
  onMoveRight?: () => void
  canMoveLeft?: boolean
  canMoveRight?: boolean
  dragHandleRef?: (element: HTMLElement | null) => void
  dragHandleProps?: HTMLAttributes<HTMLElement>
  showFilters?: boolean
  onToggleFilters?: () => void
  hasActiveFilters?: boolean
  filters?: Filters
  onFiltersChange?: (filters: Filters) => void
  providers?: string[]
  onEstimateCost?: (text: string, attachments?: Attachment[]) => Promise<CostEstimate | undefined>
  parameters?: ModelParameters
  onParametersChange?: (parameters: ModelParameters) => void
  currentChatId?: string
  availableChats?: Chat[]
  allChats?: Chat[] // All chats for IDE switcher (includes current chat)
  onApplyParametersToAll?: (parameters: ModelParameters) => void
  // Customization props for embedding ChatPanel in other contexts
  emptyStateContent?: React.ReactNode
  hideModelSelector?: boolean
  hideCopyExport?: boolean
  hideMoveControls?: boolean
  hideHeaderWhenEmpty?: boolean
  hideHeaderActions?: boolean
  inputPlaceholder?: string
  onClearChat?: (deleteWorkspace?: boolean) => void
  onToolExecuted?: ToolExecutedHandler
  isClearingChat?: boolean
  recentModelIds?: string[]
  // Filter-related props (optional, for use in ModelComparisonPage context)
  onFilterByCapability?: (modality: string) => void
  activeFilters?: string[]
  disabledChat?: boolean
  onToggleDisabled?: (value: boolean) => void
  hiddenChat?: boolean
  onToggleHidden?: (value: boolean) => void
  // Cancellation controls
  onCancel?: () => void
  canCancel?: boolean
  abortControllersRef?: React.MutableRefObject<Map<string, AbortController>>
}

function ChatPanelComponent({
  model,
  models,
  messages,
  isLoading,
  onModelSelect,
  onSendMessage,
  onUpdateMessages,
  onRemove,
  showRemove = false,
  syncMode,
  onToggleSyncMode,
  conversationId,
  onMoveLeft,
  onMoveRight,
  canMoveLeft = false,
  canMoveRight = false,
  dragHandleRef,
  dragHandleProps,
  showFilters = false,
  onToggleFilters,
  hasActiveFilters = false,
  filters,
  onFiltersChange,
  providers,
  onEstimateCost,
  parameters,
  onParametersChange,
  currentChatId,
  availableChats,
  allChats,
  onApplyParametersToAll,
  emptyStateContent,
  hideModelSelector = false,
  hideCopyExport = false,
  hideMoveControls = false,
  hideHeaderWhenEmpty = false,
  hideHeaderActions = false,
  inputPlaceholder,
  onClearChat,
  onToolExecuted,
  isClearingChat = false,
  recentModelIds,
  onFilterByCapability,
  activeFilters,
  disabledChat = false,
  onToggleDisabled,
  hiddenChat = false,
  onToggleHidden,
  onCancel,
  canCancel,
  abortControllersRef,
}: ChatPanelProps) {
  // Extract user message history for input state hook
  // Memoize to avoid recreating array on every render
  const userMessageHistory = useMemo(() =>
    messages
      .filter(m => m.role === 'user')
      .map(m => m.content)
      .reverse() // Most recent first
  , [messages])

  // Input ref and external value for MessageInput
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const [externalInputValue, setExternalInputValue] = useState<string>('')

  // Use custom hooks for cleaner state management
  const attachmentManager = useAttachmentManagement()
  const { attachments, addAttachment, addAttachments, removeAttachment, clearAttachments } = attachmentManager

  // Feature toggles for independent mode - simple single-chat states
  const {
    webSearchState,
    reasoningState,
    mcpToolsState,
    hasReasoningSupportValue,
    hasFunctionSupportValue,
    hasWebSearchSupportValue,
    activeServersValue,
    toggleWebSearch,
    toggleReasoning,
    toggleMCPTools,
  } = useChatFeatureToggles({ model, parameters, onParametersChange })

  // Use cost calculation hook
  const { totalCost, totalPromptCost, totalCompletionCost, totalTokens, formatCost, formatLatency } = useChatCosts({ messages })

  // TTS (Text-to-Speech) hook
  const { speak, stop: stopSpeaking, isSpeaking, isLoading: isTTSLoading, isSupported: isTTSSupported } = useTTS()

  const [estimatedCost, setEstimatedCost] = useState<CostEstimate | null>(null)
  const [showParametersDialog, setShowParametersDialog] = useState(false)
  const [loadingEstimate, setLoadingEstimate] = useState(false)
  const [showClearDialog, setShowClearDialog] = useState(false)
  const [suppressInterruptedWarning, setSuppressInterruptedWarning] = useState(false)
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const [messagesContainer, setMessagesContainer] = useState<HTMLDivElement | null>(null)
  const messagesContainerRef = useCallback((node: HTMLDivElement | null) => {
    if (node !== null) {
      setMessagesContainer(node)
    }
  }, [])
  const { toast } = useToast()
  const navigate = useNavigate()
  const { user, isAuthenticated } = useAuthStore()
  const { openModal } = useAuthModalStore()

  // Smart auto-scroll + scroll clamp for the independent-mode transcript
  useChatPanelScroll(scrollAreaRef, messages)

  // Reset interrupted warning suppression when a successful assistant message arrives
  // We only reset when NOT loading and we have a non-interrupted, non-error assistant response
  useEffect(() => {
    if (isLoading) return // Don't reset while loading - we want to keep suppression active during retry

    const last = messages[messages.length - 1]
    if (last && last.role === 'assistant' && !last.isInterrupted && !last.isError) {
      setSuppressInterruptedWarning(false)
    }
  }, [isLoading, messages])

  // Note: Auto-resize is now handled internally by MarkdownTextarea component

  const handleSend = useCallback((text: string) => {
    // Check authentication
    if (!isAuthenticated) {
      toast({
        title: 'Authentication required',
        description: 'Please sign in to send messages',
        variant: 'destructive'
      })
      const variant = getAuthModalVariant()
      openModal(variant, window.location.pathname)
      return
    }

    if ((text.trim() || attachments.length > 0) && !isLoading) {
      onSendMessage(text, attachments)
      setEstimatedCost(null) // Clear estimation after sending

      // Clean up blob preview URLs and clear all attachments
      attachments.forEach(att => {
        if (att.type === 'image') {
          revokeImagePreview(att.preview)
        } else if (att.type === 'video' || att.type === 'audio') {
          URL.revokeObjectURL(att.preview)
        }
      })
      clearAttachments()
    }
  }, [isAuthenticated, attachments, isLoading, onSendMessage, toast, openModal, clearAttachments])

  const handleEstimate = useCallback(async (text: string) => {
    if ((!text.trim() && attachments.length === 0) || !model || !onEstimateCost) return
    setLoadingEstimate(true)
    try {
      const result = await onEstimateCost(text, attachments)
      setEstimatedCost(result ?? null)
    } catch (error) {
      console.error('Failed to estimate cost:', error)
      toast({ title: 'Estimation failed', description: 'Failed to estimate cost for this message', variant: 'destructive' })
    } finally {
      setLoadingEstimate(false)
    }
  }, [attachments, model, onEstimateCost, toast])

  // Drag & drop / paste handlers for attaching files/images
  const { isDragOver, handleDragOver, handleDragLeave, handleDrop, handlePaste } = useAttachmentDragAndPaste({
    isAuthenticated,
    isLoading,
    disabledChat,
    attachmentCount: attachments.length,
    addAttachments,
    toast,
    openModal,
  })

  // Retry / edit / resend a message, rewinding local + persisted state as needed
  const { handleRetry, handleEditMessage, handleResend } = useMessageMutations({
    messages,
    onUpdateMessages,
    onSendMessage,
    conversationId,
    currentChatId,
    toast,
    setSuppressInterruptedWarning,
  })

  // Copy/export actions for a single message and for the whole chat
  const {
    copyMessageContent,
    copyMessageMetadata,
    exportMessageContent,
    exportMessageMetadata,
    copyChatResponses,
    copyChatMetadata,
    exportChatResponses,
    exportChatMetadata,
  } = useMessageExportActions({ messages, model, toast })

  // Handler for suggested questions in independent mode
  const handleLocalSuggestionClick = useCallback((suggestion: string) => {
    setExternalInputValue(suggestion)
  }, [])

  // Attachment viewer state: image gallery, PDF preview, text file preview, all-attachments modal
  const {
    isGalleryOpen, setIsGalleryOpen,
    galleryImages, setGalleryImages,
    selectedImageIndex, setSelectedImageIndex,
    galleryOpenedFromAttachments, setGalleryOpenedFromAttachments,
    isPdfOpen, setIsPdfOpen,
    pdfSrc, pdfName,
    isAllAttachmentsOpen, setIsAllAttachmentsOpen,
    allAttachments,
    selectedAllImage, setSelectedAllImage,
    selectedFile,
    isModalOpen, setIsModalOpen,
    fetchedFileContent,
    handleOpenImageGallery,
    handleOpenPdf,
    handleOpenTextFile,
    handleOpenAllAttachments,
    setSelectedFile,
    setPdfSrc,
    setPdfName,
  } = useAttachmentViewerState(toast)

  // Detect if a response is being generated (either "Thinking..." or streaming)
  // Find the last assistant message (skip tool messages) for robust streaming detection
  const lastAssistantMessage = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') return messages[i]
    }
    return null
  }, [messages])

  const isStreaming = useMemo(() =>
    lastAssistantMessage !== null &&
    !lastAssistantMessage.isError &&
    !lastAssistantMessage.isUnsupported &&
    !lastAssistantMessage.cost &&
    !lastAssistantMessage.tokens &&
    !lastAssistantMessage.is_stopped
  , [lastAssistantMessage])

  const isGenerating = isLoading || isStreaming

  // Check if model supports vision (memoized to avoid array lookup on every render)
  const hasVisionSupport = useMemo(() =>
    model?.input_modalities?.includes('image') || false
  , [model?.input_modalities])

  // Check if model supports PDFs (file capability)
  // Note: Text files work with any model as their content is inserted into message text
  const hasPDFSupport = useMemo(() =>
    model?.input_modalities?.includes('file') || false
  , [model?.input_modalities])

  // Model details modal: resolve a model id to its full catalog entry
  const {
    isModelDetailsOpen,
    setIsModelDetailsOpen,
    selectedModelDetails,
    openModelDetails,
  } = useChatPanelModelDetails(model, messages)

  // Hydrate missing file metadata/content from cache (survives refresh)
  const cachedAttachments = useAttachmentCacheHydration(messages, attachments)

  // Memoize the context value to prevent unnecessary re-renders of all consuming components
  const chatPanelContextValue = useMemo(() => ({
    model,
    messages,
    isLoading,
    isGenerating,
    user,
    conversationId,
    chatId: currentChatId,
    syncMode,
    messagesContainer,
    cachedAttachments,
    disabledChat,
    abortControllersRef,
    onUpdateMessages,
    onToolExecuted,
    onRetry: handleRetry,
    onEditMessage: handleEditMessage,
    onCopyContent: copyMessageContent,
    onCopyMetadata: copyMessageMetadata,
    onExportContent: exportMessageContent,
    onExportMetadata: exportMessageMetadata,
    onOpenModelDetails: openModelDetails,
    formatCost,
    formatLatency,
    onOpenImageGallery: handleOpenImageGallery,
    onOpenPdf: handleOpenPdf,
    onOpenTextFile: handleOpenTextFile,
    onOpenAllAttachments: handleOpenAllAttachments,
    // TTS props
    onSpeak: speak,
    onStopSpeaking: stopSpeaking,
    isSpeaking,
    isTTSLoading,
    isTTSSupported,
  }), [
    model, messages, isLoading, isGenerating, user, conversationId, currentChatId,
    syncMode, messagesContainer, cachedAttachments, disabledChat, abortControllersRef,
    onUpdateMessages, onToolExecuted, handleRetry, handleEditMessage, copyMessageContent,
    copyMessageMetadata, exportMessageContent, exportMessageMetadata, openModelDetails,
    formatCost, formatLatency, handleOpenImageGallery, handleOpenPdf,
    handleOpenTextFile, handleOpenAllAttachments,
    speak, stopSpeaking, isSpeaking, isTTSLoading, isTTSSupported
  ])

  return (
    <>
    <div className="h-full flex flex-col bg-background/20">
      {/* Header with Model Selector */}
      <ChatHeader
        model={model}
        models={models}
        onModelSelect={onModelSelect}
        hideModelSelector={hideModelSelector}
        recentModelIds={recentModelIds}
        showFilters={showFilters}
        onToggleFilters={onToggleFilters}
        hasActiveFilters={hasActiveFilters}
        filters={filters}
        onFiltersChange={onFiltersChange}
        providers={providers}
        parameters={parameters}
        onParametersChange={onParametersChange}
        hideHeaderActions={hideHeaderActions}
        hideMoveControls={hideMoveControls}
        hideCopyExport={hideCopyExport}
        showRemove={showRemove}
        onRemove={onRemove}
        onMoveLeft={onMoveLeft}
        onMoveRight={onMoveRight}
        canMoveLeft={canMoveLeft}
        canMoveRight={canMoveRight}
        onClearChat={onClearChat}
        onCancel={onCancel}
        canCancel={canCancel}
        chatId={currentChatId}
        conversationId={conversationId}
        dragHandleRef={dragHandleRef}
        dragHandleProps={dragHandleProps}
        messages={messages}
        isLoading={isLoading}
        isClearingChat={isClearingChat}
        disabledChat={disabledChat}
        onToggleDisabled={onToggleDisabled}
        onToggleHidden={onToggleHidden}
        totalCost={totalCost}
        totalTokens={totalTokens}
        totalPromptCost={totalPromptCost}
        totalCompletionCost={totalCompletionCost}
        onShowParametersDialog={() => setShowParametersDialog(true)}
        onShowClearDialog={() => setShowClearDialog(true)}
        onCopyResponses={copyChatResponses}
        onCopyMetadata={copyChatMetadata}
        onExportResponses={exportChatResponses}
        onExportMetadata={exportChatMetadata}
        hideHeaderWhenEmpty={hideHeaderWhenEmpty}
        isGenerating={isGenerating}
        chats={allChats}
      />


      {/* Messages Area */}
      <div
        className="flex-1 p-0 overflow-hidden min-h-0"
      >
        <ScrollArea className="h-full" ref={scrollAreaRef}>
          {/* Show empty state when no messages */}
          {messages.length === 0 && (
            <div className="px-4">
              <ChatStates
                messages={messages}
                emptyStateContent={emptyStateContent}
                syncMode={syncMode}
                model={model}
                onSuggestionClick={handleLocalSuggestionClick}
                isLoading={isLoading}
                canCancel={canCancel}
                onCancel={onCancel}
                onOpenModelDetails={openModelDetails}
                suppressInterruptedWarning={suppressInterruptedWarning}
                onResend={handleResend}
              />
            </div>
          )}

          {messages.length > 0 && (
            <div ref={messagesContainerRef} className="w-full overflow-x-hidden px-4" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', maxWidth: '100%' }}>
              <ChatPanelProvider value={chatPanelContextValue}>
                <MessageList />
              </ChatPanelProvider>

              {/* Show loading and interrupted states after messages */}
              <ChatStates
                messages={messages}
                emptyStateContent={undefined}
                syncMode={syncMode}
                model={model}
                onSuggestionClick={handleLocalSuggestionClick}
                isLoading={isLoading}
                canCancel={canCancel}
                onCancel={onCancel}
                onOpenModelDetails={openModelDetails}
                suppressInterruptedWarning={suppressInterruptedWarning}
                onResend={handleResend}
              />

              {/* Spacer: provides enough scroll room to position the user message
                  at the top of the viewport while waiting for the LLM response */}
              <div
                aria-hidden
                style={{ height: isLoading ? '70vh' : '0px' }}
              />
            </div>
          )}
        </ScrollArea>
      </div>

      {/* Input Area (only shown in independent mode) */}
      {!syncMode && (
        <MessageInput
          mode="independent"
          disabled={isLoading || disabledChat}
          placeholder={inputPlaceholder}
          externalValue={externalInputValue}
          inputRef={inputRef}
          model={model}
          attachments={attachments}
          onRemoveAttachment={removeAttachment}
          onAddAttachment={addAttachment}
          hasVisionSupport={hasVisionSupport}
          hasPDFSupport={hasPDFSupport}
          onFilterByCapability={onFilterByCapability}
          activeFilters={activeFilters}
          isDropOver={isDragOver}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onPaste={handlePaste}
          onSend={handleSend}
          onCancel={onCancel}
          canCancel={canCancel}
          onEstimate={onEstimateCost ? handleEstimate : undefined}
          isEstimating={loadingEstimate}
          estimatedCost={estimatedCost}
          setEstimatedCost={setEstimatedCost}
          messages={messages}
          isClearingChat={isClearingChat}
          onShowClearDialog={() => setShowClearDialog(true)}
          hideHeaderActions={hideHeaderActions}
          webSearchState={webSearchState}
          onToggleWebSearch={toggleWebSearch}
          hasWebSearchSupport={hasWebSearchSupportValue}
          reasoningState={reasoningState}
          onToggleReasoning={toggleReasoning}
          hasReasoningSupport={hasReasoningSupportValue}
          mcpToolsState={mcpToolsState}
          onToggleMCPTools={toggleMCPTools}
          hasFunctionSupport={hasFunctionSupportValue}
          activeServers={activeServersValue}
        />
      )}
    </div>

    {/* All Attachment-Related Modals */}
    <AttachmentModals
      isGalleryOpen={isGalleryOpen}
      setIsGalleryOpen={setIsGalleryOpen}
      galleryImages={galleryImages}
      selectedImageIndex={selectedImageIndex}
      setSelectedImageIndex={setSelectedImageIndex}
      selectedAllImage={selectedAllImage}
      setSelectedAllImage={setSelectedAllImage}
      galleryOpenedFromAttachments={galleryOpenedFromAttachments}
      setGalleryOpenedFromAttachments={setGalleryOpenedFromAttachments}
      isPdfOpen={isPdfOpen}
      setIsPdfOpen={setIsPdfOpen}
      pdfSrc={pdfSrc}
      pdfName={pdfName}
      isAllAttachmentsOpen={isAllAttachmentsOpen}
      setIsAllAttachmentsOpen={setIsAllAttachmentsOpen}
      allAttachments={allAttachments}
      isTextFileOpen={isModalOpen}
      setIsTextFileOpen={setIsModalOpen}
      selectedFile={selectedFile}
      fetchedFileContent={fetchedFileContent}
      cachedAttachments={cachedAttachments}
      onOpenPdf={(src, name) => {
        setPdfSrc(src)
        setPdfName(name)
        setIsPdfOpen(true)
      }}
      onOpenTextFile={(file) => {
        setSelectedFile(file)
        setIsModalOpen(true)
      }}
      onOpenImageGallery={(images, selectedIndex) => {
        setGalleryImages(images)
        setSelectedImageIndex(selectedIndex)
        setSelectedAllImage(images[selectedIndex])
        setIsGalleryOpen(true)
      }}
    />

    {/* All Other Modals */}
    <ChatModals
      isModelDetailsOpen={isModelDetailsOpen}
      setIsModelDetailsOpen={setIsModelDetailsOpen}
      selectedModelDetails={selectedModelDetails}
      model={model}
      models={models}
      onModelSelect={onModelSelect}
      showClearDialog={showClearDialog}
      setShowClearDialog={setShowClearDialog}
      onClearChat={onClearChat}
    />
    </>
  )
}

// Export memoized version to prevent unnecessary re-renders
export default memo(ChatPanelComponent)
