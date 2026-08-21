/**
 * useGlobalFeatureToggles Hook
 *
 * Manages global feature toggles (Web Search, Reasoning, MCP Tools, File Tools, etc.) for multiple chats
 * Eliminates duplication across feature toggle implementations
 */

import { useToast } from './use-toast'
import type { Chat } from '@/components/models/types'

interface FeatureToggleConfig {
  key: 'enable_reasoning' | 'enable_mcp_tools' | 'enable_brave_search' | 'enable_file_tools' | 'enable_image_generation' | 'enable_video_generation' | 'enable_sparks' | 'enable_knowledge_base'
  name: string
  supportCheck?: (chat: Chat) => boolean
}

interface UseGlobalFeatureTogglesProps {
  chats: Chat[]
  updateActiveGroup: (updater: (chats: Chat[]) => Chat[]) => void
  /** Optional callback to persist chat parameters to backend */
  persistChatParameters?: (chatId: string, parameters: Chat['parameters']) => void
}

export function useGlobalFeatureToggles({
  chats,
  updateActiveGroup,
  persistChatParameters,
}: UseGlobalFeatureTogglesProps) {
  const { toast } = useToast()

  /**
   * Get the state of a feature across all chats
   */
  const getFeatureState = (config: FeatureToggleConfig) => {
    const { key, supportCheck } = config

    // Count only compatible chats that have the feature enabled
    const compatibleEnabledCount = chats.filter(c =>
      (!supportCheck || supportCheck(c)) &&
      c.parameters?.[key] === true
    ).length

    const supportedCount = supportCheck
      ? chats.filter(c => supportCheck(c)).length
      : chats.length

    return {
      enabled: compatibleEnabledCount,
      total: chats.length,
      supported: supportedCount,
    }
  }

  /**
   * Toggle a feature for all compatible chats
   */
  const toggleFeature = (config: FeatureToggleConfig) => {
    const { key, name, supportCheck } = config
    const { enabled, supported } = getFeatureState(config)

    if (supported === 0) return // No compatible models

    const newValue = enabled < supported // If not all enabled, enable all. Otherwise, disable all.

    // Update local state
    updateActiveGroup(prevChats =>
      prevChats.map(chat => ({
        ...chat,
        parameters: {
          ...chat.parameters,
          [key]: newValue,
        },
      }))
    )

    // Persist to backend for each compatible chat
    if (persistChatParameters) {
      chats.forEach(chat => {
        // Only persist for compatible chats
        if (!supportCheck || supportCheck(chat)) {
          const updatedParameters = {
            ...chat.parameters,
            [key]: newValue,
          }
          persistChatParameters(chat.id, updatedParameters)
        }
      })
    }

    toast({
      title: newValue ? `${name} Enabled` : `${name} Disabled`,
      description: `${name} ${newValue ? 'enabled' : 'disabled'} for ${supported} compatible chat${supported > 1 ? 's' : ''}`,
    })
  }

  /**
   * Check if any chat supports a given feature
   */
  const hasFeatureSupport = (supportCheck?: (chat: Chat) => boolean) => {
    if (!supportCheck) return true
    return chats.some(chat => supportCheck(chat))
  }

  // Feature-specific helpers
  const webSearchConfig: FeatureToggleConfig = {
    key: 'enable_brave_search',
    name: 'Web Search',
    supportCheck: (chat) => chat.model?.supports_functions === true,
  }

  const reasoningConfig: FeatureToggleConfig = {
    key: 'enable_reasoning',
    name: 'Reasoning',
    supportCheck: (chat) => chat.model?.supports_reasoning === true,
  }

  const mcpToolsConfig: FeatureToggleConfig = {
    key: 'enable_mcp_tools',
    name: 'Connectors',
    supportCheck: (chat) => chat.model?.supports_functions === true,
  }

  const fileToolsConfig: FeatureToggleConfig = {
    key: 'enable_file_tools',
    name: 'File Tools',
    supportCheck: (chat) => chat.model?.supports_functions === true,
  }

  const imageGenerationConfig: FeatureToggleConfig = {
    key: 'enable_image_generation',
    name: 'Image Generation',
    supportCheck: (chat) => chat.model?.supports_functions === true,
  }

  const videoGenerationConfig: FeatureToggleConfig = {
    key: 'enable_video_generation',
    name: 'Video Generation',
    supportCheck: (chat) => chat.model?.supports_functions === true,
  }

  const sparksConfig: FeatureToggleConfig = {
    key: 'enable_sparks',
    name: 'Sparks',
    supportCheck: (chat) => chat.model?.supports_functions === true,
  }

  const knowledgeBaseConfig: FeatureToggleConfig = {
    key: 'enable_knowledge_base',
    name: 'Knowledge Base',
    supportCheck: (chat) => chat.model?.supports_functions === true,
  }

  /**
   * Toggle Web Search (Brave Search)
   */
  const toggleWebSearch = () => toggleFeature(webSearchConfig)

  return {
    // Web Search (Brave Search)
    getWebSearchState: () => getFeatureState(webSearchConfig),
    toggleWebSearch,
    hasWebSearchSupport: () => hasFeatureSupport(webSearchConfig.supportCheck),

    // Reasoning
    getReasoningState: () => getFeatureState(reasoningConfig),
    toggleReasoning: () => toggleFeature(reasoningConfig),
    hasReasoningSupport: () => hasFeatureSupport(reasoningConfig.supportCheck),

    // MCP Tools
    getMCPToolsState: () => getFeatureState(mcpToolsConfig),
    toggleMCPTools: () => toggleFeature(mcpToolsConfig),
    hasFunctionSupport: () => hasFeatureSupport(mcpToolsConfig.supportCheck),

    // File Tools
    getFileToolsState: () => getFeatureState(fileToolsConfig),
    toggleFileTools: () => toggleFeature(fileToolsConfig),

    // Image Generation
    getImageGenerationState: () => getFeatureState(imageGenerationConfig),
    toggleImageGeneration: () => toggleFeature(imageGenerationConfig),

    // Video Generation
    getVideoGenerationState: () => getFeatureState(videoGenerationConfig),
    toggleVideoGeneration: () => toggleFeature(videoGenerationConfig),

    // Sparks - Interactive React Components
    getSparksState: () => getFeatureState(sparksConfig),
    toggleSparks: () => toggleFeature(sparksConfig),
    hasSparksSupport: () => hasFeatureSupport(sparksConfig.supportCheck),

    // Knowledge Base - RAG with user documents
    getKnowledgeBaseState: () => getFeatureState(knowledgeBaseConfig),
    toggleKnowledgeBase: () => toggleFeature(knowledgeBaseConfig),
    hasKnowledgeBaseSupport: () => hasFeatureSupport(knowledgeBaseConfig.supportCheck),
  }
}
