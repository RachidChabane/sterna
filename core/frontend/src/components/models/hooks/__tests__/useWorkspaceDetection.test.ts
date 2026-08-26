import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const getWorkspaceInfo = vi.fn()

vi.mock('@/api/fs', () => ({
  fsAPI: {
    getWorkspaceInfo: (...args: unknown[]) => getWorkspaceInfo(...args),
  },
}))

import { useWorkspaceDetection } from '../useWorkspaceDetection'
import type { Message } from '../../types'

function makeMessages(roles: Message['role'][]): Message[] {
  return roles.map((role, i) => ({
    role,
    content: 'x',
    timestamp: new Date(),
    message_id: `msg-${i}`,
  }))
}

describe('useWorkspaceDetection', () => {
  beforeEach(() => {
    getWorkspaceInfo.mockReset()
  })

  it('reports a workspace immediately when a repo is cloned, without probing fsAPI', () => {
    const { result } = renderHook(() =>
      useWorkspaceDetection({
        messages: [],
        clonedRepo: { id: 'repo-1' } as never,
        userId: 'user-1',
        chatId: 'chat-1',
      })
    )

    expect(result.current).toBe(true)
    expect(getWorkspaceInfo).not.toHaveBeenCalled()
  })

  it('does not probe when userId or chatId is missing', () => {
    const { result } = renderHook(() =>
      useWorkspaceDetection({
        messages: [],
        clonedRepo: null,
        userId: undefined,
        chatId: 'chat-1',
      })
    )

    expect(result.current).toBe(false)
    expect(getWorkspaceInfo).not.toHaveBeenCalled()
  })

  it('probes fsAPI and reports true when files exist', async () => {
    getWorkspaceInfo.mockResolvedValue({ exists: true, file_count: 3 })

    const { result } = renderHook(() =>
      useWorkspaceDetection({
        messages: [],
        clonedRepo: null,
        userId: 'user-1',
        chatId: 'chat-1',
      })
    )

    await waitFor(() => expect(result.current).toBe(true))
    expect(getWorkspaceInfo).toHaveBeenCalledWith({ user_id: 'user-1', chat_id: 'chat-1' })
  })

  it('reports false when the workspace exists but has no files', async () => {
    getWorkspaceInfo.mockResolvedValue({ exists: true, file_count: 0 })

    const { result } = renderHook(() =>
      useWorkspaceDetection({
        messages: [],
        clonedRepo: null,
        userId: 'user-1',
        chatId: 'chat-1',
      })
    )

    await waitFor(() => expect(getWorkspaceInfo).toHaveBeenCalled())
    expect(result.current).toBe(false)
  })

  it('re-probes when the tool message count changes', async () => {
    getWorkspaceInfo.mockResolvedValue({ exists: false, file_count: 0 })

    const { rerender } = renderHook(
      ({ messages }: { messages: Message[] }) =>
        useWorkspaceDetection({ messages, clonedRepo: null, userId: 'user-1', chatId: 'chat-1' }),
      { initialProps: { messages: makeMessages(['user']) } }
    )

    await waitFor(() => expect(getWorkspaceInfo).toHaveBeenCalledTimes(1))

    rerender({ messages: makeMessages(['user', 'tool']) })

    await waitFor(() => expect(getWorkspaceInfo).toHaveBeenCalledTimes(2))
  })
})
