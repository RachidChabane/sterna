/**
 * Tests for the pure API <-> frontend conversion helpers in api/conversations.ts.
 *
 * These are the functions that implement the three-level model distinction from
 * CLAUDE.md: chat's model vs. message's own model vs. what gets rendered.
 */

import { describe, it, expect } from 'vitest'
import {
  toFrontendConversation,
  toFrontendChat,
  toFrontendMessage,
  type APIConversationDetail,
  type APIChat,
  type APIMessage,
} from '@/api/conversations'
import type { Model } from '@/api/llm'
import { getDefaultModelParameters } from '@/config/modelParameters'

/** A persisted `tool_executions` step exactly as the backend's flexible JSON carries it. */
interface PersistedToolExecutionsStep {
  type: 'tool_executions'
  isExecuting: boolean
  executions: Array<{ isExecuting: boolean; tool_call: { id: string } }>
}

function makeApiMessage(overrides: Partial<APIMessage> = {}): APIMessage {
  return {
    id: 'msg-1',
    chat: 'chat-1',
    role: 'user',
    content: { text: 'hello' },
    sequence: 0,
    model_id: null,
    model_provider: null,
    prompt_tokens: null,
    completion_tokens: null,
    cost: null,
    tool_calls: [],
    tool_call_id: null,
    steps: [],
    metadata: {},
    is_stopped: false,
    sparks: [],
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeApiChat(overrides: Partial<APIChat> = {}): APIChat {
  return {
    id: 'chat-1',
    model_id: 'openai/gpt-4o',
    model_provider: 'openai',
    parameters: getDefaultModelParameters(),
    position: 0,
    is_disabled: false,
    is_hidden: false,
    message_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('toFrontendMessage', () => {
  it('extracts text from a plain string content', () => {
    const msg = toFrontendMessage(makeApiMessage({ content: 'plain string' }))
    expect(msg.content).toBe('plain string')
  })

  it('extracts text from a { text } object content', () => {
    const msg = toFrontendMessage(makeApiMessage({ content: { text: 'wrapped' } }))
    expect(msg.content).toBe('wrapped')
  })

  it('extracts text from a multipart array content', () => {
    const msg = toFrontendMessage(
      makeApiMessage({ content: [{ type: 'text', text: 'multipart' }] })
    )
    expect(msg.content).toBe('multipart')
  })

  it('keeps only the LAST text part when multiple text parts are present (documented overwrite behavior)', () => {
    const msg = toFrontendMessage(
      makeApiMessage({
        content: [
          { type: 'text', text: 'first' },
          { type: 'text', text: 'second' },
        ],
      })
    )
    expect(msg.content).toBe('second')
  })

  it('reconstructs an image attachment from an asset_ref part', () => {
    const msg = toFrontendMessage(
      makeApiMessage({
        content: [
          { type: 'text', text: 'see attached' },
          {
            type: 'asset_ref',
            asset_id: 'asset-1',
            filename: 'photo.png',
            mime_type: 'image/png',
            asset_type: 'image',
            size_bytes: 1234,
            download_url: '/download/asset-1',
          },
        ],
      })
    )
    expect(msg.attachments).toHaveLength(1)
    expect(msg.attachments![0]).toMatchObject({
      type: 'image',
      assetId: 'asset-1',
      assetUrl: '/download/asset-1',
    })
  })

  it('treats an SVG asset_ref as a file, not an image', () => {
    const msg = toFrontendMessage(
      makeApiMessage({
        content: [
          {
            type: 'asset_ref',
            asset_id: 'asset-2',
            filename: 'diagram.svg',
            mime_type: 'image/svg+xml',
            asset_type: 'generated',
            download_url: '/download/asset-2',
          },
        ],
      })
    )
    expect(msg.attachments![0].type).toBe('file')
  })

  it('classifies video and audio asset_ref parts', () => {
    const msg = toFrontendMessage(
      makeApiMessage({
        content: [
          {
            type: 'asset_ref',
            asset_id: 'a-video',
            filename: 'clip.mp4',
            mime_type: 'video/mp4',
            asset_type: 'generated',
            download_url: '/d/a-video',
          },
          {
            type: 'asset_ref',
            asset_id: 'a-audio',
            filename: 'clip.mp3',
            mime_type: 'audio/mpeg',
            asset_type: 'generated',
            download_url: '/d/a-audio',
          },
        ],
      })
    )
    expect(msg.attachments!.map(a => a.type)).toEqual(['video', 'audio'])
  })

  it('sets tokens to undefined when both prompt and completion tokens are 0 (documented falsy-zero behavior)', () => {
    const msg = toFrontendMessage(makeApiMessage({ prompt_tokens: 0, completion_tokens: 0 }))
    expect(msg.tokens).toBeUndefined()
  })

  it('sets tokens when prompt_tokens is non-zero', () => {
    const msg = toFrontendMessage(makeApiMessage({ prompt_tokens: 10, completion_tokens: 0 }))
    expect(msg.tokens).toEqual({ prompt: 10, completion: 0 })
  })

  it('parses cost as a float from a decimal string', () => {
    const msg = toFrontendMessage(makeApiMessage({ cost: '0.001234' }))
    expect(msg.cost).toBeCloseTo(0.001234)
  })

  it('maps is_stopped onto both is_stopped and isInterrupted', () => {
    const msg = toFrontendMessage(makeApiMessage({ is_stopped: true }))
    expect(msg.is_stopped).toBe(true)
    expect(msg.isInterrupted).toBe(true)
  })

  it('sanitizes stale isExecuting flags on persisted tool_executions steps', () => {
    const rawStep: PersistedToolExecutionsStep = {
      type: 'tool_executions',
      isExecuting: true,
      executions: [{ isExecuting: true, tool_call: { id: 't1' } }],
    }
    const msg = toFrontendMessage(makeApiMessage({ steps: [rawStep] }))
    const step = msg.steps![0]
    if (step.type !== 'tool_executions') throw new Error('expected a tool_executions step')
    expect(step.isExecuting).toBe(false)
    expect(step.executions[0].isExecuting).toBe(false)
  })

  it('sanitizes stale isStreaming flags on persisted reasoning steps', () => {
    const msg = toFrontendMessage(
      makeApiMessage({ steps: [{ type: 'reasoning', content: 'thinking', isStreaming: true }] })
    )
    const step = msg.steps![0]
    if (step.type !== 'reasoning') throw new Error('expected a reasoning step')
    expect(step.isStreaming).toBe(false)
  })

  it('extracts web_sources from metadata', () => {
    const msg = toFrontendMessage(
      makeApiMessage({ metadata: { web_sources: [{ url: 'https://x.test' }] } })
    )
    expect(msg.web_sources).toEqual([{ url: 'https://x.test' }])
  })

  it('maps persisted sparks', () => {
    const msg = toFrontendMessage(
      makeApiMessage({
        sparks: [
          { id: 's1', title: 'Chart', framework: 'react', code: 'x', version: 1 },
        ],
      })
    )
    expect(msg.sparks).toHaveLength(1)
    expect(msg.sparks![0].id).toBe('s1')
  })
})

describe('toFrontendChat — the three-level model distinction', () => {
  const chatModel: Model = {
    id: 'm-1',
    model_id: 'openai/gpt-4o',
    name: 'GPT-4o',
    provider: 'openai',
    cost_per_1m_prompt: 1,
    cost_per_1m_completion: 2,
    max_tokens: 128000,
    supports_streaming: true,
    supports_functions: true,
    supports_structured_outputs: true,
    supports_reasoning: false,
    supports_prompt_caching: true,
    supports_stream_cancellation: true,
    input_modalities: ['text'],
    is_available: true,
  }

  it('resolves the chat model via modelLookup when available', () => {
    const lookup = (id: string) => (id === chatModel.model_id ? chatModel : null)
    const chat = toFrontendChat(makeApiChat(), lookup)
    expect(chat.model?.name).toBe('GPT-4o')
  })

  it('falls back to a minimal model when modelLookup misses', () => {
    const chat = toFrontendChat(makeApiChat(), () => null)
    expect(chat.model).toMatchObject({ model_id: 'openai/gpt-4o', provider: 'openai', name: 'openai/gpt-4o' })
  })

  it('leaves model null when the chat has no model_id', () => {
    const chat = toFrontendChat(makeApiChat({ model_id: null, model_provider: null }))
    expect(chat.model).toBeNull()
  })

  it('does NOT enrich non-assistant messages with model metadata', () => {
    const apiChat = makeApiChat({
      messages: [makeApiMessage({ role: 'user', model_id: null })],
    })
    const chat = toFrontendChat(apiChat, () => chatModel)
    expect(chat.messages[0].model_id).toBeUndefined()
  })

  it('an assistant message whose model_id equals the chat model falls back to the resolved chat model when the per-message lookup misses', () => {
    // Simulates a transient cache miss: the chat-level lookup (called first, while
    // resolving `chatModel`) succeeds, but the identical per-message lookup call
    // that follows misses. This is the `messageModelId === apiChat.model_id ? chatModel : null`
    // branch in toFrontendChat.
    let callCount = 0
    const statefulLookup = (id: string) => {
      callCount += 1
      return callCount === 1 && id === chatModel.model_id ? chatModel : null
    }
    const apiChat = makeApiChat({
      model_id: chatModel.model_id,
      model_provider: chatModel.provider,
      messages: [makeApiMessage({ role: 'assistant', model_id: chatModel.model_id, model_provider: chatModel.provider })],
    })
    const chat = toFrontendChat(apiChat, statefulLookup)
    // Chat-level resolution succeeded (first lookup call).
    expect(chat.model?.name).toBe('GPT-4o')
    // Message-level lookup missed but inherited the already-resolved chat model.
    expect(chat.messages[0].model).toBe('GPT-4o')
    expect(chat.messages[0].model_id).toBe(chatModel.model_id)
  })

  it('an assistant message with a DIFFERENT model_id than the chat, and modelLookup misses, uses the raw id and does NOT inherit the chat model', () => {
    const differentModelId = 'anthropic/claude-3-opus'
    const apiChat = makeApiChat({
      model_id: chatModel.model_id,
      model_provider: chatModel.provider,
      messages: [makeApiMessage({ role: 'assistant', model_id: differentModelId, model_provider: 'anthropic' })],
    })
    const chat = toFrontendChat(apiChat, () => null)
    const msg = chat.messages[0]
    expect(msg.model_id).toBe(differentModelId)
    expect(msg.model).toBe(differentModelId) // raw id used as display name, NOT the chat's model name
    expect(msg.provider).toBe('anthropic')
  })

  it('an assistant message with a different model_id resolves full metadata when modelLookup hits', () => {
    const otherModel: Model = { ...chatModel, model_id: 'anthropic/claude-3-opus', name: 'Claude 3 Opus', provider: 'anthropic' }
    const apiChat = makeApiChat({
      model_id: chatModel.model_id,
      model_provider: chatModel.provider,
      messages: [makeApiMessage({ role: 'assistant', model_id: otherModel.model_id, model_provider: 'anthropic' })],
    })
    const lookup = (id: string) => (id === otherModel.model_id ? otherModel : chatModel)
    const chat = toFrontendChat(apiChat, lookup)
    expect(chat.messages[0].model).toBe('Claude 3 Opus')
  })

  it('an assistant message with no model_id at all falls back to the chat model when modelLookup misses', () => {
    const apiChat = makeApiChat({
      model_id: chatModel.model_id,
      model_provider: chatModel.provider,
      messages: [makeApiMessage({ role: 'assistant', model_id: null, model_provider: null })],
    })
    const chat = toFrontendChat(apiChat, () => null)
    expect(chat.messages[0].model_id).toBe(chatModel.model_id)
  })

  it('maps chat-level sparks', () => {
    const apiChat = makeApiChat({
      sparks: [{ id: 'sp1', title: 'Report', framework: 'markdown', code: '# hi', version: 1 }],
    })
    const chat = toFrontendChat(apiChat)
    expect(chat.sparks).toHaveLength(1)
    expect(chat.sparks![0].id).toBe('sp1')
  })
})

describe('toFrontendConversation', () => {
  it('maps top-level conversation fields and converts nested chats', () => {
    const detail: APIConversationDetail = {
      id: 'conv-1',
      user: 'user-1',
      name: 'My Conversation',
      is_custom_name: true,
      is_archived: false,
      is_pinned: true,
      consigliere_session_id: 'sess-1',
      message_count: 2,
      chat_count: 1,
      model_id: 'openai/gpt-4o',
      model_provider: 'openai',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
      last_message_at: null,
      chats: [makeApiChat()],
    }
    const conversation = toFrontendConversation(detail)
    expect(conversation.id).toBe('conv-1')
    expect(conversation.name).toBe('My Conversation')
    expect(conversation.isCustomName).toBe(true)
    expect(conversation.consigliereSessionId).toBe('sess-1')
    expect(conversation.chats).toHaveLength(1)
  })

  it('falls back to now() for an unparseable created_at/updated_at', () => {
    const before = Date.now()
    const detail: APIConversationDetail = {
      id: 'conv-2',
      user: 'user-1',
      name: 'Broken dates',
      is_custom_name: false,
      is_archived: false,
      is_pinned: false,
      consigliere_session_id: null,
      message_count: 0,
      chat_count: 0,
      model_id: null,
      model_provider: null,
      created_at: 'not-a-date',
      updated_at: 'also-not-a-date',
      last_message_at: null,
      chats: [],
    }
    const conversation = toFrontendConversation(detail)
    expect(conversation.createdAt.getTime()).toBeGreaterThanOrEqual(before)
    expect(conversation.updatedAt.getTime()).toBeGreaterThanOrEqual(before)
  })
})
