/**
 * useCostEstimation Hook
 *
 * Manages cost estimation for ModelComparisonPage:
 * - Estimates costs for multiple models
 * - Handles loading states
 * - Formats cost data
 */

import { useState, useCallback } from 'react'
import { llmApi, normalizeCostEstimate, type NormalizedCostEstimate } from '@/api/llm'
import { buildTextFromTextAttachments } from '@/utils/tokenEstimate'
import type { Attachment } from '@/components/models/types'

interface UseCostEstimationReturn {
  estimatedCosts: NormalizedCostEstimate | null
  setEstimatedCosts: (costs: NormalizedCostEstimate | null) => void
  loadingEstimate: boolean
  estimateCosts: (modelIds: string[], typedText: string, attachments: Attachment[]) => Promise<void>
  clearEstimate: () => void
}

export function useCostEstimation(): UseCostEstimationReturn {
  const [estimatedCosts, setEstimatedCosts] = useState<NormalizedCostEstimate | null>(null)
  const [loadingEstimate, setLoadingEstimate] = useState(false)

  const estimateCosts = useCallback(async (
    modelIds: string[],
    typedText: string,
    attachments: Attachment[]
  ) => {
    if (modelIds.length === 0 || !typedText.trim()) {
      setEstimatedCosts(null)
      return
    }

    setLoadingEstimate(true)
    try {
      // Build text from attachments (text files only - backend handles images/PDFs)
      const attachmentText = buildTextFromTextAttachments(attachments)
      const fullText = attachmentText ? `${typedText}\n\n${attachmentText}` : typedText

      // Call backend to estimate costs
      // (llmApi.estimate never existed - the real endpoint is /llm/completions/estimate-batch-cost/)
      const response = await llmApi.estimateBatchCost({
        model_ids: modelIds,
        prompt_text: fullText,
        typed_text: typedText,
        files_text: attachmentText || undefined,
      })

      setEstimatedCosts(normalizeCostEstimate(response.data))
    } catch (error) {
      console.error('Failed to estimate costs:', error)
      setEstimatedCosts(null)
    } finally {
      setLoadingEstimate(false)
    }
  }, [])

  const clearEstimate = useCallback(() => {
    setEstimatedCosts(null)
  }, [])

  return {
    estimatedCosts,
    setEstimatedCosts,
    loadingEstimate,
    estimateCosts,
    clearEstimate,
  }
}
