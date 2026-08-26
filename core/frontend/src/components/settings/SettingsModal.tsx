import { useState, useEffect } from 'react'
import { useVoicePreview } from '@/hooks/useVoicePreview'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Settings,
  Volume2,
  MessageSquare,
  Accessibility,
  Shield,
  Sun,
  Moon,
  Monitor,
  Play,
  Pause,
  Loader2,
  RotateCcw,
  Globe,
  Trash2,
  Download,
  ChevronRight,
  BarChart3,
  Image,
  ScrollText,
  Check,
  Code2,
  Key,
} from 'lucide-react'
import { CircleFlag } from 'react-circle-flags'
import { cn } from '@/lib/utils'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
// Model info is now fetched from backend API instead of hardcoded utilities
import { useTheme } from '@/hooks/useTheme'
import { useSettingsStore } from '@/store/settingsStore'
import type { TTSModel } from '@/types/voiceRoom'
import useVoiceRoomStore from '@/store/voiceRoomStore'
import { UsageQuotaSettings } from './UsageQuotaSettings'
import { PlanCard } from './PlanCard'
import { BYOKSettings } from './BYOKSettings'
import { CODE_THEMES, THEME_PREVIEW_CODE, type CodeThemeId } from '@/constants/codeThemes'

interface SettingsSectionProps {
  id: string
  label: string
  icon: React.ReactNode
  isActive: boolean
  onClick: () => void
}

function SettingsNavItem({ id, label, icon, isActive, onClick }: SettingsSectionProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150",
        isActive
          ? "bg-accent-brand/10 text-accent-brand"
          : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}

interface SettingRowProps {
  label: string
  description?: string
  children: React.ReactNode
  className?: string
}

function SettingRow({ label, description, children, className }: SettingRowProps) {
  return (
    <div className={cn("flex items-center justify-between gap-4 py-3", className)}>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-foreground">{label}</div>
        {description && (
          <div className="text-xs text-muted-foreground mt-0.5">{description}</div>
        )}
      </div>
      <div className="flex-shrink-0">
        {children}
      </div>
    </div>
  )
}

function SettingSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <h3 className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider px-0.5 mb-3">
        {title}
      </h3>
      <div className="space-y-1 divide-y divide-border/50">
        {children}
      </div>
    </div>
  )
}

// Language flag component
function LanguageFlag({ countryCode, size = 16 }: { countryCode: string; size?: number }) {
  if (!countryCode) {
    return <Globe className="text-muted-foreground flex-shrink-0" style={{ width: size, height: size }} />
  }
  return (
    <span className="flex-shrink-0 inline-flex" style={{ width: size, height: size }}>
      <CircleFlag countryCode={countryCode.toLowerCase()} width={size} height={size} />
    </span>
  )
}

// Code Theme Preview Component
function CodeThemePreview({ themeId, isSelected, onSelect }: { themeId: CodeThemeId; isSelected: boolean; onSelect: () => void }) {
  const theme = CODE_THEMES.find(t => t.id === themeId)
  if (!theme) return null

  return (
    <button
      onClick={onSelect}
      className={cn(
        "relative w-full rounded-lg overflow-hidden border-2 transition-all duration-200 text-left",
        isSelected
          ? "border-accent-brand ring-2 ring-accent-brand/30"
          : "border-border hover:border-muted-foreground/50"
      )}
    >
      {/* Selected indicator */}
      {isSelected && (
        <div className="absolute top-2 right-2 z-10 h-5 w-5 rounded-full bg-accent-brand flex items-center justify-center">
          <Check className="h-3 w-3 text-white" />
        </div>
      )}

      {/* Theme name header */}
      <div className="px-3 py-1.5 bg-muted/50 border-b border-border">
        <div className="text-xs font-medium text-foreground">{theme.name}</div>
        <div className="text-[10px] text-muted-foreground truncate">{theme.description}</div>
      </div>

      {/* Code preview */}
      <div
        className="p-2 overflow-hidden [&_pre]:!text-[9px] [&_code]:!text-[9px] [&_pre]:!leading-[1.4] [&_code]:!leading-[1.4]"
        style={{ background: theme.background }}
      >
        <SyntaxHighlighter
          language="typescript"
          style={theme.style}
          customStyle={{
            margin: 0,
            padding: 0,
            background: 'transparent',
            fontSize: '9px',
            lineHeight: '1.4',
          }}
          showLineNumbers={false}
          wrapLongLines={true}
        >
          {THEME_PREVIEW_CODE}
        </SyntaxHighlighter>
      </div>
    </button>
  )
}

