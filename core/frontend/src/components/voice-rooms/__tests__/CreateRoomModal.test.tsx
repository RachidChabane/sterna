import { render, screen, fireEvent } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { CreateRoomModal } from '../CreateRoomModal'
import { useAuthStore } from '@/store/authStore'
import { useMediaQuery } from '@/hooks/use-media-query'
import { useAgentRoster } from '../createRoomModal/useAgentRoster'
import { useTtsProviderModels } from '../createRoomModal/useTtsProviderModels'
import { useRoomFormPopulation } from '../createRoomModal/useRoomFormPopulation'
import { useRoomSubmission } from '../createRoomModal/useRoomSubmission'
import type { AgentFormData } from '../createRoomModal/types'

// Smoke coverage for the container's composition: which step content and
// which shell (Sheet vs Dialog) render for a given viewport, and that the
// step tabs switch content. Everything each extracted hook itself does is
// covered by that hook's own tests.
vi.mock('@/store/authStore')
vi.mock('@/hooks/use-media-query')
vi.mock('../createRoomModal/useAgentRoster')
vi.mock('../createRoomModal/useTtsProviderModels')
vi.mock('../createRoomModal/useRoomFormPopulation')
vi.mock('../createRoomModal/useRoomSubmission')

const mockedUseAuthStore = vi.mocked(useAuthStore)
const mockedUseMediaQuery = vi.mocked(useMediaQuery)
const mockedUseAgentRoster = vi.mocked(useAgentRoster)
const mockedUseTtsProviderModels = vi.mocked(useTtsProviderModels)
const mockedUseRoomSubmission = vi.mocked(useRoomSubmission)

const oneAgent: AgentFormData[] = [
  {
    id: 'agent-1',
    display_name: 'Host',
    model_id: '',
    system_prompt: '',
    voice_id: '',
    voice_name: '',
    order: 1,
  },
]

function setUpMocks() {
  mockedUseAuthStore.mockReturnValue({ user: { first_name: 'Ada' } })
  mockedUseMediaQuery.mockReturnValue(false)

  mockedUseAgentRoster.mockReturnValue({
    agents: oneAgent,
    setAgents: vi.fn(),
    expandedAgents: new Set<number>(),
    handleAddAgent: vi.fn(),
    handleRemoveAgent: vi.fn(),
    handleAgentChange: vi.fn(),
    handleToggleAgentExpand: vi.fn(),
    sensors: [],
    handleDragEnd: vi.fn(),
  })

  mockedUseTtsProviderModels.mockReturnValue({
    selectedProvider: 'elevenlabs',
    setSelectedProvider: vi.fn(),
    resetVoiceValidation: vi.fn(),
    ttsProviders: [{ id: 'elevenlabs', name: 'ElevenLabs' }],
    ttsModels: [],
    ttsModelsLoaded: true,
    recommendedVoices: [],
    voiceRoomModels: [],
  })

  vi.mocked(useRoomFormPopulation).mockReturnValue(undefined)

  mockedUseRoomSubmission.mockReturnValue({
    isCreating: false,
    isGeneratingRoom: false,
    handleAIGenerate: vi.fn(),
    handleSubmit: vi.fn(),
    isFormValid: true,
    canProceedFromStep: vi.fn(() => true),
  })
}

describe('CreateRoomModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setUpMocks()
  })

  it('renders the desktop create dialog on the basics step', () => {
    render(<CreateRoomModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />)

    expect(screen.getByText('Create Voice Room')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('My Debate Room')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Continue/i })).toBeInTheDocument()
  })

  it('renders the desktop edit dialog title when editing an existing room', () => {
    render(
      <CreateRoomModal
        isOpen
        onClose={vi.fn()}
        onCreated={vi.fn()}
        roomToEdit={{ id: 'room-1', name: 'My Room' } as never}
      />,
    )

    expect(screen.getByText('Edit Voice Room')).toBeInTheDocument()
  })

  it('renders nothing distinctive when closed', () => {
    render(<CreateRoomModal isOpen={false} onClose={vi.fn()} onCreated={vi.fn()} />)

    expect(screen.queryByText('Create Voice Room')).not.toBeInTheDocument()
  })

  it('renders the mobile sheet and switches step content via the step tabs', () => {
    mockedUseMediaQuery.mockReturnValue(true)
    render(<CreateRoomModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />)

    expect(screen.getByText('Create Room')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('My Debate Room')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Agents/i }))
    expect(screen.getByText('1 of 6 agents')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Voice/i }))
    expect(screen.getByText('Voice Model')).toBeInTheDocument()
  })
})
