import { useCallback } from 'react'
import type { Chat, ChatGroup, FileAttachment, ImageAttachment, Model, Message, Attachment, AttachmentLike, MessageAttachment } from '@/components/models/types'
import { isPDFFile, isOfficeFile } from '@/utils/fileUtils'
import { conversationsAPI } from '@/api/conversations'
import { type AssetReference } from '@/api/assets'
import type { ModelCatalogEntry } from '@/types/models'
import type { SetChatGroups, ToastFn } from './types'
import { buildUnsupportedAttachmentsMessage, uploadAttachmentsAsAssets } from './attachmentAssets'
import type { SendToModelOptions } from './requestPayload'
import { useConversationTitleGeneration } from './useConversationTitleGeneration'

export interface UseMessageCompositionProps {
  chats: Chat[]
  activeGroupId: string
  chatGroups: ChatGroup[]
  setChatGroups: SetChatGroups
  attachments: Attachment[]
  setAttachments: React.Dispatch<React.SetStateAction<Attachment[]>>
  toast: ToastFn
  isAuthenticated: boolean
  openModal: (variant: string, returnPath: string) => void
  getAuthModalVariant: () => string
  sendToModel: (chatId: string, model: Model, messages: Message[], options?: SendToModelOptions) => Promise<void>
  addRecentChatModel: (modelId: string, model: ModelCatalogEntry) => void
}

export interface UseMessageCompositionReturn {
  composeAndSend: (targetChatIds: string[], content: string, localAttachments: AttachmentLike[], isToolContinuation?: boolean) => Promise<void>
  sendMessage: (content: string) => void
}

/**
 * Composes a user message (text + attachments) into every target chat,
 * persists it, dispatches it to each chat's model, and — for the first
 * message of a conversation — kicks off title generation.
 */
