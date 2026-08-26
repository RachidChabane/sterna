import type { Dispatch, SetStateAction } from 'react'
import type { toast } from '@/hooks/use-toast'
import type { ChatGroup, MessageContent, ToolCall } from '@/components/models/types'

/** API message shape sent to the backend; includes the `system` role which never appears in UI state. */
export type ApiMessage = {
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: MessageContent
  tool_call_id?: string
}

/** setChatGroups' React state updater. */
export type SetChatGroups = Dispatch<SetStateAction<ChatGroup[]>>

/** A toast() call's options, matching the toast() helper's own parameter. */
export type ToastFn = (options: Parameters<typeof toast>[0]) => void

/** A tool call as requested by the model mid-stream, matching Message['tool_calls']. */
export type ToolCallRequest = ToolCall
