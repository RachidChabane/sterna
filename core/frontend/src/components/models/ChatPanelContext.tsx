/**
 * ChatPanelContext
 *
 * Provides shared state and utilities to all ChatPanel child components
 * to reduce prop drilling and improve maintainability.
 */

import { createContext, useContext, type ReactNode } from 'react'
import type { Model, Message, Attachment, FileAttachment } from './types'
import type { CachedAttachment } from '@/utils/attachmentCache'
import type { User } from '@/api/types'

interface ChatPanelContextValue {
  // Models and messages
  model: Model | null
  messages: Message[]
  isLoading: boolean
  isGenerating: boolean
  user: User | null

  // Chat context for sandbox isolation
  conversationId?: string
  chatId?: string
  syncMode?: boolean

  // State
  messagesContainer: HTMLDivElement | null
  cachedAttachments: Record<string, CachedAttachment>
  disabledChat?: boolean

  // Abort controllers for stream cancellation
  abortControllersRef?: React.MutableRefObject<Map<string, AbortController>>

  // Message actions
  onUpdateMessages?: (messages: Message[]) => void
  onToolExecuted?: (toolCallId: string, toolName: string, result: any) => void
  onRetry: (assistantMessageIndex: number) => void
  onEditMessage: (messageIndex: number, newContent: string) => void

  // Copy/export actions
  onCopyContent: (content: Message['content']) => void
  onCopyMetadata: (message: Message) => void
  onExportContent: (content: Message['content'], model?: string) => void
  onExportMetadata: (message: Message) => void

  // Modal actions
  onOpenModelDetails: (modelId?: string) => void
  onOpenImageGallery: (images: { src: string; alt: string }[], selectedIndex: number, fromAttachments: boolean) => void
  onOpenPdf: (src: string, name: string) => void
  onOpenTextFile: (file: FileAttachment) => void
  onOpenAllAttachments: (attachments: Attachment[]) => void

  // Formatting utilities
  formatCost: (cost?: number) => string
  formatLatency: (latency?: number) => string

  // Text reveal state (typewriter effect continues after API streaming ends)
  onTextRevealChange?: (isRevealing: boolean) => void
  stopRevealRef?: { current: boolean }

  // TTS (Text-to-Speech) actions
  onSpeak?: (content: string) => void
  onStopSpeaking?: () => void
  isSpeaking?: boolean
  isTTSLoading?: boolean
  isTTSSupported?: boolean
}

const ChatPanelContext = createContext<ChatPanelContextValue | undefined>(undefined)

export function useChatPanelContext() {
  const context = useContext(ChatPanelContext)
  if (!context) {
    throw new Error('useChatPanelContext must be used within ChatPanelProvider')
  }
  return context
}

/**
 * Safe version of useChatPanelContext that returns undefined instead of throwing
 * when used outside of ChatPanelProvider. Useful for components that may be
 * rendered in contexts where the provider is not available.
 */
export function useChatPanelContextSafe() {
  return useContext(ChatPanelContext)
}

interface ChatPanelProviderProps {
  value: ChatPanelContextValue
  children: ReactNode
}

export function ChatPanelProvider({ value, children }: ChatPanelProviderProps) {
  return (
    <ChatPanelContext.Provider value={value}>
      {children}
    </ChatPanelContext.Provider>
  )
}
