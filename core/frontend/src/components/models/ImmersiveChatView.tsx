/**
 * ImmersiveChatView Component
 *
 * A fullscreen, focused chat experience similar to ChatGPT/Claude/Gemini.
 * Features:
 * - Centered message container with max-width
 * - Floating input with integrated controls
 * - Clean, distraction-free design
 */

import { memo, useCallback, useMemo, useRef, useEffect, useLayoutEffect, useState } from 'react'
import { useVoiceConversation } from '@/hooks/useVoiceConversation'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ImagePreviewModal } from './ImagePreviewModal'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { VisuallyHidden } from '@radix-ui/react-visually-hidden'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from '@/components/ui/dropdown-menu'
import {
  Minimize2,
  Plus,
  MoreVertical,
  Copy,
  Download,
  MessageSquarePlus,
  RefreshCw,
  ImagePlus,
  FileCode,
  FileType,
  Loader2,
  GalleryVerticalEnd,
  ScrollText,
  BookOpen,
  FileText,
  Braces,
  X,
  FolderGit2,
  Globe,
  PanelRight,
  Video,
  Music,
  Play,
  Code2,
} from 'lucide-react'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'
import { cn } from '@/lib/utils'
import { useNavigate } from '@tanstack/react-router'
import { ModelComboBox } from './ModelComboBox'
import { ModelIcon } from './ModelIcon'
import { MessageList } from './MessageList'
import { MessageInput } from './MessageInput'
import type { FeatureState } from './GlobalFeatureToggles'
import { ChatStates } from './ChatStates'
import { SuggestedQuestionsCarousel } from './SuggestedQuestionsCarousel'
import { CostEstimationDisplay } from './CostEstimationDisplay'
import { ProviderGreeting } from './ProviderGreeting'
import { CodeEditorModal } from '@/components/sandbox'
import { ModelDetailsModal } from './ModelDetailsModal'
import { FilePreviewModal } from './FilePreviewModal'
import { PdfPreviewModal } from './PdfPreviewModal'
import { ChatInstructionsSheet } from './ChatInstructionsSheet'
import { ChatPanelProvider } from './ChatPanelContext'
import { SparkAutoFixProvider, type SparkFixRequest } from './SparkAutoFixContext'
import { VoiceConversationOverlay } from './VoiceConversationOverlay'
import { useAuthStore } from '@/store/authStore'
import { extractTextFromContent } from '@/utils/chatUtils'
import useModelStore from '@/store/modelStore'
import { useNavigationStore } from '@/store/navigationStore'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import { useProjectPanelStore } from '@/store/projectPanelStore'
import { usePreviewPanelStore } from '@/store/previewPanelStore'
import { ArtifactsSidePanel } from './ArtifactsSidePanel'
import { ProjectStatusSidePanel } from './ProjectStatusSidePanel'
import { PreviewSidePanel } from '@/components/preview/PreviewSidePanel'
import { useUIStore } from '@/store/uiStore'
import { toast } from 'sonner'
import { removeProviderPrefix } from '@/lib/model-utils'
import { pricingUtils } from '@/lib/pricing-utils'
import type { Chat, Model, Message, ModelParameters, Attachment, FileAttachment, ImageAttachment, VideoAttachment, AudioAttachment } from './types'
import { getFileExtension } from '@/utils/fileUtils'
import { TypeBadge } from '@/lib/type-badges'
import { formatFileSize } from '@/utils/imageUtils'
import type { ModelCatalogEntry } from '@/types/models'
import type { CachedAttachment } from '@/utils/attachmentCache'
import { assetsAPI } from '@/api/assets'
import { conversationsAPI } from '@/api/conversations'
import { fsAPI } from '@/api/fs'
import { useVerificationGuard } from '@/components/auth/VerificationGate'

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
  onToolExecuted?: (toolCallId: string, toolName: string, result: any) => void
  onAddChat?: () => void

  // Model selection
  showFilters?: boolean
  onToggleFilters?: () => void
  hasActiveFilters?: boolean
  filters?: any
  onFiltersChange?: (filters: any) => void
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
  activeServers?: any[]

  // Cost estimation
  estimatedCosts?: any
  onEstimateCost?: (text: string) => Promise<void>
  isEstimating?: boolean
  setEstimatedCost?: (cost: any) => void

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
  const modelStore = useModelStore()
  const { openMobileSidebar } = useNavigationStore()
  const { isPanelOpen: isArtifactsPanelOpen, imageCount, videoCount } = useArtifactsPanelStore()
  const { isPanelOpen: isProjectPanelOpen, openPanel: openProjectPanel, closePanel: closeProjectPanel, clonedRepo } = useProjectPanelStore()
  const { isPanelOpen: isPreviewPanelOpen, openPanel: openPreviewPanel, closePanel: closePreviewPanel } = usePreviewPanelStore()
  const isMobile = useUIStore((state) => state.isMobile)
  const navigate = useNavigate()

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
  const [hasWorkspace, setHasWorkspace] = useState(false)
  const [inputValue, setInputValue] = useState('')

  // Detect whether this chat has workspace files (for "Open IDE" button)
  const toolMessageCount = useMemo(
    () => chat.messages.filter(m => m.role === 'tool').length,
    [chat.messages]
  )

  useEffect(() => {
    setHasWorkspace(false)

    if (clonedRepo) {
      setHasWorkspace(true)
      return
    }

    if (!user?.id || !chat?.id) return
    let cancelled = false
    fsAPI.getWorkspaceInfo({ user_id: user.id.toString(), chat_id: chat.id })
      .then(info => {
        if (!cancelled) setHasWorkspace(info.exists && (info.file_count ?? 0) > 0)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [clonedRepo, user?.id, chat?.id, toolMessageCount])

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

  const [isModelDetailsOpen, setIsModelDetailsOpen] = useState(false)
  const [selectedModelDetails, setSelectedModelDetails] = useState<ModelCatalogEntry | null>(null)
  const [mobileModelSheetOpen, setMobileModelSheetOpen] = useState(false)
  const [voiceOverlayOpen, setVoiceOverlayOpen] = useState(false)
  const [instructionsSheetOpen, setInstructionsSheetOpen] = useState(false)
  const [isSavingToKnowledgeBase, setIsSavingToKnowledgeBase] = useState(false)
  const [showSaveToKBDialog, setShowSaveToKBDialog] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const contentEndRef = useRef<HTMLDivElement>(null)
  const prevLastMsgKeyRef = useRef<string | null>(null)
  // 'pin' = user message pinned at top, 'follow' = auto-scroll to bottom
  const scrollModeRef = useRef<'pin' | 'follow'>('follow')
  const spacerActiveRef = useRef(false)
  const spacerRef = useRef<HTMLDivElement>(null)
  const pinnedScrollTopRef = useRef<number>(0)
  const pinAnimatingRef = useRef(false)
  const pinAnimFrameRef = useRef<number>(0)
  // User scroll detection — stops auto-scroll when user scrolls manually
  const userHasScrolledRef = useRef(false)
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

  // Detect user scroll via wheel/touch — these are always user-initiated (no race conditions)
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    const onUserScroll = () => { userHasScrolledRef.current = true }

    container.addEventListener('wheel', onUserScroll, { passive: true })
    container.addEventListener('touchmove', onUserScroll, { passive: true })
    return () => {
      container.removeEventListener('wheel', onUserScroll)
      container.removeEventListener('touchmove', onUserScroll)
    }
  }, [])

  // Scroll clamp: never allow scrolling past the last user message at top of visible area,
  // but allow normal scrolling when the assistant response overflows the viewport.
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    const paddingBottom = parseFloat(getComputedStyle(container).paddingBottom) || 0

    const clampScroll = () => {
      const userMsgs = container.querySelectorAll('[data-message-role="user"]')
      const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
      if (!lastUserEl) return

      const allMsgs = container.querySelectorAll('[data-message-role]')
      const lastMsgEl = allMsgs[allMsgs.length - 1] as HTMLElement | null
      if (!lastMsgEl) return

      const containerRect = container.getBoundingClientRect()
      const userMsgRect = lastUserEl.getBoundingClientRect()
      const lastMsgRect = lastMsgEl.getBoundingClientRect()

      const lastUserMsgAbsoluteTop = container.scrollTop + (userMsgRect.top - containerRect.top)
      const lastMessageBottom = container.scrollTop + (lastMsgRect.bottom - containerRect.top)
      const effectiveViewport = container.clientHeight - paddingBottom

      const maxScroll = Math.max(lastUserMsgAbsoluteTop, lastMessageBottom - effectiveViewport)

      if (container.scrollTop > maxScroll) {
        container.scrollTop = maxScroll
      }
    }

    container.addEventListener('scroll', clampScroll)
    return () => container.removeEventListener('scroll', clampScroll)
  }, [])

  // Reset spacer when switching conversations
  useEffect(() => {
    spacerActiveRef.current = false
    if (spacerRef.current) spacerRef.current.style.height = '0px'
  }, [conversationId])

  // Size the spacer so the user can scroll the last user message to the top
  // but never into empty space. As the response grows, spacer shrinks by
  // the same amount — keeping scrollHeight constant (no jumps).
  //
  // Formula: spacerH = max(0, visibleH - (contentBottom - lastUserMsgTop))
  //   visibleH = clientHeight - 176  (176 = pb-44, input zone overlap)
  //   When response overflows visibleH → spacer = 0 → normal scrolling
  const updateSpacerHeight = useCallback(() => {
    const container = scrollContainerRef.current
    const spacer = spacerRef.current
    if (!container || !spacer) return

    if (!spacerActiveRef.current) {
      spacer.style.height = '0px'
      return
    }

    const contentEndEl = contentEndRef.current
    if (!contentEndEl) return

    const containerRect = container.getBoundingClientRect()

    // Content bottom offset (where real content ends, before spacer)
    const endRect = contentEndEl.getBoundingClientRect()
    const contentBottomOffset = endRect.top - containerRect.top + container.scrollTop

    // Last user message top offset
    const userMsgs = container.querySelectorAll('[data-message-role="user"]')
    const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
    if (!lastUserEl) { spacer.style.height = '0px'; return }

    const userRect = lastUserEl.getBoundingClientRect()
    const lastUserOffset = userRect.top - containerRect.top + container.scrollTop

    // Height of content from user message top to content end
    const contentBelowUser = contentBottomOffset - lastUserOffset

    // Measure total bottom padding below the spacer:
    // scrollHeight = contentBottomOffset + currentSpacerH + totalBottomPadding
    const currentSpacerH = spacer.offsetHeight
    const totalBottomPadding = container.scrollHeight - contentBottomOffset - currentSpacerH
    const visibleHeight = container.clientHeight - totalBottomPadding

    const needed = visibleHeight - contentBelowUser
    spacer.style.height = `${Math.max(0, needed)}px`
  }, [])

  // Ctrl+L scroll behaviour:
  // 1. User sends a message → reset view: user message at the top, empty space below
  // 2. Response streams in → view stays pinned (user msg at top) until content fills viewport
  // 3. Once content overflows viewport → switch to follow-bottom (tracking real content)
  // 4. Generation ends → normal follow-bottom for subsequent interactions
  useLayoutEffect(() => {
    const container = scrollContainerRef.current
    if (!container || chat.messages.length === 0) return

    const lastMsg = chat.messages[chat.messages.length - 1]
    const lastMsgKey = `${lastMsg.role}-${lastMsg.timestamp?.getTime()}`
    const isNewMessage = lastMsgKey !== prevLastMsgKeyRef.current
    prevLastMsgKeyRef.current = lastMsgKey

    // Detect new user message → enter pin mode with smooth animation
    if (isNewMessage && lastMsg.role === 'user') {
      spacerActiveRef.current = true
      updateSpacerHeight()
      scrollModeRef.current = 'pin'
      userHasScrolledRef.current = false

      // Cancel any existing animation
      if (pinAnimFrameRef.current) {
        cancelAnimationFrame(pinAnimFrameRef.current)
        pinAnimFrameRef.current = 0
      }

      // Start smooth rAF animation to scroll user message to top
      const userMsgs = container.querySelectorAll('[data-message-role="user"]')
      const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
      if (lastUserEl) {
        const cRect = container.getBoundingClientRect()
        const mRect = lastUserEl.getBoundingClientRect()
        const startScroll = container.scrollTop
        const targetScroll = startScroll + (mRect.top - cRect.top) - 16
        const duration = 350

        pinAnimatingRef.current = true
        const startTime = performance.now()

        const animate = (now: number) => {
          // If user scrolled during animation, cancel it
          if (userHasScrolledRef.current) {
            pinAnimatingRef.current = false
            pinAnimFrameRef.current = 0
            scrollModeRef.current = 'follow'
            return
          }
          const elapsed = now - startTime
          const progress = Math.min(1, elapsed / duration)
          const eased = 1 - Math.pow(1 - progress, 3)
          container.scrollTop = startScroll + (targetScroll - startScroll) * eased

          if (progress < 1) {
            pinAnimFrameRef.current = requestAnimationFrame(animate)
          } else {
            pinAnimatingRef.current = false
            pinnedScrollTopRef.current = targetScroll
            pinAnimFrameRef.current = 0
          }
        }

        pinAnimFrameRef.current = requestAnimationFrame(animate)
      }
      return
    }

    updateSpacerHeight()

    // --- PIN MODE: keep user message at top ---
    if (scrollModeRef.current === 'pin') {
      if (pinAnimatingRef.current) return
      // User scrolled manually → release pin
      if (userHasScrolledRef.current) {
        scrollModeRef.current = 'follow'
        return
      }

      const userMsgs = container.querySelectorAll('[data-message-role="user"]')
      const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
      if (lastUserEl) {
        const cRect = container.getBoundingClientRect()
        const mRect = lastUserEl.getBoundingClientRect()
        const distFromTop = mRect.top - cRect.top

        // Correct any drift (tight 1px threshold)
        if (Math.abs(distFromTop - 16) > 1) {
          const target = container.scrollTop + distFromTop - 16
          pinnedScrollTopRef.current = target
          container.scrollTop = target
          return
        }
      }

      // Check if real content has overflowed past the viewport → switch to follow
      const contentEnd = contentEndRef.current
      if (contentEnd) {
        const cRect = container.getBoundingClientRect()
        const endRect = contentEnd.getBoundingClientRect()
        if (endRect.top > cRect.bottom - 40) {
          scrollModeRef.current = 'follow'
          // Fall through to follow logic below
        } else {
          if (!isGenerating) scrollModeRef.current = 'follow'
          return
        }
      } else {
        if (!isGenerating) scrollModeRef.current = 'follow'
        return
      }
    }

    // --- FOLLOW MODE: keep content bottom visible ---
    // Skip if user has scrolled — let them read freely
    if (userHasScrolledRef.current) {
      // Re-enable if user scrolled back near bottom
      const distFromBottom = container.scrollHeight - container.clientHeight - container.scrollTop
      if (distFromBottom >= 50) return
      userHasScrolledRef.current = false
    }

    const contentEnd = contentEndRef.current
    if (isGenerating && contentEnd) {
      const cRect = container.getBoundingClientRect()
      const endRect = contentEnd.getBoundingClientRect()
      if (endRect.bottom > cRect.bottom) {
        container.scrollTop += (endRect.bottom - cRect.bottom) + 16
      }
    } else if (!isGenerating) {
      container.scrollTop = container.scrollHeight - container.clientHeight
    }
  }, [chat.messages, isGenerating])

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

  // Memoize model name display
  const modelDisplayName = useMemo(() => {
    if (!chat.model) return 'Select a model'
    // Remove provider prefix if present
    const name = chat.model.name
    const colonIndex = name.indexOf(':')
    return colonIndex > -1 ? name.slice(colonIndex + 1).trim() : name
  }, [chat.model])

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
        if (m.role === 'assistant' && (m as any).isUnsupported) toRemove.add(i)
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

  const copyMessageContent = useCallback((content: Message['content']) => {
    navigator.clipboard.writeText(extractTextFromContent(content))
    toast.success('Copied to clipboard')
  }, [])

  const copyMessageMetadata = useCallback((message: Message) => {
    navigator.clipboard.writeText(JSON.stringify(message, null, 2))
    toast.success('Metadata copied to clipboard')
  }, [])

  const exportMessageContent = useCallback((content: Message['content'], model?: string) => {
    const blob = new Blob([extractTextFromContent(content)], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `message-${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }, [])

  const exportMessageMetadata = useCallback((message: Message) => {
    const blob = new Blob([JSON.stringify(message, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `message-metadata-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [])

  const formatCost = useCallback((cost?: number) => {
    if (!cost || cost === 0) return '$0.00'
    if (cost < 0.01) return '<$0.01'
    return `$${cost.toFixed(4)}`
  }, [])

  const formatLatency = useCallback((latency?: number) => {
    if (!latency) return '-'
    return `${(latency / 1000).toFixed(2)}s`
  }, [])

  // Image gallery state
  const [imageGalleryOpen, setImageGalleryOpen] = useState(false)
  const [galleryImages, setGalleryImages] = useState<{ src: string; alt: string }[]>([])
  const [gallerySelectedIndex, setGallerySelectedIndex] = useState(0)

  // All attachments modal state
  const [isAllAttachmentsOpen, setIsAllAttachmentsOpen] = useState(false)
  const [allAttachments, setAllAttachments] = useState<Attachment[]>([])

  // File preview modal state
  const [isFilePreviewOpen, setIsFilePreviewOpen] = useState(false)
  const [previewFile, setPreviewFile] = useState<{ name: string; size: number; content: string } | null>(null)
  const [loadingFileId, setLoadingFileId] = useState<string | null>(null)
  // PDF preview modal state
  const [isPdfOpen, setIsPdfOpen] = useState(false)
  const [pdfSrc, setPdfSrc] = useState('')
  const [pdfName, setPdfName] = useState('')
  // Blob URL loading for images/PDFs from asset storage (auth required)
  const [loadedBlobUrls, setLoadedBlobUrls] = useState<Record<string, string>>({})
  const [loadingAssetIds, setLoadingAssetIds] = useState<Set<string>>(new Set())

  // Load asset from storage via API (includes auth headers) and return blob URL
  const loadAssetAsBlobUrl = useCallback(async (assetId: string): Promise<string | null> => {
    if (loadedBlobUrls[assetId]) return loadedBlobUrls[assetId]
    if (loadingAssetIds.has(assetId)) return null

    setLoadingAssetIds(prev => new Set(prev).add(assetId))
    try {
      const blob = await assetsAPI.download(assetId)
      if (blob) {
        const blobUrl = URL.createObjectURL(blob)
        setLoadedBlobUrls(prev => ({ ...prev, [assetId]: blobUrl }))
        return blobUrl
      }
      return null
    } catch (error) {
      console.error('[ImmersiveChatView] Failed to load asset:', assetId, error)
      return null
    } finally {
      setLoadingAssetIds(prev => {
        const next = new Set(prev)
        next.delete(assetId)
        return next
      })
    }
  }, [loadedBlobUrls, loadingAssetIds])

  // Cleanup blob URLs on unmount
  useEffect(() => {
    return () => {
      Object.values(loadedBlobUrls).forEach(url => URL.revokeObjectURL(url))
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleOpenImageGallery = useCallback((images: { src: string; alt: string }[], selectedIndex: number) => {
    setGalleryImages(images)
    setGallerySelectedIndex(selectedIndex)
    setImageGalleryOpen(true)
  }, [])

  // PDF preview handler
  const handleOpenPdf = useCallback((src: string, name: string) => {
    setPdfSrc(src)
    setPdfName(name)
    setIsPdfOpen(true)
  }, [])

  const handleOpenTextFile = useCallback(async (file: FileAttachment) => {
    const fileName = file.file?.name || 'file'
    const fileSize = file.file?.size || 0

    // If we have textContent cached, show modal directly
    if (file.textContent) {
      setPreviewFile({ name: fileName, size: fileSize, content: file.textContent })
      setIsFilePreviewOpen(true)
      return
    }

    // If we have an assetId (after reload), fetch the content
    if (file.assetId) {
      setLoadingFileId(file.id)
      try {
        const blob = await assetsAPI.download(file.assetId)
        if (blob) {
          const content = await blob.text()
          setPreviewFile({ name: fileName, size: fileSize, content })
          setIsFilePreviewOpen(true)
        } else {
          toast.error('Failed to load file content')
        }
      } catch (error) {
        console.error('Failed to fetch file content:', error)
        toast.error('Failed to load file content')
      } finally {
        setLoadingFileId(null)
      }
      return
    }

    toast.error('File content not available')
  }, [])

  const handleOpenAllAttachments = useCallback((attachments: Attachment[]) => {
    // Open the all attachments modal to show all attachment types
    setAllAttachments(attachments)
    setIsAllAttachmentsOpen(true)
  }, [])

  const handleOpenModelDetails = useCallback((modelId?: string) => {
    const targetModelId = modelId || chat.model?.model_id
    if (!targetModelId) return

    // Try to find model details from model store
    const from = [
      modelStore.currentModel ? [modelStore.currentModel] : [],
      modelStore.models,
      modelStore.allModels,
      modelStore.recentModels.map(m => m.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.recentChatModels.map(m => m.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.favorites.map(f => f.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.comparisonModels,
    ].flat()
    const found = from.find(m => m.model_id === targetModelId)

    if (found) {
      setSelectedModelDetails(found)
      setIsModelDetailsOpen(true)
    } else if (chat.model) {
      // Fallback: create minimal details from current model
      const minimal: ModelCatalogEntry = {
        id: targetModelId,
        model_id: targetModelId,
        name: chat.model.name || targetModelId,
        provider: chat.model.provider || 'unknown',
        provider_icon_slug: chat.model.provider_icon_slug,
        provider_icon_url: chat.model.provider_icon_url,
        model_icon_slug: chat.model.model_icon_slug,
        model_icon_url: chat.model.model_icon_url,
        cost_per_1m_prompt: 0,
        cost_per_1m_completion: 0,
        max_tokens: chat.model.max_tokens || 0,
        supports_streaming: true,
        supports_functions: Boolean((chat.model as any).supports_functions),
        supports_structured_outputs: Boolean((chat.model as any).supports_structured_outputs),
        supports_reasoning: Boolean((chat.model as any).supports_reasoning),
        supports_prompt_caching: Boolean((chat.model as any).supports_prompt_caching),
        supports_stream_cancellation: true,
        modality: null,
        input_modalities: chat.model.input_modalities || [],
        output_modalities: (chat.model as any).output_modalities || ['text'],
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
  }, [chat.model, modelStore])

  // Open save to knowledge base confirmation dialog
  const handleSaveToKnowledgeBase = useCallback(() => {
    if (!conversationId) return
    setShowSaveToKBDialog(true)
  }, [conversationId])

  // Actually save conversation to knowledge base
  const confirmSaveToKnowledgeBase = useCallback(async () => {
    if (isSavingToKnowledgeBase || !conversationId) return

    setIsSavingToKnowledgeBase(true)
    try {
      const result = await conversationsAPI.saveToKnowledgeBase(conversationId)
      toast.success('Saved to knowledge base', {
        description: result.filename,
      })
      setShowSaveToKBDialog(false)
    } catch (error: any) {
      const errorData = error.response?.data
      if (errorData?.existing_document_id) {
        toast.error('Already saved', {
          description: errorData.error || 'This conversation is already in your knowledge base',
        })
      } else if (errorData?.error) {
        toast.error('Failed to save', {
          description: errorData.error,
        })
      } else {
        toast.error('Failed to save to knowledge base')
      }
    } finally {
      setIsSavingToKnowledgeBase(false)
    }
  }, [conversationId, isSavingToKnowledgeBase])

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
    chat.model, chat.messages, chat.isLoading, chat.id, user, conversationId,
    onUpdateMessages, onToolExecuted, handleRetry, handleEditMessage,
    copyMessageContent, copyMessageMetadata, exportMessageContent, exportMessageMetadata,
    handleOpenModelDetails, formatCost, formatLatency, handleOpenImageGallery,
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
      {/* Header bar - model selector and actions */}
      <header className="flex-shrink-0 sticky top-0 flex items-center justify-between px-3 md:px-4 py-2 border-b border-border/50 bg-background/95 backdrop-blur-sm z-10">
        {/* Left: Menu button (mobile) + Model selector */}
        <div className="flex items-center gap-1">
          {/* Mobile sidebar menu button */}
          <Button
            variant="ghost"
            size="sm"
            className="md:hidden h-8 w-8 p-0 shrink-0"
            onClick={openMobileSidebar}
          >
            <PremiumMenuIcon size={18} />
          </Button>
          <div className="hidden md:block min-w-[180px] max-w-[280px]">
            <ModelComboBox
              models={models}
              value={chat.model?.model_id}
              onValueChange={(modelId) => {
                const model = models.find(m => m.model_id === modelId)
                if (model) onModelSelect(model as Model)
              }}
              showFilters={showFilters}
              onToggleFilters={onToggleFilters}
              hasActiveFilters={hasActiveFilters}
              filters={filters}
              onFiltersChange={onFiltersChange}
              providers={providers}
              recentModelIds={recentModelIds}
              variant="ghost"
            />
          </div>
          {/* Mobile: Tap to open model selection sheet (hidden in multi-chat mode - tabs show models) */}
          {!headerCenterContent && (
            <button
              onClick={() => setMobileModelSheetOpen(true)}
              className="md:hidden flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-muted transition-colors max-w-[160px]"
            >
              {chat.model ? (
                <>
                  <ModelIcon
                    modelName={chat.model.name}
                    modelId={chat.model.model_id}
                    provider={chat.model.provider}
                    modelIconSlug={chat.model.model_icon_slug}
                    modelIconUrl={chat.model.model_icon_url}
                    providerIconSlug={chat.model.provider_icon_slug}
                    providerIconUrl={chat.model.provider_icon_url}
                    size={20}
                    showTooltip={false}
                  />
                  <span className="text-sm font-medium truncate">
                    {removeProviderPrefix(chat.model.name, chat.model.provider)}
                  </span>
                </>
              ) : (
                <span className="text-sm text-muted-foreground">Select model</span>
              )}
            </button>
          )}
        </div>

        {/* Center: Optional content (e.g., multi-chat tab bar) */}
        {headerCenterContent && (
          <div className="absolute left-1/2 -translate-x-1/2 max-w-[calc(100vw-200px)] md:max-w-[calc(100vw-400px)]">
            {headerCenterContent}
          </div>
        )}

        {/* Right: Actions */}
        <div className="flex items-center gap-1">
          {/* Add comparison chat - hidden on mobile, shown in menu instead */}
          {onAddChat && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onAddChat}
                    className="hidden md:flex h-8 px-2 text-muted-foreground hover:text-foreground"
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    <span className="text-xs">Compare</span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  Add another model to compare responses
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}

          {/* Open IDE button - desktop only */}
          {hasWorkspace && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setCodeEditorOpen(true)}
                    className="hidden md:flex h-8 px-2 text-muted-foreground hover:text-foreground"
                  >
                    <Code2 className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Open IDE</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}

          {/* Unified Panels popover */}
          {(() => {
            const totalArtifacts = currentChatSparks.length + imageCount + videoCount
            const openPanelCount = [isArtifactsPanelOpen, isProjectPanelOpen, isPreviewPanelOpen].filter(Boolean).length
            return (
              <Popover>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <PopoverTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className={cn(
                            "h-8 px-2 gap-1.5 relative",
                            openPanelCount > 0
                              ? "text-primary hover:text-primary/80"
                              : "text-muted-foreground hover:text-foreground"
                          )}
                        >
                          <PanelRight className="h-4 w-4" />
                          {openPanelCount > 0 && (
                            <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-primary" />
                          )}
                        </Button>
                      </PopoverTrigger>
                    </TooltipTrigger>
                    <TooltipContent>Panels</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <PopoverContent align="end" className="w-52 p-1.5">
                  <button
                    onClick={() => useArtifactsPanelStore.getState().setPanelOpen(!isArtifactsPanelOpen)}
                    className={cn(
                      "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
                      isArtifactsPanelOpen ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                    )}
                  >
                    <GalleryVerticalEnd className={cn("h-4 w-4 shrink-0", isArtifactsPanelOpen ? "text-brand-500" : "text-muted-foreground")} />
                    <span className="flex-1 text-left">Creations</span>
                    {totalArtifacts > 0 && (
                      <span className="text-xs tabular-nums text-muted-foreground">{totalArtifacts}</span>
                    )}
                  </button>
                  <button
                    onClick={() => isProjectPanelOpen ? closeProjectPanel() : openProjectPanel()}
                    className={cn(
                      "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
                      isProjectPanelOpen ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                    )}
                  >
                    <FolderGit2 className={cn("h-4 w-4 shrink-0", isProjectPanelOpen ? "text-blue-500" : "text-muted-foreground")} />
                    <span className="flex-1 text-left">Project</span>
                  </button>
                  <TooltipProvider delayDuration={300}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => isPreviewPanelOpen ? closePreviewPanel() : openPreviewPanel()}
                          className={cn(
                            "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
                            isPreviewPanelOpen ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                          )}
                        >
                          <Globe className={cn("h-4 w-4 shrink-0", isPreviewPanelOpen ? "text-green-500" : "text-muted-foreground")} />
                          <span className="flex-1 text-left">Dev Server</span>
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="left"><p>Live preview of running processes</p></TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </PopoverContent>
              </Popover>
            )
          })()}

          {/* More Options Menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {/* Change model - mobile only since selector opens sheet */}
              <DropdownMenuItem
                onClick={() => setMobileModelSheetOpen(true)}
                className="md:hidden"
              >
                <RefreshCw className="h-4 w-4 mr-2" /> Change model
              </DropdownMenuItem>
              {/* Compare models - mobile only, desktop has button */}
              {onAddChat && (
                <DropdownMenuItem
                  onClick={onAddChat}
                  className="md:hidden"
                >
                  <Plus className="h-4 w-4 mr-2" /> Compare models
                </DropdownMenuItem>
              )}
              {/* Remove chat - mobile only, for multi-chat mode */}
              {onRemoveChat && canRemoveChat && (
                <DropdownMenuItem
                  onClick={onRemoveChat}
                  className="md:hidden text-destructive focus:text-destructive"
                >
                  <X className="h-4 w-4 mr-2" /> Remove chat
                </DropdownMenuItem>
              )}
              {/* New conversation - mobile only */}
              <DropdownMenuItem
                onClick={() => navigate({ to: '/chats', search: { new: true } })}
                className="md:hidden"
              >
                <MessageSquarePlus className="h-4 w-4 mr-2" /> New conversation
              </DropdownMenuItem>
              <DropdownMenuSeparator className="md:hidden" />

              <DropdownMenuItem onClick={() => setInstructionsSheetOpen(true)}>
                <ScrollText className="h-4 w-4 mr-2" /> Chat instructions
              </DropdownMenuItem>
              {hasWorkspace && (
                <DropdownMenuItem onClick={() => setCodeEditorOpen(true)} className="md:hidden">
                  <Code2 className="h-4 w-4 mr-2" /> Open IDE
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />

              {(onCopyResponses || onExportResponses) && (
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <FileText className="h-4 w-4 mr-2" /> Responses
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent>
                    {onCopyResponses && (
                      <DropdownMenuItem onClick={onCopyResponses}>
                        <Copy className="h-4 w-4 mr-2" /> Copy
                      </DropdownMenuItem>
                    )}
                    {onExportResponses && (
                      <DropdownMenuItem onClick={onExportResponses}>
                        <Download className="h-4 w-4 mr-2" /> Export (.txt)
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
              )}
              {(onCopyMetadata || onExportMetadata) && (
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <Braces className="h-4 w-4 mr-2" /> Metadata
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent>
                    {onCopyMetadata && (
                      <DropdownMenuItem onClick={onCopyMetadata}>
                        <Copy className="h-4 w-4 mr-2" /> Copy (JSON)
                      </DropdownMenuItem>
                    )}
                    {onExportMetadata && (
                      <DropdownMenuItem onClick={onExportMetadata}>
                        <Download className="h-4 w-4 mr-2" /> Export (.json)
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
              )}

              {/* Save to Knowledge Base */}
              {hasMessages && (
                <DropdownMenuItem
                  onClick={handleSaveToKnowledgeBase}
                  disabled={isSavingToKnowledgeBase}
                >
                  {isSavingToKnowledgeBase ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <BookOpen className="h-4 w-4 mr-2" />
                  )}
                  Save to knowledge base
                </DropdownMenuItem>
              )}

            </DropdownMenuContent>
          </DropdownMenu>

          {/* Exit immersive - hidden on mobile (mobile is always immersive) */}
          {onExitImmersive && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onExitImmersive}
                    className="hidden md:flex h-8 px-2 text-muted-foreground hover:text-foreground"
                  >
                    <Minimize2 className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  Exit focus mode
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
      </header>

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
      <Dialog open={showSaveToKBDialog} onOpenChange={setShowSaveToKBDialog}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Save to Knowledge Base</DialogTitle>
            <DialogDescription>
              Save this conversation to your knowledge base? This will make the conversation content searchable by AI.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSaveToKBDialog(false)} disabled={isSavingToKnowledgeBase}>
              Cancel
            </Button>
            <Button onClick={confirmSaveToKnowledgeBase} disabled={isSavingToKnowledgeBase}>
              {isSavingToKnowledgeBase ? (
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
      <Dialog open={isAllAttachmentsOpen} onOpenChange={setIsAllAttachmentsOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Attachments</DialogTitle>
            <DialogDescription>
              {allAttachments.length} item{allAttachments.length !== 1 ? 's' : ''}
            </DialogDescription>
          </DialogHeader>

          {/* Group attachments into sections */}
          {(() => {
            const imageAtts = allAttachments.filter((a): a is ImageAttachment => a.type === 'image')
            const videoAtts = allAttachments.filter((a): a is VideoAttachment => a.type === 'video')
            const audioAtts = allAttachments.filter((a): a is AudioAttachment => a.type === 'audio')
            const fileAtts = allAttachments.filter((a): a is FileAttachment => a.type === 'file')

            // Categorize files by mime type or extension
            const textCodeAtts = fileAtts.filter(f => {
              const mimeType = f.file?.type || ''
              const name = f.file?.name || ''
              const ext = getFileExtension(name).toLowerCase()
              // Text-based mime types or common text file extensions
              return mimeType.startsWith('text/') ||
                mimeType === 'application/json' ||
                mimeType === 'application/xml' ||
                mimeType === 'application/javascript' ||
                ['txt', 'json', 'xml', 'csv', 'md', 'js', 'ts', 'jsx', 'tsx', 'py', 'html', 'css', 'yaml', 'yml', 'sh', 'sql'].includes(ext)
            })

            const pdfDocxAtts = fileAtts.filter(f => {
              const mimeType = f.file?.type || ''
              const name = f.file?.name || ''
              const ext = getFileExtension(name).toLowerCase()
              return ['pdf', 'doc', 'docx'].includes(ext) ||
                mimeType === 'application/pdf' ||
                mimeType === 'application/msword' ||
                mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            })

            return (
              <div className="space-y-6 max-h-[60vh] overflow-y-auto">
                {/* Images Section */}
                {imageAtts.length > 0 && (
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <ImagePlus className="h-4 w-4" />
                      <span>Images</span>
                      <span className="text-xs text-muted-foreground/70">({imageAtts.length})</span>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      {imageAtts.map((img, i) => {
                        // Use assetId to load via API (direct URLs don't work due to auth)
                        const assetId = (img as any).assetId || img.id
                        const blobUrl = assetId ? loadedBlobUrls[assetId] : null
                        const src = img.base64 || blobUrl || ''
                        const alt = img.file?.name || 'image'
                        const isLoading = assetId ? loadingAssetIds.has(assetId) : false
                        const needsLoad = !src && assetId && !isLoading

                        // Trigger loading if needed
                        if (needsLoad) {
                          loadAssetAsBlobUrl(assetId)
                        }

                        return (
                          <button
                            key={img.id}
                            type="button"
                            className="w-full h-48 rounded-md overflow-hidden cursor-zoom-in hover:opacity-90 transition-opacity"
                            onClick={() => {
                              if (!src) return
                              // Hydrate images with blob URLs
                              const imgs = imageAtts
                                .map(a => {
                                  const aAssetId = (a as any).assetId || a.id
                                  const aBlobUrl = aAssetId ? loadedBlobUrls[aAssetId] : null
                                  return { src: a.base64 || aBlobUrl || '', alt: a.file?.name || 'image' }
                                })
                                .filter(it => it.src)
                              handleOpenImageGallery(imgs, i)
                              setIsAllAttachmentsOpen(false)
                            }}
                          >
                            {isLoading ? (
                              <div className="w-full h-full flex items-center justify-center bg-muted/40">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                              </div>
                            ) : src ? (
                              <img src={src} alt={alt} className="w-full h-full object-cover" />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground bg-muted/40">
                                {alt}
                              </div>
                            )}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Videos Section */}
                {videoAtts.length > 0 && (
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <Video className="h-4 w-4" />
                      <span>Videos</span>
                      <span className="text-xs text-muted-foreground/70">({videoAtts.length})</span>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      {videoAtts.map((vid) => {
                        const name = vid.file?.name || 'video'
                        const ext = getFileExtension(name).toUpperCase()
                        const sizeStr = formatFileSize(vid.file?.size || 0)
                        const assetId = vid.assetId || vid.id
                        const blobUrl = assetId ? loadedBlobUrls[assetId] : null
                        const src = vid.preview || blobUrl || ''
                        const isLoading = assetId ? loadingAssetIds.has(assetId) : false

                        if (!src && assetId && !isLoading) {
                          loadAssetAsBlobUrl(assetId)
                        }

                        return (
                          <div
                            key={vid.id}
                            className="relative w-full h-48 rounded-md overflow-hidden bg-muted/40 group"
                          >
                            {isLoading ? (
                              <div className="w-full h-full flex items-center justify-center">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                              </div>
                            ) : src ? (
                              <video
                                src={src}
                                preload="metadata"
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center">
                                <Video className="h-8 w-8 text-muted-foreground" />
                              </div>
                            )}
                            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                              <div className="w-10 h-10 rounded-full bg-black/50 flex items-center justify-center">
                                <Play className="h-5 w-5 text-white ml-0.5" fill="white" />
                              </div>
                            </div>
                            <div className="absolute bottom-1 left-1 flex items-center gap-1">
                              <TypeBadge type={ext} />
                              <span className="text-[10px] px-1.5 py-0 rounded bg-black/60 text-white">{sizeStr}</span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Audio Section */}
                {audioAtts.length > 0 && (
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <Music className="h-4 w-4" />
                      <span>Audio</span>
                      <span className="text-xs text-muted-foreground/70">({audioAtts.length})</span>
                    </div>
                    <div className="flex flex-col gap-2">
                      {audioAtts.map((aud) => {
                        const name = aud.file?.name || 'audio'
                        const ext = getFileExtension(name).toUpperCase()
                        const sizeStr = formatFileSize(aud.file?.size || 0)
                        return (
                          <div
                            key={aud.id}
                            className="relative rounded-lg border border-border bg-secondary/30 p-2.5 w-full"
                          >
                            <div className="flex items-center gap-2">
                              <div className="flex-shrink-0 p-1.5 rounded bg-gradient-to-br from-purple-500/20 to-pink-500/20">
                                <Music className="h-4 w-4 text-purple-500" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium truncate leading-tight mb-1">{name}</p>
                                <div className="flex items-center gap-1.5">
                                  <TypeBadge type={ext} />
                                  <span className="text-[10px] text-muted-foreground">{sizeStr}</span>
                                </div>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Text/Code Section */}
                {textCodeAtts.length > 0 && (
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <FileCode className="h-4 w-4" />
                      <span>Text/Code</span>
                      <span className="text-xs text-muted-foreground/70">({textCodeAtts.length})</span>
                    </div>
                    <div className="flex flex-col gap-2">
                      {textCodeAtts.map((f) => {
                        const name = f.file?.name || 'file'
                        const extension = getFileExtension(name)
                        const sizeStr = formatFileSize(f.file?.size || 0)
                        const isAvailable = Boolean(f.textContent || f.assetId)
                        const isLoading = loadingFileId === f.id
                        return (
                          <button
                            key={f.id}
                            type="button"
                            onClick={() => handleOpenTextFile(f)}
                            disabled={!isAvailable || isLoading}
                            className={cn(
                              "relative group rounded-lg border border-border bg-secondary/30 transition-colors p-2.5 text-left w-full",
                              isAvailable && !isLoading ? "hover:bg-secondary/50" : "opacity-60 cursor-not-allowed"
                            )}
                          >
                            <div className="flex items-center gap-2">
                              <div className="flex-shrink-0 p-1.5 rounded bg-primary/10">
                                {isLoading ? (
                                  <Loader2 className="h-4 w-4 text-primary animate-spin" />
                                ) : (
                                  <FileCode className="h-4 w-4 text-primary" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium truncate leading-tight mb-1">{name}</p>
                                <div className="flex items-center gap-1.5">
                                  <span className="text-[10px] px-1.5 py-0 rounded bg-muted font-medium">{extension}</span>
                                  <span className="text-[10px] text-muted-foreground">{sizeStr}</span>
                                </div>
                              </div>
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* PDF/Docx Section */}
                {pdfDocxAtts.length > 0 && (
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <FileType className="h-4 w-4" />
                      <span>PDF/Documents</span>
                      <span className="text-xs text-muted-foreground/70">({pdfDocxAtts.length})</span>
                    </div>
                    <div className="flex flex-col gap-2">
                      {pdfDocxAtts.map((f) => {
                        const name = f.file?.name || 'file'
                        const extension = getFileExtension(name)
                        const sizeStr = formatFileSize(f.file?.size || 0)
                        const assetId = (f as any).assetId || f.id
                        const blobUrl = assetId ? loadedBlobUrls[assetId] : null
                        const isPdf = extension.toLowerCase() === 'pdf' || (!!f.base64 && !f.textContent)
                        const isAssetLoading = assetId ? loadingAssetIds.has(assetId) : false
                        // For PDFs we can use base64 or fetch via assetId; for DOCX we fetch text content
                        const isAvailable = isPdf
                          ? Boolean(f.base64 || blobUrl || assetId)
                          : Boolean(f.textContent || f.assetId)
                        const isLoading = loadingFileId === f.id || isAssetLoading
                        return (
                          <button
                            key={f.id}
                            type="button"
                            onClick={async () => {
                              if (isPdf) {
                                // Priority: base64 > loaded blob URL > fetch from API
                                let pdfSource = f.base64 || blobUrl
                                if (!pdfSource && assetId) {
                                  pdfSource = await loadAssetAsBlobUrl(assetId)
                                }
                                if (pdfSource) {
                                  handleOpenPdf(pdfSource, name)
                                } else {
                                  toast.error('Failed to load PDF')
                                }
                              } else {
                                // For non-PDF documents, use the async file handler
                                handleOpenTextFile(f)
                              }
                            }}
                            disabled={!isAvailable || isLoading}
                            className={cn(
                              "relative group rounded-lg border border-border bg-secondary/30 transition-colors p-2.5 text-left w-full",
                              isAvailable && !isLoading ? "hover:bg-secondary/50" : "opacity-60 cursor-not-allowed"
                            )}
                          >
                            <div className="flex items-center gap-2">
                              <div className="flex-shrink-0 p-1.5 rounded bg-primary/10">
                                {isLoading ? (
                                  <Loader2 className="h-4 w-4 text-primary animate-spin" />
                                ) : (
                                  <FileType className="h-4 w-4 text-primary" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium truncate leading-tight mb-1">{name}</p>
                                <div className="flex items-center gap-1.5">
                                  <span className="text-[10px] px-1.5 py-0 rounded bg-muted font-medium">{extension}</span>
                                  <span className="text-[10px] text-muted-foreground">{sizeStr}</span>
                                </div>
                              </div>
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )
          })()}

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAllAttachmentsOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Mobile Model Selection Sheet */}
      <Sheet open={mobileModelSheetOpen} onOpenChange={setMobileModelSheetOpen}>
        <SheetContent side="bottom" className="h-[70vh] rounded-t-xl">
          <SheetHeader className="pt-2 pb-4">
            <SheetTitle>Select a model</SheetTitle>
          </SheetHeader>
          <div className="overflow-y-auto h-[calc(100%-4rem)] -mx-6 px-6">
            <div className="space-y-1">
              {models.map((model) => {
                const isSelected = model.model_id === chat.model?.model_id
                return (
                  <button
                    key={model.model_id}
                    onClick={() => {
                      onModelSelect(model as Model)
                      setMobileModelSheetOpen(false)
                    }}
                    className={cn(
                      "w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors",
                      isSelected
                        ? "bg-accent text-accent-foreground"
                        : "hover:bg-muted"
                    )}
                  >
                    <ModelIcon
                      modelName={model.name}
                      modelId={model.model_id}
                      provider={model.provider}
                      modelIconSlug={model.model_icon_slug}
                      modelIconUrl={model.model_icon_url}
                      providerIconSlug={model.provider_icon_slug}
                      providerIconUrl={model.provider_icon_url}
                      size={24}
                      showTooltip={false}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate text-sm">{removeProviderPrefix(model.name, model.provider)}</div>
                      <div className="text-xs text-muted-foreground truncate">{model.provider}</div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <div className="text-xs text-muted-foreground">
                        {pricingUtils.formatCostWithUnit((model.cost_per_1m_prompt + model.cost_per_1m_completion) / 2)}
                      </div>
                    </div>
                    {isSelected && (
                      <div className="w-2 h-2 rounded-full bg-primary flex-shrink-0" />
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        </SheetContent>
      </Sheet>

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
