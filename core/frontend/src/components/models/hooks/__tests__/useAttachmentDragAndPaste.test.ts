import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { ClipboardEvent as ReactClipboardEvent, DragEvent as ReactDragEvent } from 'react'

const buildAttachmentsFromFiles = vi.fn()
const extractFilesFromDataTransfer = vi.fn()
const extractFilesFromClipboard = vi.fn()

vi.mock('@/utils/attachmentHandlers', () => ({
  buildAttachmentsFromFiles: (...args: unknown[]) => buildAttachmentsFromFiles(...args),
  extractFilesFromDataTransfer: (...args: unknown[]) => extractFilesFromDataTransfer(...args),
  extractFilesFromClipboard: (...args: unknown[]) => extractFilesFromClipboard(...args),
}))

vi.mock('@/lib/sessionDetection', () => ({
  getAuthModalVariant: () => 'sign-up-prompt',
}))

import { useAttachmentDragAndPaste } from '../useAttachmentDragAndPaste'

function emptyCounts(overrides: Record<string, unknown> = {}) {
  return {
    imagesAdded: 0, pdfsAdded: 0, officeDocsAdded: 0, textsAdded: 0,
    videosAdded: 0, audiosAdded: 0, errors: 0, blocked: 0, skippedOverflow: 0,
    securityWarnings: [] as string[],
    ...overrides,
  }
}

function makeDragEvent(): ReactDragEvent<HTMLDivElement> {
  return { preventDefault: vi.fn(), dataTransfer: {} } as Partial<ReactDragEvent<HTMLDivElement>> as ReactDragEvent<HTMLDivElement>
}

function makePasteEvent(): ReactClipboardEvent<HTMLTextAreaElement> {
  return { preventDefault: vi.fn() } as Partial<ReactClipboardEvent<HTMLTextAreaElement>> as ReactClipboardEvent<HTMLTextAreaElement>
}

describe('useAttachmentDragAndPaste', () => {
  const toast = vi.fn()
  const openModal = vi.fn()
  const addAttachments = vi.fn()

  beforeEach(() => {
    toast.mockReset()
    openModal.mockReset()
    addAttachments.mockReset()
    buildAttachmentsFromFiles.mockReset()
    extractFilesFromDataTransfer.mockReset()
    extractFilesFromClipboard.mockReset()
  })

  it('handleDragOver sets isDragOver when authenticated and not loading/disabled', () => {
    const { result } = renderHook(() => useAttachmentDragAndPaste({
      isAuthenticated: true, isLoading: false, disabledChat: false,
      attachmentCount: 0, addAttachments, toast, openModal,
    }))

    act(() => { result.current.handleDragOver(makeDragEvent()) })

    expect(result.current.isDragOver).toBe(true)
  })

  it('handleDragOver does nothing while unauthenticated', () => {
    const { result } = renderHook(() => useAttachmentDragAndPaste({
      isAuthenticated: false, isLoading: false, disabledChat: false,
      attachmentCount: 0, addAttachments, toast, openModal,
    }))

    act(() => { result.current.handleDragOver(makeDragEvent()) })

    expect(result.current.isDragOver).toBe(false)
  })

  it('handleDrop prompts sign-in and skips attachment building when unauthenticated', async () => {
    const { result } = renderHook(() => useAttachmentDragAndPaste({
      isAuthenticated: false, isLoading: false, disabledChat: false,
      attachmentCount: 0, addAttachments, toast, openModal,
    }))

    await act(async () => { await result.current.handleDrop(makeDragEvent()) })

    expect(openModal).toHaveBeenCalledWith('sign-up-prompt', expect.any(String))
    expect(buildAttachmentsFromFiles).not.toHaveBeenCalled()
  })

  it('handleDrop adds built attachments and shows a summary toast', async () => {
    extractFilesFromDataTransfer.mockReturnValue([{ name: 'a.png' }])
    buildAttachmentsFromFiles.mockResolvedValue({
      attachments: [{ id: '1' }],
      counts: emptyCounts({ imagesAdded: 1 }),
    })
    const { result } = renderHook(() => useAttachmentDragAndPaste({
      isAuthenticated: true, isLoading: false, disabledChat: false,
      attachmentCount: 2, addAttachments, toast, openModal,
    }))

    await act(async () => { await result.current.handleDrop(makeDragEvent()) })

    expect(buildAttachmentsFromFiles).toHaveBeenCalledWith([{ name: 'a.png' }], { currentCount: 2, maxCount: 8 })
    expect(addAttachments).toHaveBeenCalledWith([{ id: '1' }])
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Attachments added', description: expect.stringContaining('1 image') }))
    expect(result.current.isDragOver).toBe(false)
  })

  it('handleDrop shows a destructive toast for blocked-file security warnings', async () => {
    extractFilesFromDataTransfer.mockReturnValue([{ name: 'evil.exe' }])
    buildAttachmentsFromFiles.mockResolvedValue({
      attachments: [],
      counts: emptyCounts({ blocked: 1, securityWarnings: ['BLOCKED: dangerous file type'] }),
    })
    const { result } = renderHook(() => useAttachmentDragAndPaste({
      isAuthenticated: true, isLoading: false, disabledChat: false,
      attachmentCount: 0, addAttachments, toast, openModal,
    }))

    await act(async () => { await result.current.handleDrop(makeDragEvent()) })

    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Security Warning', variant: 'destructive' }))
  })

  it('handlePaste ignores clipboard content without files', async () => {
    extractFilesFromClipboard.mockReturnValue([])
    const event = makePasteEvent()
    const { result } = renderHook(() => useAttachmentDragAndPaste({
      isAuthenticated: true, isLoading: false, disabledChat: false,
      attachmentCount: 0, addAttachments, toast, openModal,
    }))

    await act(async () => { await result.current.handlePaste(event) })

    expect(event.preventDefault).not.toHaveBeenCalled()
    expect(buildAttachmentsFromFiles).not.toHaveBeenCalled()
  })

  it('handlePaste prevents default and adds attachments when files are present', async () => {
    extractFilesFromClipboard.mockReturnValue([{ name: 'clip.png' }])
    buildAttachmentsFromFiles.mockResolvedValue({
      attachments: [{ id: '2' }],
      counts: emptyCounts({ imagesAdded: 1 }),
    })
    const event = makePasteEvent()
    const { result } = renderHook(() => useAttachmentDragAndPaste({
      isAuthenticated: true, isLoading: false, disabledChat: false,
      attachmentCount: 0, addAttachments, toast, openModal,
    }))

    await act(async () => { await result.current.handlePaste(event) })

    expect(event.preventDefault).toHaveBeenCalled()
    expect(addAttachments).toHaveBeenCalledWith([{ id: '2' }])
  })

  it('handleDrop and handlePaste are gated by isLoading/disabledChat once authenticated', async () => {
    const { result } = renderHook(() => useAttachmentDragAndPaste({
      isAuthenticated: true, isLoading: true, disabledChat: false,
      attachmentCount: 0, addAttachments, toast, openModal,
    }))

    await act(async () => { await result.current.handleDrop(makeDragEvent()) })

    expect(extractFilesFromDataTransfer).not.toHaveBeenCalled()
  })
})
