import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

const readFile = vi.fn()
const writeFile = vi.fn()

vi.mock('@/api/fs', () => ({
  fsAPI: {
    readFile: (...args: unknown[]) => readFile(...args),
    writeFile: (...args: unknown[]) => writeFile(...args),
  },
}))

import { useFileOperations } from '../useFileOperations'

function makeFileTreeHook() {
  return {
    setSelectedPath: vi.fn(),
    loadFileTree: vi.fn().mockResolvedValue(undefined),
    fileTree: [],
  }
}

function makeEditorHook() {
  return {
    disposeModel: vi.fn(),
    getCurrentContent: vi.fn().mockReturnValue(null),
    isSavingRef: { current: false },
    renameModel: vi.fn(),
  }
}

describe('useFileOperations', () => {
  beforeEach(() => {
    readFile.mockReset()
    writeFile.mockReset()
  })

  it('blocks opening a non-previewable binary and never calls fsAPI.readFile', async () => {
    const toast = vi.fn()
    const { result } = renderHook(() =>
      useFileOperations({
        userId: 'user-1',
        projectId: 'proj-1',
        toast,
        fileTreeHook: makeFileTreeHook(),
        editorHook: makeEditorHook(),
      })
    )

    await act(async () => {
      await result.current.openFile('/workspace/archive.zip', 'archive.zip')
    })

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Cannot Preview File' })
    )
    expect(readFile).not.toHaveBeenCalled()
    expect(result.current.openFiles).toHaveLength(0)
  })

  it('opens a text file, adds it to the tab list, and makes it active', async () => {
    readFile.mockResolvedValue({ success: true, content: 'print(1)' })
    const toast = vi.fn()
    const { result } = renderHook(() =>
      useFileOperations({
        userId: 'user-1',
        projectId: 'proj-1',
        toast,
        fileTreeHook: makeFileTreeHook(),
        editorHook: makeEditorHook(),
      })
    )

    await act(async () => {
      await result.current.openFile('/workspace/main.py', 'main.py')
    })

    expect(result.current.openFiles).toHaveLength(1)
    expect(result.current.openFiles[0]).toMatchObject({ path: '/workspace/main.py', content: 'print(1)', isDirty: false })
    expect(result.current.activeFilePath).toBe('/workspace/main.py')
    expect(result.current.recentFilePaths).toEqual(['/workspace/main.py'])
    expect(toast).not.toHaveBeenCalled()
  })

  it('does nothing when there is no userId', async () => {
    const toast = vi.fn()
    const { result } = renderHook(() =>
      useFileOperations({
        userId: undefined,
        projectId: 'proj-1',
        toast,
        fileTreeHook: makeFileTreeHook(),
        editorHook: makeEditorHook(),
      })
    )

    await act(async () => {
      await result.current.openFile('/workspace/main.py', 'main.py')
    })

    expect(readFile).not.toHaveBeenCalled()
    expect(result.current.openFiles).toHaveLength(0)
  })
})
