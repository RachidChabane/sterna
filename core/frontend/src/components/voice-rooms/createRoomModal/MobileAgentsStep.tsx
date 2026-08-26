import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Plus, Play, Trash2 } from 'lucide-react'
import { VoiceRoomModelSelect } from '../VoiceRoomModelSelect'
import { AGENT_COLOR_PRESETS } from './constants'
import type { AgentFormData, VoiceSettingsFormState } from './types'
import type { Model } from '@/components/models/types'
import type { VoiceInfo, VoiceSettings } from '@/types/voiceRoom'

interface MobileAgentsStepProps {
  agents: AgentFormData[]
  handleAddAgent: () => void
  handleRemoveAgent: (index: number) => void
  handleAgentChange: (index: number, field: keyof AgentFormData, value: string | number | VoiceSettings | undefined) => void
  voiceRoomModels: Model[]
  recommendedVoices: VoiceInfo[]
  selectedProvider: string
  voiceSettings: VoiceSettingsFormState
}

/** Step 2 (Agents) content for the mobile sheet: simplified agent cards, no drag-drop. */
export function MobileAgentsStep({
  agents,
  handleAddAgent,
  handleRemoveAgent,
  handleAgentChange,
  voiceRoomModels,
  recommendedVoices,
  selectedProvider,
  voiceSettings,
}: MobileAgentsStepProps) {
  return (
    <div className="space-y-3">
      {/* Agent count header */}
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{agents.length} of 6 agents</span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleAddAgent}
          disabled={agents.length >= 6}
          className="h-8 gap-1"
        >
          <Plus className="h-3.5 w-3.5" />
          Add
        </Button>
      </div>

      {/* Simplified agent cards for mobile */}
      <div className="space-y-3">
        {agents.map((agent, index) => {
          const effectiveColor = agent.color || AGENT_COLOR_PRESETS[index % AGENT_COLOR_PRESETS.length]
          const selectedVoice = recommendedVoices.find(v => v.voice_id === agent.voice_id)

          return (
            <div
              key={agent.id}
              className="rounded-xl border border-border/50 p-3 space-y-3"
            >
              {/* Row 1: Color + Name + Delete */}
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full shrink-0"
                  style={{ backgroundColor: effectiveColor }}
                />
                <Input
                  value={agent.display_name}
                  onChange={(e) => handleAgentChange(index, 'display_name', e.target.value)}
                  placeholder="Agent name *"
                  className="h-9 flex-1 text-sm font-medium"
                />
                {agents.length > 1 && (
                  <button
                    type="button"
                    onClick={() => handleRemoveAgent(index)}
                    className="h-9 w-9 rounded-md flex items-center justify-center text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>

              {/* Row 2: Model */}
              <VoiceRoomModelSelect
                models={voiceRoomModels}
                value={agent.model_id}
                onValueChange={(v) => handleAgentChange(index, 'model_id', v)}
                className="w-full [&_button]:h-9 [&_button]:text-sm"
              />

              {/* Row 3: Voice + Preview */}
              <div className="flex items-center gap-2">
                <Select
                  value={agent.voice_id}
                  onValueChange={(v) => handleAgentChange(index, 'voice_id', v)}
                >
                  <SelectTrigger className="h-9 text-sm flex-1">
                    <SelectValue>{selectedVoice?.name || 'Select voice'}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {recommendedVoices.map((voice) => (
                      <SelectItem key={voice.voice_id} value={voice.voice_id}>
                        {voice.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <button
                  type="button"
                  onClick={() => {
                    // Simple inline preview using Web Speech API or audio element
                    const audio = new Audio(`/api/v1/voice-rooms/preview-voice?voice_id=${agent.voice_id}&provider=${selectedProvider}&tts_model=${voiceSettings.tts_model}`)
                    audio.play().catch(() => {})
                  }}
                  disabled={!selectedVoice}
                  className="h-9 w-9 rounded-md flex items-center justify-center shrink-0 bg-muted/50 text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-40"
                >
                  <Play className="h-4 w-4" />
                </button>
              </div>

              {/* Row 4: System prompt */}
              <textarea
                value={agent.system_prompt}
                onChange={(e) => handleAgentChange(index, 'system_prompt', e.target.value)}
                placeholder="Describe personality... *"
                rows={2}
                className="w-full rounded-lg border border-border/50 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 resize-none p-2.5 focus:outline-none focus:ring-1 focus:ring-border"
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
