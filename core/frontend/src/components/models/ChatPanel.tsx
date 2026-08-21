import { useState, useRef, useEffect, useLayoutEffect, useCallback, useMemo, memo } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { useToast } from '@/hooks/use-toast'
import { useAttachmentManagement } from '@/hooks/useAttachmentManagement'
import { useChatCosts } from '@/hooks/useChatCosts'
import { useTTS } from '@/hooks/useTTS'
import { useAuthStore } from '@/store/authStore'
import { useAuthModalStore } from '@/store/authModalStore'
import { getAuthModalVariant } from '@/lib/sessionDetection'
import { FilePreviewModal } from './FilePreviewModal'
import { assetsAPI } from '@/api/assets'
import { conversationsAPI } from '@/api/conversations'
import { useMCPStore } from '@/store/mcpStore'
import type { Model, Message, Filters, ModelParameters, Chat, Attachment, ImageAttachment, FileAttachment } from './types'
import { extractTextFromContent, buildChatResponsesText, buildChatMetadata, generateFilename } from '@/utils/chatUtils'
import { revokeImagePreview } from '@/utils/imageUtils'
import { cacheGet } from '@/utils/attachmentCache'
import { buildAttachmentsFromFiles, extractFilesFromClipboard, extractFilesFromDataTransfer } from '@/utils/attachmentHandlers'
import useModelStore from '@/store/modelStore'
import type { ModelCatalogEntry } from '@/types/models'
import { toModelCatalogEntry } from './modelCatalog'
import { ModelDetailsModal } from './ModelDetailsModal'
import type { CachedAttachment } from '@/utils/attachmentCache'