export function useMessageComposition({
  chats,
  activeGroupId,
  chatGroups,
  setChatGroups,
  attachments,
  setAttachments,
  toast,
  isAuthenticated,
  openModal,
  getAuthModalVariant,
  sendToModel,
  addRecentChatModel,
}: UseMessageCompositionProps): UseMessageCompositionReturn {
  // Generate a conversation title based on the first user message (async, non-blocking)
  const generateConversationTitle = useConversationTitleGeneration({ activeGroupId, setChatGroups })

  const composeAndSend = useCallback(async (
    targetChatIds: string[],
    content: string,
    localAttachments: AttachmentLike[],
    isToolContinuation: boolean = false  // Flag to bypass empty content check
  ) => {


    // Auth check
    if (!isAuthenticated) {
      toast({ title: 'Authentication required', description: 'Please sign in to send messages', variant: 'destructive' })
      const variant = getAuthModalVariant()
      openModal(variant, window.location.pathname)
      return
    }

    // Allow empty messages if continuing after tool execution
    if (!isToolContinuation && !content.trim() && localAttachments.length === 0) {

      return
    }

    // Track asset references for persistence (populated after upload)
    let assetRefs: AssetReference[] = []

    // Start asset upload in parallel (will await before persistence)
    // Assets are stored per-chat, so use the first target chat ID
    const primaryChatId = targetChatIds[0]
    const assetUploadPromise = localAttachments.length > 0 && !isToolContinuation && primaryChatId
      ? uploadAttachmentsAsAssets(primaryChatId, localAttachments)
      : Promise.resolve({ enriched: localAttachments, assetRefs: [] })

    const imageAttachments = localAttachments.filter((a): a is ImageAttachment => a.type === 'image')
    const fileAttachments = localAttachments.filter((a): a is FileAttachment => a.type === 'file')
    const pdfAttachments = fileAttachments.filter(f => f.base64 && !f.textContent && f.file && isPDFFile(f.file))
    const officeAttachments = fileAttachments.filter(f => f.base64 && !f.textContent && f.file && isOfficeFile(f.file))
    const hasImages = imageAttachments.length > 0
    const hasPDFs = pdfAttachments.length > 0
    const hasOfficeFiles = officeAttachments.length > 0
    const hasText = content.trim().length > 0
    const timestamp = new Date()

    let updatedChats: Chat[] = []

    setChatGroups(prevGroups =>
      prevGroups.map((group: ChatGroup) => {
        if (group.id !== activeGroupId) return group

        const updatedGroupChats = group.chats.map((chat: Chat) => {
          if (!targetChatIds.includes(chat.id)) return chat
          if (chat.disabled || chat.model === null) return chat

          const supportsVision = chat.model.input_modalities?.includes('image')
          const supportsFiles = chat.model.input_modalities?.includes('file')
          const messages = [...chat.messages]

          // Add user message only if not a tool continuation
          // (tool continuations just send existing messages including the tool result)
          if (!isToolContinuation) {
            const userMessage: Message = {
              role: 'user',
              content: content,
              timestamp,
              // Reconstructed (post-redirect) attachments never carry a real File; a freshly-composed one always does.
              attachments: localAttachments.length > 0 ? localAttachments as MessageAttachment[] : undefined,
            }
            messages.push(userMessage)
          }

          // Unsupported attachments notice
          const unsupportedMessage = buildUnsupportedAttachmentsMessage(
            hasImages,
            hasPDFs,
            hasOfficeFiles,
            hasText,
            supportsVision,
            supportsFiles
          )

          if (unsupportedMessage) {
            messages.push({
              role: 'assistant',
              content: unsupportedMessage,
              timestamp: new Date(),
              model: chat.model.name,
              model_id: chat.model.model_id,
              provider: chat.model.provider,
              provider_icon_slug: chat.model.provider_icon_slug,
              provider_icon_url: chat.model.provider_icon_url,
              model_icon_slug: chat.model.model_icon_slug,
              model_icon_url: chat.model.model_icon_url,
              isUnsupported: true,
            })
          }

          return { ...chat, messages }
        })

        updatedChats = updatedGroupChats
        return { ...group, chats: updatedGroupChats, updatedAt: new Date() }
      })
    )

    // Persist user messages to the database
    // Wait for asset upload to complete first so we can include asset references


    if (!isToolContinuation && (content.trim() || localAttachments.length > 0)) {
      // Wait for asset upload to complete
      const { assetRefs: uploadedAssetRefs } = await assetUploadPromise.catch(err => {
        console.error('[composeAndSend] Asset upload failed, persisting without asset refs:', err)
        return { enriched: localAttachments, assetRefs: [] as AssetReference[] }
      })
      assetRefs = uploadedAssetRefs

      // Build message content with asset references if we have any
      let messageContent: string | Array<{ type: 'text'; text: string } | AssetReference> = content
      if (assetRefs.length > 0) {
        // Store as multipart content: text + asset references
        const parts: Array<{ type: 'text'; text: string } | AssetReference> = []
        if (content.trim()) {
          parts.push({ type: 'text', text: content })
        }
        // Add asset references
        for (const ref of assetRefs) {
          parts.push(ref)
        }
        messageContent = parts.length === 1 && parts[0].type === 'text' ? content : parts
      }

      const persistPromises = targetChatIds.map(async (chatId) => {
        try {
          await conversationsAPI.createMessage(activeGroupId, chatId, {
            role: 'user',
            content: messageContent,
          })

        } catch (error) {
          console.error(`[composeAndSend] ❌ Failed to persist user message to chat ${chatId}:`, error)
        }
      })
      // Don't await - persist in background
      Promise.all(persistPromises).catch(console.error)
    }

    // Check if this is the first message in the conversation (for title generation)
    // Only generate title if:
    // 1. Not a tool continuation
    // 2. No existing user messages in any chat before this one
    // 3. Conversation doesn't have a custom name
    const activeGroup = chatGroups.find((g: ChatGroup) => g.id === activeGroupId)
    const isFirstMessage = !isToolContinuation &&
      activeGroup &&
      !activeGroup.isCustomName &&
      !activeGroup.chats.some((c) => c.messages.some((m) => m.role === 'user'))

    // Send to targets in parallel using updated state
    const enabledChats = updatedChats.filter(c => targetChatIds.includes(c.id) && c.model !== null && !c.disabled)

    // Track each model as recently used (for "Recent Chat Models" section in dropdown)
    enabledChats.forEach(c => {
      if (c.model) {
        // Model and ModelCatalogEntry are independently-typed views of the same backend record.
        addRecentChatModel(c.model.model_id, c.model as ModelCatalogEntry)
      }
    })

    const promises = enabledChats.map(c => sendToModel(c.id, c.model!, c.messages))
    await Promise.all(promises)

    // Generate title after first message is sent (async, non-blocking)
    // Also generate title for attachment-only messages using filenames
    if (isFirstMessage && enabledChats.length > 0) {
      const firstModel = enabledChats[0].model
      if (firstModel) {
        // Use text content if available, otherwise describe attachments
        let titleInput = content.trim()
        if (!titleInput && localAttachments.length > 0) {
          const fileNames = localAttachments.map(a => a.file?.name || 'file').join(', ')
          titleInput = `Attached files: ${fileNames}`
        }
        if (titleInput) {
          // Run title generation asynchronously without blocking
          generateConversationTitle(titleInput, firstModel)
        }
      }
    }
  }, [chats, chatGroups, activeGroupId, setChatGroups, toast, isAuthenticated, openModal, getAuthModalVariant, sendToModel, generateConversationTitle, addRecentChatModel])

  // Shared input entry point (synced): just call composeAndSend for all enabled chats
  const sendMessage = useCallback((content: string) => {
    const enabledIds = chats.filter(c => c.model !== null && !c.disabled).map(c => c.id)
    if (enabledIds.length === 0) return

    // Take a snapshot of current attachments with enriched metadata for serialization survival
    const currentAttachments = attachments.map(att => ({
      ...att,
      // Extract File metadata at root level so they survive JSON serialization
      fileName: att.file.name,
      fileType: att.file.type,
      fileSize: att.file.size,
    }))

    composeAndSend(enabledIds, content, currentAttachments)

    // Clear attachments after sending
    setAttachments([])
  }, [chats, attachments, setAttachments, composeAndSend])

  return { composeAndSend, sendMessage }
}