// General Settings Section
function GeneralSettings() {
  const { theme, setTheme } = useTheme()
  const { accessibility, setFontSize, setReduceMotion, setHighContrast } = useSettingsStore()

  return (
    <div className="space-y-6">
      <SettingSection title="Appearance">
        <SettingRow
          label="Theme"
          description="Choose your preferred color scheme"
        >
          <ToggleGroup
            type="single"
            value={theme}
            onValueChange={(value) => value && setTheme(value as 'light' | 'dark' | 'system')}
            className="gap-1"
          >
            <ToggleGroupItem value="light" aria-label="Light theme" className="h-8 w-8 p-0">
              <Sun className="h-4 w-4" />
            </ToggleGroupItem>
            <ToggleGroupItem value="system" aria-label="System theme" className="h-8 w-8 p-0">
              <Monitor className="h-4 w-4" />
            </ToggleGroupItem>
            <ToggleGroupItem value="dark" aria-label="Dark theme" className="h-8 w-8 p-0">
              <Moon className="h-4 w-4" />
            </ToggleGroupItem>
          </ToggleGroup>
        </SettingRow>

        <SettingRow
          label="Font Size"
          description="Adjust text size throughout the app"
        >
          <Select value={accessibility.fontSize} onValueChange={(v) => setFontSize(v as 'small' | 'medium' | 'large')}>
            <SelectTrigger className="w-28 h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="small">Small</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="large">Large</SelectItem>
            </SelectContent>
          </Select>
        </SettingRow>

        <SettingRow
          label="Reduce Motion"
          description="Minimize animations and transitions"
        >
          <Switch
            checked={accessibility.reduceMotion}
            onCheckedChange={setReduceMotion}
          />
        </SettingRow>

        <SettingRow
          label="High Contrast"
          description="Increase color contrast for better visibility"
        >
          <Switch
            checked={accessibility.highContrast}
            onCheckedChange={setHighContrast}
          />
        </SettingRow>
      </SettingSection>
    </div>
  )
}

// Code Settings Section
function CodeSettings() {
  const { codeTheme, setCodeTheme } = useSettingsStore()

  return (
    <div className="space-y-6">
      <SettingSection title="Syntax Highlighting">
        <div className="py-3">
          <p className="text-xs text-muted-foreground mb-4">
            Choose a syntax highlighting theme for code blocks
          </p>
          <div className="grid grid-cols-2 gap-3">
            {CODE_THEMES.map((theme) => (
              <CodeThemePreview
                key={theme.id}
                themeId={theme.id}
                isSelected={codeTheme === theme.id}
                onSelect={() => setCodeTheme(theme.id)}
              />
            ))}
          </div>
        </div>
      </SettingSection>
    </div>
  )
}

// STT Language type
interface STTLanguage {
  code: string
  name: string
  country_code: string
}

