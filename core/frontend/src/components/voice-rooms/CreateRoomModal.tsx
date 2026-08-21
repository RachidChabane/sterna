import { useState, useEffect, useMemo, useCallback, useRef, memo, type CSSProperties } from 'react'
import { useToast } from '@/hooks/use-toast'
import { useVoicePreview } from '@/hooks/useVoicePreview'
import { useMediaQuery } from '@/hooks/use-media-query'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Plus, Trash2, ChevronRight, ChevronLeft, RotateCcw, Play, Pause, Globe, Loader2, GripVertical, Sparkles, Settings2, Users, X } from 'lucide-react'
import { CircleFlag } from 'react-circle-flags'
import { VoiceRoomModelSelect } from './VoiceRoomModelSelect'
import useVoiceRoomStore from '@/store/voiceRoomStore'
import useModelStore from '@/store/modelStore'
import { useAuthStore } from '@/store/authStore'
import type { VoiceRoom, VoiceSettings, TTSModel, TTSLanguage, TTSProviderId } from '@/types/voiceRoom'
import type { Model } from '@/components/models/types'
import { cn } from '@/lib/utils'

// Preset configurations for quick room creation
export interface RoomPreset {
  name: string
  description: string
  agents: Array<{
    display_name: string
    model_id: string
    system_prompt: string
    color?: string
    voice_id?: string  // Optional voice selection from AI generation
    voice_name?: string
  }>
}

interface CreateRoomModalProps {
  isOpen: boolean
  onClose: () => void
  onCreated: (room: VoiceRoom) => void
  roomToEdit?: VoiceRoom | null // If provided, modal is in edit mode
  preset?: RoomPreset | null // If provided, pre-fills the form
}

interface AgentFormData {
  id: string // Unique ID for drag-and-drop
  display_name: string
  model_id: string
  system_prompt: string
  voice_id: string
  voice_name: string
  order: number
  voice_settings?: VoiceSettings
  color?: string // Hex color for UI visualization
}

