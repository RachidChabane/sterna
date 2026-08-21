/**
 * useChatCosts Hook
 *
 * Calculates and manages chat-level cost metrics:
 * - Total cost across all assistant messages
 * - Total prompt cost
 * - Total completion cost
 * - Total tokens used
 * - Individual cost formatting utilities
 */

import { useMemo } from 'react'
import { pricingUtils } from '@/lib/pricing-utils'
import { formatLatencyFromSeconds } from '@/utils/latency'
import type { Message } from '@/components/models/types'

interface UseChatCostsProps {
  messages: Message[]
}

interface ChatCosts {
  totalCost: number
  totalPromptCost: number
  totalCompletionCost: number
  totalTokens: number
  formatCost: (cost?: number) => string
  formatLatency: (latency?: number) => string
}

export function useChatCosts({ messages }: UseChatCostsProps): ChatCosts {
  // Calculate costs from assistant messages
  const costs = useMemo(() => {
    const assistantMessages = messages.filter(m => m.role === 'assistant')

    const totalPromptCost = assistantMessages.reduce(
      (sum, m) => sum + (m.prompt_cost || 0), 0
    )

    const totalCompletionCost = assistantMessages.reduce(
      (sum, m) => sum + (m.completion_cost || 0), 0
    )

    const totalCost = assistantMessages.reduce(
      (sum, m) => sum + (m.cost || 0), 0
    )

    const totalTokens = assistantMessages.reduce(
      (sum, m) => sum + (m.tokens?.prompt || 0) + (m.tokens?.completion || 0), 0
    )

    return {
      totalCost,
      totalPromptCost,
      totalCompletionCost,
      totalTokens,
    }
  }, [messages])

  // Cost formatting utility
  const formatCost = (cost?: number) => {
    return pricingUtils.formatCost(cost)
  }

  // Latency formatting utility (latency comes in seconds from backend)
  const formatLatency = (latency?: number) => formatLatencyFromSeconds(latency, 'N/A')

  return {
    ...costs,
    formatCost,
    formatLatency,
  }
}