// Voice Settings Section
function VoiceSettings() {
  const {
    stt,
    tts,
    setSTTLanguage,
    setTTSEnabled,
    setAutoRead,
    setTTSProvider,
    setVoice,
    setTTSLanguage,
    setTTSModel,
    setTTSStability,
    setTTSSimilarityBoost,
    setTTSStyle,
    setTTSSpeed,
    resetTTSSettings,
  } = useSettingsStore()

  // STT languages state
  const [sttLanguages, setSttLanguages] = useState<STTLanguage[]>([])
  const [sttLanguagesLoading, setSttLanguagesLoading] = useState(false)

  const {
    recommendedVoices,
    ttsModels,
    ttsProviders,
    fetchRecommendedVoices,
    fetchTTSModels,
    fetchTTSProviders,
    ttsModelsLoaded,
    ttsProvidersLoaded,
  } = useVoiceRoomStore()

  // Use shared voice preview hook
  const {
    playingVoiceId,
    isLoadingPreview,
    playPreview,
    cleanup: cleanupPreview,
  } = useVoicePreview({
    provider: tts.provider,
    voices: recommendedVoices,
    language: tts.language,
    ttsModel: tts.ttsModel,
    speed: tts.speed,
  })

  // Cleanup preview on unmount
  useEffect(() => {
    return cleanupPreview
  }, [cleanupPreview])

  // Fetch providers on mount
  useEffect(() => {
    if (!ttsProvidersLoaded) {
      fetchTTSProviders()
    }
  }, [ttsProvidersLoaded, fetchTTSProviders])

  // Auto-select available provider if current one isn't available
  useEffect(() => {
    if (ttsProviders.length > 0) {
      const currentProviderAvailable = ttsProviders.some(p => p.id === tts.provider)
      if (!currentProviderAvailable) {
        // Select the default provider or first available
        const defaultProvider = ttsProviders.find(p => p.is_default) || ttsProviders[0]
        setTTSProvider(defaultProvider.id as 'openai' | 'elevenlabs')
      }
    }
  }, [ttsProviders, tts.provider, setTTSProvider])

  // Fetch voices and models when provider changes
  useEffect(() => {
    fetchRecommendedVoices(tts.provider)
    fetchTTSModels(tts.provider)
  }, [tts.provider, fetchRecommendedVoices, fetchTTSModels])

  // Update selected voice when voices change (e.g., after provider switch)
  useEffect(() => {
    if (recommendedVoices.length > 0) {
      // Check if current voice is valid for the loaded voices
      const currentVoiceExists = recommendedVoices.some(v => v.voice_id === tts.voiceId)
      if (!currentVoiceExists) {
        // Select first voice from the new provider
        const firstVoice = recommendedVoices[0]
        setVoice(firstVoice.voice_id, firstVoice.name)
      }
    }
  }, [recommendedVoices, tts.voiceId, setVoice])

  // Update selected model when models change (e.g., after provider switch)
  useEffect(() => {
    if (ttsModels.length > 0) {
      // Check if current model is valid for the loaded models
      const currentModelExists = ttsModels.some(m => m.model_id === tts.ttsModel)
      if (!currentModelExists) {
        // For ElevenLabs, use the cheapest model (flash); for others use first.
        // Backend model lists are dynamic (TTSModelInfo.model_id is a plain string),
        // while the store's TTSModel union tracks the known ids — assert accordingly.
        if (tts.provider === 'elevenlabs') {
          const flashModel = ttsModels.find(m => m.model_id === 'eleven_flash_v2_5')
          setTTSModel((flashModel?.model_id || ttsModels[0].model_id) as TTSModel)
        } else {
          setTTSModel(ttsModels[0].model_id as TTSModel)
        }
      }
    }
  }, [ttsModels, tts.ttsModel, tts.provider, setTTSModel])

  // Fetch STT languages on mount
  useEffect(() => {
    const fetchSTTLanguages = async () => {
      if (sttLanguages.length > 0) return // Already loaded
      setSttLanguagesLoading(true)
      try {
        const { default: apiClient } = await import('@/api/client')
        const response = await apiClient.get('/llm/stt-languages/')
        setSttLanguages(response.data.languages || [])
      } catch (error) {
        console.error('Failed to fetch STT languages:', error)
      } finally {
        setSttLanguagesLoading(false)
      }
    }
    fetchSTTLanguages()
  }, [sttLanguages.length])

  // Get provider-specific settings
  const isElevenLabs = tts.provider === 'elevenlabs'
  const speedMin = isElevenLabs ? 0.5 : 0.25
  const speedMax = isElevenLabs ? 2.0 : 4.0

  // Get available languages for selected model
  const availableLanguages = ttsModels.find(m => m.model_id === tts.ttsModel)?.languages || []

  return (
    <div className="space-y-6">
      <SettingSection title="Speech-to-Text">
        <SettingRow
          label="Language"
          description="Language for voice input transcription"
        >
          <Select
            value={stt.language}
            onValueChange={setSTTLanguage}
            disabled={sttLanguagesLoading}
          >
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <SelectTrigger className="w-40 h-8">
                    <SelectValue>
                      {sttLanguagesLoading ? (
                        <span className="text-muted-foreground">Loading...</span>
                      ) : (
                        <div className="flex items-center gap-2 min-w-0">
                          {stt.language === 'auto' ? (
                            <>
                              <Globe className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                              <span className="truncate">Auto-detect</span>
                            </>
                          ) : (
                            <>
                              <LanguageFlag countryCode={sttLanguages.find(l => l.code === stt.language)?.country_code || ''} size={14} />
                              <span className="truncate">{sttLanguages.find(l => l.code === stt.language)?.name || stt.language}</span>
                            </>
                          )}
                        </div>
                      )}
                    </SelectValue>
                  </SelectTrigger>
                </TooltipTrigger>
                <TooltipContent>
                  {stt.language === 'auto' ? 'Auto-detect' : (sttLanguages.find(l => l.code === stt.language)?.name || stt.language)}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <SelectContent className="max-h-[280px]">
              {sttLanguages.map((lang) => (
                <SelectItem key={lang.code} value={lang.code}>
                  <div className="flex items-center gap-2">
                    {lang.code === 'auto' || lang.code === 'multi' ? (
                      <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                    ) : (
                      <LanguageFlag countryCode={lang.country_code} size={14} />
                    )}
                    <span>{lang.name}</span>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingRow>
      </SettingSection>

      <SettingSection title="Text-to-Speech">
        <SettingRow
          label="Enable TTS"
          description="Allow text-to-speech for AI responses"
        >
          <Switch
            checked={tts.enabled}
            onCheckedChange={setTTSEnabled}
          />
        </SettingRow>

        <SettingRow
          label="Auto-read Responses"
          description="Automatically read AI responses aloud"
        >
          <Switch
            checked={tts.autoRead}
            onCheckedChange={setAutoRead}
            disabled={!tts.enabled}
          />
        </SettingRow>
      </SettingSection>

      <SettingSection title="Voice Selection">
        {/* Only show provider selector if multiple providers available */}
        {ttsProviders.length > 1 && (
          <SettingRow
            label="TTS Provider"
            description={isElevenLabs ? "Premium voices with advanced tuning" : "Fast, reliable text-to-speech"}
          >
            <Select
              value={tts.provider}
              onValueChange={(value) => setTTSProvider(value as 'openai' | 'elevenlabs')}
              disabled={!tts.enabled}
            >
              <SelectTrigger className="w-32 h-8">
                <SelectValue>
                  {ttsProviders.find(p => p.id === tts.provider)?.name || tts.provider}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {ttsProviders.map((provider) => (
                  <SelectItem key={provider.id} value={provider.id}>
                    {provider.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingRow>
        )}

        {/* Model selector - only for OpenAI (ElevenLabs uses default) */}
        {!isElevenLabs && (
          <SettingRow
            label="Model"
            description={ttsModels.find(m => m.model_id === tts.ttsModel)?.description}
          >
            <Select
              value={tts.ttsModel}
              onValueChange={setTTSModel}
              disabled={!tts.enabled}
            >
              <SelectTrigger className="w-32 h-8">
                <SelectValue>
                  {ttsModels.find(m => m.model_id === tts.ttsModel)?.name || tts.ttsModel}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {ttsModels.map((model) => (
                  <SelectItem key={model.model_id} value={model.model_id}>
                    {model.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingRow>
        )}

        <SettingRow label="Voice">
          <div className="flex items-center gap-2">
            <button
              onClick={() => playPreview(tts.voiceId)}
              disabled={!tts.enabled || isLoadingPreview}
              className={cn(
                "h-8 px-3 rounded-full flex items-center gap-1.5 text-xs font-medium transition-all border",
                playingVoiceId === tts.voiceId
                  ? "bg-accent-brand text-white border-accent-brand"
                  : "bg-background text-foreground border-border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
              )}
            >
              {isLoadingPreview ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>Loading</span>
                </>
              ) : playingVoiceId === tts.voiceId ? (
                <>
                  <Pause className="h-3 w-3" />
                  <span>Stop</span>
                </>
              ) : (
                <>
                  <Play className="h-3 w-3" />
                  <span>Play</span>
                </>
              )}
            </button>
            <Select
              value={tts.voiceId}
              onValueChange={(id) => {
                const voice = recommendedVoices.find(v => v.voice_id === id)
                if (voice) setVoice(id, voice.name)
              }}
              disabled={!tts.enabled}
            >
              <SelectTrigger className="w-32 h-8">
                <SelectValue>{tts.voiceName}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {recommendedVoices.map((voice) => (
                  <SelectItem key={voice.voice_id} value={voice.voice_id}>
                    {voice.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </SettingRow>

        <SettingRow label="Language">
          <Select
            value={tts.language}
            onValueChange={setTTSLanguage}
            disabled={!tts.enabled}
          >
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <SelectTrigger className="w-32 h-8">
                    <SelectValue>
                      <div className="flex items-center gap-2 min-w-0">
                        {tts.language === 'auto' ? (
                          <>
                            <Globe className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                            <span className="truncate">Auto-detect</span>
                          </>
                        ) : (
                          <>
                            <LanguageFlag countryCode={availableLanguages.find(l => l.language_id === tts.language)?.country_code || ''} size={14} />
                            <span className="truncate">{availableLanguages.find(l => l.language_id === tts.language)?.name || tts.language}</span>
                          </>
                        )}
                      </div>
                    </SelectValue>
                  </SelectTrigger>
                </TooltipTrigger>
                <TooltipContent>
                  {tts.language === 'auto' ? 'Auto-detect' : (availableLanguages.find(l => l.language_id === tts.language)?.name || tts.language)}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <SelectContent className="max-h-[240px]">
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
        </SettingRow>
      </SettingSection>

      <SettingSection title="Voice Tuning">
        <div className="py-3 space-y-4">
          {/* ElevenLabs-specific tuning settings */}
          {isElevenLabs && (
            <>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Stability</span>
                  <span className="text-sm text-muted-foreground tabular-nums w-12 text-right">
                    {Math.round(tts.stability * 100)}%
                  </span>
                </div>
                <Slider
                  value={[tts.stability]}
                  onValueChange={([v]) => setTTSStability(v)}
                  min={0}
                  max={1}
                  step={0.01}
                  disabled={!tts.enabled}
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Clarity + Similarity</span>
                  <span className="text-sm text-muted-foreground tabular-nums w-12 text-right">
                    {Math.round(tts.similarityBoost * 100)}%
                  </span>
                </div>
                <Slider
                  value={[tts.similarityBoost]}
                  onValueChange={([v]) => setTTSSimilarityBoost(v)}
                  min={0}
                  max={1}
                  step={0.01}
                  disabled={!tts.enabled}
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Style Exaggeration</span>
                  <span className="text-sm text-muted-foreground tabular-nums w-12 text-right">
                    {Math.round(tts.style * 100)}%
                  </span>
                </div>
                <Slider
                  value={[tts.style]}
                  onValueChange={([v]) => setTTSStyle(v)}
                  min={0}
                  max={1}
                  step={0.01}
                  disabled={!tts.enabled}
                />
              </div>
            </>
          )}

          {/* Speed slider - available for all providers */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Speed</span>
              <span className="text-sm text-muted-foreground tabular-nums w-12 text-right">
                {tts.speed.toFixed(1)}x
              </span>
            </div>
            <Slider
              value={[Math.max(speedMin, Math.min(speedMax, tts.speed))]}
              onValueChange={([v]) => setTTSSpeed(v)}
              min={speedMin}
              max={speedMax}
              step={0.1}
              disabled={!tts.enabled}
            />
          </div>
        </div>

        <div className="pt-2">
          <button
            onClick={resetTTSSettings}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reset to defaults
          </button>
        </div>
      </SettingSection>
    </div>
  )
}

// Instructions Settings Section
function InstructionsSettings() {
  const {
    instructions,
    setInstructionsEnabled,
    setInstructionsContent,
  } = useSettingsStore()

  // Import prompt protection utilities
  const [validationError, setValidationError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)

  // Dynamically import to avoid circular dependencies
  const validateContent = async (content: string) => {
    const { validateInstructions, getWarning } = await import('@/lib/promptProtection')
    const result = validateInstructions(content)
    setValidationError(result.isValid ? null : result.error || null)
    setWarning(getWarning(content))
  }

  // Validate on content change
  const handleContentChange = (newContent: string) => {
    setInstructionsContent(newContent)
    validateContent(newContent)
  }

  // Validate initial content on mount
  useEffect(() => {
    if (instructions.content) {
      validateContent(instructions.content)
    }
  }, [])

  return (
    <div className="space-y-6">
      <SettingSection title="Global Instructions">
        <SettingRow
          label="Enable Global Instructions"
          description="Add custom instructions that apply to all your conversations"
        >
          <Switch
            checked={instructions.enabled}
            onCheckedChange={setInstructionsEnabled}
          />
        </SettingRow>
      </SettingSection>

      <SettingSection title="Your Instructions">
        <div className="py-3">
          <div className="space-y-2">
            <textarea
              value={instructions.content}
              onChange={(e) => handleContentChange(e.target.value)}
              placeholder="Enter your custom instructions here...

Example:
- Always respond in a concise manner
- Use code examples when explaining technical concepts
- Prefer TypeScript over JavaScript"
              rows={8}
              maxLength={4000}
              disabled={!instructions.enabled}
              className={cn(
                "w-full rounded-lg border bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 resize-none p-3 focus:outline-none focus:ring-2",
                !instructions.enabled && "opacity-50 cursor-not-allowed",
                validationError
                  ? "border-destructive focus:ring-destructive/50"
                  : "border-border focus:ring-accent-brand/50"
              )}
            />
            {/* Validation error */}
            {validationError && instructions.enabled && (
              <p className="text-xs text-destructive font-medium">
                {validationError}
              </p>
            )}
            {/* Character count warning */}
            {warning && instructions.enabled && !validationError && (
              <p className="text-xs text-amber-500">
                {warning}
              </p>
            )}
            {!validationError && !warning && (
              <p className="text-xs text-muted-foreground">
                These instructions will be included in all your conversations with AI models.
                You can also add chat-specific instructions from within individual chats.
              </p>
            )}
          </div>
        </div>
      </SettingSection>
    </div>
  )
}

// Chat Settings Section
function ChatSettings() {
  const {
    chat,
    setCompactMode,
    setShowTimestamps,
    setShowModelIcon,
    setShowUserAvatar,
    setEnterToSend,
    setStreamResponses,
  } = useSettingsStore()
  const isMobile = useMediaQuery('(max-width: 767px)')

  return (
    <div className="space-y-6">
      <SettingSection title="Display">
        <SettingRow
          label="Compact Mode"
          description="Reduce spacing between messages"
        >
          <Switch
            checked={chat.compactMode}
            onCheckedChange={setCompactMode}
          />
        </SettingRow>

        <SettingRow
          label="Show Timestamps"
          description="Display time for each message"
        >
          <Switch
            checked={chat.showTimestamps}
            onCheckedChange={setShowTimestamps}
          />
        </SettingRow>

        <SettingRow
          label="Show Model Icon"
          description={isMobile ? "Icons are hidden on mobile to save space" : "Display model icon for assistant messages"}
        >
          <Switch
            checked={chat.showModelIcon}
            onCheckedChange={setShowModelIcon}
            disabled={isMobile}
            className={isMobile ? "opacity-50" : ""}
          />
        </SettingRow>

        <SettingRow
          label="Show User Avatar"
          description={isMobile ? "Avatars are hidden on mobile to save space" : "Display your avatar for your messages"}
        >
          <Switch
            checked={chat.showUserAvatar}
            onCheckedChange={setShowUserAvatar}
            disabled={isMobile}
            className={isMobile ? "opacity-50" : ""}
          />
        </SettingRow>
      </SettingSection>

      <SettingSection title="Input">
        <SettingRow
          label="Enter to Send"
          description="Press Enter to send messages (Shift+Enter for new line)"
        >
          <Switch
            checked={chat.enterToSend}
            onCheckedChange={setEnterToSend}
          />
        </SettingRow>
      </SettingSection>
    </div>
  )
}

// Data & Privacy Settings Section
function DataPrivacySettings() {
  const {
    privacy,
    setSaveConversationHistory,
    setAnalyticsEnabled,
  } = useSettingsStore()

  const [showConfirmClear, setShowConfirmClear] = useState(false)

  const handleClearData = () => {
    // Clear localStorage conversation data
    const keys = Object.keys(localStorage)
    keys.forEach(key => {
      if (key.includes('conversation') || key.includes('chat-history')) {
        localStorage.removeItem(key)
      }
    })
    setShowConfirmClear(false)
  }

  return (
    <div className="space-y-6">
      <SettingSection title="Data">
        <SettingRow
          label="Save Conversation History"
          description="Store conversations locally for future reference"
        >
          <Switch
            checked={privacy.saveConversationHistory}
            onCheckedChange={setSaveConversationHistory}
          />
        </SettingRow>

        <div className="py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-foreground">Clear Local Data</div>
              <div className="text-xs text-muted-foreground mt-0.5">
                Remove all locally stored conversations and cache
              </div>
            </div>
            {showConfirmClear ? (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowConfirmClear(false)}
                  className="px-3 py-1.5 text-sm rounded-md bg-muted hover:bg-muted/80 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleClearData}
                  className="px-3 py-1.5 text-sm rounded-md bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors"
                >
                  Clear
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowConfirmClear(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md text-destructive hover:bg-destructive/10 transition-colors"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear Data
              </button>
            )}
          </div>
        </div>
      </SettingSection>

      <SettingSection title="Privacy">
        <SettingRow
          label="Usage Analytics"
          description="Help improve the app by sharing anonymous usage data"
        >
          <Switch
            checked={privacy.analyticsEnabled}
            onCheckedChange={setAnalyticsEnabled}
          />
        </SettingRow>
      </SettingSection>

      <SettingSection title="Export">
        <div className="py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-foreground">Export Data</div>
              <div className="text-xs text-muted-foreground mt-0.5">
                Download all your conversations and settings
              </div>
            </div>
            <button
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-muted hover:bg-muted/80 transition-colors"
            >
              <Download className="h-3.5 w-3.5" />
              Export
            </button>
          </div>
        </div>
      </SettingSection>
    </div>
  )
}

// Image & Video Settings Section
interface ImageModel {
  id: string
  name: string
  description: string
  provider: string
  price_info: string
}

interface VideoModel {
  id: string
  model_id: string
  name: string
  description: string
  best_for: string
  provider: string
  price_info: string
  input_type: 'text' | 'image' | 'video' | 'image_video' | 'text_image' | 'image_audio'
  output_type: 'video' | 'upscaled'
  max_duration: number | null
  min_duration: number | null
  valid_durations: number[] | null
  supported_resolutions: string[] | null
  supported_aspect_ratios: string[] | null
  is_pro: boolean
  is_default: boolean
}

function ImageSettings() {
  // Image settings state
  const [preferredImageModel, setPreferredImageModel] = useState<string>('google/gemini-2.5-flash-image')
  const [availableImageModels, setAvailableImageModels] = useState<ImageModel[]>([])
  const [isLoadingImages, setIsLoadingImages] = useState(true)
  const [isSavingImage, setIsSavingImage] = useState(false)

  // Video settings state
  const [preferredVideoModel, setPreferredVideoModel] = useState<string>('runway/veo3.1-fast')
  const [availableVideoModels, setAvailableVideoModels] = useState<VideoModel[]>([])
  const [isLoadingVideos, setIsLoadingVideos] = useState(true)
  const [isSavingVideo, setIsSavingVideo] = useState(false)

  // Watermark settings from store
  const {
    watermark,
    setWatermarkEnabled,
    setWatermarkPosition,
  } = useSettingsStore()

  // Fetch image settings on mount
  useEffect(() => {
    const fetchImageSettings = async () => {
      try {
        const { default: apiClient } = await import('@/api/client')
        const response = await apiClient.get('/settings/images/')
        setPreferredImageModel(response.data.preferred_image_model)
        setAvailableImageModels(response.data.available_models || [])
      } catch (error) {
        console.error('Failed to fetch image settings:', error)
      } finally {
        setIsLoadingImages(false)
      }
    }
    fetchImageSettings()
  }, [])

  // Fetch video settings on mount
  useEffect(() => {
    const fetchVideoSettings = async () => {
      try {
        const { default: apiClient } = await import('@/api/client')
        const response = await apiClient.get('/settings/videos/')
        setPreferredVideoModel(response.data.preferred_video_model)
        setAvailableVideoModels(response.data.available_models || [])
      } catch (error) {
        console.error('Failed to fetch video settings:', error)
      } finally {
        setIsLoadingVideos(false)
      }
    }
    fetchVideoSettings()
  }, [])

  const handleImageModelChange = async (newModel: string) => {
    setIsSavingImage(true)
    try {
      const { default: apiClient } = await import('@/api/client')
      await apiClient.patch('/settings/images/', { preferred_image_model: newModel })
      setPreferredImageModel(newModel)
    } catch (error) {
      console.error('Failed to update image settings:', error)
    } finally {
      setIsSavingImage(false)
    }
  }

  const handleVideoModelChange = async (newModel: string) => {
    setIsSavingVideo(true)
    try {
      const { default: apiClient } = await import('@/api/client')
      await apiClient.patch('/settings/videos/', { preferred_video_model: newModel })
      setPreferredVideoModel(newModel)
    } catch (error) {
      console.error('Failed to update video settings:', error)
    } finally {
      setIsSavingVideo(false)
    }
  }

  const isLoading = isLoadingImages || isLoadingVideos

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // Helper to get current model info
  const currentImageModel = availableImageModels.find(m => m.id === preferredImageModel)
  const currentVideoModel = availableVideoModels.find(m => m.id === preferredVideoModel)

  return (
    <div className="space-y-6">
      {/* Image Generation Section */}
      <SettingSection title="Image Generation">
        <SettingRow
          label="Preferred Model"
          description="Model used for AI image generation"
        >
          <Select
            value={preferredImageModel}
            onValueChange={handleImageModelChange}
            disabled={isSavingImage}
          >
            <SelectTrigger className="w-56 h-8">
              <SelectValue>
                {isSavingImage ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Saving...
                  </span>
                ) : (
                  currentImageModel?.name || preferredImageModel
                )}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {availableImageModels.map((model) => (
                <SelectItem key={model.id} value={model.id}>
                  <div className="flex flex-col">
                    <span>{model.name}</span>
                    {model.description && (
                      <span className="text-xs text-muted-foreground">
                        {model.description}
                      </span>
                    )}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingRow>

        {/* Dynamic model descriptions from backend */}
        {availableImageModels.length > 0 && (
          <div className="py-3 border-t border-border/50">
            <div className="text-xs text-muted-foreground space-y-1">
              {availableImageModels.map((model) => (
                <p key={model.id}>
                  <strong>{model.name}</strong> - {model.description}
                  {model.price_info && ` (${model.price_info})`}
                </p>
              ))}
            </div>
          </div>
        )}
      </SettingSection>

      {/* Video Generation Section */}
      <SettingSection title="Video Generation">
        <SettingRow
          label="Preferred Model"
          description="Model used for AI video generation"
        >
          <Select
            value={preferredVideoModel}
            onValueChange={handleVideoModelChange}
            disabled={isSavingVideo}
          >
            <SelectTrigger className="w-56 h-8">
              <SelectValue>
                {isSavingVideo ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Saving...
                  </span>
                ) : (
                  currentVideoModel?.name || preferredVideoModel
                )}
              </SelectValue>
            </SelectTrigger>
            <SelectContent className="max-h-80">
              {availableVideoModels.map((model) => {
                const inputTypeLabels: Record<string, string> = {
                  text: 'Text→Video',
                  image: 'Image→Video',
                  video: 'Video→Video',
                  image_video: 'Image/Video→Video',
                  image_audio: 'Image+Video→Video',
                }
                return (
                  <SelectItem key={model.id} value={model.id}>
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <span>{model.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                          {inputTypeLabels[model.input_type] || model.input_type}
                        </span>
                      </div>
                      {model.best_for && (
                        <span className="text-xs text-muted-foreground">
                          {model.best_for}
                        </span>
                      )}
                    </div>
                  </SelectItem>
                )
              })}
            </SelectContent>
          </Select>
        </SettingRow>
      </SettingSection>

      {/* Sharing Section */}
      <SettingSection title="Sharing">
        <SettingRow
          label="Watermark"
          description="Add 'Sterna' watermark when sharing images"
        >
          <Switch
            checked={watermark.enabled}
            onCheckedChange={setWatermarkEnabled}
          />
        </SettingRow>

        <SettingRow
          label="Watermark Position"
          description="Where to place the watermark on shared images"
        >
          <Select
            value={watermark.position}
            onValueChange={(value) => setWatermarkPosition(value as 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left')}
            disabled={!watermark.enabled}
          >
            <SelectTrigger className="w-36 h-8">
              <SelectValue>
                {watermark.position === 'bottom-right' && 'Bottom Right'}
                {watermark.position === 'bottom-left' && 'Bottom Left'}
                {watermark.position === 'top-right' && 'Top Right'}
                {watermark.position === 'top-left' && 'Top Left'}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="bottom-right">Bottom Right</SelectItem>
              <SelectItem value="bottom-left">Bottom Left</SelectItem>
              <SelectItem value="top-right">Top Right</SelectItem>
              <SelectItem value="top-left">Top Left</SelectItem>
            </SelectContent>
          </Select>
        </SettingRow>
      </SettingSection>
    </div>
  )
}

const SETTINGS_SECTIONS = [
  { id: 'general', label: 'General', icon: <Settings className="h-4 w-4" /> },
  { id: 'chat', label: 'Chat', icon: <MessageSquare className="h-4 w-4" /> },
  { id: 'instructions', label: 'Instructions', icon: <ScrollText className="h-4 w-4" /> },
  { id: 'voice', label: 'Voice & Speech', icon: <Volume2 className="h-4 w-4" /> },
  { id: 'code', label: 'Code', icon: <Code2 className="h-4 w-4" /> },
  { id: 'images', label: 'Images & Video', icon: <Image className="h-4 w-4" /> },
  { id: 'apikey', label: 'API Key', icon: <Key className="h-4 w-4" /> },
  { id: 'usage', label: 'Usage & Limits', icon: <BarChart3 className="h-4 w-4" /> },
  { id: 'data', label: 'Data & Privacy', icon: <Shield className="h-4 w-4" /> },
]

export function SettingsModal() {
  const { isOpen, closeSettings, activeSection, setActiveSection } = useSettingsStore()
  const [showContent, setShowContent] = useState(false)

  // Reset to nav view when modal closes
  useEffect(() => {
    if (!isOpen) {
      setShowContent(false)
    }
  }, [isOpen])

  const handleSectionClick = (sectionId: string) => {
    setActiveSection(sectionId)
    setShowContent(true) // On mobile, show content when section is clicked
  }

  const handleBack = () => {
    setShowContent(false)
  }

  const renderContent = () => {
    switch (activeSection) {
      case 'general':
        return <GeneralSettings />
      case 'code':
        return <CodeSettings />
      case 'instructions':
        return <InstructionsSettings />
      case 'voice':
        return <VoiceSettings />
      case 'chat':
        return <ChatSettings />
      case 'images':
        return <ImageSettings />
      case 'apikey':
        return <BYOKSettings />
      case 'usage':
        return (
          <>
            <PlanCard />
            <UsageQuotaSettings />
          </>
        )
      case 'data':
        return <DataPrivacySettings />
      default:
        return <GeneralSettings />
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={closeSettings}>
      <DialogContent
        className="max-w-2xl p-0 gap-0 overflow-hidden max-h-[85vh] md:max-h-none"
        hideCloseButton
      >
        <DialogTitle className="sr-only">Settings</DialogTitle>
        <div className="flex h-[520px] max-h-[85vh] md:max-h-[520px]">
          {/* Sidebar Navigation - always visible on desktop, toggleable on mobile */}
          <div className={cn(
            "w-full md:w-48 flex-shrink-0 md:border-r border-border bg-muted/20 p-3",
            // On mobile: hide when showing content
            showContent ? "hidden md:block" : "block"
          )}>
            <div className="mb-4 px-3 pt-2">
              <h2 className="text-base font-semibold text-foreground">Settings</h2>
            </div>
            <nav className="space-y-1">
              {SETTINGS_SECTIONS.map((section) => (
                <SettingsNavItem
                  key={section.id}
                  id={section.id}
                  label={section.label}
                  icon={section.icon}
                  isActive={activeSection === section.id}
                  onClick={() => handleSectionClick(section.id)}
                />
              ))}
            </nav>
          </div>

          {/* Content Area - always visible on desktop, toggleable on mobile */}
          <div className={cn(
            "flex-1 min-h-0 flex flex-col",
            // On mobile: hide when showing nav
            showContent ? "flex" : "hidden md:flex"
          )}>
            {/* Mobile sticky header with back button */}
            <div className="md:hidden flex-shrink-0 bg-background border-b border-border px-4 py-3 flex items-center gap-3">
              <button
                onClick={handleBack}
                className="flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              >
                <ChevronRight className="h-5 w-5 rotate-180" />
              </button>
              <h3 className="text-base font-semibold text-foreground">
                {SETTINGS_SECTIONS.find(s => s.id === activeSection)?.label}
              </h3>
            </div>

            {/* Desktop sticky header */}
            <div className="hidden md:block flex-shrink-0 bg-background border-b border-border px-6 py-4">
              <h3 className="text-lg font-semibold text-foreground">
                {SETTINGS_SECTIONS.find(s => s.id === activeSection)?.label}
              </h3>
            </div>

            {/* Scrollable content */}
            <div className="flex-1 min-h-0 overflow-y-auto p-6">
              {renderContent()}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default SettingsModal
