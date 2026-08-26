import { render, screen } from '@testing-library/react'
import { vi, describe, it, expect } from 'vitest'
import { DesktopAgentsStep } from '../DesktopAgentsStep'
import { DEFAULT_VOICE_SETTINGS } from '../constants'
import type { AgentFormData } from '../types'

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

describe('DesktopAgentsStep', () => {
  it('renders the agent count and the desktop-only "Add Agent" label (mobile step says "Add")', () => {
    render(
      <DesktopAgentsStep
        agents={oneAgent}
        handleAddAgent={vi.fn()}
        handleRemoveAgent={vi.fn()}
        handleAgentChange={vi.fn()}
        expandedAgents={new Set()}
        handleToggleAgentExpand={vi.fn()}
        sensors={[]}
        handleDragEnd={vi.fn()}
        voiceRoomModels={[]}
        recommendedVoices={[]}
        selectedProvider="elevenlabs"
        voiceSettings={{ ...DEFAULT_VOICE_SETTINGS }}
        language="auto"
      />,
    )

    expect(screen.getByText('1 of 6 agents')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add Agent' })).toBeInTheDocument()
  })
})
