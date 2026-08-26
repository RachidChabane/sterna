import { useEffect, useCallback, memo, type CSSProperties } from 'react'
import { useVoicePreview } from '@/hooks/useVoicePreview'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Trash2, ChevronRight, Play, Pause, Loader2, GripVertical } from 'lucide-react'
import { VoiceRoomModelSelect } from '../VoiceRoomModelSelect'
import type { VoiceSettings, TTSProviderId } from '@/types/voiceRoom'
import type { Model } from '@/components/models/types'
import { cn } from '@/lib/utils'
import { AGENT_COLOR_PRESETS } from './constants'
import type { AgentFormData, VoiceSettingsFormState } from './types'

// Memoized agent form to prevent re-renders when other agents change
export interface AgentFormProps {
  agent: AgentFormData
  index: number
  agentCount: number
  models: Model[]
  recommendedVoices: import('@/types/voiceRoom').VoiceInfo[]
  onAgentChange: (index: number, field: keyof AgentFormData, value: string | number | VoiceSettings | undefined) => void
  onRemoveAgent: (index: number) => void
  isExpanded: boolean
  onToggleExpand: () => void
  // For voice preview
  selectedProvider: string
  voiceSettings: VoiceSettingsFormState
  language: string
}

export const AgentForm = memo(function AgentForm({
  agent,
  index,
  agentCount,
  models,
  recommendedVoices,
  onAgentChange,
  onRemoveAgent,
  isExpanded,
  onToggleExpand,
  selectedProvider,
  voiceSettings,
  language,
}: AgentFormProps) {
  // Use shared voice preview hook
  const {
    playingVoiceId,
    isLoadingPreview,
    playPreview,
    cleanup,
  } = useVoicePreview({
    provider: selectedProvider as TTSProviderId,
    voices: recommendedVoices,
    language,
    ttsModel: voiceSettings.tts_model,
    speed: voiceSettings.speed,
  })

  // Sortable hook for drag-and-drop
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: agent.id })

  const handlePlayPreview = useCallback((e: React.MouseEvent, voiceId: string) => {
    e.preventDefault()
    e.stopPropagation()
    playPreview(voiceId)
  }, [playPreview])

  // Cleanup audio on unmount
  useEffect(() => {
    return cleanup
  }, [cleanup])

  // Create stable callbacks for this specific agent
  const handleModelChange = useCallback((value: string) => {
    onAgentChange(index, 'model_id', value)
  }, [index, onAgentChange])

  const handleDisplayNameChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    onAgentChange(index, 'display_name', e.target.value)
  }, [index, onAgentChange])

  const handleVoiceChange = useCallback((value: string) => {
    onAgentChange(index, 'voice_id', value)
  }, [index, onAgentChange])

  const handleSystemPromptChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onAgentChange(index, 'system_prompt', e.target.value)
  }, [index, onAgentChange])

  const handleColorChange = useCallback((color: string | undefined) => {
    onAgentChange(index, 'color', color)
  }, [index, onAgentChange])

  // Get effective color (custom or auto-assigned based on index)
  const effectiveColor = agent.color || AGENT_COLOR_PRESETS[index % AGENT_COLOR_PRESETS.length]

  const handleRemove = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onRemoveAgent(index)
  }, [index, onRemoveAgent])

  // Get model info for summary display
  const selectedModel = models.find(m => m.model_id === agent.model_id)
  const selectedVoice = recommendedVoices.find(v => v.voice_id === agent.voice_id)

  // Sortable style
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "group rounded-xl transition-all duration-200",
        "hover:bg-muted/20",
        isDragging && "opacity-50 bg-muted/30 shadow-lg z-50"
      )}
    >
      {/* Main row - responsive layout */}
      <div className="px-3 md:px-4 py-3">
        {/* Desktop: 7-column grid (added drag handle) */}
        <div className="hidden md:grid grid-cols-[auto_auto_minmax(5rem,1fr)_minmax(8rem,2fr)_minmax(4rem,1fr)_auto_auto] items-center gap-3">
          {/* Drag handle */}
          <button
            type="button"
            className="w-5 h-5 flex items-center justify-center cursor-grab active:cursor-grabbing text-muted-foreground/40 hover:text-muted-foreground transition-colors touch-none"
            {...attributes}
            {...listeners}
          >
            <GripVertical className="h-4 w-4" />
          </button>

          {/* Expand toggle + Color indicator */}
          <div className="flex items-center gap-2">
            <Collapsible open={isExpanded} onOpenChange={onToggleExpand}>
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className={cn(
                    "w-5 h-5 flex items-center justify-center transition-colors",
                    isExpanded ? "text-accent-brand" : "text-muted-foreground/60 hover:text-foreground"
                  )}
                >
                  <ChevronRight className={cn("h-4 w-4 transition-transform duration-200", isExpanded && "rotate-90")} />
                </button>
              </CollapsibleTrigger>
            </Collapsible>

            {/* Color indicator */}
            <div
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: effectiveColor }}
              title="Agent color"
            />
          </div>

          {/* Name */}
          <Input
            value={agent.display_name}
            onChange={handleDisplayNameChange}
            placeholder="Agent name"
            className="h-7 text-sm font-medium bg-transparent border-0 px-0 focus:ring-0 focus-visible:ring-0 focus-visible:ring-offset-0 focus:outline-none placeholder:text-muted-foreground/40"
            onClick={(e) => e.stopPropagation()}
          />

          {/* Model */}
          <div onClick={(e) => e.stopPropagation()}>
            <VoiceRoomModelSelect
              models={models}
              value={agent.model_id}
              onValueChange={handleModelChange}
              className="w-full [&_button]:h-7 [&_button]:w-full [&_button]:text-sm [&_button]:bg-transparent [&_button]:border-0 [&_button]:hover:bg-muted/60 [&_button]:rounded-md [&_button]:px-2 [&_button]:text-muted-foreground [&_button]:hover:text-foreground"
            />
          </div>

          {/* Voice */}
          <Select value={agent.voice_id} onValueChange={handleVoiceChange}>
            <SelectTrigger
              className="h-7 w-full text-sm bg-transparent border-0 hover:bg-muted/60 rounded-md px-2 text-muted-foreground hover:text-foreground"
              onClick={(e) => e.stopPropagation()}
            >
              <SelectValue>{selectedVoice?.name || 'Voice'}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {recommendedVoices.map((voice) => (
                <SelectItem key={voice.voice_id} value={voice.voice_id}>
                  {voice.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Preview */}
          <button
            type="button"
            onClick={(e) => handlePlayPreview(e, agent.voice_id)}
            disabled={!selectedVoice || isLoadingPreview}
            className={cn(
              "h-7 w-7 rounded-md flex items-center justify-center transition-all flex-shrink-0",
              playingVoiceId === agent.voice_id
                ? "bg-accent-brand text-white"
                : "text-muted-foreground/60 hover:text-foreground hover:bg-muted/60 disabled:opacity-30 disabled:hover:bg-transparent"
            )}
          >
            {isLoadingPreview ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : playingVoiceId === agent.voice_id ? (
              <Pause className="h-3 w-3" />
            ) : (
              <Play className="h-3 w-3 ml-0.5" />
            )}
          </button>

          {/* Delete */}
          {agentCount > 1 ? (
            <button
              type="button"
              onClick={handleRemove}
              className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground/40 hover:text-destructive hover:bg-destructive/10 transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          ) : (
            <div className="w-7 flex-shrink-0" />
          )}
        </div>

        {/* Mobile: Stacked layout */}
        <div className="md:hidden space-y-2">
          {/* Row 1: Drag + Expand + Color + Name + Delete */}
          <div className="flex items-center gap-2">
            {/* Drag handle */}
            <button
              type="button"
              className="w-5 h-5 flex items-center justify-center cursor-grab active:cursor-grabbing text-muted-foreground/40 hover:text-muted-foreground transition-colors touch-none flex-shrink-0"
              {...attributes}
              {...listeners}
            >
              <GripVertical className="h-4 w-4" />
            </button>

            <Collapsible open={isExpanded} onOpenChange={onToggleExpand}>
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className={cn(
                    "w-5 h-5 flex items-center justify-center transition-colors flex-shrink-0",
                    isExpanded ? "text-accent-brand" : "text-muted-foreground/60 hover:text-foreground"
                  )}
                >
                  <ChevronRight className={cn("h-4 w-4 transition-transform duration-200", isExpanded && "rotate-90")} />
                </button>
              </CollapsibleTrigger>
            </Collapsible>

            <div
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: effectiveColor }}
            />

            <Input
              value={agent.display_name}
              onChange={handleDisplayNameChange}
              placeholder="Agent name"
              className="h-8 flex-1 text-sm font-medium bg-transparent border-0 px-1 focus:ring-0 focus-visible:ring-0 focus-visible:ring-offset-0 focus:outline-none placeholder:text-muted-foreground/40"
              onClick={(e) => e.stopPropagation()}
            />

            {agentCount > 1 && (
              <button
                type="button"
                onClick={handleRemove}
                className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground/40 hover:text-destructive hover:bg-destructive/10 transition-colors flex-shrink-0"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Row 2: Model + Voice + Preview */}
          <div className="flex items-center gap-2 pl-7">
            <div onClick={(e) => e.stopPropagation()} className="flex-1 min-w-0">
              <VoiceRoomModelSelect
                models={models}
                value={agent.model_id}
                onValueChange={handleModelChange}
                className="w-full [&_button]:h-8 [&_button]:w-full [&_button]:text-sm [&_button]:bg-muted/30 [&_button]:border-0 [&_button]:hover:bg-muted/60 [&_button]:rounded-md [&_button]:px-2"
              />
            </div>

            <Select value={agent.voice_id} onValueChange={handleVoiceChange}>
              <SelectTrigger
                className="h-8 w-24 text-sm bg-muted/30 border-0 hover:bg-muted/60 rounded-md px-2 flex-shrink-0"
                onClick={(e) => e.stopPropagation()}
              >
                <SelectValue>{selectedVoice?.name || 'Voice'}</SelectValue>
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
              onClick={(e) => handlePlayPreview(e, agent.voice_id)}
              disabled={!selectedVoice || isLoadingPreview}
              className={cn(
                "h-8 w-8 rounded-md flex items-center justify-center transition-all flex-shrink-0",
                playingVoiceId === agent.voice_id
                  ? "bg-accent-brand text-white"
                  : "bg-muted/30 text-muted-foreground hover:text-foreground hover:bg-muted/60 disabled:opacity-30"
              )}
            >
              {isLoadingPreview ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : playingVoiceId === agent.voice_id ? (
                <Pause className="h-3.5 w-3.5" />
              ) : (
                <Play className="h-3.5 w-3.5 ml-0.5" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Expanded content */}
      <Collapsible open={isExpanded} onOpenChange={onToggleExpand}>
        <CollapsibleContent className="data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
          <div className="px-3 md:px-4 pb-4 space-y-3">
            {/* Color picker */}
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground/70">Color</span>
              <div className="flex items-center gap-1.5">
                {AGENT_COLOR_PRESETS.map((color) => (
                  <button
                    key={color}
                    type="button"
                    onClick={() => handleColorChange(color)}
                    className={cn(
                      "w-5 h-5 rounded-full transition-all duration-150",
                      effectiveColor === color
                        ? "ring-2 ring-offset-2 ring-offset-background scale-110"
                        : "hover:scale-110 ring-1 ring-white/10"
                    )}
                    style={{
                      backgroundColor: color,
                      // Tailwind's ring color is driven by the --tw-ring-color CSS variable
                      '--tw-ring-color': effectiveColor === color ? color : undefined,
                    } as CSSProperties}
                    title={color}
                  />
                ))}
                {/* Custom color input */}
                <div className="relative ml-1">
                  <input
                    type="color"
                    value={effectiveColor}
                    onChange={(e) => handleColorChange(e.target.value)}
                    className="w-5 h-5 rounded-full cursor-pointer opacity-0 absolute inset-0"
                    title="Custom color"
                  />
                  <div
                    className={cn(
                      "w-5 h-5 rounded-full border-2 border-dashed border-muted-foreground/30 flex items-center justify-center text-muted-foreground/50 text-[10px] hover:border-muted-foreground/50 transition-colors",
                      !AGENT_COLOR_PRESETS.includes(effectiveColor) && "ring-2 ring-offset-2 ring-offset-background"
                    )}
                    style={{
                      backgroundColor: !AGENT_COLOR_PRESETS.includes(effectiveColor) ? effectiveColor : 'transparent',
                      // Tailwind's ring color is driven by the --tw-ring-color CSS variable
                      '--tw-ring-color': !AGENT_COLOR_PRESETS.includes(effectiveColor) ? effectiveColor : undefined,
                    } as CSSProperties}
                  >
                    {AGENT_COLOR_PRESETS.includes(effectiveColor) && '+'}
                  </div>
                </div>
              </div>
            </div>

            {/* System prompt */}
            <textarea
              value={agent.system_prompt}
              onChange={handleSystemPromptChange}
              placeholder="Describe personality and behavior..."
              rows={2}
              className="w-full rounded-2xl border border-border/40 bg-transparent shadow-none focus:outline-none text-sm text-foreground placeholder:text-muted-foreground/50 resize-none p-4"
            />
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
})
