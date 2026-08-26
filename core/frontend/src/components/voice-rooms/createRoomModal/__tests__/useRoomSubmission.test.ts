import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useRoomSubmission, type RoomFormSnapshot, type RoomFormResetSetters } from '../useRoomSubmission'
import { DEFAULT_VOICE_SETTINGS, createDefaultAgent } from '../constants'
import type { AgentFormData } from '../types'
import type { VoiceRoom } from '@/types/voiceRoom'

const toast = vi.fn()
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast }) }))

const createRoom = vi.fn()
const updateRoom = vi.fn()
const generateRoom = vi.fn()
vi.mock('@/store/voiceRoomStore', () => ({
  default: () => ({ createRoom, updateRoom, generateRoom, isGeneratingRoom: false }),
}))

function agent(overrides: Partial<AgentFormData> = {}): AgentFormData {
  return { ...createDefaultAgent(1), display_name: 'Host', model_id: 'openai/gpt-4o-mini', system_prompt: 'Be nice', ...overrides }
}

function baseForm(overrides: Partial<RoomFormSnapshot> = {}): RoomFormSnapshot {
  return {
    name: 'My Room',
    description: '',
    userName: '',
    language: 'auto',
    agents: [agent()],
    voiceSettings: { ...DEFAULT_VOICE_SETTINGS, tts_model: 'model-1' },
    selectedProvider: 'elevenlabs',
    isEditMode: false,
    roomToEdit: null,
    defaultUserName: '',
    aiDescription: '',
    ...overrides,
  }
}

function noopSetters(): RoomFormResetSetters {
  return {
    setName: vi.fn(), setDescription: vi.fn(), setUserName: vi.fn(), setLanguage: vi.fn(),
    setVoiceSettings: vi.fn(), setAgents: vi.fn(), setAiGenerateOpen: vi.fn(), setAiDescription: vi.fn(),
  }
}

describe('useRoomSubmission — validation', () => {
  it('isFormValid requires a room name and every agent to be fully filled in', () => {
    const { result, rerender } = renderHook(
      ({ form }) => useRoomSubmission(form, noopSetters(), vi.fn()),
      { initialProps: { form: baseForm() } }
    )
    expect(result.current.isFormValid).toBe(true)

    rerender({ form: baseForm({ name: '' }) })
    expect(result.current.isFormValid).toBe(false)

    rerender({ form: baseForm({ agents: [agent({ display_name: '' })] }) })
    expect(result.current.isFormValid).toBe(false)
  })

  it('canProceedFromStep gates step 1 on the name and step 2 on complete agents', () => {
    const { result } = renderHook(() => useRoomSubmission(baseForm({ name: '' }), noopSetters(), vi.fn()))
    expect(result.current.canProceedFromStep(1)).toBe(false)
    expect(result.current.canProceedFromStep(3)).toBe(true)
  })

  it('canProceedFromStep(2) is false when any agent is missing a required field', () => {
    const { result } = renderHook(() =>
      useRoomSubmission(baseForm({ agents: [agent(), agent({ model_id: '' })] }), noopSetters(), vi.fn())
    )
    expect(result.current.canProceedFromStep(2)).toBe(false)
  })
})

describe('useRoomSubmission — handleSubmit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('rejects duplicate agent display names (case-insensitive) without calling createRoom', async () => {
    const form = baseForm({ agents: [agent({ display_name: 'Host' }), agent({ display_name: 'HOST' })] })
    const { result } = renderHook(() => useRoomSubmission(form, noopSetters(), vi.fn()))

    await act(async () => { await result.current.handleSubmit() })

    expect(createRoom).not.toHaveBeenCalled()
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Duplicate agent names', variant: 'destructive' }))
  })

  it('calls createRoom with agents carrying room-level voice settings and a fallback color', async () => {
    createRoom.mockResolvedValue({ id: 'room-1', name: 'My Room' })
    const onCreated = vi.fn()
    const form = baseForm({ agents: [agent({ color: undefined })] })
    const { result } = renderHook(() => useRoomSubmission(form, noopSetters(), onCreated))

    await act(async () => { await result.current.handleSubmit() })

    expect(createRoom).toHaveBeenCalledTimes(1)
    const [payload] = createRoom.mock.calls[0]
    expect(payload.name).toBe('My Room')
    expect(payload.agents[0].voice_settings.tts_provider).toBe('elevenlabs')
    expect(payload.agents[0].color).toBeTruthy()
    expect(onCreated).toHaveBeenCalledWith({ id: 'room-1', name: 'My Room' })
  })

  it('calls updateRoom (with agent ids preserved) when editing an existing room', async () => {
    updateRoom.mockResolvedValue({ id: 'room-1', name: 'My Room' })
    // Only `.id` is read by handleSubmit's edit path; the rest just satisfies VoiceRoom's shape.
    const roomToEdit: VoiceRoom = {
      id: 'room-1',
      name: 'My Room',
      user_id: 'user-1',
      agents: [],
      language: 'en',
      max_response_tokens: 500,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    }
    const form = baseForm({ isEditMode: true, roomToEdit })
    const { result } = renderHook(() => useRoomSubmission(form, noopSetters(), vi.fn()))

    await act(async () => { await result.current.handleSubmit() })

    expect(updateRoom).toHaveBeenCalledTimes(1)
    const [roomId, payload] = updateRoom.mock.calls[0]
    expect(roomId).toBe('room-1')
    expect(payload.agents[0].id).toBe(form.agents[0].id)
  })

  it('does nothing when the room name or a required agent field is empty', async () => {
    const form = baseForm({ name: '' })
    const { result } = renderHook(() => useRoomSubmission(form, noopSetters(), vi.fn()))

    await act(async () => { await result.current.handleSubmit() })

    expect(createRoom).not.toHaveBeenCalled()
  })
})
