import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

const download = vi.fn()

vi.mock('@/api/assets', () => ({
  assetsAPI: {
    download: (...args: unknown[]) => download(...args),
  },
}))

import { useAttachmentViewerState } from '../useAttachmentViewerState'
import type { FileAttachment } from '../../types'

function makeFileAttachment(overrides: Partial<FileAttachment> = {}): FileAttachment {
  return {
    id: 'file-1',
    type: 'file',
    file: new File(['content'], 'notes.txt', { type: 'text/plain' }),
    ...overrides,
  }
}

describe('useAttachmentViewerState', () => {
  const toast = vi.fn()

  beforeEach(() => {
    toast.mockReset()
    download.mockReset()
  })

  it('handleOpenImageGallery opens the gallery and records whether it came from attachments', () => {
    const { result } = renderHook(() => useAttachmentViewerState(toast))

    act(() => {
      result.current.handleOpenImageGallery([{ src: 'a.png', alt: 'a' }], 0, true)
    })

    expect(result.current.isGalleryOpen).toBe(true)
    expect(result.current.selectedImageIndex).toBe(0)
    expect(result.current.selectedAllImage).toEqual({ src: 'a.png', alt: 'a' })
    expect(result.current.galleryOpenedFromAttachments).toBe(true)
  })

  it('handleOpenPdf opens the PDF viewer with source and name', () => {
    const { result } = renderHook(() => useAttachmentViewerState(toast))

    act(() => { result.current.handleOpenPdf('blob:pdf', 'doc.pdf') })

    expect(result.current.isPdfOpen).toBe(true)
    expect(result.current.pdfSrc).toBe('blob:pdf')
    expect(result.current.pdfName).toBe('doc.pdf')
  })

  it('handleOpenAllAttachments opens the all-attachments modal with the given list', () => {
    const { result } = renderHook(() => useAttachmentViewerState(toast))
    const attachments = [makeFileAttachment()]

    act(() => { result.current.handleOpenAllAttachments(attachments) })

    expect(result.current.isAllAttachmentsOpen).toBe(true)
    expect(result.current.allAttachments).toBe(attachments)
  })

  it('handleOpenTextFile shows cached textContent without hitting the API', async () => {
    const { result } = renderHook(() => useAttachmentViewerState(toast))
    const file = makeFileAttachment({ textContent: 'cached body' })

    await act(async () => { await result.current.handleOpenTextFile(file) })

    expect(download).not.toHaveBeenCalled()
    expect(result.current.isModalOpen).toBe(true)
    expect(result.current.selectedFile).toBe(file)
    expect(result.current.fetchedFileContent).toBeNull()
  })

  it('handleOpenTextFile fetches content from storage when only an assetId is available', async () => {
    download.mockResolvedValue({ text: async () => 'fetched body' } as Partial<Blob> as Blob)
    const { result } = renderHook(() => useAttachmentViewerState(toast))
    const file = { ...makeFileAttachment({ textContent: undefined }), assetId: 'asset-1' } as FileAttachment

    await act(async () => { await result.current.handleOpenTextFile(file) })

    expect(download).toHaveBeenCalledWith('asset-1')
    expect(result.current.fetchedFileContent).toBe('fetched body')
    expect(result.current.isModalOpen).toBe(true)
  })

  it('handleOpenTextFile toasts a destructive error when download fails', async () => {
    download.mockResolvedValue(null)
    const { result } = renderHook(() => useAttachmentViewerState(toast))
    const file = { ...makeFileAttachment({ textContent: undefined }), assetId: 'asset-1' } as FileAttachment

    await act(async () => { await result.current.handleOpenTextFile(file) })

    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Failed to load file', variant: 'destructive' }))
    expect(result.current.isModalOpen).toBe(false)
  })

  it('handleOpenTextFile toasts when there is neither cached content nor an assetId', async () => {
    const { result } = renderHook(() => useAttachmentViewerState(toast))
    const file = makeFileAttachment({ textContent: undefined, assetId: undefined })

    await act(async () => { await result.current.handleOpenTextFile(file) })

    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'File content not available' }))
    expect(result.current.isModalOpen).toBe(false)
  })
})
