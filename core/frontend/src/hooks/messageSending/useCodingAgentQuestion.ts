import { useCallback, useRef, useState } from 'react'
import type { CodingAgentQuestion } from '@/api/llm'
import { codeSessionApi } from '@/api/codeSession'

export interface UseCodingAgentQuestionReturn {
  /**
   * Ref mutated by stream callbacks as an ask_user tool call arrives and
   * resolves. Exposed for useMessageStreamLifecycle to read/clear during a
   * live sendToModel call; consumers of this hook's public API should read
   * pendingCodingAgentQuestion instead.
   */
  pendingCodingAgentQuestionRef: React.MutableRefObject<CodingAgentQuestion | null>
  /** Bumped whenever the ref above changes, so pendingCodingAgentQuestion re-derives on render. */
  setPendingQuestionVersion: React.Dispatch<React.SetStateAction<number>>
  pendingCodingAgentQuestion: CodingAgentQuestion | null
  answerCodingAgentQuestion: (chatId: string, answer: string) => void
}

/**
 * Owns the coding agent's pending ask_user question (from the MCP ask_user
 * tool) and the round-trip to answer it. The question itself is written into
 * pendingCodingAgentQuestionRef by stream callbacks during a live sendToModel
 * call (see useMessageStreamLifecycle) — this hook owns the ref/version
 * bookkeeping and the answer call.
 */
export function useCodingAgentQuestion(): UseCodingAgentQuestionReturn {
  const pendingCodingAgentQuestionRef = useRef<CodingAgentQuestion | null>(null)
  const [pendingQuestionVersion, setPendingQuestionVersion] = useState(0)

  const answerCodingAgentQuestion = useCallback((chatId: string, answer: string) => {
    codeSessionApi.sendCodingAgentAnswer(chatId, answer).catch((err) => {
      console.error('[CodingAgent] Failed to send answer:', err)
    })
    pendingCodingAgentQuestionRef.current = null
    setPendingQuestionVersion(v => v + 1)
  }, [])

  // Derive pendingCodingAgentQuestion from ref + version counter for reactivity
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _questionVersion = pendingQuestionVersion  // subscribe to state changes
  const pendingCodingAgentQuestion = pendingCodingAgentQuestionRef.current

  return {
    pendingCodingAgentQuestionRef,
    setPendingQuestionVersion,
    pendingCodingAgentQuestion,
    answerCodingAgentQuestion,
  }
}
