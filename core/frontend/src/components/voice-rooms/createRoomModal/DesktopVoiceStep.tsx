import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { RotateCcw } from 'lucide-react'
import { DEFAULT_VOICE_SETTINGS } from './constants'
import type { VoiceSettingsFormState } from './types'
import type { TTSProvider, TTSModelInfo, VoiceSettings } from '@/types/voiceRoom'

interface DesktopVoiceStepProps {
  ttsProviders: TTSProvider[]
  ttsModels: TTSModelInfo[]
  selectedProvider: string
  setSelectedProvider: (v: string) => void
  voiceSettings: VoiceSettingsFormState
  setVoiceSettings: React.Dispatch<React.SetStateAction<VoiceSettingsFormState>>
  handleVoiceSettingChange: (key: keyof VoiceSettings, value: number | boolean | string) => void
}

/** Step 3 (Voice) content for the desktop dialog. */
export function DesktopVoiceStep({
  ttsProviders,
  ttsModels,
  selectedProvider,
  setSelectedProvider,
  voiceSettings,
  setVoiceSettings,
  handleVoiceSettingChange,
}: DesktopVoiceStepProps) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        {/* Provider */}
        {ttsProviders.length > 1 && (
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Provider</Label>
            <Select
              value={selectedProvider}
              onValueChange={(v) => {
                setSelectedProvider(v)
                setVoiceSettings(prev => ({ ...prev, tts_model: '' }))
              }}
            >
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Select provider">
                  {ttsProviders.find(p => p.id === selectedProvider)?.name || 'Select provider'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {ttsProviders.map((provider, index) => (
                  <SelectItem key={provider.id || index} value={provider.id}>
                    {provider.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {/* TTS Model */}
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Voice Model</Label>
          <Select
            value={ttsModels.find(m => m.model_id === voiceSettings.tts_model)?.model_id || ''}
            onValueChange={(v) => handleVoiceSettingChange('tts_model', v)}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select model">
                {ttsModels.find(m => m.model_id === voiceSettings.tts_model)?.name || 'Select model'}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {ttsModels.map((model, index) => (
                <SelectItem key={model.model_id || index} value={model.model_id}>
                  {model.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Sliders */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-4">
        {/* Speed */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">Speed</Label>
            <span className="text-sm text-muted-foreground tabular-nums">{voiceSettings.speed.toFixed(1)}x</span>
          </div>
          <Slider
            value={[voiceSettings.speed]}
            onValueChange={([v]) => handleVoiceSettingChange('speed', v)}
            min={0.5} max={2.0} step={0.1}
          />
        </div>

        {/* ElevenLabs settings */}
        {selectedProvider === 'elevenlabs' && (
          <>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">Stability</Label>
                <span className="text-sm text-muted-foreground tabular-nums">{Math.round(voiceSettings.stability * 100)}%</span>
              </div>
              <Slider
                value={[voiceSettings.stability]}
                onValueChange={([v]) => handleVoiceSettingChange('stability', v)}
                min={0} max={1} step={0.01}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">Similarity</Label>
                <span className="text-sm text-muted-foreground tabular-nums">{Math.round(voiceSettings.similarity_boost * 100)}%</span>
              </div>
              <Slider
                value={[voiceSettings.similarity_boost]}
                onValueChange={([v]) => handleVoiceSettingChange('similarity_boost', v)}
                min={0} max={1} step={0.01}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">Style</Label>
                <span className="text-sm text-muted-foreground tabular-nums">{Math.round(voiceSettings.style * 100)}%</span>
              </div>
              <Slider
                value={[voiceSettings.style]}
                onValueChange={([v]) => handleVoiceSettingChange('style', v)}
                min={0} max={1} step={0.01}
              />
            </div>
          </>
        )}
      </div>

      <button
        type="button"
        onClick={() => setVoiceSettings({
          ...DEFAULT_VOICE_SETTINGS,
          tts_model: ttsModels.length > 0 ? ttsModels[0].model_id : '',
        })}
        className="text-sm text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        Reset to defaults
      </button>
    </div>
  )
}
