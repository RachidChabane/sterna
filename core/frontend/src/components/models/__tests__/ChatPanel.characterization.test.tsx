/**
 * Characterization tests: record ChatPanel's current rendered output for a
 * set of representative prop/store states. A snapshot diff means the
 * rendered output changed — investigate before updating the snapshot.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import ChatPanel from '../ChatPanel'
import type { Message } from '../types'
import type { Model } from '@/api/llm'

// jsdom does not implement Element.scrollTo — ChatPanel's auto-scroll effect
// calls it inside a requestAnimationFrame callback, after the test's own
// assertions have already run.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = vi.fn()
}

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

vi.mock('@/api/conversations', () => ({
  conversationsAPI: {
    deleteMessage: vi.fn(),
  },
}))

vi.mock('@/api/assets', () => ({
  assetsAPI: {
    download: vi.fn(),
    upload: vi.fn(),
  },
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

describe('ChatPanel — empty states', () => {
  it('shows suggested questions when no model and no messages (default mode)', () => {
    const { container } = render(
      <ChatPanel
        model={null}
        models={[]}
        messages={[]}
        isLoading={false}
        onModelSelect={vi.fn()}
        onSendMessage={vi.fn()}
        syncMode={false}
      />
    )
    expect(container).toMatchSnapshot()
  })

  it('shows the "select a model" placeholder when no model in sync mode', () => {
    const { container } = render(
      <ChatPanel
        model={null}
        models={[]}
        messages={[]}
        isLoading={false}
        onModelSelect={vi.fn()}
        onSendMessage={vi.fn()}
        syncMode={true}
      />
    )
    expect(container).toMatchSnapshot()
  })

  it('shows a model-specific empty state once a model is selected in sync mode', () => {
    const { container } = render(
      <ChatPanel
        model={makeModel()}
        models={[makeModel()]}
        messages={[]}
        isLoading={false}
        onModelSelect={vi.fn()}
        onSendMessage={vi.fn()}
        syncMode={true}
      />
    )
    expect(container).toMatchSnapshot()
  })
})

describe('ChatPanel — conversation states', () => {
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
      <ChatPanel
        model={makeModel()}
        models={[makeModel()]}
        messages={messages}
        isLoading={false}
        onModelSelect={vi.fn()}
        onSendMessage={vi.fn()}
        syncMode={false}
      />
    )
    expect(container).toMatchSnapshot()
  })

  it('renders the loading state while a response is streaming in', () => {
    const messages: Message[] = [
      makeMessage({ role: 'user', content: 'Tell me a joke', message_id: 'msg-1' }),
    ]
    const { container } = render(
      <ChatPanel
        model={makeModel()}
        models={[makeModel()]}
        messages={messages}
        isLoading={true}
        onModelSelect={vi.fn()}
        onSendMessage={vi.fn()}
        syncMode={false}
        canCancel={true}
        onCancel={vi.fn()}
      />
    )
    expect(container).toMatchSnapshot()
  })

  it('shows the interrupted-response warning when the last assistant message errored', () => {
    const messages: Message[] = [
      makeMessage({ role: 'user', content: 'Summarize this document', message_id: 'msg-1' }),
      makeMessage({
        role: 'assistant',
        content: '',
        message_id: 'msg-2',
        error: 'The model ran out of credits.',
        errorCode: 'insufficient_credits',
        isError: true,
      }),
    ]
    const { container } = render(
      <ChatPanel
        model={makeModel()}
        models={[makeModel()]}
        messages={messages}
        isLoading={false}
        onModelSelect={vi.fn()}
        onSendMessage={vi.fn()}
        syncMode={false}
      />
    )
    expect(container).toMatchSnapshot()
  })
})

describe('ChatPanel — disabled and hidden chat flags', () => {
  it('renders with disabledChat=true', () => {
    const { container } = render(
      <ChatPanel
        model={makeModel()}
        models={[makeModel()]}
        messages={[]}
        isLoading={false}
        onModelSelect={vi.fn()}
        onSendMessage={vi.fn()}
        syncMode={false}
        disabledChat={true}
      />
    )
    expect(container).toMatchSnapshot()
  })

  it('renders with hiddenChat=true', () => {
    const { container } = render(
      <ChatPanel
        model={makeModel()}
        models={[makeModel()]}
        messages={[]}
        isLoading={false}
        onModelSelect={vi.fn()}
        onSendMessage={vi.fn()}
        syncMode={false}
        hiddenChat={true}
      />
    )
    expect(container).toMatchSnapshot()
  })
})
