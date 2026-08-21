/**
 * useComparisonHelpers Hook
 *
 * Provides helper functions for ModelComparisonPage:
 * - Group name generation
 * - Message existence checks
 * - Capability checks (vision, PDF support)
 * - Token counting
 */

import { useMemo, useCallback } from 'react'
import type { Chat } from '@/components/models/types'

interface UseComparisonHelpersProps {
  chats: Chat[]
}

interface UseComparisonHelpersReturn {
  generateFullGroupName: (chatsToName: Chat[]) => string
  generateGroupName: (chatsToName: Chat[]) => string
  hasMessages: (chatsToCheck: Chat[]) => boolean
  hasVisionSupport: (chatsToCheck: Chat[]) => boolean
  hasPDFSupport: (chatsToCheck: Chat[]) => boolean
  getTotalTokens: () => number
}

export function useComparisonHelpers({ chats }: UseComparisonHelpersProps): UseComparisonHelpersReturn {
  // Generate full group name (no longer auto-generates from model names)
  const generateFullGroupName = useCallback((chatsToName: Chat[]): string => {
    return 'New Conversation'
  }, [])

  // Generate group name (no longer auto-generates from model names)
  const generateGroupName = useCallback((chatsToName: Chat[]): string => {
    return 'New Conversation'
  }, [])

  // Check if conversation has any messages
  const hasMessages = useCallback((chatsToCheck: Chat[]): boolean => {
    return chatsToCheck.some(chat => chat.messages.length > 0)
  }, [])

  // Check if any selected model supports vision
  const hasVisionSupport = useCallback((chatsToCheck: Chat[]): boolean => {
    return chatsToCheck.some(chat =>
      chat.model?.input_modalities?.includes('image') || false
    )
  }, [])

  // Check if any selected model supports PDFs
  const hasPDFSupport = useCallback((chatsToCheck: Chat[]): boolean => {
    return chatsToCheck.some(chat =>
      chat.model?.input_modalities?.includes('file') || false
    )
  }, [])

  // Calculate total tokens in current conversation
  const getTotalTokens = useCallback((): number => {
    return chats.reduce((total, chat) => {
      const chatTokens = chat.messages
        .filter(m => m.role === 'assistant')
        .reduce((sum, m) => {
          const prompt = m.tokens?.prompt || 0
          const completion = m.tokens?.completion || 0
          return sum + prompt + completion
        }, 0)
      return total + chatTokens
    }, 0)
  }, [chats])

  return {
    generateFullGroupName,
    generateGroupName,
    hasMessages,
    hasVisionSupport,
    hasPDFSupport,
    getTotalTokens,
  }
}
