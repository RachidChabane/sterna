import { describe, it, expect, vi, beforeEach } from 'vitest'
import { prepareApiMessagesWithAttachments } from '../attachmentPreparation'
import { assetsAPI } from '@/api/assets'
import type { Message, Model } from '@/components/models/types'
import type { ApiMessage } from '../types'

vi.mock('@/api/assets', () => ({
  assetsAPI: { download: vi.fn() },
}))

const TEXT_ONLY_MODEL: Model = { model_id: 'm', name: 'M', provider: 'p', input_modalities: ['text'] } as Model
const VISION_MODEL: Model = { model_id: 'm', name: 'M', provider: 'p', input_modalities: ['text', 'image', 'file'] } as Model

function userMessage(content: string, attachments: unknown[] = []): Message {
  return { role: 'user', content, timestamp: new Date(), attachments } as Message
}

function apiMessagesFor(content: string): ApiMessage[] {
  return [{ role: 'user', content }]
}

describe('prepareApiMessagesWithAttachments', () => {
  beforeEach(() => vi.clearAllMocks())

  it('returns synchronously (no Promise) when there is no attachment needing a base64 fetch', () => {
    const result = prepareApiMessagesWithAttachments(apiMessagesFor('hi'), 0, userMessage('hi'), TEXT_ONLY_MODEL)
    expect(result).not.toBeInstanceOf(Promise)
  })

  it('rebuilds the last user message as plain text when there are no attachments', () => {
    const result = prepareApiMessagesWithAttachments(apiMessagesFor('hello'), 0, userMessage('hello'), TEXT_ONLY_MODEL)
    expect(result).not.toBeInstanceOf(Promise)
    if (result instanceof Promise) throw new Error('unreachable')
    expect(result.apiMessages[0]).toEqual({ role: 'user', content: 'hello' })
    expect(result.hasSendableContent).toBe(true)
    expect(result.hasFileAttachments).toBe(false)
  })

  it('reports hasSendableContent: false when text is empty and nothing else is supported', () => {
    const msg = userMessage('', [{ id: 'i1', type: 'image', base64: 'data:image/png;base64,x' }])
    const result = prepareApiMessagesWithAttachments(apiMessagesFor(''), 0, msg, TEXT_ONLY_MODEL) // model has no vision support
    if (result instanceof Promise) throw new Error('unreachable')
    expect(result.hasSendableContent).toBe(false)
  })

  it('includes an already-base64 image as an image_url part when the model supports vision', () => {
    const msg = userMessage('look at this', [{ id: 'i1', type: 'image', base64: 'data:image/png;base64,abc' }])
    const result = prepareApiMessagesWithAttachments(apiMessagesFor('look at this'), 0, msg, VISION_MODEL)
    if (result instanceof Promise) throw new Error('unreachable')
    const content = result.apiMessages[0].content
    expect(content.some((p) => p.type === 'image_url' && p.image_url.url === 'data:image/png;base64,abc')).toBe(true)
  })

  it('drops an image the target model does not support and keeps the text', () => {
    const msg = userMessage('hi', [{ id: 'i1', type: 'image', base64: 'data:image/png;base64,abc' }])
    const result = prepareApiMessagesWithAttachments(apiMessagesFor('hi'), 0, msg, TEXT_ONLY_MODEL)
    if (result instanceof Promise) throw new Error('unreachable')
    expect(result.apiMessages[0]).toEqual({ role: 'user', content: 'hi' })
  })

  it('appends text-file contents to the outgoing text', () => {
    const msg = userMessage('see attached', [{ id: 'f1', type: 'file', textContent: 'file body', file: { name: 'notes.txt' } }])
    const result = prepareApiMessagesWithAttachments(apiMessagesFor('see attached'), 0, msg, TEXT_ONLY_MODEL)
    if (result instanceof Promise) throw new Error('unreachable')
    expect(result.apiMessages[0].content).toContain('file body')
    expect(result.apiMessages[0].content).toContain('notes.txt')
  })

  it('appends an asset_url reference line for video/audio attachments', () => {
    const msg = userMessage('watch this', [{ id: 'v1', type: 'video', assetId: 'asset-1', fileName: 'clip.mp4' }])
    const result = prepareApiMessagesWithAttachments(apiMessagesFor('watch this'), 0, msg, TEXT_ONLY_MODEL)
    if (result instanceof Promise) throw new Error('unreachable')
    expect(result.apiMessages[0].content).toContain('/api/workspaces/assets/asset-1/download/')
  })

  it('goes async and fetches base64 for an attachment that only has an assetId', async () => {
    vi.mocked(assetsAPI.download).mockResolvedValue(new Blob(['fake-image-bytes'], { type: 'image/png' }))
    const msg = userMessage('reloaded image', [{ id: 'i1', type: 'image', assetId: 'asset-9' }])

    const maybe = prepareApiMessagesWithAttachments(apiMessagesFor('reloaded image'), 0, msg, VISION_MODEL)
    expect(maybe).toBeInstanceOf(Promise)
    const result = await maybe

    expect(assetsAPI.download).toHaveBeenCalledWith('asset-9')
    const content = result.apiMessages[0].content
    expect(content.some((p) => p.type === 'image_url')).toBe(true)
  })

  it('collects workspace asset references for attachments with an assetId but no File object', () => {
    const msg = userMessage('doc', [{ id: 'f1', type: 'file', assetId: 'asset-5', fileName: 'doc.pdf', base64: 'data:...' }])
    const result = prepareApiMessagesWithAttachments(apiMessagesFor('doc'), 0, msg, TEXT_ONLY_MODEL)
    if (result instanceof Promise) throw new Error('unreachable')
    expect(result.workspaceAssets).toEqual([{ asset_id: 'asset-5', filename: 'doc.pdf' }])
  })
})
