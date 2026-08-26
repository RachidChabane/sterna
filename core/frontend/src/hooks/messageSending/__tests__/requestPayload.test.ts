import { describe, it, expect } from 'vitest'
import { buildLLMRequestPayload } from '../requestPayload'
import { getDefaultModelParameters } from '@/config/modelParameters'
import type { Model } from '@/components/models/types'

const MODEL: Model = { model_id: 'openai/gpt-4o', name: 'GPT-4o', provider: 'openai', input_modalities: ['text'] } as Model

function baseArgs(overrides: Partial<Parameters<typeof buildLLMRequestPayload>[0]> = {}) {
  return {
    model: MODEL,
    apiMessages: [{ role: 'user' as const, content: 'hi' }],
    parameters: getDefaultModelParameters(),
    streamResponsesSetting: true,
    hasFileAttachments: false,
    voiceConversationActive: false,
    options: undefined,
    activeGroupId: 'group-1',
    chatId: 'chat-1',
    messageId: 'msg-1',
    workspaceAssets: [],
    ...overrides,
  }
}

describe('buildLLMRequestPayload', () => {
  it('carries model id, messages and conversation/chat ids', () => {
    const payload = buildLLMRequestPayload(baseArgs())
    expect(payload.model).toBe('openai/gpt-4o')
    expect(payload.messages).toEqual([{ role: 'user', content: 'hi' }])
    expect(payload.conversation_id).toBe('group-1')
    expect(payload.chat_id).toBe('chat-1')
  })

  it('falls back to the streaming setting when the parameters do not specify enable_streaming', () => {
    const params = { ...getDefaultModelParameters(), enable_streaming: undefined }
    const payload = buildLLMRequestPayload(baseArgs({ parameters: params, streamResponsesSetting: false }))
    expect(payload.stream).toBe(false)
  })

  it('omits optional sampling parameters that are undefined', () => {
    const params = { ...getDefaultModelParameters(), top_k: undefined, frequency_penalty: undefined }
    const payload = buildLLMRequestPayload(baseArgs({ parameters: params }))
    expect(payload).not.toHaveProperty('top_k')
    expect(payload).not.toHaveProperty('frequency_penalty')
  })

  it('includes optional sampling parameters that are defined, even when 0', () => {
    const params = { ...getDefaultModelParameters(), top_k: 0, presence_penalty: 0.5 }
    const payload = buildLLMRequestPayload(baseArgs({ parameters: params }))
    expect(payload.top_k).toBe(0)
    expect(payload.presence_penalty).toBe(0.5)
  })

  it('includes the file-parser plugin only when file attachments are present', () => {
    expect(buildLLMRequestPayload(baseArgs({ hasFileAttachments: false })).plugins).toBeUndefined()
    expect(buildLLMRequestPayload(baseArgs({ hasFileAttachments: true })).plugins).toEqual([{ id: 'file-parser' }])
  })

  it('includes message_id only when a tool-producing feature is enabled', () => {
    const allDisabled = {
      ...getDefaultModelParameters(),
      enable_file_tools: false,
      enable_image_generation: false,
      enable_video_generation: false,
      enable_sparks: false,
      enable_knowledge_base: false,
    }
    const withoutTools = buildLLMRequestPayload(baseArgs({ parameters: allDisabled }))
    expect(withoutTools.message_id).toBeUndefined()

    const withTools = buildLLMRequestPayload(baseArgs({ parameters: { ...allDisabled, enable_file_tools: true } }))
    expect(withTools.message_id).toBe('msg-1')
  })

  it('forwards spark fix/ignite and sterna strength overrides from options', () => {
    const payload = buildLLMRequestPayload(baseArgs({
      options: {
        sparkFixRequest: { spark_id: 's1', spark_title: 'Spark', error: 'boom' },
        sternaStrength: 'strong',
      },
    }))
    expect(payload.spark_fix_request).toEqual({ spark_id: 's1', spark_title: 'Spark', error: 'boom' })
    expect(payload.sterna_strength).toBe('strong')
    expect(payload.spark_ignite_request).toBeUndefined()
  })

  it('includes workspace_assets only when there are any', () => {
    expect(buildLLMRequestPayload(baseArgs()).workspace_assets).toBeUndefined()
    const payload = buildLLMRequestPayload(baseArgs({ workspaceAssets: [{ asset_id: 'a1', filename: 'f.txt' }] }))
    expect(payload.workspace_assets).toEqual([{ asset_id: 'a1', filename: 'f.txt' }])
  })

  it('sets enable_voice_mode only when voice conversation mode is active', () => {
    expect(buildLLMRequestPayload(baseArgs()).enable_voice_mode).toBeUndefined()
    expect(buildLLMRequestPayload(baseArgs({ voiceConversationActive: true })).enable_voice_mode).toBe(true)
  })
})
