import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const cacheGet = vi.fn()

vi.mock('@/utils/attachmentCache', () => ({
  cacheGet: (...args: unknown[]) => cacheGet(...args),
}))

import { useAttachmentCacheHydration } from '../useAttachmentCacheHydration'
import type { Attachment, FileAttachment, ImageAttachment, Message } from '../../types'

function makeFileAttachment(overrides: Partial<FileAttachment> = {}): FileAttachment {
  return { id: 'f1', type: 'file', file: new File(['x'], 'a.txt'), ...overrides } as FileAttachment
}

/** A file attachment that lost its in-memory File (e.g. after a page reload). */
function makeFileAttachmentWithoutFile(overrides: Partial<Omit<FileAttachment, 'file'>> = {}): FileAttachment {
  return { id: 'f1', type: 'file', ...overrides } as Partial<FileAttachment> as FileAttachment
}

function makeImageAttachment(overrides: Partial<ImageAttachment> = {}): ImageAttachment {
  return { id: 'i1', type: 'image', file: new File(['x'], 'a.png'), preview: 'blob:preview', ...overrides } as ImageAttachment
}

describe('useAttachmentCacheHydration', () => {
  beforeEach(() => {
    cacheGet.mockReset()
  })

  it('starts with no cached attachments and skips the cache when nothing needs hydration', async () => {
    const { result } = renderHook(() => useAttachmentCacheHydration([], []))
    expect(result.current).toEqual({})
    await waitFor(() => expect(cacheGet).not.toHaveBeenCalled())
  })

  it('hydrates a compose-area file attachment missing both base64 and textContent', async () => {
    cacheGet.mockResolvedValue({ base64: 'aGVsbG8=', mimeType: 'text/plain' })
    const attachments: Attachment[] = [makeFileAttachmentWithoutFile()]

    const { result } = renderHook(() => useAttachmentCacheHydration([], attachments))

    await waitFor(() => expect(result.current['f1']).toBeDefined())
    expect(cacheGet).toHaveBeenCalledWith('f1')
  })

  it('hydrates an image attachment missing base64 and preview', async () => {
    cacheGet.mockResolvedValue({ base64: 'aGVsbG8=', mimeType: 'image/png' })
    const attachments: Attachment[] = [makeImageAttachment({ preview: '', base64: undefined })]

    const { result } = renderHook(() => useAttachmentCacheHydration([], attachments))

    await waitFor(() => expect(result.current['i1']).toBeDefined())
  })

  it('does not hydrate a file attachment that already has textContent', async () => {
    const attachments: Attachment[] = [makeFileAttachment({ textContent: 'already here' })]

    renderHook(() => useAttachmentCacheHydration([], attachments))

    await waitFor(() => expect(cacheGet).not.toHaveBeenCalled())
  })

  it('checks attachments embedded in messages as well as the compose area', async () => {
    cacheGet.mockResolvedValue({ base64: 'aGVsbG8=', mimeType: 'text/plain' })
    const messages: Message[] = [{
      role: 'user',
      content: 'see attached',
      timestamp: new Date('2026-01-01T00:00:00Z'),
      attachments: [makeFileAttachmentWithoutFile({ id: 'm1' })],
    } as Message]

    const { result } = renderHook(() => useAttachmentCacheHydration(messages, []))

    await waitFor(() => expect(result.current['m1']).toBeDefined())
  })

  it('swallows a rejected cacheGet lookup without crashing', async () => {
    cacheGet.mockRejectedValue(new Error('cache miss'))
    const attachments: Attachment[] = [makeFileAttachmentWithoutFile()]

    const { result } = renderHook(() => useAttachmentCacheHydration([], attachments))

    await waitFor(() => expect(cacheGet).toHaveBeenCalled())
    expect(result.current).toEqual({})
  })
})
