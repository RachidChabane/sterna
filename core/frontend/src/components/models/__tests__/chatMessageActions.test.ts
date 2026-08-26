import { describe, it, expect, vi, beforeEach } from 'vitest'

const toastSuccess = vi.fn()
const toastError = vi.fn()

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}))

import {
  formatCost,
  formatLatency,
  copyMessageContent,
  copyMessageMetadata,
  exportMessageContent,
  exportMessageMetadata,
} from '../chatMessageActions'
import type { Message } from '../types'

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    role: 'assistant',
    content: 'hello world',
    timestamp: new Date('2026-01-01T00:00:00Z'),
    message_id: 'msg-1',
    ...overrides,
  }
}

describe('formatCost', () => {
  it('renders zero cost as $0.00', () => {
    expect(formatCost(0)).toBe('$0.00')
  })

  it('renders undefined cost as $0.00', () => {
    expect(formatCost(undefined)).toBe('$0.00')
  })

  it('renders sub-cent cost as <$0.01', () => {
    expect(formatCost(0.004)).toBe('<$0.01')
  })

  it('renders larger cost to 4 decimal places', () => {
    expect(formatCost(0.0234)).toBe('$0.0234')
  })
})

describe('formatLatency', () => {
  it('delegates to formatLatencyFromSeconds', () => {
    // 1.4s should render as a human-readable duration containing the value.
    expect(formatLatency(1.4)).toContain('1.4')
  })
})

describe('copyMessageContent', () => {
  beforeEach(() => {
    toastSuccess.mockReset()
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } })
  })

  it('writes extracted text to the clipboard and toasts success', () => {
    copyMessageContent('hello there')
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('hello there')
    expect(toastSuccess).toHaveBeenCalledWith('Copied to clipboard')
  })
})

describe('copyMessageMetadata', () => {
  beforeEach(() => {
    toastSuccess.mockReset()
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } })
  })

  it('writes the full message as JSON to the clipboard', () => {
    const message = makeMessage()
    copyMessageMetadata(message)
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(JSON.stringify(message, null, 2))
    expect(toastSuccess).toHaveBeenCalledWith('Metadata copied to clipboard')
  })
})

describe('exportMessageContent', () => {
  it('creates a downloadable text blob and clicks it', () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:fake-url')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    const click = vi.fn()
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag)
      if (tag === 'a') el.click = click
      return el
    })

    exportMessageContent('plain text body')

    expect(createObjectURL).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake-url')

    vi.restoreAllMocks()
  })
})

describe('exportMessageMetadata', () => {
  it('creates a downloadable JSON blob and clicks it', () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:fake-url-2')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    const click = vi.fn()
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag)
      if (tag === 'a') el.click = click
      return el
    })

    exportMessageMetadata(makeMessage())

    expect(createObjectURL).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake-url-2')

    vi.restoreAllMocks()
  })
})
