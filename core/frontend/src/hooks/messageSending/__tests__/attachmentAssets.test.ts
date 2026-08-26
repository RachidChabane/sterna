import { describe, it, expect, vi, beforeEach } from 'vitest'
import { buildUnsupportedAttachmentsMessage, uploadAttachmentsAsAssets } from '../attachmentAssets'
import { assetsAPI } from '@/api/assets'
import type { Attachment } from '@/components/models/types'

interface FakeAsset {
  id: string
  filename: string
  mime_type: string
  asset_type: string
  size_bytes: number
  download_url: string
}

vi.mock('@/api/assets', () => ({
  assetsAPI: { uploadFile: vi.fn() },
  assetToReference: (asset: FakeAsset) => ({ type: 'asset_ref', asset_id: asset.id, filename: asset.filename, mime_type: asset.mime_type, asset_type: asset.asset_type, size_bytes: asset.size_bytes, download_url: asset.download_url }),
  getAssetTypeFromMime: () => 'generated',
}))

describe('buildUnsupportedAttachmentsMessage', () => {
  it('returns null when every attachment type is supported', () => {
    expect(buildUnsupportedAttachmentsMessage(true, false, false, true, true, true)).toBeNull()
  })

  it('names the single unsupported type and what will still be processed', () => {
    const msg = buildUnsupportedAttachmentsMessage(true, false, false, true, /* supportsVision */ false, true)
    expect(msg).toContain('image inputs')
    expect(msg).toContain('text')
  })

  it('combines PDF and Office into "document file" when both are unsupported', () => {
    const msg = buildUnsupportedAttachmentsMessage(false, true, true, false, true, /* supportsFiles */ false)
    expect(msg).toContain('document file inputs')
  })

  it('returns the "cannot be processed" message when nothing is supported', () => {
    const msg = buildUnsupportedAttachmentsMessage(true, false, false, false, false, false)
    expect(msg).toMatch(/cannot be processed/)
  })

  it('lists multiple supported parts with an Oxford-style join', () => {
    const msg = buildUnsupportedAttachmentsMessage(true, true, false, true, /* supportsVision */ false, true)
    expect(msg).toContain('Only the text and PDF files')
  })
})

describe('uploadAttachmentsAsAssets', () => {
  beforeEach(() => vi.clearAllMocks())

  it('returns empty results for an empty attachment list', async () => {
    const result = await uploadAttachmentsAsAssets('chat-1', [])
    expect(result).toEqual({ enriched: [], assetRefs: [] })
  })

  it('reuses an existing assetRef without calling uploadFile', async () => {
    const att = { id: 'a1', type: 'file', file: new File(['x'], 'a.txt'), assetRef: { type: 'asset_ref', asset_id: 'existing-1', filename: 'a.txt', mime_type: 'text/plain', asset_type: 'generated', size_bytes: 1, download_url: '/d' } } as unknown as Attachment
    const result = await uploadAttachmentsAsAssets('chat-1', [att])
    expect(assetsAPI.uploadFile).not.toHaveBeenCalled()
    expect(result.assetRefs).toEqual([att.assetRef])
    expect(result.enriched).toEqual([att])
  })

  it('uploads an attachment with no existing asset reference', async () => {
    vi.mocked(assetsAPI.uploadFile).mockResolvedValue({
      success: true,
      asset: { id: 'new-1', filename: 'b.txt', mime_type: 'text/plain', asset_type: 'generated', size_bytes: 2, download_url: '/download/new-1' },
    })
    const file = new File(['y'], 'b.txt')
    const att = { id: 'a2', type: 'file', file } as unknown as Attachment

    const result = await uploadAttachmentsAsAssets('chat-1', [att])

    expect(assetsAPI.uploadFile).toHaveBeenCalledWith('chat-1', file, { assetType: 'generated' })
    expect(result.assetRefs).toEqual([{ type: 'asset_ref', asset_id: 'new-1', filename: 'b.txt', mime_type: 'text/plain', asset_type: 'generated', size_bytes: 2, download_url: '/download/new-1' }])
    expect(result.enriched[0].assetId).toBe('new-1')
  })

  it('returns the original attachment with no assetRef when upload fails', async () => {
    vi.mocked(assetsAPI.uploadFile).mockResolvedValue({ success: false, error: 'boom' })
    const att = { id: 'a3', type: 'file', file: new File(['z'], 'c.txt') } as unknown as Attachment

    const result = await uploadAttachmentsAsAssets('chat-1', [att])

    expect(result.assetRefs).toEqual([])
    expect(result.enriched).toEqual([att])
  })

  it('skips upload and returns the attachment unchanged when there is no File object', async () => {
    const att = { id: 'a4', type: 'file' } as unknown as Attachment
    const result = await uploadAttachmentsAsAssets('chat-1', [att])
    expect(assetsAPI.uploadFile).not.toHaveBeenCalled()
    expect(result.enriched).toEqual([att])
    expect(result.assetRefs).toEqual([])
  })
})
