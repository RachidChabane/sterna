import { MessageSquare, Search } from 'lucide-react'
import type { CommandProvider, ConversationCommandItem, ActionCommandItem, CommandItem } from '../types'
import type { ChatGroup } from '@/components/models/types'
import { matchQuery, scoreMatch } from '../utils/search'
import { extractTextFromContent } from '@/utils/chatUtils'

const STORAGE_BASE_KEY = 'chat-groups'

/** Shape of a `ChatGroup` as persisted to localStorage, before date deserialization. */
type StoredChatGroup = Omit<ChatGroup, 'createdAt' | 'updatedAt'> & {
  createdAt: string
  updatedAt: string
}

function isStoredChatGroup(value: unknown): value is StoredChatGroup {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>
  return typeof record.createdAt === 'string' && typeof record.updatedAt === 'string'
}

function getCurrentUserId(): string | null {
  try {
    const auth = localStorage.getItem('auth-storage')
    if (!auth) return null
    const parsed = JSON.parse(auth)
    return parsed?.state?.user?.id || null
  } catch {
    return null
  }
}

function getStorageKey(): string {
  const uid = getCurrentUserId()
  return uid ? `${STORAGE_BASE_KEY}-${uid}` : STORAGE_BASE_KEY
}

/**
 * Load conversations from localStorage
 */
function loadConversations(): ChatGroup[] {
  try {
    const stored = localStorage.getItem(getStorageKey())
    if (!stored) return []

    const parsed: unknown = JSON.parse(stored)
    if (!Array.isArray(parsed)) return []

    // Deserialize dates
    return parsed.filter(isStoredChatGroup).map((group) => ({
      ...group,
      createdAt: new Date(group.createdAt),
      updatedAt: new Date(group.updatedAt),
    }))
  } catch (error) {
    console.error('[ConversationsProvider] Failed to load conversations:', error)
    return []
  }
}

/**
 * Format relative date
 */
function formatRelativeDate(date: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`
  return `${Math.floor(diffDays / 365)} years ago`
}

/**
 * Conversations Provider
 *
 * Provides search for model comparison conversations
 */
export class ConversationsProvider implements CommandProvider {
  id = 'conversations'
  name = 'Conversations'
  icon = MessageSquare
  priority = 1 // Show after pages

  getItems(query: string): CommandItem[] {
    const items: CommandItem[] = []

    // Load conversations from localStorage
    const conversations = loadConversations()

    // Filter by query
    const filtered = conversations.filter((conv) =>
      matchQuery(conv.name, query)
    )

    // Sort by match score, then by date
    const scored = filtered.map((conv) => ({
      conv,
      score: scoreMatch(conv.name, query),
    }))

    scored.sort((a, b) => {
      // First by score
      if (a.score !== b.score) return b.score - a.score
      // Then by date (newest first)
      return b.conv.updatedAt.getTime() - a.conv.updatedAt.getTime()
    })

    // Limit to 10 results for performance
    const limited = scored.slice(0, 10)

    // Convert to ConversationCommandItems
    const conversationItems: ConversationCommandItem[] = limited.map(({ conv }) => {
      // Get first user message as preview
      const firstUserMessage = conv.chats[0]?.messages.find(m => m.role === 'user')
      const preview = firstUserMessage
        ? extractTextFromContent(firstUserMessage.content).slice(0, 100)
        : ''

      return {
        id: conv.id,
        type: 'conversation' as const,
        title: conv.name,
        subtitle: formatRelativeDate(conv.updatedAt),
        icon: MessageSquare,
        conversationId: conv.id,
        preview,
        updatedAt: conv.updatedAt,
        onSelect: () => {
          // Navigation will be handled by the component
          // Store the selected conversation ID for the chats page to pick up
          sessionStorage.setItem('selected-conversation', conv.id)
        },
      }
    })

    items.push(...conversationItems)

    // Add "Find in chats" action when there's a query
    // This enables full-text search across all message content
    if (query.trim().length >= 2) {
      const searchAction: ActionCommandItem = {
        id: 'search-all-conversations',
        type: 'action',
        actionId: 'search-all-conversations',
        title: `Find "${query}" in all chats`,
        subtitle: 'Search all message content',
        icon: Search,
        onSelect: () => {
          // Store the query for the search page to use
          sessionStorage.setItem('search-query', query)
        },
      }
      items.push(searchAction)
    }

    return items
  }

  isEnabled(): boolean {
    // Always enabled to show the search action
    return true
  }
}
