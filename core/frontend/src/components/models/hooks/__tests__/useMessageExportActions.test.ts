import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useMessageExportActions } from '../useMessageExportActions'
import type { Message, Model } from '../../types'

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    role: 'assistant',
    content: 'The answer is 42.',
    timestamp: new Date('2026-01-01T00:00:00Z'),
    model: 'GPT-5',
    ...overrides,
  } as Message
}

function makeModel(overrides: Partial<Model> = {}): Model {
  return {
    id: 'model-1',
    model_id: 'gpt-5',
    name: 'GPT-5',
    provider: 'openai',
    cost_per_1m_prompt: 5,
    cost_per_1m_completion: 15,
    max_tokens: 128000,
    supports_streaming: true,
    supports_functions: true,
    supports_structured_outputs: true,
    supports_reasoning: false,
    supports_prompt_caching: false,
    supports_stream_cancellation: true,
    input_modalities: ['text'],
    is_available: true,
    ...overrides,
  } as Model
}

describe('useMessageExportActions', () => {
  const toast = vi.fn()
  const writeText = vi.fn()

  beforeEach(() => {
    toast.mockReset()
    writeText.mockReset()
    Object.assign(navigator, { clipboard: { writeText } })
    Object.assign(URL, { createObjectURL: vi.fn().mockReturnValue('blob:export'), revokeObjectURL: vi.fn() })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('copyMessageContent copies extracted text and toasts', () => {
    const messages: Message[] = []
    const { result } = renderHook(() => useMessageExportActions({ messages, model: null, toast }))

    result.current.copyMessageContent('hello world')

    expect(writeText).toHaveBeenCalledWith('hello world')
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Copied' }))
  })

  it('copyMessageMetadata copies a JSON snapshot of the message metadata', () => {
    const { result } = renderHook(() => useMessageExportActions({ messages: [], model: null, toast }))
    const message = makeMessage({ cost: 0.01, tokens: 42 })

    result.current.copyMessageMetadata(message)

    const payload = JSON.parse(writeText.mock.calls[0][0])
    expect(payload).toMatchObject({ model: 'GPT-5', cost: 0.01, tokens: 42 })
  })

  it('exportMessageContent triggers a text-file download named after the model', () => {
    const clickSpy = vi.fn()
    const anchor = { click: clickSpy, href: '', download: '' } as Partial<HTMLAnchorElement> as HTMLAnchorElement
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) =>
      tag === 'a' ? anchor : originalCreateElement(tag)
    )

    const { result } = renderHook(() => useMessageExportActions({ messages: [], model: null, toast }))
    result.current.exportMessageContent('response text', 'GPT 5!')

    expect(anchor.download.startsWith('response-GPT_5_')).toBe(true)
    expect(anchor.download.endsWith('.txt')).toBe(true)
    expect(clickSpy).toHaveBeenCalled()
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Exported' }))
  })

  it('copyChatResponses builds text from every message in the chat', () => {
    const messages = [makeMessage({ content: 'first' }), makeMessage({ content: 'second' })]
    const { result } = renderHook(() => useMessageExportActions({ messages, model: makeModel(), toast }))

    result.current.copyChatResponses()

    expect(writeText).toHaveBeenCalled()
    expect(writeText.mock.calls[0][0]).toContain('first')
    expect(writeText.mock.calls[0][0]).toContain('second')
  })

  it('exportChatMetadata exports only assistant messages', () => {
    const clickSpy = vi.fn()
    const anchor = { click: clickSpy, href: '', download: '' } as Partial<HTMLAnchorElement> as HTMLAnchorElement
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) =>
      tag === 'a' ? anchor : originalCreateElement(tag)
    )

    const messages = [
      makeMessage({ role: 'user', content: 'question' }),
      makeMessage({ role: 'assistant', content: 'answer', tokens: 10 }),
    ]
    const { result } = renderHook(() => useMessageExportActions({ messages, model: makeModel(), toast }))

    result.current.exportChatMetadata()

    expect(anchor.download.startsWith('chat-metadata-GPT-5_')).toBe(true)
    expect(anchor.download.endsWith('.json')).toBe(true)
  })

  it('keeps every handler reference stable across a no-op re-render, so the memoized chat context does not churn', () => {
    const props = { messages: [], model: makeModel(), toast }
    const { result, rerender } = renderHook((p) => useMessageExportActions(p), { initialProps: props })

    const before = { ...result.current }

    rerender(props)

    expect(result.current.copyMessageContent).toBe(before.copyMessageContent)
    expect(result.current.copyMessageMetadata).toBe(before.copyMessageMetadata)
    expect(result.current.exportMessageContent).toBe(before.exportMessageContent)
    expect(result.current.exportMessageMetadata).toBe(before.exportMessageMetadata)
    expect(result.current.copyChatResponses).toBe(before.copyChatResponses)
    expect(result.current.copyChatMetadata).toBe(before.copyChatMetadata)
    expect(result.current.exportChatResponses).toBe(before.exportChatResponses)
    expect(result.current.exportChatMetadata).toBe(before.exportChatMetadata)
  })
})
