import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useSearch, useNavigate } from '@tanstack/react-router'
import { generateUUID } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/hooks/use-toast'
import { useModelFilters } from '@/hooks/useModelFilters'
import { ImmersiveChatView } from './ImmersiveChatView'
import { ChatTabContainer } from './ChatTabContainer'
import type { ImmersiveChatViewProps } from './ChatTabContainer'
import { ChatGrid } from './ChatGrid'
import type { ChatGridCardProps } from './ChatGrid'
import { ChatInstructionsSheet } from './ChatInstructionsSheet'
import { ArtifactsSidePanel } from './ArtifactsSidePanel'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import { ConversationsModal } from './ConversationsModal'
import { ConfirmDeleteModal } from '@/components/shared'
import { ConsigliereModal } from '@/components/consigliere/ConsigliereModal'
import { SuggestedQuestionsCarousel } from './SuggestedQuestionsCarousel'
import { CostEstimationDisplay } from './CostEstimationDisplay'
import { llmApi, type ModelCostEstimate, type ChatFeatureFlags } from '@/api/llm'
import { revokeImagePreview } from '@/utils/imageUtils'
import { buildConversationResponsesText, buildConversationMetadata, buildChatResponsesText, buildChatMetadata, generateFilename, extractTextFromContent } from '@/utils/chatUtils'
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
import { assetsAPI, assetToReference, getAssetTypeFromMime } from '@/api/assets'
import { conversationsAPI } from '@/api/conversations'
import { getApiErrorMessage, hasErrorResponse } from '@/utils/errorMessages'
import { sparksAPI } from '@/api/sparks'
import type { Model, Message, ModelParameters, Chat, ChatGroup, Attachment, AttachmentLike, ToolExecutedHandler, FileAttachment, ImageAttachment } from './types'
import type { ModelCatalogEntry } from '@/types/models'
import { toModelCatalogEntry } from './modelCatalog'

