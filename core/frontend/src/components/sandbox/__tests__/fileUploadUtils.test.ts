import { describe, it, expect } from 'vitest'
import {
  detectRealFileType,
  getRootUploadPath,
  readFileContent,
  validateFileType,
} from '../fileUploadUtils'

// PNG magic bytes: 89 50 4E 47
const PNG_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
// PDF magic bytes: 25 50 44 46
const PDF_BYTES = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34])
// ELF magic bytes (Linux executable): 7f 45 4c 46
const ELF_BYTES = new Uint8Array([0x7f, 0x45, 0x4c, 0x46, 0x02, 0x01, 0x01, 0x00])

function makeFile(name: string, bytes: Uint8Array, mime = 'application/octet-stream'): File {
  return new File([bytes], name, { type: mime })
}

describe('detectRealFileType', () => {
  it('identifies a file from its magic bytes, independent of its extension', async () => {
    const file = makeFile('photo.txt', PNG_BYTES)
    const result = await detectRealFileType(file)
    expect(result).toEqual({ mime: 'image/png', category: 'image' })
  })

  it('falls back to unknown/octet-stream when no signature matches', async () => {
    const file = makeFile('data.bin', new Uint8Array([0x00, 0x01, 0x02]))
    const result = await detectRealFileType(file)
    expect(result).toEqual({ mime: 'application/octet-stream', category: 'unknown' })
  })
})

describe('validateFileType', () => {
  it('blocks an executable masquerading as a declared text extension', async () => {
    const file = makeFile('notes.txt', ELF_BYTES)
    const result = await validateFileType(file)
    expect(result.valid).toBe(false)
    expect(result.shouldBlock).toBe(true)
    expect(result.warning).toMatch(/executable/i)
  })

  it('blocks a PNG masquerading as a declared code extension', async () => {
    const file = makeFile('script.py', PNG_BYTES)
    const result = await validateFileType(file)
    expect(result.valid).toBe(false)
    expect(result.shouldBlock).toBe(true)
    expect(result.warning).toMatch(/binary file/i)
  })

  it('warns but does not block a PDF declared as a .png (specific type mismatch)', async () => {
    const file = makeFile('image.png', PDF_BYTES)
    const result = await validateFileType(file)
    expect(result.valid).toBe(true)
    expect(result.shouldBlock).toBeFalsy()
    expect(result.warning).toMatch(/type mismatch/i)
  })

  it('does not warn when a .zip reads back as generic octet-stream', async () => {
    const file = makeFile('archive.zip', new Uint8Array([0x00, 0x01, 0x02]))
    const result = await validateFileType(file)
    expect(result).toEqual({ valid: true })
  })

  it('accepts an unrecognized extension with no expectations to violate', async () => {
    const file = makeFile('data.custom', new Uint8Array([0x00, 0x01, 0x02]))
    const result = await validateFileType(file)
    expect(result).toEqual({ valid: true })
  })
})

describe('readFileContent', () => {
  it('reads a text file as plain text', async () => {
    const file = new File(['hello world'], 'notes.txt', { type: 'text/plain' })
    const { content, isBinary } = await readFileContent(file)
    expect(isBinary).toBe(false)
    expect(content).toBe('hello world')
  })

  it('reads a binary-extension file as base64 (no data: prefix)', async () => {
    const file = makeFile('photo.png', PNG_BYTES, 'image/png')
    const { content, isBinary } = await readFileContent(file)
    expect(isBinary).toBe(true)
    expect(content).not.toMatch(/^data:/)
    expect(content.length).toBeGreaterThan(0)
  })
})

describe('getRootUploadPath', () => {
  it('extracts the first path segment relative to the target directory', () => {
    const root = getRootUploadPath('/workspace/my-folder/nested/file.txt', 'my-folder/nested/file.txt')
    expect(root).toBe('/workspace/my-folder')
  })

  it('returns the file itself when it is uploaded directly (no nesting)', () => {
    const root = getRootUploadPath('/workspace/file.txt', 'file.txt')
    expect(root).toBe('/workspace/file.txt')
  })
})
