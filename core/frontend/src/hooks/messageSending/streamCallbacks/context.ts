import type { Dispatch, MutableRefObject, SetStateAction } from 'react'
import type { Chat, Model } from '@/components/models/types'
import type { CodingAgentQuestion } from '@/api/llm'
import type { StreamAccumulator } from '../streamAccumulator'
import type { SetChatGroups, ToastFn } from '../types'

/** Shared context threaded through every stream-callback builder for one sendToModel call. */
export interface StreamCallbacksContext {
  acc: StreamAccumulator
  setChatGroups: SetChatGroups
  chats: Chat[]
  activeGroupId: string
  chatId: string
  model: Model
  messageId: string
  toast: ToastFn
  pendingCodingAgentQuestionRef: MutableRefObject<CodingAgentQuestion | null>
  setPendingQuestionVersion: Dispatch<SetStateAction<number>>
}