// Generate a unique ID for new agents
const generateAgentId = () => `agent-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

// Premium color palette for agent presets
const AGENT_COLOR_PRESETS = [
  '#38bdf8', // sky-400
  '#a78bfa', // violet-400
  '#fb923c', // orange-400
  '#f472b6', // pink-400
  '#2dd4bf', // teal-400
  '#facc15', // yellow-400
  '#818cf8', // indigo-400
  '#4ade80', // green-400
]

// Allowed models for voice rooms (fast & cheap models only)
// Must be kept in sync with backend VOICE_ROOM_MODELS in voice_rooms/constants.py
const VOICE_ROOM_ALLOWED_MODELS = [
  // OpenAI
  'openai/gpt-4o-mini',
  'openai/gpt-5-mini',
  // Anthropic (Haiku series)
  'anthropic/claude-3-haiku',
  'anthropic/claude-3.5-haiku',
  'anthropic/claude-haiku-4.5',
  // Google
  'google/gemini-2.0-flash-lite-001',
  'google/gemini-2.5-flash-lite',
  'google/gemini-2.5-flash',
  'google/gemini-3-flash-preview',
]

/**
 * Form-local voice settings state.
 * `tts_model` is a plain string here because model ids come dynamically from the
 * TTS models API ('' = not selected yet), while the TTSModel union in
 * types/voiceRoom.ts is a static snapshot of known models.
 */
type VoiceSettingsFormState = Omit<VoiceSettings, 'tts_model'> & { tts_model: string }

const DEFAULT_VOICE_SETTINGS: VoiceSettingsFormState = {
  tts_model: '', // Will be set from first available model
  stability: 0.5,
  similarity_boost: 0.8,
  style: 0.3,
  use_speaker_boost: true,
  speed: 1.0,
}

const DEFAULT_VOICE_ID = '21m00Tcm4TlvDq8ikWAM'
const DEFAULT_VOICE_NAME = 'Rachel'

const createDefaultAgent = (order: number = 0): AgentFormData => ({
  id: generateAgentId(),
  display_name: '',
  model_id: '',
  system_prompt: '',
  voice_id: DEFAULT_VOICE_ID,
  voice_name: DEFAULT_VOICE_NAME,
  order,
})

// Flag component with fallback for unknown country codes
const LanguageFlag = ({ countryCode, size = 16 }: { countryCode: string; size?: number }) => {
  if (!countryCode) {
    return <Globe className="text-muted-foreground flex-shrink-0" style={{ width: size, height: size }} />
  }
  return (
    <span className="flex-shrink-0 inline-flex" style={{ width: size, height: size }}>
      <CircleFlag countryCode={countryCode.toLowerCase()} width={size} height={size} />
    </span>
  )
}

// Memoized agent form to prevent re-renders when other agents change
interface AgentFormProps {
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

const AgentForm = memo(function AgentForm({
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

export function CreateRoomModal({ isOpen, onClose, onCreated, roomToEdit, preset }: CreateRoomModalProps) {
  const { toast } = useToast()
  const { user } = useAuthStore()
  const isMobile = useMediaQuery('(max-width: 640px)')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [userName, setUserName] = useState('')
  const [language, setLanguage] = useState('auto')
  const [agents, setAgents] = useState<AgentFormData[]>([createDefaultAgent(1)])
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettingsFormState>({ ...DEFAULT_VOICE_SETTINGS })
  const [voiceSettingsOpen, setVoiceSettingsOpen] = useState(false)
  const [agentsSectionOpen, setAgentsSectionOpen] = useState(true)
  const [expandedAgents, setExpandedAgents] = useState<Set<number>>(new Set())
  const [isCreating, setIsCreating] = useState(false)
  const [aiGenerateOpen, setAiGenerateOpen] = useState(false)
  const [aiDescription, setAiDescription] = useState('')

  // Mobile wizard state
  const [mobileStep, setMobileStep] = useState(1)
  const MOBILE_STEPS = [
    { id: 1, label: 'Basics', icon: Sparkles },
    { id: 2, label: 'Agents', icon: Users },
    { id: 3, label: 'Voice', icon: Settings2 },
  ]

  const isEditMode = !!roomToEdit
  const {
    createRoom,
    updateRoom,
    recommendedVoices,
    ttsModels,
    fetchTTSModels,
    ttsModelsLoaded,
    fetchRecommendedVoices,
    ttsProviders,
    fetchTTSProviders,
    ttsProvidersLoaded,
    generateRoom,
    isGeneratingRoom,
  } = useVoiceRoomStore()

  // Provider state - default to first available provider
  const [selectedProvider, setSelectedProvider] = useState<string>('')

  // Refs for tracking validation state (must be before effects that use them)
  const prevProviderRef = useRef<string>('')
  const validatedVoicesRef = useRef<string>('') // Track last validated state to avoid loops

  // Get available languages for the selected TTS model
  const availableLanguages = useMemo(() => {
    const selectedModel = ttsModels.find(m => m.model_id === voiceSettings.tts_model)
    return selectedModel?.languages || []
  }, [ttsModels, voiceSettings.tts_model])


  // Get default user name from auth store (first name only)
  const defaultUserName = user?.first_name || ''

  // Populate form when editing or using preset
  useEffect(() => {
    // Reset validation refs when modal opens
    if (isOpen) {
      validatedVoicesRef.current = ''
      prevProviderRef.current = ''
    }

    if (isOpen && roomToEdit) {
      setName(roomToEdit.name)
      setDescription(roomToEdit.description || '')
      setUserName(roomToEdit.user_name || defaultUserName)
      setLanguage(roomToEdit.language || 'auto')
      // Get voice settings from first agent (room-level now), merge with defaults for any missing fields
      const firstAgentSettings = roomToEdit.agents?.[0]?.voice_settings
      setVoiceSettings({ ...DEFAULT_VOICE_SETTINGS, ...firstAgentSettings })

      // Set provider from saved settings
      const savedProvider = firstAgentSettings?.tts_provider
      if (savedProvider) {
        setSelectedProvider(savedProvider)
      }

      setAgents(
        roomToEdit.agents?.map((a, i) => ({
          id: generateAgentId(),
          display_name: a.display_name,
          model_id: a.model_id,
          system_prompt: a.system_prompt,
          voice_id: a.voice_id,
          voice_name: a.voice_name,
          order: a.order || i + 1,
          color: a.color,
        })) || [createDefaultAgent(1)]
      )
    } else if (isOpen && preset) {
      // Pre-fill from preset
      setName(preset.name)
      setDescription(preset.description)
      setUserName(defaultUserName)
      setLanguage('auto')
      setVoiceSettings({ ...DEFAULT_VOICE_SETTINGS })

      // Randomly assign unique voices from recommended voices
      const getRandomVoices = (count: number) => {
        if (recommendedVoices.length === 0) {
          // Fallback to default if voices not loaded yet
          return Array(count).fill({ voice_id: DEFAULT_VOICE_ID, voice_name: DEFAULT_VOICE_NAME })
        }
        // Shuffle and pick unique voices, cycling if needed
        const shuffled = [...recommendedVoices].sort(() => Math.random() - 0.5)
        return Array.from({ length: count }, (_, i) => {
          const voice = shuffled[i % shuffled.length]
          return { voice_id: voice.voice_id, voice_name: voice.name }
        })
      }

      const randomVoices = getRandomVoices(preset.agents.length)

      setAgents(
        preset.agents.map((a, i) => ({
          ...createDefaultAgent(i + 1),
          display_name: a.display_name,
          model_id: a.model_id,
          system_prompt: a.system_prompt,
          color: a.color || AGENT_COLOR_PRESETS[i % AGENT_COLOR_PRESETS.length],
          // Use preset voice if available (from AI generation), otherwise random
          voice_id: a.voice_id || randomVoices[i].voice_id,
          voice_name: a.voice_name || randomVoices[i].voice_name,
        }))
      )
    } else if (isOpen && !roomToEdit && !preset) {
      // Reset form for create mode
      setName('')
      setDescription('')
      setUserName(defaultUserName)
      setLanguage('auto')
      setVoiceSettings({ ...DEFAULT_VOICE_SETTINGS })
      setSelectedProvider('') // Will be set to default by the provider effect
      setAgents([createDefaultAgent(1)])
    }

    // Reset mobile step when modal opens
    if (isOpen) {
      setMobileStep(1)
    }
  }, [isOpen, roomToEdit, preset, defaultUserName])

  // Update agent voices when recommendedVoices becomes available (for presets without AI-generated voices)
  useEffect(() => {
    if (isOpen && preset && recommendedVoices.length > 0) {
      // Check if agents still have the default voice (meaning voices weren't available when preset was applied)
      // But only if the preset didn't include voice selections (from AI generation)
      const presetHasVoices = preset.agents.some(a => a.voice_id)
      if (presetHasVoices) return // AI-generated presets have voices already

      const hasDefaultVoices = agents.every(a => a.voice_id === DEFAULT_VOICE_ID)
      if (hasDefaultVoices && agents.length === preset.agents.length) {
        // Assign random unique voices now that they're available
        const shuffled = [...recommendedVoices].sort(() => Math.random() - 0.5)
        setAgents(prev => prev.map((agent, i) => ({
          ...agent,
          voice_id: shuffled[i % shuffled.length].voice_id,
          voice_name: shuffled[i % shuffled.length].name,
        })))
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recommendedVoices.length, isOpen, preset])

  const { allModels, fetchAllModels, allModelsLoading, allModelsLoaded } = useModelStore()

  // Load providers and models when modal opens
  useEffect(() => {
    if (isOpen) {
      if (!allModelsLoaded && !allModelsLoading) {
        fetchAllModels()
      }
      if (!ttsProvidersLoaded) {
        fetchTTSProviders()
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  // Helper to check if a model matches a provider
  const isModelForProvider = useCallback((modelId: string, providerId: string): boolean => {
    if (!modelId || !providerId) return false
    const modelLower = modelId.toLowerCase()
    const providerLower = providerId.toLowerCase()

    if (providerLower === 'openai') {
      return modelLower.startsWith('tts-')
    }
    if (providerLower === 'elevenlabs') {
      return modelLower.startsWith('eleven')
    }
    return modelLower.includes(providerLower)
  }, [])

  // Set default provider when providers load (only if not already set)
  useEffect(() => {
    if (ttsProviders.length === 0 || selectedProvider) return
    // Default to first provider
    setSelectedProvider(ttsProviders[0].id)
  }, [ttsProviders, selectedProvider])

  // Fetch models and voices when modal opens or provider changes
  useEffect(() => {
    if (!isOpen || !selectedProvider) return

    // Reset validation ref when provider changes
    if (prevProviderRef.current !== selectedProvider) {
      validatedVoicesRef.current = ''
      prevProviderRef.current = selectedProvider
    }

    fetchTTSModels(selectedProvider as any)
    fetchRecommendedVoices(selectedProvider as any)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, selectedProvider])

  // Validate and fix agent voices when voices load or provider changes
  // This handles: 1) provider change, 2) editing room with mismatched voices
  useEffect(() => {
    if (!selectedProvider || recommendedVoices.length === 0) return

    // Ensure voices are for the current provider (check first voice's provider)
    const voicesMatchProvider = recommendedVoices.some(v =>
      v.provider?.toLowerCase() === selectedProvider.toLowerCase()
    )
    if (!voicesMatchProvider) {
      // Voices are stale (from different provider), wait for correct ones
      return
    }

    // Create a key to track if we've already validated this combination
    const validationKey = `${selectedProvider}:${recommendedVoices.map(v => v.voice_id).join(',')}`
    if (validatedVoicesRef.current === validationKey) return

    const validVoiceIds = new Set(recommendedVoices.map(v => v.voice_id))

    // Check if any agent has an invalid voice for current provider
    setAgents(prev => {
      const hasInvalidVoices = prev.some(a => !validVoiceIds.has(a.voice_id))
      if (!hasInvalidVoices) {
        validatedVoicesRef.current = validationKey
        return prev
      }

      // Reset invalid voices to valid ones for current provider
      const shuffled = [...recommendedVoices].sort(() => Math.random() - 0.5)
      validatedVoicesRef.current = validationKey

      return prev.map((agent, i) => {
        if (!validVoiceIds.has(agent.voice_id)) {
          const newVoice = shuffled[i % shuffled.length]
          return {
            ...agent,
            voice_id: newVoice.voice_id,
            voice_name: newVoice.name,
          }
        }
        return agent
      })
    })
  }, [selectedProvider, recommendedVoices])

  // Set default TTS model when models load (or validate existing model)
  useEffect(() => {
    if (ttsModels.length > 0 && selectedProvider) {
      // Ensure ttsModels are for the current provider (not stale from previous session)
      const modelsMatchProvider = ttsModels.some(m =>
        isModelForProvider(m.model_id, selectedProvider)
      )
      if (!modelsMatchProvider) {
        // Models are stale (from different provider), wait for correct ones to load
        return
      }

      // Check if current model is valid for the loaded models (case-insensitive)
      const currentModel = voiceSettings.tts_model || ''
      const currentModelValid = ttsModels.some(m =>
        m.model_id.toLowerCase() === currentModel.toLowerCase()
      )
      if (!currentModelValid) {
        // Use first available model
        setVoiceSettings(prev => ({ ...prev, tts_model: ttsModels[0].model_id }))
      }
    }
  }, [ttsModels, voiceSettings.tts_model, selectedProvider, isModelForProvider])

  // Filter models to only allowed voice room models
  const voiceRoomModels = useMemo(() => {
    return allModels.filter((model) =>
      VOICE_ROOM_ALLOWED_MODELS.includes(model.model_id)
    )
  }, [allModels])

  const handleAddAgent = () => {
    if (agents.length >= 6) return
    setAgents([
      ...agents,
      createDefaultAgent(agents.length + 1),
    ])
  }

  const handleRemoveAgent = useCallback((index: number) => {
    setAgents(prevAgents => {
      if (prevAgents.length <= 1) return prevAgents
      const newAgents = prevAgents.filter((_, i) => i !== index)
      // Reorder remaining agents
      return newAgents.map((a, i) => ({ ...a, order: i + 1 }))
    })
  }, [])

  const handleAgentChange = useCallback((index: number, field: keyof AgentFormData, value: string | number | VoiceSettings | undefined) => {
    setAgents(prevAgents => {
      const newAgents = [...prevAgents]
      newAgents[index] = { ...newAgents[index], [field]: value }

      // If voice_id changes, update voice_name
      if (field === 'voice_id' && typeof value === 'string') {
        const voice = recommendedVoices.find((v) => v.voice_id === value)
        if (voice) {
          newAgents[index].voice_name = voice.name
        }
      }

      return newAgents
    })
  }, [recommendedVoices])

  const handleVoiceSettingChange = useCallback((key: keyof VoiceSettings, value: number | boolean | string) => {
    setVoiceSettings(prev => ({ ...prev, [key]: value }))
  }, [])

  const handleToggleAgentExpand = useCallback((index: number) => {
    setExpandedAgents(prev => {
      const newSet = new Set(prev)
      if (newSet.has(index)) {
        newSet.delete(index)
      } else {
        newSet.add(index)
      }
      return newSet
    })
  }, [])

  // Drag-and-drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Require 8px movement before starting drag
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  // Handle drag end - reorder agents
  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      setAgents((items) => {
        const oldIndex = items.findIndex((item) => item.id === active.id)
        const newIndex = items.findIndex((item) => item.id === over.id)

        const reordered = arrayMove(items, oldIndex, newIndex)
        // Update order values
        return reordered.map((item, i) => ({ ...item, order: i + 1 }))
      })

      // Update expanded agents indices after reorder
      setExpandedAgents((prev) => {
        const items = agents
        const oldIndex = items.findIndex((item) => item.id === active.id)
        const newIndex = items.findIndex((item) => item.id === over.id)

        const newSet = new Set<number>()
        prev.forEach((expandedIndex) => {
          if (expandedIndex === oldIndex) {
            newSet.add(newIndex)
          } else if (oldIndex < newIndex) {
            // Item moved down
            if (expandedIndex > oldIndex && expandedIndex <= newIndex) {
              newSet.add(expandedIndex - 1)
            } else {
              newSet.add(expandedIndex)
            }
          } else {
            // Item moved up
            if (expandedIndex >= newIndex && expandedIndex < oldIndex) {
              newSet.add(expandedIndex + 1)
            } else {
              newSet.add(expandedIndex)
            }
          }
        })
        return newSet
      })
    }
  }, [agents])

  // Handle AI room generation
  const handleAIGenerate = async () => {
    if (!aiDescription.trim()) return

    // Pass the selected TTS provider so AI can choose appropriate voices
    const generated = await generateRoom(aiDescription.trim(), selectedProvider || undefined)
    if (generated) {
      // Fill the form with generated config
      setName(generated.name)
      setDescription(generated.description)
      // Set detected language from AI (e.g., "en", "fr", "es")
      if (generated.language && generated.language !== 'auto') {
        setLanguage(generated.language)
      }

      // Set agents from generated config
      setAgents(
        generated.agents.map((agent, i) => ({
          id: generateAgentId(),
          display_name: agent.display_name,
          model_id: agent.model_id,
          system_prompt: agent.system_prompt,
          voice_id: agent.voice_id,
          voice_name: agent.voice_name,
          order: agent.order,
          color: agent.color,
        }))
      )

      // Collapse the AI section and clear input
      setAiGenerateOpen(false)
      setAiDescription('')

      toast({
        title: 'Room generated',
        description: 'Review the configuration and make any adjustments before creating.',
      })
    }
  }

  const handleSubmit = async () => {
    if (!name.trim() || agents.some((a) => !a.display_name || !a.model_id || !a.system_prompt)) {
      return
    }

    // Check for duplicate display names (case-insensitive)
    const displayNames = agents.map((a) => a.display_name.trim().toLowerCase())
    const duplicates = displayNames.filter((n, index) => displayNames.indexOf(n) !== index)
    if (duplicates.length > 0) {
      toast({
        title: 'Duplicate agent names',
        description: `Each agent must have a unique name. Duplicates: ${[...new Set(duplicates)].join(', ')}`,
        variant: 'destructive',
      })
      return
    }

    setIsCreating(true)
    try {
      // Apply room-level voice settings to all agents.
      // tts_model is validated against the provider's model list in the effect
      // above; the API accepts any model id the TTS provider exposes, so assert
      // the static TTSModel union at this boundary.
      const agentVoiceSettings: VoiceSettings = {
        ...voiceSettings,
        tts_model: voiceSettings.tts_model as TTSModel,
        tts_provider: selectedProvider as TTSProviderId,
      }
      const buildAgent = (a: AgentFormData, index: number) => ({
        display_name: a.display_name,
        model_id: a.model_id,
        system_prompt: a.system_prompt,
        voice_id: a.voice_id,
        voice_name: a.voice_name,
        order: a.order,
        voice_settings: agentVoiceSettings,
        color: a.color || AGENT_COLOR_PRESETS[index % AGENT_COLOR_PRESETS.length],
      })
      const roomData = {
        name: name.trim(),
        description: description.trim() || undefined,
        user_name: userName.trim() || undefined,
        language,
      }

      let room: VoiceRoom | null = null
      if (isEditMode && roomToEdit) {
        room = await updateRoom(roomToEdit.id, {
          ...roomData,
          // Include IDs when editing to preserve agent references in messages
          agents: agents.map((a, index) => ({ ...buildAgent(a, index), id: a.id })),
        })
      } else {
        room = await createRoom({
          ...roomData,
          agents: agents.map((a, index) => buildAgent(a, index)),
        })
      }

      if (room) {
        onCreated(room)
        // Reset form
        setName('')
        setDescription('')
        setUserName(defaultUserName)
        setLanguage('auto')
        setVoiceSettings({ ...DEFAULT_VOICE_SETTINGS })
        setAgents([createDefaultAgent(1)])
      }
    } finally {
      setIsCreating(false)
    }
  }

  // Check if form is valid for submission
  const isFormValid = name.trim() && !agents.some((a) => !a.display_name || !a.model_id || !a.system_prompt)

  // Mobile step validation
  const canProceedFromStep = (step: number) => {
    if (step === 1) return name.trim() !== ''
    if (step === 2) return !agents.some((a) => !a.display_name || !a.model_id || !a.system_prompt)
    return true
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
                onClick={() => {
                  handleAddAgent()
                  setExpandedAgents(prev => new Set([...prev, agents.length]))
                }}
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
          {MOBILE_STEPS.map((step, idx) => {
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
