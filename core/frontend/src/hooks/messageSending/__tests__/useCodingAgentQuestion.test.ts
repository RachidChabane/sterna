import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useCodingAgentQuestion } from '../useCodingAgentQuestion'
import { codeSessionApi } from '@/api/codeSession'

vi.mock('@/api/codeSession', () => ({
  codeSessionApi: {
    sendCodingAgentAnswer: vi.fn().mockResolvedValue({}),
  },
}))

describe('useCodingAgentQuestion', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('starts with no pending question', () => {
    const { result } = renderHook(() => useCodingAgentQuestion())
    expect(result.current.pendingCodingAgentQuestion).toBeNull()
  })

  it('reflects a question written directly into the ref once the version is bumped', () => {
    const { result } = renderHook(() => useCodingAgentQuestion())

    act(() => {
      result.current.pendingCodingAgentQuestionRef.current = { question: 'Proceed?' }
      result.current.setPendingQuestionVersion((v) => v + 1)
    })

    expect(result.current.pendingCodingAgentQuestion).toEqual({ question: 'Proceed?' })
  })

  it('answerCodingAgentQuestion sends the answer, clears the ref, and clears the derived state', async () => {
    const { result } = renderHook(() => useCodingAgentQuestion())

    act(() => {
      result.current.pendingCodingAgentQuestionRef.current = { question: 'Proceed?' }
      result.current.setPendingQuestionVersion((v) => v + 1)
    })
    expect(result.current.pendingCodingAgentQuestion).not.toBeNull()

    act(() => {
      result.current.answerCodingAgentQuestion('chat-1', 'yes')
    })

    expect(codeSessionApi.sendCodingAgentAnswer).toHaveBeenCalledWith('chat-1', 'yes')
    expect(result.current.pendingCodingAgentQuestionRef.current).toBeNull()
    expect(result.current.pendingCodingAgentQuestion).toBeNull()
  })

  it('logs but does not throw when sendCodingAgentAnswer rejects', async () => {
    vi.mocked(codeSessionApi.sendCodingAgentAnswer).mockRejectedValueOnce(new Error('network error'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { result } = renderHook(() => useCodingAgentQuestion())

    act(() => {
      result.current.answerCodingAgentQuestion('chat-1', 'no')
    })

    // Flush the rejected promise's microtask.
    await act(async () => {
      await Promise.resolve()
    })

    expect(errorSpy).toHaveBeenCalledWith('[CodingAgent] Failed to send answer:', expect.any(Error))
    errorSpy.mockRestore()
  })
})