import { ChatHeader } from './ChatHeader'
import { MessageInput } from './MessageInput'
import { MessageList } from './MessageList'
import { AttachmentModals } from './AttachmentModals'
import { ChatStates } from './ChatStates'
import { ChatModals } from './ChatModals'
import { ChatPanelProvider } from './ChatPanelContext'
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
  dragHandleProps?: Record<string, any>
  showFilters?: boolean
  onToggleFilters?: () => void
  hasActiveFilters?: boolean
  filters?: Filters
  onFiltersChange?: (filters: Filters) => void
  providers?: string[]
  onEstimateCost?: (text: string, attachments?: Attachment[]) => Promise<any>
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
  onToolExecuted?: (toolCallId: string, toolName: string, result: any) => void
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

  // MCP store - always available
  const getActiveServers = useMCPStore((state) => state.getActiveServers)

  // Feature toggles for independent mode - simple single-chat states
  const webSearchState = useMemo(() => ({
    enabled: parameters?.enable_brave_search === true ? 1 : 0,
    total: 1,
    supported: model?.supports_functions === true ? 1 : 0,
  }), [parameters?.enable_brave_search, model?.supports_functions])

  const reasoningState = useMemo(() => ({
    enabled: parameters?.enable_reasoning === true ? 1 : 0,
    total: 1,
    supported: model?.supports_reasoning === true ? 1 : 0,
  }), [parameters?.enable_reasoning, model?.supports_reasoning])

  const mcpToolsState = useMemo(() => ({
    enabled: parameters?.enable_mcp_tools === true ? 1 : 0,
    total: 1,
    supported: model?.supports_functions === true ? 1 : 0,
  }), [parameters?.enable_mcp_tools, model?.supports_functions])

  const hasReasoningSupportValue = model?.supports_reasoning === true
  const hasFunctionSupportValue = model?.supports_functions === true
  const activeServersValue = useMemo(() => {
    try {
      return getActiveServers ? getActiveServers() : []
    } catch (e) {
      console.error('Error getting active servers:', e)
      return []
    }
  }, [getActiveServers])

  // Feature toggle handlers for independent mode
  const toggleWebSearch = useCallback(() => {
    if (!onParametersChange || !parameters) return
    onParametersChange({
      ...parameters,
      enable_brave_search: !parameters.enable_brave_search,
    })
  }, [onParametersChange, parameters])

  const hasWebSearchSupportValue = model?.supports_functions === true

  const toggleReasoning = useCallback(() => {
    if (!onParametersChange || !parameters) return
    onParametersChange({
      ...parameters,
      enable_reasoning: !parameters.enable_reasoning,
    })
  }, [onParametersChange, parameters])

  const toggleMCPTools = useCallback(() => {
    if (!onParametersChange || !parameters) return
    onParametersChange({
      ...parameters,
      enable_mcp_tools: !parameters.enable_mcp_tools,
    })
  }, [onParametersChange, parameters])

  // Use cost calculation hook
  const { totalCost, totalPromptCost, totalCompletionCost, totalTokens, formatCost, formatLatency } = useChatCosts({ messages })

  // TTS (Text-to-Speech) hook
  const { speak, stop: stopSpeaking, isSpeaking, isLoading: isTTSLoading, isSupported: isTTSSupported } = useTTS()

  const [estimatedCost, setEstimatedCost] = useState<any>(null)
  const [showParametersDialog, setShowParametersDialog] = useState(false)
  const [loadingEstimate, setLoadingEstimate] = useState(false)
  const [showClearDialog, setShowClearDialog] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const [selectedFile, setSelectedFile] = useState<FileAttachment | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [fetchedFileContent, setFetchedFileContent] = useState<string | null>(null)
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

  // Smart auto-scroll: positions user message at top of viewport when sent,
  // then follows streaming content at the bottom
  const prevLastMsgKeyRef = useRef<string | null>(null)
  useLayoutEffect(() => {
    const viewport = scrollAreaRef.current?.querySelector(
      '[data-radix-scroll-area-viewport]'
    ) as HTMLElement | null
    if (!viewport || messages.length === 0) return

    const lastMsg = messages[messages.length - 1]
    const lastMsgKey = `${lastMsg.role}-${lastMsg.timestamp?.getTime()}`
    const isNewMessage = lastMsgKey !== prevLastMsgKeyRef.current
    prevLastMsgKeyRef.current = lastMsgKey

    if (isNewMessage && lastMsg.role === 'user') {
      // New user message — scroll it to the top of the visible area
      requestAnimationFrame(() => {
        const userMsgs = viewport.querySelectorAll('[data-message-role="user"]')
        const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
        if (lastUserEl) {
          const vRect = viewport.getBoundingClientRect()
          const mRect = lastUserEl.getBoundingClientRect()
          const target = viewport.scrollTop + (mRect.top - vRect.top) - 16
          viewport.scrollTo({ top: target, behavior: 'smooth' })
        } else {
          viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' })
        }
      })
    } else {
      // Streaming update or assistant message — keep scrolled to bottom
      viewport.scrollTop = viewport.scrollHeight
    }
  }, [messages])

  // Scroll clamp: never allow scrolling past the last user message at top of visible area,
  // but allow normal scrolling when the assistant response overflows the viewport.
  useEffect(() => {
    const viewport = scrollAreaRef.current?.querySelector(
      '[data-radix-scroll-area-viewport]'
    ) as HTMLElement | null
    if (!viewport) return

    const paddingBottom = parseFloat(getComputedStyle(viewport).paddingBottom) || 0

    const clampScroll = () => {
      const userMsgs = viewport.querySelectorAll('[data-message-role="user"]')
      const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
      if (!lastUserEl) return

      const allMsgs = viewport.querySelectorAll('[data-message-role]')
      const lastMsgEl = allMsgs[allMsgs.length - 1] as HTMLElement | null
      if (!lastMsgEl) return

      const viewportRect = viewport.getBoundingClientRect()
      const userMsgRect = lastUserEl.getBoundingClientRect()
      const lastMsgRect = lastMsgEl.getBoundingClientRect()

      const lastUserMsgAbsoluteTop = viewport.scrollTop + (userMsgRect.top - viewportRect.top)
      const lastMessageBottom = viewport.scrollTop + (lastMsgRect.bottom - viewportRect.top)
      const effectiveViewport = viewport.clientHeight - paddingBottom

      const maxScroll = Math.max(lastUserMsgAbsoluteTop, lastMessageBottom - effectiveViewport)

      if (viewport.scrollTop > maxScroll) {
        viewport.scrollTop = maxScroll
      }
    }

    viewport.addEventListener('scroll', clampScroll)
    return () => viewport.removeEventListener('scroll', clampScroll)
  }, [])

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
          URL.revokeObjectURL((att as any).preview)
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
      setEstimatedCost(result)
    } catch (error) {
      console.error('Failed to estimate cost:', error)
      toast({ title: 'Estimation failed', description: 'Failed to estimate cost for this message', variant: 'destructive' })
    } finally {
      setLoadingEstimate(false)
    }
  }, [attachments, model, onEstimateCost, toast])

  // Drag & drop handlers for attaching files/images
  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    if (!isAuthenticated || isLoading || disabledChat) return
    setIsDragOver(true)
  }, [isAuthenticated, isLoading, disabledChat])

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragOver(false)
  }, [])

  const handleDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragOver(false)
    if (!isAuthenticated) {
      toast({ title: 'Authentication required', description: 'Please sign in to attach files', variant: 'destructive' })
      const variant = getAuthModalVariant()
      openModal(variant, window.location.pathname)
      return
    }
    if (isLoading || disabledChat) return
    const files = extractFilesFromDataTransfer(e.dataTransfer)
    if (!files.length) return
    const { attachments: newAtts, counts } = await buildAttachmentsFromFiles(files, { currentCount: attachments.length, maxCount: 8 })
    if (newAtts.length) addAttachments(newAtts)

    // Show security warnings first
    if (counts.securityWarnings && counts.securityWarnings.length > 0) {
      for (const warning of counts.securityWarnings) {
        if (warning.startsWith('BLOCKED:')) {
          toast({
            title: 'Security Warning',
            description: warning.replace('BLOCKED: ', ''),
            variant: 'destructive'
          })
        } else if (warning.startsWith('INVALID:')) {
          toast({
            title: 'Invalid File',
            description: warning.replace('INVALID: ', ''),
            variant: 'destructive'
          })
        } else if (warning.startsWith('WARNING:')) {
          toast({
            title: 'File Type Warning',
            description: warning.replace('WARNING: ', ''),
            variant: 'default'
          })
        }
      }
    }

    // Show summary of successfully added files
    const total = newAtts.length
    if (total > 0 || counts.errors > 0 || counts.blocked > 0) {
      const parts = [] as string[]
      if (counts.imagesAdded) parts.push(`${counts.imagesAdded} image${counts.imagesAdded > 1 ? 's' : ''}`)
      if (counts.pdfsAdded) parts.push(`${counts.pdfsAdded} PDF${counts.pdfsAdded > 1 ? 's' : ''}`)
      if (counts.officeDocsAdded) parts.push(`${counts.officeDocsAdded} Office doc${counts.officeDocsAdded > 1 ? 's' : ''}`)
      if (counts.textsAdded) parts.push(`${counts.textsAdded} file${counts.textsAdded > 1 ? 's' : ''}`)

      if (parts.length > 0) {
        const totalFailed = counts.errors + counts.blocked
        const desc = `${parts.join(' + ')} added${totalFailed ? ` • ${totalFailed} failed` : ''}${counts.skippedOverflow ? ` • ${counts.skippedOverflow} skipped (limit)` : ''}`
        toast({ title: 'Attachments added', description: desc })
      }
    }
  }, [isAuthenticated, isLoading, disabledChat, attachments.length, addAttachments, toast, openModal])

  // Paste handler for images/files from clipboard
  const handlePaste = useCallback(async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!isAuthenticated || isLoading || disabledChat) return
    const files = extractFilesFromClipboard(e)
    if (!files.length) return
    // Prevent inserting binary data as text
    e.preventDefault()
    const { attachments: newAtts, counts } = await buildAttachmentsFromFiles(files, { currentCount: attachments.length, maxCount: 8 })
    if (newAtts.length) addAttachments(newAtts)

    // Show security warnings first
    if (counts.securityWarnings && counts.securityWarnings.length > 0) {
      for (const warning of counts.securityWarnings) {
        if (warning.startsWith('BLOCKED:')) {
          toast({
            title: 'Security Warning',
            description: warning.replace('BLOCKED: ', ''),
            variant: 'destructive'
          })
        } else if (warning.startsWith('INVALID:')) {
          toast({
            title: 'Invalid File',
            description: warning.replace('INVALID: ', ''),
            variant: 'destructive'
          })
        } else if (warning.startsWith('WARNING:')) {
          toast({
            title: 'File Type Warning',
            description: warning.replace('WARNING: ', ''),
            variant: 'default'
          })
        }
      }
    }

    // Show summary of successfully added files
    const parts = [] as string[]
    if (counts.imagesAdded) parts.push(`${counts.imagesAdded} image${counts.imagesAdded > 1 ? 's' : ''}`)
    if (counts.pdfsAdded) parts.push(`${counts.pdfsAdded} PDF${counts.pdfsAdded > 1 ? 's' : ''}`)
    if (counts.officeDocsAdded) parts.push(`${counts.officeDocsAdded} Office doc${counts.officeDocsAdded > 1 ? 's' : ''}`)
    if (counts.textsAdded) parts.push(`${counts.textsAdded} file${counts.textsAdded > 1 ? 's' : ''}`)

    if (parts.length > 0 || (counts.errors + counts.blocked) > 0) {
      const totalFailed = counts.errors + counts.blocked
      toast({
        title: 'Attachments added',
        description: parts.length
          ? `${parts.join(' + ')} added${totalFailed ? ` • ${totalFailed} failed` : ''}`
          : 'No supported items found'
      })
    }
  }, [isAuthenticated, isLoading, disabledChat, attachments.length, addAttachments, toast])

  const handleRetry = useCallback(async (assistantMessageIndex: number) => {
    if (!onUpdateMessages) return

    // Find the closest preceding user message (skip any assistant notices)
    let userMessageIndex = -1
    for (let i = assistantMessageIndex - 1; i >= 0; i--) {
      if (messages[i].role === 'user') { userMessageIndex = i; break }
    }

    if (userMessageIndex < 0) {
      toast({ title: 'Cannot retry', description: 'No user message found before this response', variant: 'destructive' })
      return
    }

    const userMessage = messages[userMessageIndex]
    const userMessageText = extractTextFromContent(userMessage.content)
    const userAttachments = (userMessage.attachments || []) as Attachment[]

    // Remove the user message, the selected assistant message, and any assistant notices between them
    const toRemove = new Set<number>([userMessageIndex, assistantMessageIndex])
    for (let i = userMessageIndex + 1; i < assistantMessageIndex; i++) {
      const m = messages[i]
      if (m.role === 'assistant' && (m as any).isUnsupported) toRemove.add(i)
    }
    const updatedMessages = messages.filter((_, idx) => !toRemove.has(idx))

    // Delete removed messages from the database (if they have message_id)
    if (conversationId && currentChatId) {
      const messagesToDelete = messages.filter((_, idx) => toRemove.has(idx))
      await Promise.all(
        messagesToDelete
          .filter(m => m.message_id)
          .map(m => conversationsAPI.deleteMessage(conversationId, currentChatId, m.message_id!).catch(err => {
            console.error('Failed to delete message from database:', err)
          }))
      )
    }

    // Update messages first
    onUpdateMessages(updatedMessages)

    // Wait for React to apply the state update before resending
    // This prevents a race condition where the new message would be added to the old state
    await new Promise(resolve => setTimeout(resolve, 0))

    // Prevent transient interrupted banner while retry triggers send
    setSuppressInterruptedWarning(true)

    // Then resend the user message (text + attachments if any)
    await onSendMessage(userMessageText, userAttachments.length ? userAttachments : undefined)
  }, [messages, onUpdateMessages, onSendMessage, toast, conversationId, currentChatId])

  const handleEditMessage = useCallback(async (messageIndex: number, content: string) => {
    if (!onUpdateMessages) return

    // Get the message being edited
    const editedMessage = messages[messageIndex]
    if (!editedMessage || editedMessage.role !== 'user') return

    // Get attachments from the message being edited
    const userAttachments = (editedMessage.attachments || []) as Attachment[]

    // Delete ALL messages from the edited message onwards (complete rewind)
    const messagesToDelete = messages.slice(messageIndex)
    const updatedMessages = messages.slice(0, messageIndex)

    // Delete removed messages from the database (if they have message_id)
    if (conversationId && currentChatId) {
      await Promise.all(
        messagesToDelete
          .filter(m => m.message_id)
          .map(m => conversationsAPI.deleteMessage(conversationId, currentChatId, m.message_id!).catch(err => {
            console.error('Failed to delete message from database:', err)
          }))
      )
    }

    // Update messages to remove everything from the edited message onwards
    onUpdateMessages(updatedMessages)

    // Wait for React to apply the state update
    await new Promise(resolve => setTimeout(resolve, 0))

    // Send the edited message as a new message
    await onSendMessage(content, userAttachments.length ? userAttachments : undefined)
  }, [messages, onUpdateMessages, onSendMessage, conversationId, currentChatId])

  const copyMessageContent = useCallback((content: Message['content']) => {
    const text = extractTextFromContent(content)
    navigator.clipboard.writeText(text)
    toast({
      title: 'Copied',
      description: 'Response copied to clipboard'
    })
  }, [toast])

  const copyMessageMetadata = useCallback((message: Message) => {
    const metadata = {
      model: message.model,
      model_id: message.model_id,
      provider: message.provider,
      timestamp: message.timestamp,
      cost: message.cost,
      prompt_cost: message.prompt_cost,
      completion_cost: message.completion_cost,
      latency: message.latency,
      tokens: message.tokens
    }
    navigator.clipboard.writeText(JSON.stringify(metadata, null, 2))
    toast({
      title: 'Copied',
      description: 'Metadata copied to clipboard'
    })
  }, [toast])

  const exportMessageContent = useCallback((content: Message['content'], model?: string) => {
    const text = extractTextFromContent(content)
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const modelName = model ? model.replace(/[^a-zA-Z0-9-]/g, '_') : 'unknown'
    a.download = generateFilename(`response-${modelName}`, 'txt')
    a.click()
    URL.revokeObjectURL(url)
    toast({
      title: 'Exported',
      description: 'Response exported as text file'
    })
  }, [toast])

  const exportMessageMetadata = useCallback((message: Message) => {
    const metadata = {
      model: message.model,
      model_id: message.model_id,
      provider: message.provider,
      timestamp: message.timestamp,
      cost: message.cost,
      prompt_cost: message.prompt_cost,
      completion_cost: message.completion_cost,
      latency: message.latency,
      tokens: message.tokens
    }
    const blob = new Blob([JSON.stringify(metadata, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const modelName = message.model ? message.model.replace(/[^a-zA-Z0-9-]/g, '_') : 'unknown'
    a.download = generateFilename(`metadata-${modelName}`, 'json')
    a.click()
    URL.revokeObjectURL(url)
    toast({
      title: 'Exported',
      description: 'Metadata exported as JSON file'
    })
  }, [toast])

  // Chat-level functions
  const copyChatResponses = useCallback(() => {
    const text = buildChatResponsesText(messages)
    navigator.clipboard.writeText(text)
    toast({
      title: 'Copied',
      description: 'All responses copied to clipboard'
    })
  }, [messages, toast])

  const copyChatMetadata = useCallback(() => {
    const metadata = buildChatMetadata(messages)
    navigator.clipboard.writeText(JSON.stringify(metadata, null, 2))
    toast({
      title: 'Copied',
      description: 'All metadata copied to clipboard'
    })
  }, [messages, toast])

  const exportChatResponses = useCallback(() => {
    const text = buildChatResponsesText(messages)
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const modelName = model?.name ? model.name.replace(/[^a-zA-Z0-9-]/g, '_') : 'unknown'
    a.download = generateFilename(`chat-${modelName}`, 'txt')
    a.click()
    URL.revokeObjectURL(url)
    toast({
      title: 'Exported',
      description: 'All responses exported'
    })
  }, [messages, model, toast])

  const exportChatMetadata = useCallback(() => {
    const assistantMessages = messages.filter(m => m.role === 'assistant')
    const metadata = assistantMessages.map(m => ({
      model: m.model,
      model_id: m.model_id,
      provider: m.provider,
      timestamp: m.timestamp,
      cost: m.cost,
      prompt_cost: m.prompt_cost,
      completion_cost: m.completion_cost,
      latency: m.latency,
      tokens: m.tokens
    }))
    const blob = new Blob([JSON.stringify(metadata, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const modelName = model?.name ? model.name.replace(/[^a-zA-Z0-9-]/g, '_') : 'unknown'
    a.download = generateFilename(`chat-metadata-${modelName}`, 'json')
    a.click()
    URL.revokeObjectURL(url)
    toast({
      title: 'Exported',
      description: 'All metadata exported'
    })
  }, [messages, model, toast])

  // Handler for suggested questions in independent mode
  const handleLocalSuggestionClick = useCallback((suggestion: string) => {
    setExternalInputValue(suggestion)
  }, [])

  // Memoize inline handler functions to prevent ChatPanelProvider from re-rendering children
  const handleResend = useCallback(async (message: string) => {
    if (!onUpdateMessages) return

    // Find the last user message and its index
    let userMessageIndex = -1
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        userMessageIndex = i
        break
      }
    }

    if (userMessageIndex < 0) return

    // Get attachments from the original user message
    const userMessage = messages[userMessageIndex]
    const userAttachments = (userMessage.attachments || []) as Attachment[]

    // Remove the user message and any assistant messages after it (including interrupted/errored ones)
    const messagesToDelete = messages.slice(userMessageIndex)
    const updatedMessages = messages.slice(0, userMessageIndex)

    // Delete removed messages from the database (if they have message_id)
    if (conversationId && currentChatId) {
      await Promise.all(
        messagesToDelete
          .filter(m => m.message_id)
          .map(m => conversationsAPI.deleteMessage(conversationId, currentChatId, m.message_id!).catch(err => {
            console.error('Failed to delete message from database:', err)
          }))
      )
    }

    // Update messages first to remove the failed exchange
    onUpdateMessages(updatedMessages)

    // Suppress the warning while resending
    setSuppressInterruptedWarning(true)

    // Use setTimeout to ensure React has applied the state update before resending
    setTimeout(() => {
      onSendMessage(message, userAttachments.length ? userAttachments : undefined)
    }, 0)
  }, [messages, onUpdateMessages, onSendMessage, conversationId, currentChatId])

  const handleOpenImageGallery = useCallback((images: { src: string; alt: string }[], selectedIndex: number, fromAttachments: boolean) => {
    setGalleryImages(images)
    setSelectedImageIndex(selectedIndex)
    setSelectedAllImage(images[selectedIndex])
    setIsGalleryOpen(true)
    setGalleryOpenedFromAttachments(fromAttachments)
  }, [])

  const handleOpenPdf = useCallback((src: string, name: string) => {
    setPdfSrc(src)
    setPdfName(name)
    setIsPdfOpen(true)
  }, [])

  const handleOpenTextFile = useCallback(async (file: FileAttachment) => {
    const fileName = file.file?.name || 'file'

    // If we have textContent cached, show modal directly
    if (file.textContent) {
      setFetchedFileContent(null) // Clear any previously fetched content
      setSelectedFile(file)
      setIsModalOpen(true)
      return
    }

    // If we have an assetId (after reload), fetch the content
    const assetId = (file as any).assetId
    if (assetId) {
      try {
        const blob = await assetsAPI.download(assetId)
        if (blob) {
          const content = await blob.text()
          setFetchedFileContent(content)
          setSelectedFile(file)
          setIsModalOpen(true)
        } else {
          toast({
            title: 'Failed to load file',
            description: `Could not load content for ${fileName}`,
            variant: 'destructive'
          })
        }
      } catch (error) {
        console.error('Failed to fetch file content:', error)
        toast({
          title: 'Failed to load file',
          description: `Could not load content for ${fileName}`,
          variant: 'destructive'
        })
      }
      return
    }

    toast({
      title: 'File content not available',
      description: `${fileName} has no content to display`,
      variant: 'destructive'
    })
  }, [toast])

  const handleOpenAllAttachments = useCallback((atts: Attachment[]) => {
    setAllAttachments(atts)
    setIsAllAttachmentsOpen(true)
  }, [])

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

  // Image gallery dialog state
  const [isGalleryOpen, setIsGalleryOpen] = useState(false)
  const [galleryImages, setGalleryImages] = useState<{ src: string; alt: string }[]>([])
  const [selectedImageIndex, setSelectedImageIndex] = useState<number | null>(null)
  const [galleryOpenedFromAttachments, setGalleryOpenedFromAttachments] = useState(false)
  const [isPdfOpen, setIsPdfOpen] = useState(false)
  const [pdfSrc, setPdfSrc] = useState<string>("")
  const [pdfName, setPdfName] = useState<string>("")
  const [isAllAttachmentsOpen, setIsAllAttachmentsOpen] = useState(false)
  const [allAttachments, setAllAttachments] = useState<Attachment[]>([])
  const [selectedAllImage, setSelectedAllImage] = useState<{ src: string; alt: string } | null>(null)
  const [cachedAttachments, setCachedAttachments] = useState<Record<string, CachedAttachment>>({})
  const [isModelDetailsOpen, setIsModelDetailsOpen] = useState(false)
  const [selectedModelDetails, setSelectedModelDetails] = useState<ModelCatalogEntry | null>(null)

  // Access model catalog/caches to resolve details for modal
  const modelStore = useModelStore()

  const resolveModelDetails = useCallback((modelId?: string): ModelCatalogEntry | null => {
    if (!modelId) return null

    // First, try to find in model store
    const from = [
      modelStore.currentModel ? [modelStore.currentModel] : [],
      modelStore.models,
      modelStore.allModels,
      modelStore.recentModels.map(m => m.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.recentChatModels.map(m => m.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.favorites.map(f => f.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.comparisonModels,
    ].flat()
    const found = from.find(m => m.model_id === modelId)
    if (found) return found

    // If not found, search in messages to get metadata
    const messageWithModel = messages.find(msg => msg.model_id === modelId)
    if (messageWithModel && messageWithModel.model && messageWithModel.provider) {
      // Construct minimal entry from message metadata
      return toModelCatalogEntry({
        id: modelId,
        model_id: modelId,
        name: messageWithModel.model,
        provider: messageWithModel.provider,
        provider_icon_slug: messageWithModel.provider_icon_slug,
        provider_icon_url: messageWithModel.provider_icon_url,
        model_icon_slug: messageWithModel.model_icon_slug,
        model_icon_url: messageWithModel.model_icon_url,
        cost_per_1m_prompt: 0,
        cost_per_1m_completion: 0,
        max_tokens: 0,
        supports_streaming: true,
        supports_functions: false,
        supports_structured_outputs: false,
        supports_reasoning: false,
        supports_prompt_caching: false,
        supports_stream_cancellation: false,
        input_modalities: [],
        tags: [],
        is_available: true,
      })
    }

    return null
  }, [modelStore, messages])

  const openModelDetails = useCallback((modelId?: string) => {
    const targetModelId = modelId || model?.model_id
    const details = resolveModelDetails(targetModelId)
    if (details) {
      setSelectedModelDetails(details)
      setIsModelDetailsOpen(true)
    } else if (targetModelId && model) {
      // Final fallback: use current model info if nothing else worked
      const minimal: ModelCatalogEntry = {
        id: targetModelId,
        model_id: targetModelId,
        name: model.name || targetModelId,
        provider: model.provider || 'unknown',
        provider_icon_slug: model.provider_icon_slug,
        provider_icon_url: model.provider_icon_url,
        model_icon_slug: model.model_icon_slug,
        model_icon_url: model.model_icon_url,
        cost_per_1m_prompt: 0,
        cost_per_1m_completion: 0,
        max_tokens: model.max_tokens || 0,
        supports_streaming: true,
        supports_functions: Boolean((model as any).supports_functions),
        supports_structured_outputs: Boolean((model as any).supports_structured_outputs),
        supports_reasoning: Boolean((model as any).supports_reasoning),
        supports_prompt_caching: Boolean((model as any).supports_prompt_caching),
        supports_stream_cancellation: true,
        modality: null,
        input_modalities: model.input_modalities || [],
        output_modalities: (model as any).output_modalities || ['text'],
        tokenizer: null,
        max_completion_tokens: null,
        is_moderated: false,
        default_parameters: {},
        description: undefined,
        tags: [],
        is_available: true,
        fetched_at: new Date().toISOString(),
      }
      setSelectedModelDetails(minimal)
      setIsModelDetailsOpen(true)
    }
  }, [model, resolveModelDetails])

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

  // Hydrate missing file metadata/content from cache (survives refresh)
  useEffect(() => {
    const loadCache = async () => {
      const toCheck: string[] = []
      // attachments in compose area
      attachments.forEach(att => {
        if (att.type === 'file') {
          if (!att.file || (!att.base64 && !att.textContent)) toCheck.push(att.id)
        } else if (att.type === 'image') {
          // After refresh, images may miss base64/preview (sanitized). Try to hydrate.
          if (!(att as any).base64 && !(att as any).preview) toCheck.push(att.id)
        }
      })
      // attachments inside messages
      messages.forEach(m => {
        const atts = (m.attachments || []) as Attachment[]
        atts.forEach(att => {
          if (att.type === 'file') {
            if (!att.file || (!att.base64 && !att.textContent)) toCheck.push(att.id)
          } else if (att.type === 'image') {
            if (!(att as any).base64 && !(att as any).preview) toCheck.push(att.id)
          }
        })
      })
      if (toCheck.length === 0) return
      const entries: Record<string, CachedAttachment> = {}
      for (const id of toCheck) {
        try {
          const cached = await cacheGet(id)
          if (cached) entries[id] = cached
        } catch {}
      }
      if (Object.keys(entries).length > 0) {
        setCachedAttachments(prev => ({ ...prev, ...entries }))
      }
    }
    loadCache()
    // Re-run when messages or attachments change
  }, [messages, attachments])

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
