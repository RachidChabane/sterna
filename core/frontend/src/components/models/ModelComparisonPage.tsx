import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useSearch, useNavigate } from '@tanstack/react-router'
import { generateUUID } from '@/lib/utils'
import { useToast } from '@/hooks/use-toast'
import { useModelFilters } from '@/hooks/useModelFilters'
import { ImmersiveChatView } from './ImmersiveChatView'
import { ChatTabContainer } from './ChatTabContainer'
import type { ImmersiveChatViewProps } from './ChatTabContainer'
import { ChatGrid } from './ChatGrid'
import { ModelComparisonSkeleton } from './ModelComparisonSkeleton'
import { NewConversationView } from './NewConversationView'
import type { ChatGridCardProps } from './ChatGrid'
import { ChatInstructionsSheet } from './ChatInstructionsSheet'
import { ArtifactsSidePanel } from './ArtifactsSidePanel'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import { ConversationsModal } from './ConversationsModal'
import { ConfirmDeleteModal } from '@/components/shared'
import { ConsigliereModal } from '@/components/consigliere/ConsigliereModal'
import { SuggestedQuestionsCarousel } from './SuggestedQuestionsCarousel'
import { CostEstimationDisplay } from './CostEstimationDisplay'
import { llmApi, type ChatFeatureFlags } from '@/api/llm'
import { revokeImagePreview } from '@/utils/imageUtils'
import { extractTextFromContent } from '@/utils/chatUtils'
import { buildTextFromTextAttachments } from '@/utils/tokenEstimate'
import useModelStore from '@/store/modelStore'
import { useAuthStore } from '@/store/authStore'
import { useAuthModalStore } from '@/store/authModalStore'
import { useConsigliereStore } from '@/store/consigliereStore'
import { useMCPStore } from '@/store/mcpStore'
import { getAuthModalVariant } from '@/lib/sessionDetection'
import { useConversations } from '@/hooks/useConversations'
import { useGlobalFeatureToggles } from '@/hooks/useGlobalFeatureToggles'
import { useAttachmentManagement } from '@/hooks/useAttachmentManagement'
import { useComparisonInput } from '@/hooks/useComparisonInput'
import { useCostEstimation } from '@/hooks/useCostEstimation'
import { useComparisonHelpers } from '@/hooks/useComparisonHelpers'
import { useChatManagement } from '@/hooks/useChatManagement'
import { useMessageSending } from '@/hooks/useMessageSending'
import { useMultiChatTabState } from '@/hooks/useMultiChatTabState'
import { preferencesSync } from '@/lib/preferencesSync'
import { PREFERENCE_KEYS } from '@/hooks/usePreferencesLoader'
import { useActiveConversationStore } from '@/store/activeConversationStore'
import { getApiErrorMessage } from '@/utils/errorMessages'
import { sparksAPI } from '@/api/sparks'
import type { Model, Chat, Attachment, AttachmentLike, FileAttachment, ImageAttachment } from './types'
import type { ModelCatalogEntry } from '@/types/models'
import { toModelCatalogEntry } from './modelCatalog'

import { MAX_CHATS, DEFAULT_PARAMETERS } from './constants'
import { useImmersiveModePreference } from './hooks/useImmersiveModePreference'
import { useChatHandlerMaps } from './hooks/useChatHandlerMaps'
import { useConversationActions } from './hooks/useConversationActions'

const MAX_GROUPS = 50
const HIGH_TOKEN_COUNT_THRESHOLD = 200000 // Performance warning threshold for total tokens in a conversation

