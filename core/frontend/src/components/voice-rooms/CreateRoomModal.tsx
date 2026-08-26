import { useState, useMemo } from 'react'
import { useMediaQuery } from '@/hooks/use-media-query'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DndContext,
  closestCenter,
} from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { Plus, ChevronRight, ChevronLeft, RotateCcw, Play, Loader2, Globe, Sparkles, Settings2, Users, X, Trash2 } from 'lucide-react'
import { AgentForm } from './createRoomModal/AgentForm'
import { LanguageFlag } from './createRoomModal/LanguageFlag'
import { VoiceRoomModelSelect } from './VoiceRoomModelSelect'
import { useAgentRoster } from './createRoomModal/useAgentRoster'
import { useTtsProviderModels } from './createRoomModal/useTtsProviderModels'
import { useRoomFormPopulation } from './createRoomModal/useRoomFormPopulation'
import { useRoomSubmission } from './createRoomModal/useRoomSubmission'
import { AGENT_COLOR_PRESETS, DEFAULT_VOICE_SETTINGS } from './createRoomModal/constants'
import type { RoomPreset, VoiceSettingsFormState } from './createRoomModal/types'
import { useAuthStore } from '@/store/authStore'
import type { VoiceRoom, VoiceSettings } from '@/types/voiceRoom'
import { cn } from '@/lib/utils'

export type { RoomPreset } from './createRoomModal/types'

interface CreateRoomModalProps {
  isOpen: boolean
  onClose: () => void
  onCreated: (room: VoiceRoom) => void
  roomToEdit?: VoiceRoom | null // If provided, modal is in edit mode
  preset?: RoomPreset | null // If provided, pre-fills the form
}

const MOBILE_STEPS = [
  { id: 1, label: 'Basics', icon: Sparkles },
  { id: 2, label: 'Agents', icon: Users },
  { id: 3, label: 'Voice', icon: Settings2 },
]

