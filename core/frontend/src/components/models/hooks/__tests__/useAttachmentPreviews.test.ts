import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

const download = vi.fn()
const toastError = vi.fn()

vi.mock('@/api/assets', () => ({
  assetsAPI: {
    download: (...args: unknown[]) => download(...args),
  },
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: (...args: unknown[]) => toastError(...args),
  },
}))

import { useAttachmentPreviews } from '../useAttachmentPreviews'
import type { FileAttachment } from '../../types'

function makeFileAttachment(overrides: Partial<FileAttachment> = {}): FileAttachment {
  return {
    id: 'file-1',
    type: 'file',
    file: new File(['content'], 'notes.txt', { type: 'text/plain' }),
    ...overrides,
  }
}

describe('useAttachmentPreviews', () => {
  beforeEach(() => {
    download.mockReset()
    toastError.mockReset()
    Object.assign(URL, { createObjectURL: vi.fn().mockReturnValue('blob:asset-url'), revokeObjectURL: vi.fn() })
  })

  it('opens the image gallery with the given images and index', () => {
    const { result } = renderHook(() => useAttachmentPreviews())

    act(() => {
      result.current.handleOpenImageGallery([{ src: 'a.png', alt: 'a' }], 0)
    })

    expect(result.current.imageGalleryOpen).toBe(true)
    expect(result.current.galleryImages).toEqual([{ src: 'a.png', alt: 'a' }])
  })

  it('opens the PDF viewer with source and name', () => {
    const { result } = renderHook(() => useAttachmentPreviews())

    act(() => {
      result.current.handleOpenPdf('blob:pdf', 'doc.pdf')
    })

    expect(result.current.isPdfOpen).toBe(true)
    expect(result.current.pdfSrc).toBe('blob:pdf')
    expect(result.current.pdfName).toBe('doc.pdf')
  })

  it('opens the all-attachments modal with the given list', () => {
    const { result } = renderHook(() => useAttachmentPreviews())
    const attachments = [makeFileAttachment()]

    act(() => {
      result.current.handleOpenAllAttachments(attachments)
    })

    expect(result.current.isAllAttachmentsOpen).toBe(true)
    expect(result.current.allAttachments).toBe(attachments)
  })

  it('shows a text file directly from cached textContent without hitting the API', async () => {
    const { result } = renderHook(() => useAttachmentPreviews())
    const file = makeFileAttachment({ textContent: 'cached body' })

    await act(async () => {
      await result.current.handleOpenTextFile(file)
    })

    expect(download).not.toHaveBeenCalled()
    expect(result.current.isFilePreviewOpen).toBe(true)
    expect(result.current.previewFile).toMatchObject({ name: 'notes.txt', content: 'cached body' })
  })

  it('fetches a text file from storage when only an assetId is available', async () => {
    // jsdom's Blob has no .text(); stub the shape handleOpenTextFile actually reads.
    download.mockResolvedValue({ text: async () => 'fetched body' } as unknown as Blob)
    const { result } = renderHook(() => useAttachmentPreviews())
    const file = makeFileAttachment({ assetId: 'asset-1', textContent: undefined })

    await act(async () => {
      await result.current.handleOpenTextFile(file)
    })

    expect(download).toHaveBeenCalledWith('asset-1')
    expect(result.current.previewFile?.content).toBe('fetched body')
    expect(result.current.isFilePreviewOpen).toBe(true)
  })

  it('toasts an error when a file has neither cached content nor an assetId', async () => {
    const { result } = renderHook(() => useAttachmentPreviews())
    const file = makeFileAttachment({ textContent: undefined, assetId: undefined })

    await act(async () => {
      await result.current.handleOpenTextFile(file)
    })

    expect(toastError).toHaveBeenCalledWith('File content not available')
    expect(result.current.isFilePreviewOpen).toBe(false)
  })

  it('loadAssetAsBlobUrl caches the resolved blob URL and skips a second download', async () => {
    download.mockResolvedValue(new Blob(['bytes']))
    const { result } = renderHook(() => useAttachmentPreviews())

    let first: string | null = null
    await act(async () => {
      first = await result.current.loadAssetAsBlobUrl('asset-1')
    })
    expect(first).toBe('blob:asset-url')

    await waitFor(() => expect(result.current.loadedBlobUrls['asset-1']).toBe('blob:asset-url'))

    await act(async () => {
      await result.current.loadAssetAsBlobUrl('asset-1')
    })

    expect(download).toHaveBeenCalledTimes(1)
  })
})
