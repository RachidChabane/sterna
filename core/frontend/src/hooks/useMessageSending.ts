/**
 * useMessageSending Hook
 *
 * Composes the message-sending subsystem from its per-concern hooks:
 * - useCodingAgentQuestion: pending ask_user tool question + answer round-trip
 * - useMessageStreamLifecycle: send-to-model streaming, accumulation, persistence
 * - useMessageComposition: compose a message (text + attachments) and dispatch it
 * - useSparkMessaging: spark fix/ignite message flows
 */

import type { Chat, ChatGroup, Attachment } from '@/components/models/types'
import type { CodingAgentQuestion } from '@/api/llm'
import { useUsageQuotaStore } from '@/store/usageQuotaStore'
import { useSettingsStore } from '@/store/settingsStore'
import useModelStore from '@/store/modelStore'
import type { SetChatGroups, ToastFn } from './messageSending/types'
import { useCodingAgentQuestion } from './messageSending/useCodingAgentQuestion'
import { useMessageStreamLifecycle } from './messageSending/useMessageStreamLifecycle'
import { useMessageComposition } from './messageSending/useMessageComposition'
import { useSparkMessaging } from './messageSending/useSparkMessaging'

interface UseMessageSendingProps {
  chats: Chat[]
  activeGroupId: string
  chatGroups: ChatGroup[]
  setChatGroups: SetChatGroups
  attachments: Attachment[]
  setAttachments: React.Dispatch<React.SetStateAction<Attachment[]>>
  toast: ToastFn
  isAuthenticated: boolean
  openModal: (variant: string, returnPath: string) => void
  getAuthModalVariant: () => string
}

interface UseMessageSendingReturn {
  sendToModel: ReturnType<typeof useMessageStreamLifecycle>['sendToModel']
  composeAndSend: ReturnType<typeof useMessageComposition>['composeAndSend']
  sendMessage: ReturnType<typeof useMessageComposition>['sendMessage']
  sendSparkFixMessage: ReturnType<typeof useSparkMessaging>['sendSparkFixMessage']
  sendIgniteMessage: ReturnType<typeof useSparkMessaging>['sendIgniteMessage']
  abortControllersRef: ReturnType<typeof useMessageStreamLifecycle>['abortControllersRef']
  pendingCodingAgentQuestion: CodingAgentQuestion | null
  answerCodingAgentQuestion: (chatId: string, answer: string) => void
}

export function useMessageSending({
  chats,
  activeGroupId,
  chatGroups,
  setChatGroups,
  attachments,
  setAttachments,
  toast,
  isAuthenticated,
  openModal,
  getAuthModalVariant,
}: UseMessageSendingProps): UseMessageSendingReturn {
  // Get streaming preference from settings (used as fallback if not specified in parameters)
  const streamResponsesSetting = useSettingsStore((state) => state.chat.streamResponses)

  // Get voice conversation mode from settings (adjusts system prompt for voice output)
  const voiceConversationActive = useSettingsStore((state) => state.voiceConversationActive)

  // Get addRecentChatModel to track model usage when messages are sent
  const addRecentChatModel = useModelStore((state) => state.addRecentChatModel)

  // Get quota refresh function to update usage display after message sends
  const refreshQuotaAfterUsage = useUsageQuotaStore((state) => state.refreshAfterUsage)

  const {
    pendingCodingAgentQuestionRef,
    setPendingQuestionVersion,
    pendingCodingAgentQuestion,
    answerCodingAgentQuestion,
  } = useCodingAgentQuestion()

  const { sendToModel, abortControllersRef } = useMessageStreamLifecycle({
    chats,
    activeGroupId,
    setChatGroups,
    toast,
    streamResponsesSetting,
    voiceConversationActive,
    refreshQuotaAfterUsage,
    pendingCodingAgentQuestionRef,
    setPendingQuestionVersion,
  })

  const { composeAndSend, sendMessage } = useMessageComposition({
    chats,
    activeGroupId,
    chatGroups,
    setChatGroups,
    attachments,
    setAttachments,
    toast,
    isAuthenticated,
    openModal,
    getAuthModalVariant,
    sendToModel,
    addRecentChatModel,
  })

  const { sendSparkFixMessage, sendIgniteMessage } = useSparkMessaging({
    chats,
    activeGroupId,
    setChatGroups,
    sendToModel,
  })

  return {
    sendToModel,
    composeAndSend,
    sendMessage,
    sendSparkFixMessage,
    sendIgniteMessage,
    abortControllersRef,
    pendingCodingAgentQuestion,
    answerCodingAgentQuestion,
  }
}
