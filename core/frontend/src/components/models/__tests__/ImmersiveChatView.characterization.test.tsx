/**
 * Characterization tests: record ImmersiveChatView's current rendered
 * output for a set of representative prop/store states. A snapshot diff
 * means the rendered output changed — investigate before updating the
 * snapshot.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { ImmersiveChatView } from '../ImmersiveChatView'
import type { Chat, ImageAttachment, Message } from '../types'
import type { Model, ModelCatalogEntry } from '@/api/llm'

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

vi.mock('@/api/conversations', () => ({
  conversationsAPI: { deleteMessage: vi.fn() },
}))

vi.mock('@/api/assets', () => ({
  assetsAPI: { download: vi.fn(), upload: vi.fn() },
}))

vi.mock('@/api/fs', () => ({
  fsAPI: { listFiles: vi.fn() },
}))

function makeModel(overrides: Partial<Model> = {}): Model {
  return {
    id: 'model-uuid-1',
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
  }
}

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    role: 'user',
    content: 'Hello there',
    timestamp: new Date('2026-01-01T00:00:00Z'),
    message_id: 'msg-1',
    ...overrides,
  }
}

function makeChat(overrides: Partial<Chat> = {}): Chat {
  return {
    id: 'chat-1',
    model: null,
    messages: [],
    isLoading: false,
    parameters: {} as Chat['parameters'],
    ...overrides,
  }
}

const baseHandlers = {
  onModelSelect: vi.fn(),
  onSendMessage: vi.fn(),
  onUpdateMessages: vi.fn(),
  onCancel: vi.fn(),
  onParametersChange: vi.fn(),
  onAddAttachment: vi.fn(),
  onRemoveAttachment: vi.fn(),
}

describe('ImmersiveChatView — empty states', () => {
  it('renders an empty chat with no model selected', () => {
    const { container } = render(
      <ImmersiveChatView
        chat={makeChat()}
        models={[] as ModelCatalogEntry[]}
        canCancel={false}
        attachments={[]}
        hasVisionSupport={false}
        hasPDFSupport={false}
        conversationId="conv-1"
        {...baseHandlers}
      />
    )
    expect(container).toMatchSnapshot()
  })

  it('renders an empty chat with a model already selected', () => {
    const { container } = render(
      <ImmersiveChatView
        chat={makeChat({ model: makeModel() })}
        models={[] as ModelCatalogEntry[]}
        canCancel={false}
        attachments={[]}
        hasVisionSupport={true}
        hasPDFSupport={true}
        conversationId="conv-1"
        {...baseHandlers}
      />
    )
    expect(container).toMatchSnapshot()
  })
})

describe('ImmersiveChatView — conversation states', () => {
  it('renders a short user/assistant exchange', () => {
    const messages: Message[] = [
      makeMessage({ role: 'user', content: 'What is the capital of France?', message_id: 'msg-1' }),
      makeMessage({
        role: 'assistant',
        content: 'The capital of France is Paris.',
        message_id: 'msg-2',
        model: 'gpt-5',
        cost: 0.0021,
        latency: 1.4,
      }),
    ]
    const { container } = render(
      <ImmersiveChatView
        chat={makeChat({ model: makeModel(), messages })}
        models={[] as ModelCatalogEntry[]}
        canCancel={false}
        attachments={[]}
        hasVisionSupport={false}
        hasPDFSupport={false}
        conversationId="conv-1"
        {...baseHandlers}
      />
    )
    expect(container).toMatchSnapshot()
  })

  it('renders the loading state while a response is streaming in, with cancel available', () => {
    const messages: Message[] = [
      makeMessage({ role: 'user', content: 'Tell me a joke', message_id: 'msg-1' }),
    ]
    const { container } = render(
      <ImmersiveChatView
        chat={makeChat({ model: makeModel(), messages, isLoading: true })}
        models={[] as ModelCatalogEntry[]}
        canCancel={true}
        attachments={[]}
        hasVisionSupport={false}
        hasPDFSupport={false}
        conversationId="conv-1"
        {...baseHandlers}
      />
    )
    expect(container).toMatchSnapshot()
  })

  it('renders with pending attachments queued for the next message', () => {
    const imageAttachment: ImageAttachment = {
      id: 'att-1',
      type: 'image',
      file: new File(['fake-image-bytes'], 'screenshot.png', { type: 'image/png' }),
      preview: 'blob:http://localhost/screenshot-preview',
    }
    const { container } = render(
      <ImmersiveChatView
        chat={makeChat({ model: makeModel() })}
        models={[] as ModelCatalogEntry[]}
        canCancel={false}
        attachments={[imageAttachment]}
        hasVisionSupport={true}
        hasPDFSupport={false}
        conversationId="conv-1"
        {...baseHandlers}
      />
    )
    expect(container).toMatchSnapshot()
  })
})