import { MAX_CHATS, DEFAULT_PARAMETERS } from './constants'

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

  // Helper functions to persist immersive mode per conversation
  // Uses localStorage as primary source to avoid 404 API calls for new preferences
  const getImmersiveModeKey = (conversationId: string) => `models.immersive_mode.${conversationId}`

  const saveImmersiveMode = useCallback((conversationId: string, isImmersive: boolean) => {
    // Save to localStorage only (no backend API call needed for UI state)
    try {
      localStorage.setItem(getImmersiveModeKey(conversationId), JSON.stringify(isImmersive))
    } catch (e) {
      // localStorage might be full or disabled
    }
  }, [])

  const loadImmersiveMode = useCallback((conversationId: string, defaultValue: boolean): boolean => {
    const key = getImmersiveModeKey(conversationId)

    // Use localStorage only (no backend API call needed for UI state)
    try {
      const saved = localStorage.getItem(key)
      if (saved !== null) {
        return JSON.parse(saved)
      }
    } catch (e) {
      // Parse error or localStorage disabled
    }

    return defaultValue
  }, [])

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

  // Create stable handler Maps to prevent ALL chats from re-rendering when typing in one
  // Maps ensure each chatId gets the SAME function reference across renders
  const sendMessageHandlers = useRef(new Map<string, (content: string, localAttachments?: Attachment[]) => Promise<void>>())
  const modelSelectHandlers = useRef(new Map<string, (model: Model) => void>())
  const updateMessagesHandlers = useRef(new Map<string, (messages: Message[]) => void>())
  const removeHandlers = useRef(new Map<string, () => void>())
  const estimateCostHandlers = useRef(new Map<string, (text: string, atts?: Attachment[]) => Promise<Omit<ModelCostEstimate, 'model_id'> | null>>())

  // Track previous function references to detect changes synchronously
  // IMPORTANT: This must clear the cache DURING render, not in an effect
  // Otherwise, get*Handler returns stale handlers before the effect runs
  // This fixes issues like voice mode not being passed when the overlay opens
  const prevComposeAndSendRef = useRef(composeAndSend)
  if (prevComposeAndSendRef.current !== composeAndSend) {
    sendMessageHandlers.current.clear()
    prevComposeAndSendRef.current = composeAndSend
  }

  // Clear model select handlers synchronously when updateChatModel changes
  // This is CRITICAL: without this, changing one chat's model would affect other chats
  // because the old handlers capture stale closure values
  const prevUpdateChatModelRef = useRef(updateChatModel)
  if (prevUpdateChatModelRef.current !== updateChatModel) {
    modelSelectHandlers.current.clear()
    prevUpdateChatModelRef.current = updateChatModel
  }

  // Clear update messages handlers synchronously when updateChatMessages changes
  const prevUpdateChatMessagesRef = useRef(updateChatMessages)
  if (prevUpdateChatMessagesRef.current !== updateChatMessages) {
    updateMessagesHandlers.current.clear()
    prevUpdateChatMessagesRef.current = updateChatMessages
  }

  // Get or create stable handler for each chat (sends to single chat only)
  const getSendMessageHandler = useCallback((chatId: string) => {
    if (!sendMessageHandlers.current.has(chatId)) {
      sendMessageHandlers.current.set(chatId, async (content: string, localAttachments?: Attachment[]) => {
        await composeAndSend([chatId], content, localAttachments || [])
      })
    }
    return sendMessageHandlers.current.get(chatId)!
  }, [composeAndSend])

  // Broadcast handler for multi-chat mode: sends to ALL enabled chats
  const sendToAllChatsHandler = useCallback(async (content: string, localAttachments?: Attachment[]) => {
    const enabledIds = chats.filter(c => c.model !== null && !c.disabled).map(c => c.id)
    if (enabledIds.length === 0) {
      toast({
        title: 'No model selected',
        description: 'Please select at least one model to send a message.',
        variant: 'destructive'
      })
      return
    }
    await composeAndSend(enabledIds, content, localAttachments || [])
  }, [chats, composeAndSend, toast])

  const getModelSelectHandler = useCallback((chatId: string) => {
    if (!modelSelectHandlers.current.has(chatId)) {
      modelSelectHandlers.current.set(chatId, (model: Model) => {
        // Only update the chat's model, don't affect global model selection
        updateChatModel(chatId, model)
      })
    }
    return modelSelectHandlers.current.get(chatId)!
  }, [updateChatModel])

  const getUpdateMessagesHandler = useCallback((chatId: string) => {
    if (!updateMessagesHandlers.current.has(chatId)) {
      updateMessagesHandlers.current.set(chatId, (messages: Message[]) => {
        updateChatMessages(chatId, messages)
      })
    }
    return updateMessagesHandlers.current.get(chatId)!
  }, [updateChatMessages])

  const getRemoveHandler = useCallback((chatId: string) => {
    if (!removeHandlers.current.has(chatId)) {
      removeHandlers.current.set(chatId, () => {
        setClosingChatId(chatId)
        setShowCloseDialog(true)
      })
    }
    return removeHandlers.current.get(chatId)!
  }, [])

  // Handle cost estimation for individual chat in independent mode (memoized)
  const handleEstimateCostForChat = useCallback(async (chatId: string, text: string, localAttachments: Attachment[] = []) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat?.model) return null
    try {
      const filesText = buildTextFromTextAttachments(localAttachments)
      const filesMeta = (localAttachments || [])
        .filter((a): a is FileAttachment => a.type === 'file')
        .map((f) => ({ filename: f.file?.name || 'file', mime: f.file?.type || undefined, size: f.file?.size || undefined }))
      const imagesMeta = (localAttachments || [])
        .filter((a): a is ImageAttachment => a.type === 'image')
        .map((img) => ({ mime: img.file?.type || undefined, size: img.file?.size || undefined }))
      const response = await llmApi.estimateBatchCost({
        model_ids: [chat.model.model_id],
        prompt_text: text + filesText,
        typed_text: text,
        files_text: filesText,
        features_by_model: {
          [chat.model.model_id]: {
            system_prompt: chat.parameters?.system_prompt || '',
            enable_mcp_tools: chat.parameters?.enable_mcp_tools || false,
            enable_reasoning: chat.parameters?.enable_reasoning || false,
            enable_file_tools: chat.parameters?.enable_file_tools || false,
          }
        },
        files: filesMeta,
        images: imagesMeta,
        max_new_tokens_by_model: chat.parameters?.max_tokens
          ? { [chat.model.model_id]: chat.parameters.max_tokens }
          : undefined,
      })
      const data = {
        ...response.data,
        total_cost: typeof response.data.total_cost === 'string' ? parseFloat(response.data.total_cost) : response.data.total_cost,
        costs: response.data.costs.map((c) => ({ ...c, cost: typeof c.cost === 'string' ? parseFloat(c.cost) : c.cost })),
      }
      if (data.costs && data.costs.length > 0) {
        return {
          cost: data.costs[0].cost,
          prompt_tokens: data.costs[0].prompt_tokens,
          completion_tokens: data.costs[0].completion_tokens,
          model_name: data.costs[0].model_name,
        }
      }
      return null
    } catch (error) {
      throw error
    }
  }, [chats])

  const getEstimateCostHandler = useCallback((chatId: string) => {
    if (!estimateCostHandlers.current.has(chatId)) {
      estimateCostHandlers.current.set(chatId, (text: string, atts?: Attachment[]) => {
        return handleEstimateCostForChat(chatId, text, atts)
      })
    }
    return estimateCostHandlers.current.get(chatId)!
  }, [handleEstimateCostForChat])

  const moveLeftHandlers = useRef(new Map<string, () => void>())
  const moveRightHandlers = useRef(new Map<string, () => void>())
  const parametersChangeHandlers = useRef(new Map<string, (params: ModelParameters) => void>())
  const toggleDisabledHandlers = useRef(new Map<string, (value: boolean) => void>())
  const toggleHiddenHandlers = useRef(new Map<string, (value: boolean) => void>())
  const clearChatHandlers = useRef(new Map<string, (deleteWorkspace?: boolean) => void>())
  const cancelChatHandlers = useRef(new Map<string, () => void>())

  const getMoveLeftHandler = useCallback((chatId: string) => {
    if (!moveLeftHandlers.current.has(chatId)) {
      moveLeftHandlers.current.set(chatId, () => moveLeft(chatId))
    }
    return moveLeftHandlers.current.get(chatId)!
  }, [moveLeft])

  const getMoveRightHandler = useCallback((chatId: string) => {
    if (!moveRightHandlers.current.has(chatId)) {
      moveRightHandlers.current.set(chatId, () => moveRight(chatId))
    }
    return moveRightHandlers.current.get(chatId)!
  }, [moveRight])

  const getParametersChangeHandler = useCallback((chatId: string) => {
    if (!parametersChangeHandlers.current.has(chatId)) {
      parametersChangeHandlers.current.set(chatId, (params: ModelParameters) => updateChatParameters(chatId, params))
    }
    return parametersChangeHandlers.current.get(chatId)!
  }, [updateChatParameters])

  const getToggleDisabledHandler = useCallback((chatId: string) => {
    if (!toggleDisabledHandlers.current.has(chatId)) {
      toggleDisabledHandlers.current.set(chatId, (value: boolean) => updateChatDisabled(chatId, value))
    }
    return toggleDisabledHandlers.current.get(chatId)!
  }, [updateChatDisabled])

  const getToggleHiddenHandler = useCallback((chatId: string) => {
    if (!toggleHiddenHandlers.current.has(chatId)) {
      toggleHiddenHandlers.current.set(chatId, (value: boolean) => updateChatHidden(chatId, value))
    }
    return toggleHiddenHandlers.current.get(chatId)!
  }, [updateChatHidden])

  const getClearChatHandler = useCallback((chatId: string) => {
    if (!clearChatHandlers.current.has(chatId)) {
      clearChatHandlers.current.set(chatId, (deleteWorkspace?: boolean) => clearChat(chatId, deleteWorkspace))
    }
    return clearChatHandlers.current.get(chatId)!
  }, [clearChat])

  const getCancelChatHandler = useCallback((chatId: string) => {
    if (!cancelChatHandlers.current.has(chatId)) {
      cancelChatHandlers.current.set(chatId, () => cancelChat(chatId))
    }
    return cancelChatHandlers.current.get(chatId)!
  }, [cancelChat])

  const toolExecutedHandlers = useRef(new Map<string, ToolExecutedHandler>())

  const getToolExecutedHandler = useCallback((chatId: string) => {
    if (!toolExecutedHandlers.current.has(chatId)) {
      toolExecutedHandlers.current.set(chatId, (toolCallId: string, toolName: string, result: Record<string, unknown> | undefined) => {
        // Get current chat using ref to avoid stale closure issues in multi-chat parallel scenarios
        const currentChat = chatsRef.current.find(c => c.id === chatId)
        if (!currentChat) return

        // Add a "tool" message with the execution result (OpenAI format)
        // This message will be sent to the model but NOT displayed in the UI
        const toolMessage: Message = {
          role: 'tool',
          tool_call_id: toolCallId,
          content: JSON.stringify(result?.content),  // Send the raw tool result to the model
          timestamp: new Date(),
        }

        // Update messages to include the tool result
        const updatedMessages = [...currentChat.messages, toolMessage]

        // Update state with the tool message
        updateChatMessages(chatId, updatedMessages)

        // Continue the conversation immediately by sending the updated messages directly
        // We pass the messages explicitly to avoid async state issues
        if (currentChat.model) {
          sendToModel(chatId, currentChat.model, updatedMessages)
        }
      })
    }
    return toolExecutedHandlers.current.get(chatId)!
  }, [updateChatMessages, sendToModel])

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

  const copyConversationResponses = () => {
    const text = buildConversationResponsesText(chats)
    navigator.clipboard.writeText(text)
    toast({ title: 'Copied', description: 'All responses copied to clipboard' })
  }

  const copyConversationMetadata = () => {
    const data = buildConversationMetadata(chats, false)
    navigator.clipboard.writeText(JSON.stringify(data, null, 2))
    toast({ title: 'Copied', description: 'All metadata copied to clipboard' })
  }

  const exportConversationResponses = () => {
    const text = buildConversationResponsesText(chats)
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = generateFilename('conversation', 'txt')
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'All responses exported' })
  }

  const exportConversationMetadata = () => {
    const data = buildConversationMetadata(chats, false)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = generateFilename('conversation-metadata', 'json')
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'All metadata exported' })
  }

  // Save conversation to knowledge base (for all views)
  const handleSaveToKnowledgeBase = useCallback(async () => {
    if (isSavingToKnowledgeBase || !activeGroupId) return

    setIsSavingToKnowledgeBase(true)
    try {
      const result = await conversationsAPI.saveToKnowledgeBase(activeGroupId)
      toast({ title: 'Saved', description: `Saved to knowledge base: ${result.filename}` })
    } catch (error) {
      const errorData = hasErrorResponse(error)
        ? error.response?.data as { existing_document_id?: string; error?: string } | undefined
        : undefined
      if (errorData?.existing_document_id) {
        toast({ title: 'Already saved', description: errorData.error || 'This conversation is already in your knowledge base', variant: 'destructive' })
      } else if (errorData?.error) {
        toast({ title: 'Failed to save', description: errorData.error, variant: 'destructive' })
      } else {
        toast({ title: 'Error', description: 'Failed to save to knowledge base', variant: 'destructive' })
      }
    } finally {
      setIsSavingToKnowledgeBase(false)
    }
  }, [activeGroupId, isSavingToKnowledgeBase, toast])

  // Save single chat to knowledge base
  const handleSaveChatToKnowledgeBase = useCallback(async (chatId: string) => {
    if (savingChatId || !activeGroupId) return

    const chat = chats.find(c => c.id === chatId)
    if (!chat) return

    setSavingChatId(chatId)
    try {
      // Currently saves entire conversation - in future could be chat-specific
      const result = await conversationsAPI.saveToKnowledgeBase(activeGroupId)
      const modelName = chat.model?.name || 'Chat'
      toast({ title: 'Saved', description: `${modelName} saved to knowledge base: ${result.filename}` })
    } catch (error) {
      const errorData = hasErrorResponse(error)
        ? error.response?.data as { existing_document_id?: string; error?: string } | undefined
        : undefined
      if (errorData?.existing_document_id) {
        toast({ title: 'Already saved', description: errorData.error || 'This conversation is already in your knowledge base', variant: 'destructive' })
      } else if (errorData?.error) {
        toast({ title: 'Failed to save', description: errorData.error, variant: 'destructive' })
      } else {
        toast({ title: 'Error', description: 'Failed to save to knowledge base', variant: 'destructive' })
      }
    } finally {
      setSavingChatId(null)
    }
  }, [activeGroupId, chats, savingChatId, toast])

  // Per-chat copy/export functions (for immersive mode options menu)
  const copyChatResponses = (chatId: string) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat) return
    const text = buildChatResponsesText(chat.messages)
    navigator.clipboard.writeText(text)
    toast({ title: 'Copied', description: 'Responses copied to clipboard' })
  }

  const copyChatMetadata = (chatId: string) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat) return
    const data = buildChatMetadata(chat.messages)
    navigator.clipboard.writeText(JSON.stringify(data, null, 2))
    toast({ title: 'Copied', description: 'Metadata copied to clipboard' })
  }

  const exportChatResponses = (chatId: string) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat) return
    const text = buildChatResponsesText(chat.messages)
    const modelName = chat.model?.name?.replace(/[^a-z0-9]/gi, '-') || 'chat'
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = generateFilename(modelName, 'txt')
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'Responses exported' })
  }

  const exportChatMetadata = (chatId: string) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat) return
    const data = buildChatMetadata(chat.messages)
    const modelName = chat.model?.name?.replace(/[^a-z0-9]/gi, '-') || 'chat'
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = generateFilename(`${modelName}-metadata`, 'json')
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'Metadata exported' })
  }

  const handleOpenConsigliere = async () => {
    if (activeGroup && currentModel) {
      const sessionId = await openConsigliere(activeGroup, currentModel.model_id)
      if (sessionId && sessionId !== activeGroup.consigliereSessionId) {
        setChatGroups(prevGroups =>
          prevGroups.map(group =>
            group.id === activeGroupId
              ? { ...group, consigliereSessionId: sessionId }
              : group
          )
        )
      }
    } else {
      toast({
        title: "Cannot open Consigliere",
        description: "Please select a model first",
        variant: "destructive"
      })
    }
  }

  const clearConversations = () => {
    // Clear messages and Consigliere session in a single state update to avoid race conditions
    setChatGroups(prevGroups =>
      prevGroups.map(group => {
        if (group.id !== activeGroupId) return group

        // Clear messages from all chats
        const clearedChats = group.chats.map(chat => ({
          ...chat,
          messages: []
        }))

        return {
          ...group,
          chats: clearedChats,
          consigliereSessionId: undefined,
          updatedAt: new Date(),
          name: 'New Conversation',
          isCustomName: false  // Allow LLM to generate name after next message
        }
      })
    )

    setSharedInput('')
    setEstimatedCosts(null)
    toast({
      title: 'Cleared',
      description: 'All conversations have been cleared'
    })
  }

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
    // Handler to create the real conversation when first message is sent
    const handleFirstMessage = async (content: string, localAttachments?: Attachment[]) => {
      try {
        // Create the real conversation with the configured parameters
        const newGroup = await createConversation([
          { id: generateUUID(), model: newConvoChat.model, messages: [], isLoading: false, parameters: { ...newConvoChat.parameters }, instructions: newConvoChat.instructions }
        ])

        // Get the chat ID from the created group
        const chatId = newGroup.chats[0]?.id || generateUUID()

        

        setActiveGroupId(newGroup.id)
        setIsImmersiveMode(true)
        preferencesSync.update(PREFERENCE_KEYS.MODELS_ACTIVE_CHAT_GROUP, newGroup.id, 'models')

        // Upload attachments as assets BEFORE storing in sessionStorage
        // This is necessary because File objects don't survive JSON serialization
        const attachmentsToProcess = localAttachments || newConvoAttachments || []
        const serializableAttachments: AttachmentLike[] = []

        if (attachmentsToProcess.length > 0) {


          // Upload each attachment in parallel
          const uploadPromises = attachmentsToProcess.map(async (att: AttachmentLike) => {
            try {
              // Only upload if we have a File object
              if (att.file instanceof File) {
                const result = await assetsAPI.uploadFile(chatId, att.file, {
                  assetType: att.type === 'image' ? 'image' : getAssetTypeFromMime(att.file.type),
                })

                if (result.success && result.asset) {
                  // Create serializable attachment with asset reference
                  const assetRef = assetToReference(result.asset)
                  return {
                    id: att.id,
                    type: att.type,
                    assetId: result.asset.id,
                    assetUrl: result.asset.download_url,
                    assetRef, // Store the full asset reference for message persistence
                    // Store file metadata for display (serializable)
                    fileName: att.file.name,
                    fileType: att.file.type,
                    fileSize: att.file.size,
                    // For images, store the preview URL (will need to be replaced with assetUrl after load)
                    preview: att.type === 'image' ? result.asset.download_url : undefined,
                    // For text files, preserve textContent if available
                    textContent: att.textContent,
                    // Preserve base64 for immediate display/sending
                    base64: att.base64,
                  }
                } else {
                  console.warn('[handleFirstMessage] Failed to upload attachment:', att.file.name, result.error)
                  // Return a serializable version without assetId (will be skipped in persistence)
                  return {
                    id: att.id,
                    type: att.type,
                    fileName: att.file.name,
                    fileType: att.file.type,
                    fileSize: att.file.size,
                    textContent: att.textContent,
                    base64: att.base64,
                    uploadFailed: true,
                  }
                }
              } else {
                // File object not available - store what we can
                return {
                  id: att.id,
                  type: att.type,
                  fileName: att.fileName || att.file?.name,
                  fileType: att.fileType || att.file?.type,
                  fileSize: att.fileSize || att.file?.size,
                  textContent: att.textContent,
                  base64: att.base64,
                  assetId: att.assetId,
                  assetUrl: att.assetUrl,
                }
              }
            } catch (error) {
              console.error('[handleFirstMessage] Error uploading attachment:', att.file?.name, error)
              return {
                id: att.id,
                type: att.type,
                fileName: att.file?.name,
                fileType: att.file?.type,
                fileSize: att.file?.size,
                uploadFailed: true,
              }
            }
          })

          const results = await Promise.all(uploadPromises)
          serializableAttachments.push(...results.filter(Boolean))
          
        }

        // Store the pending message in a ref so the URL effect can dispatch it
        // after loadConversation resolves (no page reload needed).
        const pendingMsg = { content, attachments: serializableAttachments, chatId }
        pendingFirstMessageRef.current = pendingMsg

        // Also store in sessionStorage as fallback (e.g. auth redirect / page reload)
        sessionStorage.setItem('pending-message', JSON.stringify(pendingMsg))

        // Block the pending-message useEffect from firing — the URL effect will
        // handle dispatch after loadConversation resolves instead.
        pendingMessageProcessedRef.current = true

        // SPA navigate — the URL effect will pick up the conversation, load it,
        // then dispatch the pending message once chats are ready.
        navigate({ to: '/chats', search: { conversation: newGroup.id }, replace: true })
      } catch (err) {
        console.error('[ModelComparisonPage] Failed to create conversation from first message:', err)
        toast({
          title: 'Failed to create conversation',
          description: 'Please try again',
          variant: 'destructive'
        })
      }
    }

    // Compute feature states based on temp chat parameters
    const tempParams = newConvoChat.parameters || {}
    const tempHasReasoning = newConvoChat.model?.supports_reasoning || false
    const tempHasFunction = newConvoChat.model?.supports_functions || false
    // Convert to FeatureState objects for GlobalFeatureToggles compatibility
    const tempWebSearchState = { enabled: tempParams.enable_brave_search ? 1 : 0, total: 1, supported: tempHasFunction ? 1 : 0 }
    const tempReasoningState = { enabled: tempParams.enable_reasoning ? 1 : 0, total: 1, supported: tempHasReasoning ? 1 : 0 }
    const tempMcpToolsState = { enabled: tempParams.enable_mcp_tools ? 1 : 0, total: 1, supported: tempHasFunction ? 1 : 0 }
    const tempFileToolsState = { enabled: tempParams.enable_file_tools ? 1 : 0, total: 1, supported: tempHasFunction ? 1 : 0 }
    const tempImageGenerationState = { enabled: tempParams.enable_image_generation ? 1 : 0, total: 1, supported: tempHasFunction ? 1 : 0 }
    const tempVideoGenerationState = { enabled: tempParams.enable_video_generation ? 1 : 0, total: 1, supported: tempHasFunction ? 1 : 0 }
    const tempSparksState = { enabled: tempParams.enable_sparks ? 1 : 0, total: 1, supported: tempHasFunction ? 1 : 0 }
    const tempKnowledgeBaseState = { enabled: tempParams.enable_knowledge_base ? 1 : 0, total: 1, supported: tempHasFunction ? 1 : 0 }

    // Ensure the selected model is included in the models list even if filtered out
    const newConvoModels = (() => {
      if (!newConvoChat.model) return filteredModels
      const isSelectedModelInList = filteredModels.some(m => m.model_id === newConvoChat.model?.model_id)
      if (!isSelectedModelInList) {
        // Try to find in full models list, fall back to the model object itself
        const selectedModelEntry = models.find(m => m.model_id === newConvoChat.model?.model_id)
        return [selectedModelEntry ?? toModelCatalogEntry(newConvoChat.model), ...filteredModels]
      }
      return filteredModels
    })()

    return (
      <ImmersiveChatView
        chat={newConvoChat}
        models={newConvoModels}
        onModelSelect={(model) => {
          // Only update the local new conversation state, don't affect global model selection
          setNewConvoChat(prev => ({ ...prev, model }))
        }}
        onSendMessage={handleFirstMessage}
        onUpdateMessages={() => {}}
        onCancel={() => {}}
        canCancel={false}
        onExitImmersive={undefined}
        onParametersChange={(params) => {
          setNewConvoChat(prev => ({ ...prev, parameters: params }))
        }}
        onToolExecuted={() => {}}
        onAddChat={async () => {
          try {
            // Create a real conversation with two chats
            const newGroup = await createConversation([
              { id: generateUUID(), model: newConvoChat.model, messages: [], isLoading: false, parameters: { ...newConvoChat.parameters }, instructions: newConvoChat.instructions },
              { id: generateUUID(), model: null, messages: [], isLoading: false, parameters: { ...DEFAULT_PARAMETERS } }
            ])
            setActiveGroupId(newGroup.id)
            setIsImmersiveMode(true) // Stay in immersive mode
            saveImmersiveMode(newGroup.id, true)
            navigate({ to: '/chats', search: { conversation: newGroup.id }, replace: true })
          } catch (err) {
            console.error('[ModelComparisonPage] Failed to create conversation:', err)
            toast({
              title: 'Failed to create conversation',
              description: 'Please try again',
              variant: 'destructive'
            })
          }
        }}
        showFilters={showFilters}
        onToggleFilters={handleToggleFilters}
        hasActiveFilters={hasActiveFilters()}
        filters={filters}
        onFiltersChange={setFilters}
        providers={providers}
        recentModelIds={recentModelIds}
        webSearchState={tempWebSearchState}
        onToggleWebSearch={() => {
          setNewConvoChat(prev => ({
            ...prev,
            parameters: {
              ...prev.parameters,
              enable_brave_search: !prev.parameters?.enable_brave_search
            }
          }))
        }}
        hasWebSearchSupport={tempHasFunction}
        reasoningState={tempReasoningState}
        onToggleReasoning={() => {
          setNewConvoChat(prev => ({
            ...prev,
            parameters: { ...prev.parameters, enable_reasoning: !prev.parameters?.enable_reasoning }
          }))
        }}
        hasReasoningSupport={tempHasReasoning}
        mcpToolsState={tempMcpToolsState}
        onToggleMCPTools={() => {
          setNewConvoChat(prev => ({
            ...prev,
            parameters: { ...prev.parameters, enable_mcp_tools: !prev.parameters?.enable_mcp_tools }
          }))
        }}
        hasFunctionSupport={tempHasFunction}
        fileToolsState={tempFileToolsState}
        onToggleFileTools={() => {
          setNewConvoChat(prev => ({
            ...prev,
            parameters: { ...prev.parameters, enable_file_tools: !prev.parameters?.enable_file_tools }
          }))
        }}
        imageGenerationState={tempImageGenerationState}
        onToggleImageGeneration={() => {
          setNewConvoChat(prev => ({
            ...prev,
            parameters: { ...prev.parameters, enable_image_generation: !prev.parameters?.enable_image_generation }
          }))
        }}
        videoGenerationState={tempVideoGenerationState}
        onToggleVideoGeneration={() => {
          setNewConvoChat(prev => ({
            ...prev,
            parameters: { ...prev.parameters, enable_video_generation: !prev.parameters?.enable_video_generation }
          }))
        }}
        sparksState={tempSparksState}
        onToggleSparks={() => {
          setNewConvoChat(prev => ({
            ...prev,
            parameters: { ...prev.parameters, enable_sparks: !prev.parameters?.enable_sparks }
          }))
        }}
        knowledgeBaseState={tempKnowledgeBaseState}
        onToggleKnowledgeBase={() => {
          setNewConvoChat(prev => ({
            ...prev,
            parameters: { ...prev.parameters, enable_knowledge_base: !prev.parameters?.enable_knowledge_base }
          }))
        }}
        hasKnowledgeBaseSupport={tempHasFunction}
        activeServers={activeServersValue}
        estimatedCosts={estimatedCosts}
        onEstimateCost={handleEstimateCost}
        isEstimating={loadingEstimate}
        setEstimatedCost={setEstimatedCosts}
        attachments={newConvoAttachments}
        onAddAttachment={(att) => setNewConvoAttachments(prev => [...prev, att])}
        onRemoveAttachment={(id) => setNewConvoAttachments(prev => prev.filter(a => a.id !== id))}
        hasVisionSupport={newConvoChat.model?.input_modalities?.includes('image') || false}
        hasPDFSupport={newConvoChat.model?.input_modalities?.includes('file') || false}
        onFilterByCapability={handleFilterByCapability}
        activeFilters={filters.input_modalities}
        isDropOver={isDropOverInput}
        onDragOver={handleSharedDragOver}
        onDragLeave={handleSharedDragLeave}
        onDrop={handleSharedDrop}
        onPaste={handleSharedPaste}
        conversationId=""
        onSuggestionClick={handleSuggestionClick}
        onClearChat={() => {}}
        onCopyResponses={() => {}}
        onCopyMetadata={() => {}}
        onExportResponses={() => {}}
        onExportMetadata={() => {}}
        onUpdateChat={(data) => setNewConvoChat(prev => ({ ...prev, ...data }))}
      />
    )
  }

  // Show loading skeleton when activeGroupId is set but chats haven't loaded yet
  // This prevents briefly showing the comparison view during state transitions
  // Matches ImmersiveChatView structure with max-w-[52rem] centered content
  if (activeGroupId && chats.length === 0) {
    return (
      <div className="h-full flex flex-col bg-background relative">
        {/* Header skeleton - matches ImmersiveChatView header */}
        <div className="sticky top-0 z-10 flex items-center justify-between gap-2 px-3 py-2 border-b bg-background/95 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-8 rounded-lg" />
            <Skeleton className="hidden md:block h-5 w-32" />
          </div>
          <div className="flex items-center gap-1">
            <Skeleton className="h-8 w-8 rounded-md" />
            <Skeleton className="h-8 w-8 rounded-md" />
          </div>
        </div>

        {/* Messages area skeleton - centered with max-w-[52rem] like ImmersiveChatView */}
        <div className="flex-1 overflow-y-auto pb-44">
          <div className="max-w-[52rem] mx-auto px-6 py-8 space-y-6">
            {/* User message skeleton */}
            <div className="flex justify-end">
              <div className="max-w-[85%] md:max-w-[75%]">
                <div className="bg-primary/10 rounded-2xl rounded-tr-sm px-4 py-3 space-y-2">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-4 w-32" />
                </div>
              </div>
            </div>

            {/* Assistant message skeleton */}
            <div className="flex justify-start gap-3">
              <Skeleton className="h-8 w-8 rounded-full flex-shrink-0 mt-1" />
              <div className="max-w-[85%] md:max-w-[75%]">
                <div className="space-y-2">
                  <Skeleton className="h-4 w-64" />
                  <Skeleton className="h-4 w-56" />
                  <Skeleton className="h-4 w-40" />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Input area skeleton - floating at bottom like ImmersiveChatView */}
        <div className="absolute bottom-0 left-0 right-0 pointer-events-none">
          <div className="bg-background pb-3 md:pb-5 px-4 md:px-6 pointer-events-auto">
            <div className="max-w-[52rem] mx-auto">
              <div className="rounded-2xl bg-card/98 backdrop-blur-md border border-border/40 shadow-lg p-3">
                <div className="flex items-center gap-2">
                  <Skeleton className="h-10 flex-1 rounded-xl" />
                  <Skeleton className="h-10 w-10 rounded-xl" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
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
