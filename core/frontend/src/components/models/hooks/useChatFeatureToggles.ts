/**
 * Independent-mode feature toggle state for a single chat panel: web search,
 * reasoning, and MCP tools. Each toggle reports whether the current model
 * supports it and flips the corresponding parameter through the shared
 * onParametersChange callback.
 */
import { useCallback, useMemo } from 'react'
import { useMCPStore } from '@/store/mcpStore'
import type { Model, ModelParameters } from '../types'

interface UseChatFeatureTogglesParams {
  model: Model | null
  parameters?: ModelParameters
  onParametersChange?: (parameters: ModelParameters) => void
}

export function useChatFeatureToggles({ model, parameters, onParametersChange }: UseChatFeatureTogglesParams) {
  const getActiveServers = useMCPStore((state) => state.getActiveServers)

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
  const hasWebSearchSupportValue = model?.supports_functions === true

  const activeServersValue = useMemo(() => {
    try {
      return getActiveServers ? getActiveServers() : []
    } catch (e) {
      console.error('Error getting active servers:', e)
      return []
    }
  }, [getActiveServers])

  const toggleWebSearch = useCallback(() => {
    if (!onParametersChange || !parameters) return
    onParametersChange({
      ...parameters,
      enable_brave_search: !parameters.enable_brave_search,
    })
  }, [onParametersChange, parameters])

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

  return {
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
  }
}
