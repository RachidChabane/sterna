import type { Dispatch, SetStateAction } from 'react'
import type { Message } from '@/components/models/types'

/** API message shape sent to the backend; includes the `system` role which never appears in UI state. */
export type ApiMessage = {
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: any
  tool_call_id?: string
}

/**
 * setChatGroups' React state updater. Chat groups themselves stay loosely typed
 * (`any[]`) across this hook, same as the rest of the models components — named
 * here once so that isn't a separately-declared `any` at every call site.
 */
export type SetChatGroups = Dispatch<SetStateAction<any[]>>

/** A toast() call's options — the toast hook itself does not export a narrower type. */
export type ToastFn = (options: any) => void

/** A tool call as requested by the model mid-stream, matching Message['tool_calls']. */
export type ToolCallRequest = NonNullable<Message['tool_calls']>[number]
