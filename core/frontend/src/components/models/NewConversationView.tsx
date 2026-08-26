/**
 * Renders /chats?new=true: an ImmersiveChatView backed by a temporary,
 * unsaved chat. The real conversation is only created in the database once
 * the first message is sent (handleFirstMessage) or a second chat is added
 * (onAddChat) - until then every edit (model, parameters, attachments) just
 * updates the local newConvoChat/newConvoAttachments state the caller owns.
 *
 * newConvoChat/newConvoAttachments intentionally live in the parent
 * container, not here: navigating from ?new=true to ?conversation=<id> does
 * not unmount the container, so keeping this state one level up is what
 * lets a first message survive that transition instead of resetting.
 */
import { useNavigate } from '@tanstack/react-router'
import { generateUUID } from '@/lib/utils'
import { useToast } from '@/hooks/use-toast'
import { useConversations } from '@/hooks/useConversations'
import { useModelFilters } from '@/hooks/useModelFilters'
import { useCostEstimation } from '@/hooks/useCostEstimation'
import { ImmersiveChatView } from './ImmersiveChatView'
import { assetsAPI, assetToReference, getAssetTypeFromMime } from '@/api/assets'
import { preferencesSync } from '@/lib/preferencesSync'
import { PREFERENCE_KEYS } from '@/hooks/usePreferencesLoader'
import { toModelCatalogEntry } from './modelCatalog'
import { DEFAULT_PARAMETERS } from './constants'
import type { Dispatch, MutableRefObject, SetStateAction } from 'react'
import type { Attachment, AttachmentLike, Chat } from './types'
import type { ModelCatalogEntry } from '@/types/models'
import type { MCPServer } from '@/api/mcp'

type ModelFiltersState = ReturnType<typeof useModelFilters>
type CostEstimationState = ReturnType<typeof useCostEstimation>

interface PendingFirstMessage {
  content: string
  attachments: AttachmentLike[]
  chatId: string
}

interface NewConversationViewProps {
  newConvoChat: Chat
  setNewConvoChat: Dispatch<SetStateAction<Chat>>
  newConvoAttachments: Attachment[]
  setNewConvoAttachments: Dispatch<SetStateAction<Attachment[]>>
  createConversation: ReturnType<typeof useConversations>['createConversation']
  setActiveGroupId: (id: string) => void
  setIsImmersiveMode: (value: boolean) => void
  saveImmersiveMode: (conversationId: string, isImmersive: boolean) => void
  pendingFirstMessageRef: MutableRefObject<PendingFirstMessage | null>
  pendingMessageProcessedRef: MutableRefObject<boolean>
  models: ModelCatalogEntry[]
  filteredModels: ModelCatalogEntry[]
  showFilters: ModelFiltersState['showFilters']
  onToggleFilters: () => void
  hasActiveFilters: ModelFiltersState['hasActiveFilters']
  filters: ModelFiltersState['filters']
  setFilters: ModelFiltersState['setFilters']
  providers: ModelFiltersState['providers']
  recentModelIds: string[]
  activeServers: MCPServer[]
  estimatedCosts: CostEstimationState['estimatedCosts']
  onEstimateCost: (text: string) => Promise<void>
  loadingEstimate: CostEstimationState['loadingEstimate']
  setEstimatedCosts: CostEstimationState['setEstimatedCosts']
  onFilterByCapability: (modality: string) => void
  onSuggestionClick: (suggestion: string) => void
  isDropOverInput: boolean
  onDragOver: (e: React.DragEvent<HTMLDivElement>) => void
  onDragLeave: (e: React.DragEvent<HTMLDivElement>) => void
  onDrop: (e: React.DragEvent<HTMLDivElement>) => void | Promise<void>
  onPaste: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void | Promise<void>
}

export function NewConversationView({
  newConvoChat,
  setNewConvoChat,
  newConvoAttachments,
  setNewConvoAttachments,
  createConversation,
  setActiveGroupId,
  setIsImmersiveMode,
  saveImmersiveMode,
  pendingFirstMessageRef,
  pendingMessageProcessedRef,
  models,
  filteredModels,
  showFilters,
  onToggleFilters,
  hasActiveFilters,
  filters,
  setFilters,
  providers,
  recentModelIds,
  activeServers,
  estimatedCosts,
  onEstimateCost,
  loadingEstimate,
  setEstimatedCosts,
  onFilterByCapability,
  onSuggestionClick,
  isDropOverInput,
  onDragOver,
  onDragLeave,
  onDrop,
  onPaste,
}: NewConversationViewProps) {
  const navigate = useNavigate()
  const { toast } = useToast()

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
      onToggleFilters={onToggleFilters}
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
      activeServers={activeServers}
      estimatedCosts={estimatedCosts}
      onEstimateCost={onEstimateCost}
      isEstimating={loadingEstimate}
      setEstimatedCost={setEstimatedCosts}
      attachments={newConvoAttachments}
      onAddAttachment={(att) => setNewConvoAttachments(prev => [...prev, att])}
      onRemoveAttachment={(id) => setNewConvoAttachments(prev => prev.filter(a => a.id !== id))}
      hasVisionSupport={newConvoChat.model?.input_modalities?.includes('image') || false}
      hasPDFSupport={newConvoChat.model?.input_modalities?.includes('file') || false}
      onFilterByCapability={onFilterByCapability}
      activeFilters={filters.input_modalities}
      isDropOver={isDropOverInput}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onPaste={onPaste}
      conversationId=""
      onSuggestionClick={onSuggestionClick}
      onClearChat={() => {}}
      onCopyResponses={() => {}}
      onCopyMetadata={() => {}}
      onExportResponses={() => {}}
      onExportMetadata={() => {}}
      onUpdateChat={(data) => setNewConvoChat(prev => ({ ...prev, ...data }))}
    />
  )
}
