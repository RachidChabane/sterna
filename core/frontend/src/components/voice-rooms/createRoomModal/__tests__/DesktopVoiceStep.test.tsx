import { render, screen } from '@testing-library/react'
import { vi, describe, it, expect } from 'vitest'
import { DesktopVoiceStep } from '../DesktopVoiceStep'
import { DEFAULT_VOICE_SETTINGS } from '../constants'

describe('DesktopVoiceStep', () => {
  it('shows the Style slider alongside Speed/Stability/Similarity for ElevenLabs (desktop-only, unlike the mobile step)', () => {
    render(
      <DesktopVoiceStep
        ttsProviders={[]}
        ttsModels={[]}
        selectedProvider="elevenlabs"
        setSelectedProvider={vi.fn()}
        voiceSettings={{ ...DEFAULT_VOICE_SETTINGS }}
        setVoiceSettings={vi.fn()}
        handleVoiceSettingChange={vi.fn()}
      />,
    )

    expect(screen.getByText('Speed')).toBeInTheDocument()
    expect(screen.getByText('Stability')).toBeInTheDocument()
    expect(screen.getByText('Similarity')).toBeInTheDocument()
    expect(screen.getByText('Style')).toBeInTheDocument()
  })

  it('hides the ElevenLabs-only sliders for other providers', () => {
    render(
      <DesktopVoiceStep
        ttsProviders={[]}
        ttsModels={[]}
        selectedProvider="openai"
        setSelectedProvider={vi.fn()}
        voiceSettings={{ ...DEFAULT_VOICE_SETTINGS }}
        setVoiceSettings={vi.fn()}
        handleVoiceSettingChange={vi.fn()}
      />,
    )

    expect(screen.getByText('Speed')).toBeInTheDocument()
    expect(screen.queryByText('Stability')).not.toBeInTheDocument()
    expect(screen.queryByText('Similarity')).not.toBeInTheDocument()
    expect(screen.queryByText('Style')).not.toBeInTheDocument()
  })
})