export default function ModelComparisonPage() {
  const { toast } = useToast()
  const navigate = useNavigate()
  const { conversation: conversationIdFromUrl, new: isNewConversation, fix_spark: fixSparkId, fix_error: fixError, ignite: igniteSparkId } = useSearch({ from: '/chats' })

  // Use Zustand selectors to prevent re-renders when unrelated store values change
  // Without selectors, the component re-renders on EVERY store update, causing lag
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const openModal = useAuthModalStore((state) => state.openModal)
  const currentModel = useModelStore((state) => state.currentModel)
  const setCurrentModel = useModelStore((state) => state.setCurrentModel)
  const recentChatModels = useModelStore((state) => state.recentChatModels)
  const openConsigliere = useConsigliereStore((state) => state.openConsigliere)
  const getActiveServers = useMCPStore((state) => state.getActiveServers)
  const fetchServers = useMCPStore((state) => state.fetchServers)
  const servers = useMCPStore((state) => state.servers)

  // Load MCP servers on mount for badge count
  useEffect(() => {
    fetchServers()
  }, [fetchServers])

  // Load conversations from database
  const { chatGroups, setChatGroups, isLoading: isLoadingConversations, createConversation, loadConversation, deleteConversation, clearConversation, renameConversation } = useConversations()

  // Track if we're currently creating a new conversation to prevent duplicate creation
  const isCreatingConversationRef = useRef(false)

  // Carry pending first-message data through SPA navigation (no page reload needed).
  // handleFirstMessage writes this; the URL effect reads it after loadConversation resolves.
  const pendingFirstMessageRef = useRef<{ content: string; attachments: AttachmentLike[]; chatId: string } | null>(null)

  const [activeGroupId, setActiveGroupId] = useState<string>('')

  // Sync activeGroupId with the global store for sidebar highlighting
  const setActiveConversationId = useActiveConversationStore((state) => state.setActiveConversationId)
  useEffect(() => {
    // Clear selection when in new conversation mode
    if (isNewConversation) {
      setActiveConversationId(null)
    } else {
      setActiveConversationId(activeGroupId || null)
    }
  }, [activeGroupId, isNewConversation, setActiveConversationId])

  // Derive active group and chats (MEMOIZED to prevent recreation on every render)
  // This is critical for performance - if chats changes on every render, ALL hooks and
  // memoized values that depend on it will recalculate, causing massive performance issues
  const activeGroup = useMemo(() => {
    return chatGroups.find(g => g.id === activeGroupId)
  }, [chatGroups, activeGroupId])

  // Extract chats from active group
  // Important: Return the actual chats array reference to ensure updates propagate
  const chats = useMemo(() => {
    return activeGroup?.chats || []
  }, [activeGroup?.chats])

  // Keep a ref to chats for callbacks that need current state without stale closures
  const chatsRef = useRef(chats)
  useEffect(() => {
    chatsRef.current = chats
  }, [chats])

  // Use helper hooks
  const helpers = useComparisonHelpers({ chats })
  const { generateFullGroupName, generateGroupName, hasMessages, hasVisionSupport, hasPDFSupport, getTotalTokens } = helpers

  // Persist immersive mode per conversation (localStorage only, no backend call)
  const { saveImmersiveMode, loadImmersiveMode } = useImmersiveModePreference()

  // Initialize default group if needed after loading
  // IMPORTANT: Skip this when in "new conversation" mode - we want to wait for the first message
  useEffect(() => {


    if (!isLoadingConversations && chatGroups.length === 0 && !isCreatingConversationRef.current && !isNewConversation) {
      // Create default group with 1 chat (starts in immersive mode)
      isCreatingConversationRef.current = true

      const initializeDefaultConversation = async () => {
        try {
          // Create conversation in database with an initial chat
          const newGroup = await createConversation([
            { id: generateUUID(), model: currentModel, messages: [], isLoading: false, parameters: { ...DEFAULT_PARAMETERS } }
          ])

          setActiveGroupId(newGroup.id)
          setIsImmersiveMode(true)
          // Persist the new active group
          preferencesSync.update(PREFERENCE_KEYS.MODELS_ACTIVE_CHAT_GROUP, newGroup.id, 'models')
        } catch (err) {
          console.error('[ModelComparisonPage] Failed to create default conversation:', err)
        } finally {
          isCreatingConversationRef.current = false
        }
      }

      initializeDefaultConversation()
    } else if (!isLoadingConversations && chatGroups.length > 0 && !activeGroupId && !isNewConversation && !conversationIdFromUrl) {
      // Load persisted active group ID from user preferences
      // Skip if: in new conversation mode, OR there's a conversation ID in the URL (URL takes priority)
      
      const loadPersistedActiveGroup = async () => {
        try {
          const persistedGroupId = await preferencesSync.get(PREFERENCE_KEYS.MODELS_ACTIVE_CHAT_GROUP)

          // Check if the persisted group still exists
          if (typeof persistedGroupId === 'string' && chatGroups.some(g => g.id === persistedGroupId)) {
            setActiveGroupId(persistedGroupId)
            // Load full conversation data (chatGroups only has summaries with empty chats)
            const fullGroup = await loadConversation(persistedGroupId)
            // Load saved immersive mode, defaulting to true for single chat
            const chatCount = fullGroup?.chats.length ?? 1
            const savedImmersiveMode = loadImmersiveMode(persistedGroupId, chatCount === 1)
            setIsImmersiveMode(savedImmersiveMode)
          } else {
            // Fall back to most recent conversation if persisted group doesn't exist
            const fallbackGroupId = chatGroups[0].id
            setActiveGroupId(fallbackGroupId)
            preferencesSync.update(PREFERENCE_KEYS.MODELS_ACTIVE_CHAT_GROUP, fallbackGroupId, 'models')
            // Load full conversation data (chatGroups only has summaries with empty chats)
            const fullGroup = await loadConversation(fallbackGroupId)
            // Load saved immersive mode, defaulting to true for single chat
            const chatCount = fullGroup?.chats.length ?? 1
            const savedImmersiveMode = loadImmersiveMode(fallbackGroupId, chatCount === 1)
            setIsImmersiveMode(savedImmersiveMode)
          }
        } catch (err) {
          console.error('[ModelComparisonPage] Failed to load persisted active group:', err)
          // Fall back to most recent on error
          const fallbackGroupId = chatGroups[0].id
          setActiveGroupId(fallbackGroupId)
          preferencesSync.update(PREFERENCE_KEYS.MODELS_ACTIVE_CHAT_GROUP, fallbackGroupId, 'models')
          // Load full conversation data (chatGroups only has summaries with empty chats)
          const fullGroup = await loadConversation(fallbackGroupId)
          // Load saved immersive mode, defaulting to true for single chat
          const chatCount = fullGroup?.chats.length ?? 1
          const savedImmersiveMode = loadImmersiveMode(fallbackGroupId, chatCount === 1)
          setIsImmersiveMode(savedImmersiveMode)
        }
      }

      loadPersistedActiveGroup()
    }
  }, [isLoadingConversations, chatGroups.length, activeGroupId, chatGroups, loadImmersiveMode, isNewConversation, createConversation, loadConversation, conversationIdFromUrl])

  const [conversationsModalOpen, setConversationsModalOpen] = useState(false)
  const [showClearDialog, setShowClearDialog] = useState(false)
  const [showCloseDialog, setShowCloseDialog] = useState(false)
  const [closingChatId, setClosingChatId] = useState<string | null>(null)
  const [isImmersiveMode, setIsImmersiveMode] = useState(true) // Fullscreen immersive chat mode (default on)
  const [gridInstructionsOpen, setGridInstructionsOpen] = useState(false)
  const [gridInstructionsEditingChatId, setGridInstructionsEditingChatId] = useState<string | null>(null)
  const [isSavingToKnowledgeBase, setIsSavingToKnowledgeBase] = useState(false)
  const [savingChatId, setSavingChatId] = useState<string | null>(null)
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches
  ) // Track mobile screen size

  // Detect mobile screen size (< 768px / md breakpoint)
  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 767px)')
    setIsMobile(mediaQuery.matches)

    const handleChange = (e: MediaQueryListEvent) => {
      setIsMobile(e.matches)
    }

    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [])

  // On mobile, always use immersive mode
  const effectiveIsImmersiveMode = isMobile || isImmersiveMode

  // Track processed URL conversation to prevent duplicate handling
  const processedUrlConversationRef = useRef<string | null>(null)

  // Redirect to new conversation mode when navigating to /chats without params
  useEffect(() => {
    // Only redirect when:
    // - No conversation ID in URL
    // - Not already in new conversation mode
    // - Not loading
    // - No active conversation selected (prevents redirect after conversation is loaded from URL)
    if (!conversationIdFromUrl && !isNewConversation && !isLoadingConversations && !activeGroupId) {
      
      navigate({ to: '/chats', search: { new: true }, replace: true })
    }
  }, [conversationIdFromUrl, isNewConversation, isLoadingConversations, activeGroupId, navigate])

  // Handle conversation selection from URL (e.g., from sidebar Recent Activity)
  useEffect(() => {
    
    if (!conversationIdFromUrl || isLoadingConversations || chatGroups.length === 0) return

    // Prevent duplicate processing of the same URL conversation
    if (processedUrlConversationRef.current === conversationIdFromUrl) {
      return
    }

    // Check if the requested conversation exists in our list
    const targetGroup = chatGroups.find(g => g.id === conversationIdFromUrl)
    if (targetGroup) {
      // Mark as being processed to prevent race conditions
      processedUrlConversationRef.current = conversationIdFromUrl

      const loadAndSetImmersiveMode = async () => {
        // Set as active group
        setActiveGroupId(conversationIdFromUrl)
        preferencesSync.update(PREFERENCE_KEYS.MODELS_ACTIVE_CHAT_GROUP, conversationIdFromUrl, 'models')

        // Load the full conversation with chats from the database
        const fullGroup = await loadConversation(conversationIdFromUrl)

        // Load saved immersive mode, defaulting to true for single chat
        const chatCount = fullGroup?.chats.length ?? targetGroup.chats.length
        const savedImmersiveMode = loadImmersiveMode(conversationIdFromUrl, chatCount === 1)
        setIsImmersiveMode(savedImmersiveMode)

        // Dispatch pending first message if handleFirstMessage left one for us
        if (pendingFirstMessageRef.current) {
          const msg = pendingFirstMessageRef.current
          pendingFirstMessageRef.current = null
          pendingMessageProcessedRef.current = true
          sessionStorage.removeItem('pending-message')
          // Small delay to let React commit the state updates above
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('send-pending-message', { detail: msg }))
          }, 50)
        }
      }
      loadAndSetImmersiveMode()
    } else {
      // Conversation not in local chatGroups - could be newly created or from pagination
      // Try to load it from the API
      const tryLoadConversation = async () => {
        try {
          const loadedGroup = await loadConversation(conversationIdFromUrl)
          if (loadedGroup) {
            // Conversation exists - set up the view
            processedUrlConversationRef.current = conversationIdFromUrl
            setActiveGroupId(conversationIdFromUrl)
            preferencesSync.update(PREFERENCE_KEYS.MODELS_ACTIVE_CHAT_GROUP, conversationIdFromUrl, 'models')

            const chatCount = loadedGroup.chats.length
            const savedImmersiveMode = loadImmersiveMode(conversationIdFromUrl, chatCount === 1)
            setIsImmersiveMode(savedImmersiveMode)

            // Dispatch pending first message if handleFirstMessage left one for us
            if (pendingFirstMessageRef.current) {
              const msg = pendingFirstMessageRef.current
              pendingFirstMessageRef.current = null
              pendingMessageProcessedRef.current = true
              sessionStorage.removeItem('pending-message')
              setTimeout(() => {
                window.dispatchEvent(new CustomEvent('send-pending-message', { detail: msg }))
              }, 50)
            }
          } else {
            // Conversation truly doesn't exist - clear the URL
            console.warn(`[ModelComparisonPage] Conversation ${conversationIdFromUrl} not found in database, clearing URL`)
            navigate({ to: '/chats', search: {}, replace: true })
          }
        } catch (error) {
          console.error(`[ModelComparisonPage] Failed to load conversation ${conversationIdFromUrl}:`, error)
          navigate({ to: '/chats', search: {}, replace: true })
        }
      }
      tryLoadConversation()
    }
  }, [conversationIdFromUrl, isLoadingConversations, chatGroups, navigate, loadImmersiveMode, loadConversation])

  // Track if we've already processed the pending message to avoid duplicate sends
  const pendingMessageProcessedRef = useRef(false)

  // Clean up any legacy pending-group from sessionStorage (no longer used with DB storage)
  useEffect(() => {
    sessionStorage.removeItem('pending-group')
  }, [])

  // Process pending message from new conversation creation
  // This runs after navigation from handleFirstMessage stores a message in sessionStorage
  useEffect(() => {
    const pendingMessageJson = sessionStorage.getItem('pending-message')

    

    // Skip if already processed, no active group, or chats not loaded
    if (pendingMessageProcessedRef.current || !activeGroupId || chats.length === 0) return

    if (!pendingMessageJson) return

    // Check authentication BEFORE processing the pending message
    // If not authenticated, keep the pending message for after login
    if (!isAuthenticated) {
      
      // Show auth modal
      const variant = getAuthModalVariant()
      openModal(variant, window.location.pathname + window.location.search)
      return
    }

    try {
      const pendingMessage = JSON.parse(pendingMessageJson)
      const { content, attachments: pendingAttachments, chatId } = pendingMessage

      // Verify the chat exists in the active group
      
      const targetChat = chats.find(c => c.id === chatId)
      if (!targetChat) {
        console.warn('[ModelComparisonPage] Pending message chat not found:', chatId, 'available:', chats.map(c => c.id))
        sessionStorage.removeItem('pending-message')
        return
      }

      // Safety check: if the chat already has messages, the pending message was likely already sent
      // This prevents duplicate sends after logout/login when sessionStorage persists unexpectedly
      if (targetChat.messages.length > 0) {
        console.warn('[ModelComparisonPage] Chat already has messages, skipping pending message to prevent duplicate')
        sessionStorage.removeItem('pending-message')
        return
      }

      // Mark as processed before sending to prevent duplicate sends in this render cycle
      pendingMessageProcessedRef.current = true

      // NOTE: We intentionally DON'T remove pending-message from sessionStorage here!
      // It will be removed by the event handler after composeAndSend starts.
      // This ensures that if auth fails (401), the message stays in sessionStorage
      // and can be sent again after re-authentication.

      // Send the pending message (composeAndSend will be available from messageSending hook)
      // We need to delay slightly to ensure all hooks are initialized
      setTimeout(() => {
        // Access composeAndSend from the messaging hook - it should compose and send the message
        const event = new CustomEvent('send-pending-message', {
          detail: { content, attachments: pendingAttachments, chatId }
        })
        window.dispatchEvent(event)
      }, 100)

    } catch (err) {
      console.error('[ModelComparisonPage] Failed to process pending message:', err)
      sessionStorage.removeItem('pending-message')
    }
  }, [activeGroupId, chats, isAuthenticated, openModal])

  // Helper function to update active group (memoized to prevent recreation on every render)
  const updateActiveGroup = useCallback((updater: (chats: Chat[]) => Chat[]) => {
    setChatGroups(prevGroups =>
      prevGroups.map(group => {
        if (group.id !== activeGroupId) return group

        const updatedChats = updater(group.chats)

        return {
          ...group,
          chats: updatedChats,
          updatedAt: new Date(),
          // Don't override name - it's set by LLM after first message or by user rename
        }
      })
    )
  }, [activeGroupId, setChatGroups])

  // Use custom hooks for cleaner code
  const attachmentManager = useAttachmentManagement()
  const { attachments, setAttachments, addAttachments } = attachmentManager

  // Clear attachments when switching conversations
  const prevActiveGroupIdRef = useRef<string>('')
  useEffect(() => {
    if (prevActiveGroupIdRef.current && prevActiveGroupIdRef.current !== activeGroupId) {
      // Conversation changed - clear pending attachments
      setAttachments([])
    }
    prevActiveGroupIdRef.current = activeGroupId
  }, [activeGroupId, setAttachments])

  // Extract user message history from all chats (memoized to avoid recalculation on every render)
  // Deduplicate by timestamp to avoid showing same message multiple times in sync mode
  const userMessageHistory = useMemo(() => {
    return Array.from(
      chats
        .flatMap(chat => chat.messages)
        .filter(m => m.role === 'user')
        .reduce((map, msg) => {
          const timestampKey = msg.timestamp.getTime()
          if (!map.has(timestampKey)) {
            map.set(timestampKey, extractTextFromContent(msg.content))
          }
          return map
        }, new Map<number, string>())
        .entries()
    )
      .sort((a, b) => b[0] - a[0]) // Sort by timestamp desc (most recent first)
      .map(([_, content]) => content)
  }, [chats])

  // Input management hook
  // Only check active chats (non-disabled and with a model) for capabilities (memoized)
  const activeChats = useMemo(() => {
    return chats.filter(c => c.model !== null && !c.disabled)
  }, [chats])

  // Find first model with each capability (even if disabled) (memoized)
  const firstVisionChat = useMemo(() => {
    return chats.find(c => c.model?.input_modalities?.includes('image'))
  }, [chats])

  const firstPDFChat = useMemo(() => {
    return chats.find(c => c.model?.input_modalities?.includes('file'))
  }, [chats])

  // Memoize vision/PDF support checks to avoid recalculation on every render
  const hasActiveVisionSupport = useMemo(() => hasVisionSupport(activeChats), [hasVisionSupport, activeChats])
  const hasActivePDFSupport = useMemo(() => hasPDFSupport(activeChats), [hasPDFSupport, activeChats])
  const firstVisionModelName = useMemo(() => firstVisionChat?.model?.name, [firstVisionChat])
  const firstPDFModelName = useMemo(() => firstPDFChat?.model?.name, [firstPDFChat])
  const isFirstVisionModelDisabled = useMemo(() => firstVisionChat ? !!firstVisionChat.disabled : false, [firstVisionChat])
  const isFirstPDFModelDisabled = useMemo(() => firstPDFChat ? !!firstPDFChat.disabled : false, [firstPDFChat])

  const comparisonInput = useComparisonInput({
    userMessageHistory,
    onAddAttachments: addAttachments,
    currentAttachmentsCount: attachments.length,
    hasVisionSupport: hasActiveVisionSupport,
    hasPDFSupport: hasActivePDFSupport,
    firstVisionModelName,
    firstPDFModelName,
    isFirstVisionModelDisabled,
    isFirstPDFModelDisabled,
  })
  const {
    sharedInput,
    setSharedInput,
    sharedInputRef,
    isDropOverInput,
    handleSharedDragOver,
    handleSharedDragLeave,
    handleSharedDrop,
    handleSharedPaste,
    handleKeyDown: handleInputKeyDown,
    clearInput
  } = comparisonInput

  // Cost estimation hook
  const costEstimation = useCostEstimation()
  const { estimatedCosts, loadingEstimate, setEstimatedCosts } = costEstimation

  // Message sending hook
  // Adapter: the hook types openModal's variant as plain string, while the auth
  // modal store only accepts AuthModalVariant. The hook only ever passes values
  // produced by getAuthModalVariant, so narrow the variant here.
  const openModalAdapter = useCallback((variant: string, returnPath: string) => {
    openModal(variant === 'session-expired' ? 'session-expired' : 'sign-up-prompt', returnPath)
  }, [openModal])
  const messageSending = useMessageSending({
    chats,
    activeGroupId,
    chatGroups,
    setChatGroups,
    attachments,
    setAttachments,
    toast,
    isAuthenticated,
    openModal: openModalAdapter,
    getAuthModalVariant
  })
  const {
    sendToModel,
    composeAndSend,
    sendSparkFixMessage,
    sendIgniteMessage,
    abortControllersRef
  } = messageSending

  // Listen for pending message event from new conversation creation
  useEffect(() => {
    const handlePendingMessage = (event: CustomEvent<{ content: string; attachments: AttachmentLike[]; chatId: string }>) => {
      const { content, attachments: pendingAttachments, chatId } = event.detail

      // Reconstruct file-like objects from serialized attachments
      // The UI expects file.name, file.type, file.size but serialized attachments have fileName, fileType, fileSize
      const reconstructedAttachments = pendingAttachments.map((att) => ({
        ...att,
        // Reconstruct file object for UI display (not a real File, but has the properties UI needs)
        file: att.file || {
          name: att.fileName || 'file',
          type: att.fileType || 'application/octet-stream',
          size: att.fileSize || 0,
        },
        // Preserve preview URL for images
        preview: att.preview || att.assetUrl,
      }))

      // Send to the specific chat
      // composeAndSend adds the user message synchronously before the API call
      composeAndSend([chatId], content, reconstructedAttachments)

      // Remove pending message AFTER composeAndSend starts
      // At this point, the user message has been added to state (scheduled)
      // If auth fails (401), the error handler will show the auth modal
      // The user message will be visible in the chat, and they can retry after re-auth
      sessionStorage.removeItem('pending-message')
    }

    window.addEventListener('send-pending-message', handlePendingMessage as EventListener)
    return () => {
      window.removeEventListener('send-pending-message', handlePendingMessage as EventListener)
    }
  }, [composeAndSend])

  // Handle spark fix request from URL params (from /sparks page)
  const sparkFixHandledRef = useRef<string | null>(null)
  useEffect(() => {
    // Skip if no fix params
    if (!fixSparkId || !fixError) return
    // Skip if already handled this specific spark
    if (sparkFixHandledRef.current === fixSparkId) return
    // Wait for conversation to be loaded
    if (!activeGroupId || chats.length === 0 || isLoadingConversations) return

    const handleSparkFix = async () => {
      // Mark as handled before async operation to prevent duplicate calls
      sparkFixHandledRef.current = fixSparkId

      try {
        // Fetch spark details to get the title and chat_id
        const spark = await sparksAPI.get(fixSparkId)
        if (!spark) {
          toast({
            title: 'Spark not found',
            description: 'Could not find the spark to fix.',
            variant: 'destructive',
          })
          // Clear the fix params from URL even on error
          navigate({
            to: '/chats',
            search: { conversation: activeGroupId },
            replace: true,
          })
          return
        }

        // Find the chat that matches the spark's chat_id, or use the first chat
        const targetChat = chats.find(c => c.id === spark.chat_id) || chats[0]
        if (!targetChat) {
          toast({
            title: 'No chat available',
            description: 'Could not find a chat to send the fix request.',
            variant: 'destructive',
          })
          navigate({
            to: '/chats',
            search: { conversation: activeGroupId },
            replace: true,
          })
          return
        }

        // Enable sparks on the target chat if not already enabled
        if (!targetChat.parameters?.enable_sparks) {
          updateActiveGroup(prevChats =>
            prevChats.map(chat =>
              chat.id === targetChat.id
                ? { ...chat, parameters: { ...chat.parameters, enable_sparks: true } }
                : chat
            )
          )
        }

        // Send the fix message
        await sendSparkFixMessage(targetChat.id, `Please fix the "${spark.title}" spark component.`, {
          spark_id: spark.id,
          spark_title: spark.title,
          error: fixError,
        })

        // Clear the fix params from URL
        navigate({
          to: '/chats',
          search: { conversation: activeGroupId },
          replace: true,
        })

        toast({
          title: 'Fix requested',
          description: `Asking AI to fix "${spark.title}"...`,
        })
      } catch (error) {
        console.error('Failed to handle spark fix:', error)
        toast({
          title: 'Failed to request fix',
          description: 'Could not send the fix request. Please try again.',
          variant: 'destructive',
        })
        // Clear the fix params from URL even on error
        navigate({
          to: '/chats',
          search: { conversation: activeGroupId },
          replace: true,
        })
      }
    }

    handleSparkFix()
  }, [fixSparkId, fixError, activeGroupId, chats, isLoadingConversations, sendSparkFixMessage, navigate, toast, updateActiveGroup])

  // Handle spark ignite request from URL params (from /sparks gallery)
  const sparkIgniteHandledRef = useRef<string | null>(null)
  useEffect(() => {
    if (!igniteSparkId) return
    if (sparkIgniteHandledRef.current === igniteSparkId) return
    if (!activeGroupId || chats.length === 0 || isLoadingConversations) return

    const handleSparkIgnite = async () => {
      sparkIgniteHandledRef.current = igniteSparkId

      try {
        const spark = await sparksAPI.get(igniteSparkId)
        if (!spark) {
          toast({
            title: 'Spark not found',
            description: 'Could not find the spark to ignite.',
            variant: 'destructive',
          })
          navigate({
            to: '/chats',
            search: { conversation: activeGroupId },
            replace: true,
          })
          return
        }

        const targetChat = chats.find(c => c.id === spark.chat_id) || chats[0]
        if (!targetChat) {
          toast({
            title: 'No chat available',
            description: 'Could not find a chat to send the ignite request.',
            variant: 'destructive',
          })
          navigate({
            to: '/chats',
            search: { conversation: activeGroupId },
            replace: true,
          })
          return
        }

        // Enable sparks + file tools on the target chat
        if (!targetChat.parameters?.enable_sparks || !targetChat.parameters?.enable_file_tools) {
          updateActiveGroup(prevChats =>
            prevChats.map(chat =>
              chat.id === targetChat.id
                ? { ...chat, parameters: { ...chat.parameters, enable_sparks: true, enable_file_tools: true } }
                : chat
            )
          )
        }

        await sendIgniteMessage(targetChat.id, {
          spark_id: spark.id,
          spark_title: spark.title,
        })

        navigate({
          to: '/chats',
          search: { conversation: activeGroupId },
          replace: true,
        })

        toast({
          title: 'Igniting spark...',
          description: `Creating Next.js project from "${spark.title}"`,
        })
      } catch (error) {
        console.error('Failed to handle spark ignite:', error)
        toast({
          title: 'Failed to ignite',
          description: 'Could not send the ignite request. Please try again.',
          variant: 'destructive',
        })
        navigate({
          to: '/chats',
          search: { conversation: activeGroupId },
          replace: true,
        })
      }
    }

    handleSparkIgnite()
  }, [igniteSparkId, activeGroupId, chats, isLoadingConversations, sendIgniteMessage, navigate, toast, updateActiveGroup])

  // Listen for setInputMessage events from the Project panel (e.g., "Implement" button)
  useEffect(() => {
    const handleSetInputMessage = (event: CustomEvent<{ message: string }>) => {
      setSharedInput(event.detail.message)
    }
    window.addEventListener('setInputMessage', handleSetInputMessage as EventListener)
    return () => {
      window.removeEventListener('setInputMessage', handleSetInputMessage as EventListener)
    }
  }, [setSharedInput])

  // Chat management hook
  const chatManagement = useChatManagement({
    chats,
    currentModel,
    updateActiveGroup,
    cancelChat: (chatId: string) => {
      const controller = abortControllersRef.current.get(chatId)
      if (controller) {
        controller.abort()
        abortControllersRef.current.delete(chatId)
      }
    },
    conversationId: activeGroupId
  })
  const {
    addChat,
    removeChat,
    clearChat,
    updateChat,
    updateChatModel,
    updateChatMessages,
    updateChatParameters,
    updateChatDisabled,
    updateChatHidden,
    applyParametersToAllChats,
    moveLeft,
    moveRight
  } = chatManagement

  // Feature toggles (moved after chatManagement so we can use updateChatParameters)
  const featureToggles = useGlobalFeatureToggles({
    chats,
    updateActiveGroup,
    persistChatParameters: (chatId, parameters) => {
      updateChatParameters(chatId, parameters)
    }
  })

  // Available models (normalized to the catalog shape used by the model store)
  const [models, setModels] = useState<ModelCatalogEntry[]>([])

  // Model filtering
  const {
    showFilters,
    setShowFilters,
    filters,
    setFilters,
    providers,
    filteredModels,
    hasActiveFilters
  } = useModelFilters(models)

  // Memoize filter toggle to prevent breaking ChatHeader memo
  const handleToggleFilters = useCallback(() => {
    setShowFilters(!showFilters)
  }, [showFilters, setShowFilters])

  // Memoize models per chat to prevent ChatPanel re-render on every keystroke
  const modelsPerChat = useMemo(() => {
    const map = new Map<string, ModelCatalogEntry[]>()

    chats.forEach(chat => {
      if (!chat.model) {
        map.set(chat.id, filteredModels)
        return
      }

      // Check if the selected model is in the filtered list
      const isSelectedModelInList = filteredModels.some(m => m.model_id === chat.model?.model_id)

      // If the selected model is not in list, add it (try full models list, fall back to model itself)
      if (!isSelectedModelInList) {
        const selectedModelEntry = models.find(m => m.model_id === chat.model?.model_id)
        map.set(chat.id, [selectedModelEntry ?? toModelCatalogEntry(chat.model), ...filteredModels])
      } else {
        map.set(chat.id, filteredModels)
      }
    })

    return map
  }, [chats, filteredModels, models])

  // Memoize availableChats per chat to prevent re-render on every keystroke
  const availableChatsPerChat = useMemo(() => {
    const map = new Map<string, Chat[]>()

    chats.forEach(chat => {
      map.set(chat.id, chats.filter(c => c.id !== chat.id))
    })

    return map
  }, [chats])

  // Get models for a specific chat (now using memoized map)
  const getModelsForChat = useCallback((chatId: string) => {
    return modelsPerChat.get(chatId) || filteredModels
  }, [modelsPerChat, filteredModels])

  // Get recent chat model IDs from user preferences (models used in /chats that have received messages)
  const recentModelIds = useMemo(() => {
    return recentChatModels.map(rm => rm.model_id)
  }, [recentChatModels])

  useEffect(() => {
    fetchModels()
  }, [])

  // Note: Auto-resize is now handled internally by MarkdownTextarea component

  // Chat group management functions (memoized to prevent recreation on every render)
  const createNewGroup = useCallback(async () => {
    if (chatGroups.length >= MAX_GROUPS) {
      // Remove oldest group if at limit
      setChatGroups(prev => {
        const sorted = [...prev].sort((a, b) => {
          const aTime = a.updatedAt instanceof Date ? a.updatedAt.getTime() : 0
          const bTime = b.updatedAt instanceof Date ? b.updatedAt.getTime() : 0
          return bTime - aTime
        })
        return sorted.slice(0, MAX_GROUPS - 1)
      })
    }

    try {
      // Create conversation in database with an initial chat
      const newGroup = await createConversation([
        { id: generateUUID(), model: currentModel, messages: [], isLoading: false, parameters: { ...DEFAULT_PARAMETERS } }
      ])

      setActiveGroupId(newGroup.id)
      setConversationsModalOpen(false) // Close modal after creation
      setIsImmersiveMode(true) // Enter immersive mode for new single-chat conversation

      // Persist the new active group
      preferencesSync.update(PREFERENCE_KEYS.MODELS_ACTIVE_CHAT_GROUP, newGroup.id, 'models')

      toast({
        title: 'New conversation created',
        description: 'Start chatting'
      })
    } catch (err) {
      console.error('[ModelComparisonPage] Failed to create conversation:', err)
      toast({
        title: 'Failed to create conversation',
        description: 'Please try again',
        variant: 'destructive'
      })
    }
  }, [chatGroups.length, currentModel, setChatGroups, createConversation, toast])

  const switchGroup = useCallback(async (groupId: string) => {
    setActiveGroupId(groupId)
    setConversationsModalOpen(false) // Close modal after selection

    // Load saved immersive mode, defaulting to true for single chat
    const targetGroup = chatGroups.find(g => g.id === groupId)
    const defaultImmersive = targetGroup ? targetGroup.chats.length === 1 : true
    const savedImmersiveMode = loadImmersiveMode(groupId, defaultImmersive)
    setIsImmersiveMode(savedImmersiveMode)

    // Persist the active group ID to user preferences
    preferencesSync.update(PREFERENCE_KEYS.MODELS_ACTIVE_CHAT_GROUP, groupId, 'models')
  }, [chatGroups, loadImmersiveMode])

  const deleteGroup = useCallback((groupId: string, deleteWorkspace?: boolean) => {
    if (chatGroups.length <= 1) {
      toast({
        title: 'Cannot delete',
        description: 'You must have at least one conversation',
        variant: 'destructive'
      })
      return
    }

    // Delete conversation via backend-persisted store
    deleteConversation(groupId, deleteWorkspace)
  }, [chatGroups.length, deleteConversation, toast])

  const renameGroup = useCallback((groupId: string, newName: string) => {
    setChatGroups(prev =>
      prev.map(group =>
        group.id === groupId
          ? { ...group, name: newName, updatedAt: new Date(), isCustomName: true }
          : group
      )
    )

    toast({
      title: 'Conversation renamed',
      description: 'The conversation name has been updated'
    })
  }, [setChatGroups, toast])

  // Feature toggle helpers (now using useGlobalFeatureToggles hook)
  const getGlobalWebSearchState = featureToggles.getWebSearchState
  const toggleWebSearchForAll = featureToggles.toggleWebSearch
  const hasWebSearchSupport = () => featureToggles.hasWebSearchSupport()
  const hasReasoningSupport = () => featureToggles.hasReasoningSupport()
  const getGlobalReasoningState = featureToggles.getReasoningState
  const toggleReasoningForAll = featureToggles.toggleReasoning
  const getGlobalMCPToolsState = featureToggles.getMCPToolsState
  const toggleMCPToolsForAll = featureToggles.toggleMCPTools
  const hasFunctionSupport = () => featureToggles.hasFunctionSupport()
  const getGlobalFileToolsState = featureToggles.getFileToolsState
  const toggleFileToolsForAll = featureToggles.toggleFileTools
  const getGlobalImageGenerationState = featureToggles.getImageGenerationState
  const toggleImageGenerationForAll = featureToggles.toggleImageGeneration
  const getGlobalVideoGenerationState = featureToggles.getVideoGenerationState
  const toggleVideoGenerationForAll = featureToggles.toggleVideoGeneration
  const getGlobalSparksState = featureToggles.getSparksState
  const toggleSparksForAll = featureToggles.toggleSparks
  const getGlobalKnowledgeBaseState = featureToggles.getKnowledgeBaseState
  const toggleKnowledgeBaseForAll = featureToggles.toggleKnowledgeBase
  const hasKnowledgeBaseSupport = featureToggles.hasKnowledgeBaseSupport

  const fetchModels = async () => {
    try {
      // Fetch first page to get total count
      const firstPage = await llmApi.models({
        available_only: true,
        page: 1
      })

      const totalCount = firstPage.data.count
      const pageSize = firstPage.data.results.length
      const totalPages = Math.ceil(totalCount / pageSize)

      let allModels: Model[] = []

      if (totalPages === 1) {
        allModels = firstPage.data.results || []
      } else {
        // Fetch all pages in parallel
        const pagePromises = []
        for (let page = 1; page <= totalPages; page++) {
          pagePromises.push(llmApi.models({
            available_only: true,
            page
          }))
        }

        const allResponses = await Promise.all(pagePromises)
        allModels = allResponses.flatMap(res => res.data.results || [])
      }

      // Normalize to the catalog shape (also converts cost strings to numbers —
      // Django DecimalField serializes as string)
      setModels(allModels.map(toModelCatalogEntry))

      // Set default models for chats without models (only on first load)
      if (allModels.length > 0 && chats.every(c => c.model === null)) {
        updateActiveGroup(prevChats =>
          prevChats.map((chat, index) => {
            // Use currentModel for first chat if available, otherwise use models from list
            if (index === 0 && currentModel) {
              return { ...chat, model: currentModel }
            }
            return {
              ...chat,
              model: index < allModels.length ? allModels[index] : null
            }
          })
        )
      }
    } catch (error) {
      toast({
        title: 'Error loading models',
        description: 'Failed to fetch available models',
        variant: 'destructive'
      })
    }
  }

  // Shared input entry point (synced): just call composeAndSend for all enabled chats (memoized)
  const sendMessage = useCallback((content: string) => {
    const enabledIds = chats.filter(c => c.model !== null && !c.disabled).map(c => c.id)
    if (enabledIds.length === 0) {
      const hasModelsSelected = chats.some(c => c.model !== null)
      const allDisabled = hasModelsSelected && enabledIds.length === 0

      toast({
        title: allDisabled ? 'All chats disabled' : 'No model selected',
        description: allDisabled
          ? 'All chats are currently disabled. Please enable at least one chat to send a message.'
          : 'Please select at least one model to send a message.',
        variant: 'destructive'
      })
      return
    }

    // Take a snapshot of current attachments with enriched metadata for serialization survival
    const currentAttachments = attachments.map(att => ({
      ...att,
      // Extract File metadata at root level so they survive JSON serialization
      fileName: att.file.name,
      fileType: att.file.type,
      fileSize: att.file.size,
    }))

    // Fire-and-forget the compose/send so UI clears immediately
    void composeAndSend(enabledIds, content, currentAttachments)

    // Clear shared composer UI state immediately (do not wait for models)
    clearInput()
    setEstimatedCosts(null)
    currentAttachments.forEach(att => { if (att.type === 'image') revokeImagePreview(att.preview) })
    setAttachments([])
  }, [chats, attachments, toast, composeAndSend, clearInput, setEstimatedCosts, setAttachments, revokeImagePreview])

  // Cancellation helpers (memoized to prevent recreation on every render)
  const cancelChat = useCallback((chatId: string) => {
    const controller = abortControllersRef.current.get(chatId)
    if (controller) {
      controller.abort()
      abortControllersRef.current.delete(chatId)
      // Stop loading and mark any streaming assistant message as finalized
      setChatGroups(prev => prev.map(g => g.id === activeGroupId ? {
        ...g,
        chats: g.chats.map(c => {
          if (c.id !== chatId) return c
          // If last assistant message is streaming (no tokens/cost), mark as finished to re-enable UI
          const newMessages = [...c.messages]
          const last = newMessages[newMessages.length - 1]
          if (last && last.role === 'assistant' && !last.isError && !last.isUnsupported && !last.tokens && !last.cost) {
            // Mark any executing file tools as cancelled
            let updatedExecutions = last.file_tool_executions
            if (updatedExecutions && updatedExecutions.some(e => e.isExecuting)) {
              updatedExecutions = updatedExecutions.map(e =>
                e.isExecuting
                  ? { ...e, isExecuting: false, success: false, result: { success: false, error: 'Cancelled by user' } }
                  : e
              )
            }

            // Update the last message steps to reflect cancelled tools
            let updatedSteps = last.steps
            if (updatedSteps) {
              updatedSteps = updatedSteps.map(step => {
                if (step.type === 'tool_executions' && step.executions) {
                  return {
                    ...step,
                    executions: step.executions.map((e) =>
                      e.isExecuting
                        ? { ...e, isExecuting: false, success: false, result: { success: false, error: 'Cancelled by user' } }
                        : e
                    ),
                    isExecuting: false
                  }
                }
                return step
              })
            }

            newMessages[newMessages.length - 1] = {
              ...last,
              finish_reason: 'cancelled',
              isInterrupted: true,
              is_stopped: true,
              // If interrupted during reasoning, preserve reasoning content
              reasoning_content: last.is_reasoning ? extractTextFromContent(last.content) : last.reasoning_content,
              content: last.is_reasoning ? '' : last.content,
              is_reasoning: false,
              file_tool_executions: updatedExecutions,
              steps: updatedSteps,
            }
          }
          return { ...c, isLoading: false, messages: newMessages }
        }),
        updatedAt: new Date(),
      } : g))
    }
  }, [activeGroupId, setChatGroups])

  // Per-chat handler-map factories (stable function identity per chatId, so
  // typing in one chat's input doesn't re-render every other chat)
  const requestRemoveChat = useCallback((chatId: string) => {
    setClosingChatId(chatId)
    setShowCloseDialog(true)
  }, [])

  const {
    getSendMessageHandler,
    sendToAllChatsHandler,
    getModelSelectHandler,
    getUpdateMessagesHandler,
    getEstimateCostHandler,
    getMoveLeftHandler,
    getMoveRightHandler,
    getParametersChangeHandler,
    getToggleDisabledHandler,
    getToggleHiddenHandler,
    getClearChatHandler,
    getCancelChatHandler,
    getToolExecutedHandler,
  } = useChatHandlerMaps({
    chats,
    chatsRef,
    composeAndSend,
    sendToModel,
    updateChatModel,
    updateChatMessages,
    updateChatParameters,
    updateChatDisabled,
    updateChatHidden,
    moveLeft,
    moveRight,
    clearChat,
    cancelChat,
    toast,
    onRequestRemoveChat: requestRemoveChat,
  })

  const cancelAll = useCallback(() => {
    abortControllersRef.current.forEach(ctrl => ctrl.abort())
    abortControllersRef.current.clear()
    setChatGroups(prev => prev.map(g => g.id === activeGroupId ? {
      ...g,
      chats: g.chats.map(c => {
        const newMessages = [...c.messages]
        const last = newMessages[newMessages.length - 1]
        if (last && last.role === 'assistant' && !last.isError && !last.isUnsupported && !last.tokens && !last.cost) {
          // Mark any executing file tools as cancelled
          let updatedExecutions = last.file_tool_executions
          if (updatedExecutions && updatedExecutions.some(e => e.isExecuting)) {
            updatedExecutions = updatedExecutions.map(e =>
              e.isExecuting
                ? { ...e, isExecuting: false, success: false, result: { success: false, error: 'Cancelled by user' } }
                : e
            )
          }

          // Update the last message steps to reflect cancelled tools
          let updatedSteps = last.steps
          if (updatedSteps) {
            updatedSteps = updatedSteps.map(step => {
              if (step.type === 'tool_executions' && step.executions) {
                return {
                  ...step,
                  executions: step.executions.map((e) =>
                    e.isExecuting
                      ? { ...e, isExecuting: false, success: false, result: { success: false, error: 'Cancelled by user' } }
                      : e
                  ),
                  isExecuting: false
                }
              }
              return step
            })
          }

          newMessages[newMessages.length - 1] = {
            ...last,
            finish_reason: 'cancelled',
            tokens: { prompt: 0, completion: 0 },
            cost: 0,
            isInterrupted: true,
            is_stopped: true,
            // If interrupted during reasoning, preserve reasoning content
            reasoning_content: last.is_reasoning ? extractTextFromContent(last.content) : last.reasoning_content,
            content: last.is_reasoning ? '' : last.content,
            is_reasoning: false,
            file_tool_executions: updatedExecutions,
            steps: updatedSteps,
          }
        }
        return { ...c, isLoading: false, messages: newMessages }
      }),
      updatedAt: new Date(),
    } : g))
  }, [activeGroupId, setChatGroups])

  const {
    copyConversationResponses,
    copyConversationMetadata,
    exportConversationResponses,
    exportConversationMetadata,
    handleSaveChatToKnowledgeBase,
    copyChatResponses,
    copyChatMetadata,
    exportChatResponses,
    exportChatMetadata,
  } = useConversationActions({
    chats,
    activeGroup,
    activeGroupId,
    currentModel,
    openConsigliere,
    setChatGroups,
    toast,
    setSharedInput,
    setEstimatedCosts,
    isSavingToKnowledgeBase,
    setIsSavingToKnowledgeBase,
    savingChatId,
    setSavingChatId,
  })

  // Ask backend to estimate costs (uses hook state management)
  const estimateCostsLocal = async (modelIds: string[], typedText: string, atts: Attachment[]) => {
    const filesText = buildTextFromTextAttachments(atts)
    const filesMeta = atts
      .filter((a): a is FileAttachment => a.type === 'file')
      .map((f) => ({ filename: f.file?.name || 'file', mime: f.file?.type || undefined, size: f.file?.size || undefined }))
    const imagesMeta = atts
      .filter((a): a is ImageAttachment => a.type === 'image')
      .map((img) => ({ mime: img.file?.type || undefined, size: img.file?.size || undefined }))
    // Per-model max_new_tokens and features from chats' parameters
    const maxNewByModel: Record<string, number> = {}
    const featuresByModel: Record<string, ChatFeatureFlags> = {}

    chats.forEach(c => {
      if (!c.model) return
      if (!modelIds.includes(c.model.model_id)) return

      const modelId = c.model.model_id

      // Track max_tokens (use min if duplicates)
      const m = c.parameters?.max_tokens
      if (typeof m === 'number' && m > 0) {
        if (maxNewByModel[modelId] === undefined) {
          maxNewByModel[modelId] = m
        } else {
          maxNewByModel[modelId] = Math.min(maxNewByModel[modelId], m)
        }
      }

      // Track features per model (if multiple chats use same model, OR the features)
      if (!featuresByModel[modelId]) {
        featuresByModel[modelId] = {
          system_prompt: c.parameters?.system_prompt || '',
          enable_mcp_tools: c.parameters?.enable_mcp_tools || false,
          enable_reasoning: c.parameters?.enable_reasoning || false,
          enable_file_tools: c.parameters?.enable_file_tools || false,
        }
      } else {
        // OR logic for features if same model is used in multiple chats
        if (c.parameters?.enable_mcp_tools) featuresByModel[modelId].enable_mcp_tools = true
        if (c.parameters?.enable_reasoning) featuresByModel[modelId].enable_reasoning = true
        if (c.parameters?.enable_file_tools) featuresByModel[modelId].enable_file_tools = true
        // Use longest system prompt for this model
        const sp = c.parameters?.system_prompt || ''
        if (sp.length > (featuresByModel[modelId].system_prompt?.length ?? 0)) {
          featuresByModel[modelId].system_prompt = sp
        }
      }
    })

    try {
      const response = await llmApi.estimateBatchCost({
        model_ids: modelIds,
        prompt_text: typedText + filesText,
        typed_text: typedText,
        files_text: filesText,
        features_by_model: featuresByModel,
        files: filesMeta,
        images: imagesMeta,
        max_new_tokens_by_model: maxNewByModel,
      })
      const data = {
        ...response.data,
        total_cost: typeof response.data.total_cost === 'string' ? parseFloat(response.data.total_cost) : response.data.total_cost,
        costs: response.data.costs.map((c) => ({ ...c, cost: typeof c.cost === 'string' ? parseFloat(c.cost) : c.cost })),
      }
      setEstimatedCosts(data)
      if (data.costs.length === 0) {
        toast({
          title: 'No costs calculated',
          description: 'Selected models may not have pricing information',
          variant: 'destructive'
        })
      }
    } catch (error) {
      const errorMessage = getApiErrorMessage(error, 'Failed to estimate costs. Please try again.')
      toast({
        title: 'Estimation failed',
        description: errorMessage,
        variant: 'destructive'
      })
    }
  }

  const handleEstimateCost = useCallback(async (text: string) => {
    if (!text.trim() && attachments.length === 0) {
      toast({
        title: 'No text to estimate',
        description: 'Please enter some text in the input field',
        variant: 'destructive'
      })
      return
    }

    const modelIds = [
      ...new Set(
        chats
          .filter(chat => chat.model !== null)
          .map(chat => chat.model!.model_id)
      )
    ]

    if (modelIds.length === 0) {
      toast({
        title: 'No models selected',
        description: 'Please select at least one model',
        variant: 'destructive'
      })
      return
    }

    // Call the local batch estimator
    await estimateCostsLocal(modelIds, text, attachments)
  }, [attachments, chats, estimateCostsLocal, toast])

  // Handler for suggested question clicks (memoized)
  const handleSuggestionClick = useCallback((suggestion: string) => {
    // Fill the shared input without sending
    // User can review/modify the suggestion before manually sending
    setSharedInput(suggestion)
  }, [setSharedInput])

  // Handler for filtering models by capability (toggle) (memoized)
  const handleFilterByCapability = useCallback((modality: string) => {
    const currentModalities = filters.input_modalities || []

    // Check if modality is already in the filter
    if (currentModalities.includes(modality)) {
      // Remove the modality (toggle off)
      setFilters({
        ...filters,
        input_modalities: currentModalities.filter(m => m !== modality)
      })

      // Show toast for filter removal
      const modalityLabel = modality === 'image' ? 'Vision' : 'PDF'
      toast({
        title: `${modalityLabel} filter cleared`,
        description: 'Showing all models'
      })
    } else {
      // Add the new modality (AND logic - intersection)
      setFilters({
        ...filters,
        input_modalities: [...currentModalities, modality]
      })

      // Show toast for filter activation
      const modalityLabel = modality === 'image' ? 'Vision' : 'PDF'
      toast({
        title: `Filter applied: ${modalityLabel}`,
        description: `Showing only ${modalityLabel.toLowerCase()}-capable models`
      })
    }
  }, [filters, toast])

  // Memoize frequently recalculated values to prevent MessageInput from re-rendering on every keystroke
  const isAnyLoading = useMemo(() => chats.some(c => c.isLoading), [chats])
  const hasChatsVisionSupport = useMemo(() => hasVisionSupport(chats), [hasVisionSupport, chats])
  const hasChatsPDFSupport = useMemo(() => hasPDFSupport(chats), [hasPDFSupport, chats])
  const chatsWithModelsCount = useMemo(() => chats.filter(c => c.model !== null).length, [chats])
  const canCancelAll = useMemo(() => abortControllersRef.current.size > 0, [chats]) // chats as proxy for re-check

  // Memoize callback for removing attachments
  const handleRemoveAttachment = useCallback((attachmentId: string) => {
    const attachment = attachments.find(att => att.id === attachmentId)
    if (attachment && attachment.type === 'image') {
      revokeImagePreview(attachment.preview)
    }
    setAttachments(prev => prev.filter(att => att.id !== attachmentId))
  }, [attachments, setAttachments, revokeImagePreview])

  // Memoize callback for adding attachments
  const handleAddAttachment = useCallback((attachment: Attachment) => {
    setAttachments(prev => [...prev, attachment])
  }, [setAttachments])

  // Memoize callback for sending message (receives text from MessageInput)
  const handleSendSharedMessage = useCallback((text: string) => {
    sendMessage(text)
    setSharedInput('') // Clear external value after sending
  }, [sendMessage, setSharedInput])

  // Memoize callback for handling keydown in shared input
  const handleSharedInputKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    handleInputKeyDown(e, () => sendMessage(sharedInput))
  }, [handleInputKeyDown, sendMessage, sharedInput])

  // Memoize feature toggle states to prevent recalculation on every render
  // NOTE: Do NOT include the getter functions in dependencies - they use chats from their closure
  // Only depend on chats itself to ensure re-calculation when chats change
  const webSearchState = useMemo(() => getGlobalWebSearchState(), [chats])
  const reasoningState = useMemo(() => getGlobalReasoningState(), [chats])
  const mcpToolsState = useMemo(() => getGlobalMCPToolsState(), [chats])
  const fileToolsState = useMemo(() => getGlobalFileToolsState(), [chats])
  const imageGenerationState = useMemo(() => getGlobalImageGenerationState(), [chats])
  const videoGenerationState = useMemo(() => getGlobalVideoGenerationState(), [chats])
  const sparksState = useMemo(() => getGlobalSparksState(), [chats])
  const knowledgeBaseState = useMemo(() => getGlobalKnowledgeBaseState(), [chats])
  const hasReasoningSupportValue = useMemo(() => hasReasoningSupport(), [chats])
  const hasFunctionSupportValue = useMemo(() => hasFunctionSupport(), [chats])
  const hasKnowledgeBaseSupportValue = useMemo(() => hasKnowledgeBaseSupport(), [chats])
  const activeServersValue = useMemo(() => getActiveServers(), [servers])

  // Aggregate sparks from all chats for grid view artifacts panel
  const gridSparks = useMemo(() => {
    const allSparks = chats.flatMap(chat => {
      const messageSparks = (chat.messages || [])
        .filter((m) => m.sparks && m.sparks.length > 0)
        .flatMap((m) => m.sparks || [])
      const chatSparks = chat.sparks || []
      return [...messageSparks, ...chatSparks]
    })
    // Deduplicate by ID
    const uniqueSparks = allSparks.filter((spark, index, self) =>
      index === self.findIndex((s) => s.id === spark.id)
    )
    // Filter out older versions - only show sparks that don't have a newer version
    const parentIds = new Set(uniqueSparks.map((s) => s.parent_id).filter(Boolean))
    return uniqueSparks.filter((spark) => !parentIds.has(spark.id))
  }, [chats])

  // Prepare chats with their sparks for the ArtifactsSidePanel
  const chatsWithSparks = useMemo(() => {
    return chats.map(chat => {
      const messageSparks = (chat.messages || [])
        .filter((m) => m.sparks && m.sparks.length > 0)
        .flatMap((m) => m.sparks || [])
      const chatSparks = chat.sparks || []
      const allSparks = [...messageSparks, ...chatSparks]
      // Deduplicate and filter older versions
      const uniqueSparks = allSparks.filter((spark, index, self) =>
        index === self.findIndex((s) => s.id === spark.id)
      )
      const parentIds = new Set(uniqueSparks.map((s) => s.parent_id).filter(Boolean))
      const filteredSparks = uniqueSparks.filter((spark) => !parentIds.has(spark.id))

      return {
        id: chat.id,
        model: chat.model,
        sparks: filteredSparks,
      }
    })
  }, [chats])

  // Multi-chat tab state for immersive comparison mode
  const {
    activeTabId,
    setActiveTabId,
    seenResponseCounts,
  } = useMultiChatTabState({ chats, conversationId: activeGroupId })

  // Factory function to generate ImmersiveChatView props for each chat in multi-chat mode
  const getImmersiveChatViewProps = useCallback((chatId: string): ImmersiveChatViewProps => {
    const chat = chats.find(c => c.id === chatId)!
    return {
      chat,
      models: getModelsForChat(chatId),
      onModelSelect: getModelSelectHandler(chatId),
      onSendMessage: sendToAllChatsHandler, // Broadcast to ALL chats in multi-chat mode
      onUpdateMessages: getUpdateMessagesHandler(chatId),
      onCancel: getCancelChatHandler(chatId),
      canCancel: abortControllersRef.current.has(chatId),
      onParametersChange: getParametersChangeHandler(chatId),
      onToolExecuted: getToolExecutedHandler(chatId),
      showFilters,
      onToggleFilters: handleToggleFilters,
      hasActiveFilters: hasActiveFilters(),
      filters,
      onFiltersChange: setFilters,
      providers,
      recentModelIds,
      webSearchState,
      onToggleWebSearch: toggleWebSearchForAll,
      hasWebSearchSupport: hasWebSearchSupport(),
      reasoningState,
      onToggleReasoning: toggleReasoningForAll,
      hasReasoningSupport: hasReasoningSupportValue,
      mcpToolsState,
      onToggleMCPTools: toggleMCPToolsForAll,
      hasFunctionSupport: hasFunctionSupportValue,
      fileToolsState,
      onToggleFileTools: toggleFileToolsForAll,
      imageGenerationState,
      onToggleImageGeneration: toggleImageGenerationForAll,
      videoGenerationState,
      onToggleVideoGeneration: toggleVideoGenerationForAll,
      sparksState,
      onToggleSparks: toggleSparksForAll,
      knowledgeBaseState,
      onToggleKnowledgeBase: toggleKnowledgeBaseForAll,
      hasKnowledgeBaseSupport: hasKnowledgeBaseSupportValue,
      activeServers: activeServersValue,
      estimatedCosts,
      onEstimateCost: handleEstimateCost,
      isEstimating: loadingEstimate,
      setEstimatedCost: setEstimatedCosts,
      attachments,
      onAddAttachment: handleAddAttachment,
      onRemoveAttachment: handleRemoveAttachment,
      hasVisionSupport: hasChatsVisionSupport,
      hasPDFSupport: hasChatsPDFSupport,
      onFilterByCapability: handleFilterByCapability,
      activeFilters: filters.input_modalities,
      isDropOver: isDropOverInput,
      onDragOver: handleSharedDragOver,
      onDragLeave: handleSharedDragLeave,
      onDrop: handleSharedDrop,
      onPaste: handleSharedPaste,
      conversationId: activeGroupId,
      onSuggestionClick: handleSuggestionClick,
      onClearChat: getClearChatHandler(chatId),
      onCopyResponses: () => copyChatResponses(chatId),
      onCopyMetadata: () => copyChatMetadata(chatId),
      onExportResponses: () => exportChatResponses(chatId),
      onExportMetadata: () => exportChatMetadata(chatId),
      onUpdateChat: (data) => updateChat(chatId, data),
      // Spark auto-fix support
      sendSparkFixRequest: (content: string, sparkFixRequest: { spark_id: string; spark_title: string; error: string }) =>
        sendSparkFixMessage(chatId, content, sparkFixRequest),
      onIgnite: (sparkId: string, sparkTitle: string) =>
        sendIgniteMessage(chatId, { spark_id: sparkId, spark_title: sparkTitle }),
    }
  }, [
    chats, getModelsForChat, getModelSelectHandler, sendToAllChatsHandler,
    getUpdateMessagesHandler, getCancelChatHandler, getParametersChangeHandler,
    getToolExecutedHandler, showFilters, handleToggleFilters, hasActiveFilters,
    filters, setFilters, providers, recentModelIds, webSearchState, toggleWebSearchForAll,
    hasWebSearchSupport, reasoningState, toggleReasoningForAll, hasReasoningSupportValue,
    mcpToolsState, toggleMCPToolsForAll, hasFunctionSupportValue, fileToolsState,
    toggleFileToolsForAll, imageGenerationState, toggleImageGenerationForAll,
    videoGenerationState, toggleVideoGenerationForAll, sparksState, toggleSparksForAll,
    knowledgeBaseState, toggleKnowledgeBaseForAll, hasKnowledgeBaseSupportValue,
    activeServersValue, estimatedCosts, handleEstimateCost, loadingEstimate,
    setEstimatedCosts, attachments, handleAddAttachment, handleRemoveAttachment,
    hasChatsVisionSupport, hasChatsPDFSupport, handleFilterByCapability, isDropOverInput,
    handleSharedDragOver, handleSharedDragLeave, handleSharedDrop, handleSharedPaste,
    activeGroupId, handleSuggestionClick, getClearChatHandler, copyChatResponses,
    copyChatMetadata, exportChatResponses, exportChatMetadata, updateChat, sendSparkFixMessage, sendIgniteMessage,
  ])

  // Factory function to generate ChatGridCard props for each chat in grid view
  // Simplified - input is shared at grid level, not per card
  const getChatGridCardProps = useCallback((chatId: string): ChatGridCardProps => {
    const chat = chats.find(c => c.id === chatId)!
    return {
      chat,
      models: getModelsForChat(chatId),
      onModelSelect: getModelSelectHandler(chatId),
      onUpdateMessages: getUpdateMessagesHandler(chatId),
      onRemove: () => {
        setClosingChatId(chatId)
        setShowCloseDialog(true)
      },
      showRemove: chats.length > 1,
      onToolExecuted: getToolExecutedHandler(chatId),
      showFilters,
      onToggleFilters: handleToggleFilters,
      hasActiveFilters: hasActiveFilters(),
      filters,
      onFiltersChange: setFilters,
      providers,
      recentModelIds,
      conversationId: activeGroupId,
      // Per-chat options handlers
      onOpenInstructions: () => {
        setGridInstructionsEditingChatId(chatId)
        setGridInstructionsOpen(true)
      },
      onCopyResponses: () => copyChatResponses(chatId),
      onCopyMetadata: () => copyChatMetadata(chatId),
      onExportResponses: () => exportChatResponses(chatId),
      onExportMetadata: () => exportChatMetadata(chatId),
      onSaveToKnowledgeBase: () => handleSaveChatToKnowledgeBase(chatId),
      isSavingToKnowledgeBase: savingChatId === chatId,
      // Spark auto-fix support
      sendSparkFixRequest: (content: string, sparkFixRequest: { spark_id: string; spark_title: string; error: string }) =>
        sendSparkFixMessage(chatId, content, sparkFixRequest),
      sparksEnabled: sparksState?.enabled !== undefined && sparksState.enabled > 0,
    }
  }, [
    chats, getModelsForChat, getModelSelectHandler, getUpdateMessagesHandler,
    getToolExecutedHandler, showFilters, handleToggleFilters, hasActiveFilters,
    filters, setFilters, providers, recentModelIds, activeGroupId,
    copyChatResponses, copyChatMetadata, exportChatResponses, exportChatMetadata,
    savingChatId, sendSparkFixMessage, sparksState,
  ])

  // Sort groups by updatedAt (most recent first) - MEMOIZED to avoid re-sorting on every render
  const sortedGroups = useMemo(() => {
    return [...chatGroups].sort((a, b) => {
      // Defensive check for undefined dates
      const aTime = a.updatedAt instanceof Date ? a.updatedAt.getTime() : 0
      const bTime = b.updatedAt instanceof Date ? b.updatedAt.getTime() : 0
      return bTime - aTime
    })
  }, [chatGroups])

  // Prepare groups for ConversationsModal - MEMOIZED to avoid expensive generateFullGroupName calls
  const modalGroups = useMemo(() => {
    return sortedGroups.map(g => ({
      id: g.id,
      name: g.name,
      fullName: g.isCustomName ? g.name : generateFullGroupName(g.chats),
      createdAt: g.createdAt,
      updatedAt: g.updatedAt
    }))
  }, [sortedGroups, generateFullGroupName])

  // Memoized callbacks to prevent unnecessary re-renders of memoized child components
  const handleCloseConversationsModal = useCallback(() => {
    setConversationsModalOpen(false)
  }, [])

  const handleToggleConversations = useCallback(() => {
    setConversationsModalOpen(!conversationsModalOpen)
  }, [conversationsModalOpen])

  const handleShowClearDialog = useCallback(() => {
    setShowClearDialog(true)
  }, [])

  const handleToggleImmersiveMode = useCallback(() => {
    const newValue = !isImmersiveMode
    setIsImmersiveMode(newValue)
    // Save the preference for this conversation
    if (activeGroupId) {
      saveImmersiveMode(activeGroupId, newValue)
    }
  }, [isImmersiveMode, activeGroupId, saveImmersiveMode])

  // State for new conversation mode (temporary unsaved chat)
  const [newConvoChat, setNewConvoChat] = useState<Chat>(() => ({
    id: 'new-conversation-temp',
    model: currentModel,
    messages: [],
    isLoading: false,
    parameters: { ...DEFAULT_PARAMETERS }
  }))
  const [newConvoAttachments, setNewConvoAttachments] = useState<Attachment[]>([])

  // Update newConvoChat model when entering new conversation mode or when currentModel changes
  useEffect(() => {
    if (isNewConversation && currentModel) {
      setNewConvoChat(prev => ({
        ...prev,
        model: currentModel
      }))
    }
  }, [isNewConversation, currentModel])

  // Automatically update empty chats (no messages) when sidebar model changes
  // Only updates chats that have NO model set (model === null)
  // Chats with a model already set keep their model even if messages are empty
  // (e.g., when editing the first message clears all messages)
  useEffect(() => {
    

    if (!currentModel || !activeGroup) return

    // Skip auto-update if there's a pending message from new conversation creation
    // This prevents overwriting the deliberately-selected model before the first message is sent
    const hasPendingMessage = sessionStorage.getItem('pending-message') !== null
    if (hasPendingMessage) {
      
      return
    }

    // Find all chats that need model update (no messages AND no model set)
    const chatsNeedingModel = activeGroup.chats.filter(
      chat => chat.messages.length === 0 && chat.model === null
    )

    

    // Update each chat's model using updateChatModel (which persists to backend)
    chatsNeedingModel.forEach(chat => {
      
      updateChatModel(chat.id, currentModel)
    })
  }, [currentModel, activeGroup, updateChatModel])

  // Show nothing while loading conversations to prevent flash of non-immersive view
  if (isLoadingConversations || (!activeGroup && !isNewConversation)) {
    return null
  }

  // Handle new conversation mode - render with a temporary unsaved chat
  if (isNewConversation) {
    return (
      <NewConversationView
        newConvoChat={newConvoChat}
        setNewConvoChat={setNewConvoChat}
        newConvoAttachments={newConvoAttachments}
        setNewConvoAttachments={setNewConvoAttachments}
        createConversation={createConversation}
        setActiveGroupId={setActiveGroupId}
        setIsImmersiveMode={setIsImmersiveMode}
        saveImmersiveMode={saveImmersiveMode}
        pendingFirstMessageRef={pendingFirstMessageRef}
        pendingMessageProcessedRef={pendingMessageProcessedRef}
        models={models}
        filteredModels={filteredModels}
        showFilters={showFilters}
        onToggleFilters={handleToggleFilters}
        hasActiveFilters={hasActiveFilters}
        filters={filters}
        setFilters={setFilters}
        providers={providers}
        recentModelIds={recentModelIds}
        activeServers={activeServersValue}
        estimatedCosts={estimatedCosts}
        onEstimateCost={handleEstimateCost}
        loadingEstimate={loadingEstimate}
        setEstimatedCosts={setEstimatedCosts}
        onFilterByCapability={handleFilterByCapability}
        onSuggestionClick={handleSuggestionClick}
        isDropOverInput={isDropOverInput}
        onDragOver={handleSharedDragOver}
        onDragLeave={handleSharedDragLeave}
        onDrop={handleSharedDrop}
        onPaste={handleSharedPaste}
      />
    )
  }

  // Show loading skeleton when activeGroupId is set but chats haven't loaded yet
  // This prevents briefly showing the comparison view during state transitions
  if (activeGroupId && chats.length === 0) {
    return <ModelComparisonSkeleton />
  }

  // Render immersive mode when single chat and immersive is enabled (always on mobile)
  if (effectiveIsImmersiveMode && chats.length === 1) {
    const singleChat = chats[0]
    return (
      <ImmersiveChatView
        chat={singleChat}
        models={getModelsForChat(singleChat.id)}
        onModelSelect={getModelSelectHandler(singleChat.id)}
        onSendMessage={getSendMessageHandler(singleChat.id)}
        onUpdateMessages={getUpdateMessagesHandler(singleChat.id)}
        onCancel={getCancelChatHandler(singleChat.id)}
        canCancel={abortControllersRef.current.has(singleChat.id)}
        onExitImmersive={handleToggleImmersiveMode}
        onParametersChange={getParametersChangeHandler(singleChat.id)}
        onToolExecuted={getToolExecutedHandler(singleChat.id)}
        onAddChat={addChat}
        showFilters={showFilters}
        onToggleFilters={handleToggleFilters}
        hasActiveFilters={hasActiveFilters()}
        filters={filters}
        onFiltersChange={setFilters}
        providers={providers}
        recentModelIds={recentModelIds}
        webSearchState={webSearchState}
        onToggleWebSearch={toggleWebSearchForAll}
        hasWebSearchSupport={hasWebSearchSupport()}
        reasoningState={reasoningState}
        onToggleReasoning={toggleReasoningForAll}
        hasReasoningSupport={hasReasoningSupportValue}
        mcpToolsState={mcpToolsState}
        onToggleMCPTools={toggleMCPToolsForAll}
        hasFunctionSupport={hasFunctionSupportValue}
        fileToolsState={fileToolsState}
        onToggleFileTools={toggleFileToolsForAll}
        imageGenerationState={imageGenerationState}
        onToggleImageGeneration={toggleImageGenerationForAll}
        videoGenerationState={videoGenerationState}
        onToggleVideoGeneration={toggleVideoGenerationForAll}
        sparksState={sparksState}
        onToggleSparks={toggleSparksForAll}
        knowledgeBaseState={knowledgeBaseState}
        onToggleKnowledgeBase={toggleKnowledgeBaseForAll}
        hasKnowledgeBaseSupport={hasKnowledgeBaseSupportValue}
        activeServers={activeServersValue}
        estimatedCosts={estimatedCosts}
        onEstimateCost={handleEstimateCost}
        isEstimating={loadingEstimate}
        setEstimatedCost={setEstimatedCosts}
        attachments={attachments}
        onAddAttachment={handleAddAttachment}
        onRemoveAttachment={handleRemoveAttachment}
        hasVisionSupport={hasChatsVisionSupport}
        hasPDFSupport={hasChatsPDFSupport}
        onFilterByCapability={handleFilterByCapability}
        activeFilters={filters.input_modalities}
        isDropOver={isDropOverInput}
        onDragOver={handleSharedDragOver}
        onDragLeave={handleSharedDragLeave}
        onDrop={handleSharedDrop}
        onPaste={handleSharedPaste}
        conversationId={activeGroupId}
        onSuggestionClick={handleSuggestionClick}
        onClearChat={getClearChatHandler(singleChat.id)}
        onCopyResponses={copyConversationResponses}
        onCopyMetadata={copyConversationMetadata}
        onExportResponses={exportConversationResponses}
        onExportMetadata={exportConversationMetadata}
        onUpdateChat={(data) => updateChat(singleChat.id, data)}
        sendSparkFixRequest={(content, sparkFixRequest) =>
          sendSparkFixMessage(singleChat.id, content, sparkFixRequest)
        }
        onIgnite={(sparkId, sparkTitle) =>
          sendIgniteMessage(singleChat.id, { spark_id: sparkId, spark_title: sparkTitle })
        }
      />
    )
  }

  // Render multi-chat immersive mode when multiple chats and immersive is enabled (always on mobile)
  if (effectiveIsImmersiveMode && chats.length > 1) {
    return (
      <>
        <ChatTabContainer
          chats={chats}
          conversationId={activeGroupId}
          activeTabId={activeTabId}
          onActiveTabChange={setActiveTabId}
          seenResponseCounts={seenResponseCounts}
          onAddChat={addChat}
          onRemoveChat={(chatId) => {
            setClosingChatId(chatId)
            setShowCloseDialog(true)
          }}
          onExitImmersive={handleToggleImmersiveMode}
          getImmersiveChatViewProps={getImmersiveChatViewProps}
        />

        {/* Close Chat Confirmation Dialog */}
        <ConfirmDeleteModal
          isOpen={showCloseDialog}
          onClose={() => {
            setShowCloseDialog(false)
            setClosingChatId(null)
          }}
          onConfirm={(deleteWorkspace) => {
            if (closingChatId) {
              removeChat(closingChatId, deleteWorkspace)
              setClosingChatId(null)
            }
            setShowCloseDialog(false)
          }}
          title="Remove Chat?"
          description="This will remove this chat from the comparison."
          showWorkspaceCheckbox={false}
        />
      </>
    )
  }

  // Render grid view when not in immersive mode and has multiple chats
  return (
    <div className="h-full flex overflow-hidden">
      {/* Main grid area */}
      <div className="flex-1 overflow-hidden">
        <ChatGrid
        chats={chats}
        maxChats={MAX_CHATS}
        onAddChat={addChat}
        onRemoveChat={(chatId) => {
          setClosingChatId(chatId)
          setShowCloseDialog(true)
        }}
        onEnterImmersive={handleToggleImmersiveMode}
        getChatGridCardProps={getChatGridCardProps}
        // Shared input props
        onSendMessage={sendToAllChatsHandler}
        onCancel={() => chats.forEach(c => getCancelChatHandler(c.id)())}
        canCancel={chats.some(c => abortControllersRef.current.has(c.id))}
        isAnyLoading={chats.some(c => c.isLoading)}
        hasAnyModel={chats.some(c => c.model !== null)}
        attachments={attachments}
        onAddAttachment={handleAddAttachment}
        onRemoveAttachment={handleRemoveAttachment}
        hasVisionSupport={hasChatsVisionSupport}
        hasPDFSupport={hasChatsPDFSupport}
        onFilterByCapability={handleFilterByCapability}
        activeFilters={filters.input_modalities}
        isDropOver={isDropOverInput}
        onDragOver={handleSharedDragOver}
        onDragLeave={handleSharedDragLeave}
        onDrop={handleSharedDrop}
        onPaste={handleSharedPaste}
        webSearchState={webSearchState}
        onToggleWebSearch={toggleWebSearchForAll}
        hasWebSearchSupport={hasWebSearchSupport()}
        reasoningState={reasoningState}
        onToggleReasoning={toggleReasoningForAll}
        hasReasoningSupport={hasReasoningSupportValue}
        mcpToolsState={mcpToolsState}
        onToggleMCPTools={toggleMCPToolsForAll}
        hasFunctionSupport={hasFunctionSupportValue}
        fileToolsState={fileToolsState}
        onToggleFileTools={toggleFileToolsForAll}
        imageGenerationState={imageGenerationState}
        onToggleImageGeneration={toggleImageGenerationForAll}
        videoGenerationState={videoGenerationState}
        onToggleVideoGeneration={toggleVideoGenerationForAll}
        sparksState={sparksState}
        onToggleSparks={toggleSparksForAll}
        knowledgeBaseState={knowledgeBaseState}
        onToggleKnowledgeBase={toggleKnowledgeBaseForAll}
        hasKnowledgeBaseSupport={hasKnowledgeBaseSupportValue}
        activeServers={activeServersValue}
      />
      </div>

      {/* Artifacts Side Panel - with chat tabs for grid view */}
      <ArtifactsSidePanel
        chatId={chats[0]?.id || ''}
        conversationId={activeGroupId}
        sparks={gridSparks}
        chats={chatsWithSparks}
        onIgnite={(sparkId, sparkTitle) => {
          const chatId = chats[0]?.id
          if (chatId) sendIgniteMessage(chatId, { spark_id: sparkId, spark_title: sparkTitle })
        }}
      />

      {/* Grid view instructions sheet - per chat */}
      <ChatInstructionsSheet
        isOpen={gridInstructionsOpen}
        onClose={() => {
          setGridInstructionsOpen(false)
          setGridInstructionsEditingChatId(null)
        }}
        instructions={gridInstructionsEditingChatId ? chats.find(c => c.id === gridInstructionsEditingChatId)?.instructions : undefined}
        onSave={(instructions) => {
          if (gridInstructionsEditingChatId) {
            updateChat(gridInstructionsEditingChatId, { instructions })
          }
        }}
        modelName={gridInstructionsEditingChatId ? chats.find(c => c.id === gridInstructionsEditingChatId)?.model?.name : undefined}
      />

      {/* Conversations Modal */}
      <ConversationsModal
        isOpen={conversationsModalOpen}
        onClose={handleCloseConversationsModal}
        groups={modalGroups}
        activeGroupId={activeGroupId}
        onSelectGroup={switchGroup}
        onNewGroup={createNewGroup}
        onDeleteGroup={deleteGroup}
        onRenameGroup={renameGroup}
      />

      {/* Consigliere Modal */}
      <ConsigliereModal />

      {/* Close Chat Confirmation Dialog */}
      <ConfirmDeleteModal
        isOpen={showCloseDialog}
        onClose={() => {
          setShowCloseDialog(false)
          setClosingChatId(null)
        }}
        onConfirm={(deleteWorkspace) => {
          if (closingChatId) {
            removeChat(closingChatId, deleteWorkspace)
            setClosingChatId(null)
          }
          setShowCloseDialog(false)
        }}
        title="Remove Chat?"
        description="This will remove this chat from the comparison."
        showWorkspaceCheckbox={false}
      />
    </div>
  )
}
