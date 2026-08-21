/**
 * useMultiChatTabState Hook
 *
 * Manages tab state for multi-chat comparison view.
 * Handles:
 * - Active tab tracking (by ID, not index)
 * - Seen counts (local state only)
 * - Unread count calculation per tab
 * - Auto-switching when active chat is removed
 */

import { useState, useCallback, useEffect } from 'react'
import type { Chat } from '@/components/models/types'

interface UseMultiChatTabStateOptions {
  chats: Chat[]
  conversationId: string
}

interface UseMultiChatTabStateReturn {
  activeTabId: string
  setActiveTabId: (id: string) => void
  seenResponseCounts: Record<string, number>
  updateSeenCount: (chatId: string, count: number) => void
  getUnreadCount: (chatId: string) => number
}

export function useMultiChatTabState({
  chats,
  conversationId,
}: UseMultiChatTabStateOptions): UseMultiChatTabStateReturn {
  // Active tab tracked by ID (not index) for stability across reorders
  const [activeTabId, setActiveTabId] = useState<string>(() => chats[0]?.id ?? '')

  // Seen counts per chat - how many responses the user has "seen" for each chat
  // Kept in local state only (no backend persistence)
  const [seenResponseCounts, setSeenResponseCounts] = useState<Record<string, number>>({})

  // Reset seen counts when conversation changes
  useEffect(() => {
    setSeenResponseCounts({})
  }, [conversationId])

  // Handle active chat removal or initial load - switch to first available chat
  useEffect(() => {
    const chatIds = chats.map((c) => c.id)
    // If no active tab is set but we have chats, set to first chat
    if (!activeTabId && chats.length > 0) {
      setActiveTabId(chats[0].id)
    }
    // If active tab was removed, switch to first chat
    else if (activeTabId && !chatIds.includes(activeTabId)) {
      setActiveTabId(chats[0]?.id ?? '')
    }
  }, [chats, activeTabId])

  // Mark responses as seen when tab becomes active
  useEffect(() => {
    if (!activeTabId) return
    const activeChat = chats.find((c) => c.id === activeTabId)
    if (!activeChat) return

    const responseCount = activeChat.messages.filter((m) => m.role === 'assistant').length
    setSeenResponseCounts((prev) => {
      // Only update if the count actually changed
      if (prev[activeTabId] === responseCount) return prev
      return {
        ...prev,
        [activeTabId]: responseCount,
      }
    })
  }, [activeTabId, chats])

  // Update seen count for a specific chat
  const updateSeenCount = useCallback(
    (chatId: string, count: number) => {
      setSeenResponseCounts((prev) => ({
        ...prev,
        [chatId]: count,
      }))
    },
    []
  )

  // Get unread count for a specific chat
  const getUnreadCount = useCallback(
    (chatId: string): number => {
      const chat = chats.find((c) => c.id === chatId)
      if (!chat) return 0
      const responseCount = chat.messages.filter((m) => m.role === 'assistant').length
      const seenCount = seenResponseCounts[chatId] || 0
      return Math.max(0, responseCount - seenCount)
    },
    [chats, seenResponseCounts]
  )

  return {
    activeTabId,
    setActiveTabId,
    seenResponseCounts,
    updateSeenCount,
    getUnreadCount,
  }
}
