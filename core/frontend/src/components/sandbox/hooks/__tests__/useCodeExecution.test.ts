import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { OpenFile } from '../../types'

const post = vi.fn()

vi.mock('@/api/client', () => ({
  getAccessToken: () => 'test-token',
  orchestratorClient: { post: (...args: unknown[]) => post(...args) },
}))

import { useCodeExecution } from '../useCodeExecution'

function makeFile(overrides: Partial<OpenFile> = {}): OpenFile {
  return {
    path: '/workspace/readme.md',
    name: 'readme.md',
    content: '# hello',
    language: 'markdown',
    isDirty: false,
    ...overrides,
  }
}

describe('useCodeExecution', () => {
  beforeEach(() => {
    post.mockReset()
  })

  it('refuses to run a non-executable file: toasts and never posts /execute', async () => {
    const toast = vi.fn()
    const saveFile = vi.fn()
    const onBeforeRun = vi.fn()

    const { result } = renderHook(() =>
      useCodeExecution({
        activeFile: makeFile(),
        userId: 'user-1',
        projectId: 'proj-1',
        toast,
        saveFile,
        onBeforeRun,
      })
    )

    await act(async () => {
      await result.current.handleRunFile()
    })

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Cannot Execute', variant: 'destructive' })
    )
    expect(post).not.toHaveBeenCalled()
    expect(onBeforeRun).not.toHaveBeenCalled()
    expect(result.current.isExecuting).toBe(false)
  })

  it('does nothing when there is no active file', async () => {
    const toast = vi.fn()
    const { result } = renderHook(() =>
      useCodeExecution({
        activeFile: undefined,
        userId: 'user-1',
        projectId: 'proj-1',
        toast,
        saveFile: vi.fn(),
        onBeforeRun: vi.fn(),
      })
    )

    await act(async () => {
      await result.current.handleRunFile()
    })

    expect(toast).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })

  it('saves a dirty file, opens the output panel, and posts /execute for an executable file', async () => {
    post.mockResolvedValue({ data: { output: 'ok', exit_code: 0, execution_time: 0.1 } })
    const toast = vi.fn()
    const saveFile = vi.fn().mockResolvedValue(undefined)
    const onBeforeRun = vi.fn()

    const { result } = renderHook(() =>
      useCodeExecution({
        activeFile: makeFile({ path: '/workspace/main.py', name: 'main.py', isDirty: true }),
        userId: 'user-1',
        projectId: 'proj-1',
        toast,
        saveFile,
        onBeforeRun,
      })
    )

    await act(async () => {
      await result.current.handleRunFile()
    })

    expect(saveFile).toHaveBeenCalledWith('/workspace/main.py')
    expect(onBeforeRun).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith('/execute', expect.objectContaining({ language: 'python' }), expect.anything())
    expect(result.current.result).toEqual({ output: 'ok', exit_code: 0, execution_time: 0.1 })
  })
})
