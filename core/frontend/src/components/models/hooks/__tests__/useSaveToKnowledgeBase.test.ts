import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

const saveToKnowledgeBase = vi.fn()
const toastSuccess = vi.fn()
const toastError = vi.fn()

vi.mock('@/api/conversations', () => ({
  conversationsAPI: {
    saveToKnowledgeBase: (...args: unknown[]) => saveToKnowledgeBase(...args),
  },
}))

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}))

import { useSaveToKnowledgeBase } from '../useSaveToKnowledgeBase'

describe('useSaveToKnowledgeBase', () => {
  beforeEach(() => {
    saveToKnowledgeBase.mockReset()
    toastSuccess.mockReset()
    toastError.mockReset()
  })

  it('opens the confirmation dialog without saving', () => {
    const { result } = renderHook(() => useSaveToKnowledgeBase('conv-1'))

    act(() => {
      result.current.handleSaveToKnowledgeBase()
    })

    expect(result.current.showSaveToKBDialog).toBe(true)
    expect(saveToKnowledgeBase).not.toHaveBeenCalled()
  })

  it('does nothing when there is no conversation id', () => {
    const { result } = renderHook(() => useSaveToKnowledgeBase(''))

    act(() => {
      result.current.handleSaveToKnowledgeBase()
    })

    expect(result.current.showSaveToKBDialog).toBe(false)
  })

  it('saves successfully, toasts, and closes the dialog', async () => {
    saveToKnowledgeBase.mockResolvedValue({ filename: 'conv-1.md' })
    const { result } = renderHook(() => useSaveToKnowledgeBase('conv-1'))

    act(() => {
      result.current.setShowSaveToKBDialog(true)
    })

    await act(async () => {
      await result.current.confirmSaveToKnowledgeBase()
    })

    expect(saveToKnowledgeBase).toHaveBeenCalledWith('conv-1')
    expect(toastSuccess).toHaveBeenCalledWith('Saved to knowledge base', { description: 'conv-1.md' })
    expect(result.current.showSaveToKBDialog).toBe(false)
    expect(result.current.isSavingToKnowledgeBase).toBe(false)
  })

  it('surfaces the already-saved case as a distinct toast and keeps the dialog open', async () => {
    saveToKnowledgeBase.mockRejectedValue({
      response: { data: { existing_document_id: 'doc-1', error: 'Already in your knowledge base' } },
    })
    const { result } = renderHook(() => useSaveToKnowledgeBase('conv-1'))

    await act(async () => {
      await result.current.confirmSaveToKnowledgeBase()
    })

    expect(toastError).toHaveBeenCalledWith('Already saved', { description: 'Already in your knowledge base' })
    expect(result.current.isSavingToKnowledgeBase).toBe(false)
  })

  it('ignores a second concurrent save attempt while one is in flight', async () => {
    let resolveSave: (value: { filename: string }) => void = () => {}
    saveToKnowledgeBase.mockReturnValue(new Promise((resolve) => { resolveSave = resolve }))
    const { result } = renderHook(() => useSaveToKnowledgeBase('conv-1'))

    let firstCall: Promise<void>
    act(() => {
      firstCall = result.current.confirmSaveToKnowledgeBase()
    })

    await waitFor(() => expect(result.current.isSavingToKnowledgeBase).toBe(true))

    await act(async () => {
      await result.current.confirmSaveToKnowledgeBase()
    })

    expect(saveToKnowledgeBase).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveSave({ filename: 'conv-1.md' })
      await firstCall
    })
  })
})