export function CreateRoomModal({ isOpen, onClose, onCreated, roomToEdit, preset }: CreateRoomModalProps) {
  const { user } = useAuthStore()
  const isMobile = useMediaQuery('(max-width: 640px)')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [userName, setUserName] = useState('')
  const [language, setLanguage] = useState('auto')
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettingsFormState>({ ...DEFAULT_VOICE_SETTINGS })
  const [aiGenerateOpen, setAiGenerateOpen] = useState(false)
  const [aiDescription, setAiDescription] = useState('')
  const [mobileStep, setMobileStep] = useState(1)

  const isEditMode = !!roomToEdit

  const {
    agents, setAgents, expandedAgents,
    handleAddAgent, handleRemoveAgent, handleAgentChange, handleToggleAgentExpand,
    sensors, handleDragEnd,
  } = useAgentRoster()

  const {
    selectedProvider, setSelectedProvider, resetVoiceValidation,
    ttsProviders, ttsModels, recommendedVoices, voiceRoomModels,
  } = useTtsProviderModels(isOpen, setAgents, voiceSettings, setVoiceSettings)

  // Get available languages for the selected TTS model
  const availableLanguages = useMemo(() => {
    const selectedModel = ttsModels.find(m => m.model_id === voiceSettings.tts_model)
    return selectedModel?.languages || []
  }, [ttsModels, voiceSettings.tts_model])

  // Get default user name from auth store (first name only)
  const defaultUserName = user?.first_name || ''

  useRoomFormPopulation(
    isOpen, roomToEdit, preset, defaultUserName, recommendedVoices, agents, resetVoiceValidation,
    { setName, setDescription, setUserName, setLanguage, setVoiceSettings, setSelectedProvider, setAgents, setMobileStep },
  )

  const { isCreating, isGeneratingRoom, handleAIGenerate, handleSubmit, isFormValid, canProceedFromStep } = useRoomSubmission(
    { name, description, userName, language, agents, voiceSettings, selectedProvider, isEditMode, roomToEdit, defaultUserName, aiDescription },
    { setName, setDescription, setUserName, setLanguage, setVoiceSettings, setAgents, setAiGenerateOpen, setAiDescription },
    onCreated,
  )

  const handleVoiceSettingChange = (key: keyof VoiceSettings, value: number | boolean | string) => {
    setVoiceSettings(prev => ({ ...prev, [key]: value }))
  }

  // Render mobile step content
  const renderMobileStepContent = () => {
    switch (mobileStep) {
      case 1:
        return (
          <div className="space-y-4">
            {/* AI Generate - only in create mode */}
            {!isEditMode && (
              <div className="rounded-xl border border-accent-brand/40 bg-gradient-to-br from-accent-brand/10 via-accent-brand/5 to-transparent p-3 space-y-2.5">
                <p className="text-sm font-medium text-foreground">Generate with AI</p>
                <textarea
                  value={aiDescription}
                  onChange={(e) => setAiDescription(e.target.value)}
                  placeholder="A podcast with a host and two guests..."
                  rows={2}
                  disabled={isGeneratingRoom}
                  className="w-full rounded-lg border border-accent-brand/20 bg-background/50 shadow-none focus:outline-none focus:border-accent-brand/50 text-sm text-foreground placeholder:text-muted-foreground/50 resize-none p-3"
                />
                {aiDescription.trim() && (
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleAIGenerate}
                    disabled={isGeneratingRoom}
                    className="w-full btn-premium h-9"
                  >
                    {isGeneratingRoom ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Generating...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4 mr-2" />
                        Generate Room
                      </>
                    )}
                  </Button>
                )}
              </div>
            )}

            {/* Basic Fields */}
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Room Name *</Label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="My Debate Room"
                  className="h-10 text-base"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Your Name</Label>
                <Input
                  value={userName}
                  onChange={(e) => setUserName(e.target.value)}
                  placeholder="How agents address you"
                  className="h-10 text-base"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Description</Label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What's this room about?"
                  rows={2}
                  className="w-full rounded-lg border border-border bg-transparent text-base text-foreground placeholder:text-muted-foreground/50 resize-none p-3 focus:outline-none focus:ring-1 focus:ring-border"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Language</Label>
                <Select value={language} onValueChange={setLanguage}>
                  <SelectTrigger className="h-10 text-base">
                    <SelectValue>
                      <div className="flex items-center gap-2">
                        {language === 'auto' ? (
                          <>
                            <Globe className="h-4 w-4 text-muted-foreground" />
                            <span>Auto-detect</span>
                          </>
                        ) : (
                          <>
                            <LanguageFlag countryCode={availableLanguages.find(l => l.language_id === language)?.country_code || ''} size={16} />
                            <span>{availableLanguages.find(l => l.language_id === language)?.name || language}</span>
                          </>
                        )}
                      </div>
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent className="max-h-[300px]">
                    <SelectItem value="auto">
                      <div className="flex items-center gap-2">
                        <Globe className="h-4 w-4 text-muted-foreground" />
                        <span>Auto-detect</span>
                      </div>
                    </SelectItem>
                    {availableLanguages.map((lang) => (
                      <SelectItem key={lang.language_id} value={lang.language_id}>
                        <div className="flex items-center gap-2">
                          <LanguageFlag countryCode={lang.country_code} size={16} />
                          <span>{lang.name}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        )

      case 2:
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

      case 3:
        return (
          <div className="space-y-4">
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
                  <SelectTrigger className="h-10 text-base">
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
                <SelectTrigger className="h-10 text-base">
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
              </>
            )}

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

      default:
        return null
    }
  }

  // Render desktop step content (enhanced version of mobile)
  const renderDesktopStepContent = () => {
    switch (mobileStep) {
      case 1:
        return (
          <div className="h-full flex flex-col gap-5">
            {/* AI Generate - only in create mode */}
            {!isEditMode && (
              <div className="shrink-0 rounded-xl border border-accent-brand/40 bg-gradient-to-br from-accent-brand/10 via-accent-brand/5 to-transparent p-4 space-y-3">
                <div>
                  <p className="text-sm font-medium text-foreground">Generate with AI</p>
                  <p className="text-xs text-muted-foreground">Describe your room and we'll configure it for you</p>
                </div>
                <textarea
                  value={aiDescription}
                  onChange={(e) => setAiDescription(e.target.value)}
                  placeholder="A podcast with a host and two guests discussing technology trends..."
                  rows={2}
                  disabled={isGeneratingRoom}
                  className="w-full rounded-lg border border-accent-brand/20 bg-background/50 shadow-none focus:outline-none focus:border-accent-brand/50 focus:ring-1 focus:ring-accent-brand/20 text-sm text-foreground placeholder:text-muted-foreground/50 resize-none p-3"
                />
                {aiDescription.trim() && (
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleAIGenerate}
                    disabled={isGeneratingRoom}
                    className="btn-premium h-8"
                  >
                    {isGeneratingRoom ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                        Generating...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-3.5 w-3.5 mr-1.5" />
                        Generate Room
                      </>
                    )}
                  </Button>
                )}
              </div>
            )}

            {/* Basic Fields - 2 column grid on desktop */}
            <div className="grid grid-cols-2 gap-4 shrink-0">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Room Name *</Label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="My Debate Room"
                  className="h-9"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Your Name</Label>
                <Input
                  value={userName}
                  onChange={(e) => setUserName(e.target.value)}
                  placeholder="How agents address you"
                  className="h-9"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Language</Label>
                <Select value={language} onValueChange={setLanguage}>
                  <SelectTrigger className="h-9">
                    <SelectValue>
                      <div className="flex items-center gap-2">
                        {language === 'auto' ? (
                          <>
                            <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                            <span>Auto-detect</span>
                          </>
                        ) : (
                          <>
                            <LanguageFlag countryCode={availableLanguages.find(l => l.language_id === language)?.country_code || ''} size={14} />
                            <span>{availableLanguages.find(l => l.language_id === language)?.name || language}</span>
                          </>
                        )}
                      </div>
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent className="max-h-[300px]">
                    <SelectItem value="auto">
                      <div className="flex items-center gap-2">
                        <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                        <span>Auto-detect</span>
                      </div>
                    </SelectItem>
                    {availableLanguages.map((lang) => (
                      <SelectItem key={lang.language_id} value={lang.language_id}>
                        <div className="flex items-center gap-2">
                          <LanguageFlag countryCode={lang.country_code} size={14} />
                          <span>{lang.name}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Description - fills remaining space */}
            <div className="flex-1 flex flex-col space-y-1.5 min-h-0">
              <Label className="text-xs text-muted-foreground shrink-0">Description</Label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What's this room about?"
                className="flex-1 w-full rounded-lg border border-border bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 resize-none p-3 focus:outline-none focus:ring-1 focus:ring-border"
              />
            </div>
          </div>
        )

      case 2:
        return (
          <div className="space-y-4">
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
                Add Agent
              </Button>
            </div>

            {/* Agent cards with drag-drop */}
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={agents.map(a => a.id)}
                strategy={verticalListSortingStrategy}
              >
                <div className="space-y-2">
                  {agents.map((agent, index) => (
                    <AgentForm
                      key={agent.id}
                      agent={agent}
                      index={index}
                      agentCount={agents.length}
                      models={voiceRoomModels}
                      recommendedVoices={recommendedVoices}
                      onAgentChange={handleAgentChange}
                      onRemoveAgent={handleRemoveAgent}
                      isExpanded={expandedAgents.has(index)}
                      onToggleExpand={() => handleToggleAgentExpand(index)}
                      selectedProvider={selectedProvider}
                      voiceSettings={voiceSettings}
                      language={language}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          </div>
        )

      case 3:
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

      default:
        return null
    }
  }

  // Mobile UI - Full screen sheet with steps
  if (isMobile) {
    return (
      <Sheet open={isOpen} onOpenChange={onClose}>
        <SheetContent side="bottom" className="h-[85vh] rounded-t-2xl p-0 flex flex-col [&>button]:hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
            <div className="flex items-center gap-3">
              {mobileStep > 1 && (
                <button
                  onClick={() => setMobileStep(mobileStep - 1)}
                  className="p-1 -ml-1 rounded-md text-muted-foreground hover:text-foreground"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
              )}
              <SheetTitle className="text-base">
                {isEditMode ? 'Edit Room' : 'Create Room'}
              </SheetTitle>
            </div>
            <button
              onClick={onClose}
              className="p-1 -mr-1 rounded-md text-muted-foreground hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Step indicator */}
          <div className="flex items-center justify-center gap-2 py-3 border-b shrink-0">
            {MOBILE_STEPS.map((step) => {
              const StepIcon = step.icon
              const isActive = mobileStep === step.id
              const isCompleted = mobileStep > step.id

              return (
                <button
                  key={step.id}
                  onClick={() => setMobileStep(step.id)}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                    isActive
                      ? "bg-accent-brand/15 text-accent-brand"
                      : isCompleted
                        ? "bg-muted/50 text-foreground"
                        : "text-muted-foreground"
                  )}
                >
                  <StepIcon className="h-3.5 w-3.5" />
                  {step.label}
                </button>
              )
            })}
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-4 py-4">
            <div
              key={mobileStep}
              className="animate-in fade-in-0 slide-in-from-right-4 duration-200"
            >
              {renderMobileStepContent()}
            </div>
          </div>

          {/* Footer */}
          <div className="shrink-0 border-t p-4 bg-background">
            {mobileStep < 3 ? (
              <Button
                onClick={() => setMobileStep(mobileStep + 1)}
                disabled={!canProceedFromStep(mobileStep)}
                className="w-full h-11"
              >
                Continue
              </Button>
            ) : (
              <Button
                onClick={handleSubmit}
                disabled={isCreating || !isFormValid}
                className="w-full h-11"
              >
                {isCreating
                  ? isEditMode ? 'Saving...' : 'Creating...'
                  : isEditMode ? 'Save Changes' : 'Create Room'}
              </Button>
            )}
          </div>
        </SheetContent>
      </Sheet>
    )
  }

  // Desktop UI - Step-based dialog
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl h-[85vh] max-h-[700px] p-0 gap-0 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b shrink-0">
          <DialogTitle className="text-lg font-semibold">
            {isEditMode ? 'Edit Voice Room' : 'Create Voice Room'}
          </DialogTitle>
        </div>

        {/* Step indicator */}
        <div className="flex items-center justify-center gap-3 py-3 border-b shrink-0 bg-muted/30">
          {MOBILE_STEPS.map((step) => {
            const StepIcon = step.icon
            const isActive = mobileStep === step.id
            const isCompleted = mobileStep > step.id

            return (
              <button
                key={step.id}
                onClick={() => setMobileStep(step.id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                  isActive
                    ? "bg-accent-brand/15 text-accent-brand"
                    : isCompleted
                      ? "bg-background text-foreground hover:bg-muted/50"
                      : "text-muted-foreground hover:bg-muted/50"
                )}
              >
                <StepIcon className="h-4 w-4" />
                {step.label}
              </button>
            )
          })}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5 min-h-0">
          <div
            key={mobileStep}
            className="h-full animate-in fade-in-0 slide-in-from-right-4 duration-200"
          >
            {renderDesktopStepContent()}
          </div>
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t px-6 py-4 flex items-center justify-between bg-background">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <div className="flex items-center gap-2">
            {mobileStep > 1 && (
              <Button
                variant="outline"
                onClick={() => setMobileStep(mobileStep - 1)}
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Back
              </Button>
            )}
            {mobileStep < 3 ? (
              <Button
                onClick={() => setMobileStep(mobileStep + 1)}
                disabled={!canProceedFromStep(mobileStep)}
              >
                Continue
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            ) : (
              <Button
                onClick={handleSubmit}
                disabled={isCreating || !isFormValid}
              >
                {isCreating
                  ? isEditMode ? 'Saving...' : 'Creating...'
                  : isEditMode ? 'Save Changes' : 'Create Room'}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
