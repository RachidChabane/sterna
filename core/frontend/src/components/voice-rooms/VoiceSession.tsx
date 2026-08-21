import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Slider } from '@/components/ui/slider'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Mic, MicOff, X, Settings, MessageSquareText, Hand, Maximize2, Minimize2 } from 'lucide-react'
import { useVoiceRoomSocket } from '@/hooks/useVoiceRoomSocket'
import useVoiceRoomStore from '@/store/voiceRoomStore'
import useModelStore from '@/store/modelStore'
import { getAccessToken } from '@/api/client'
import { SpatialPresence } from './SpatialPresence'
import { getAgentColor } from './AgentPresence'
import { TranscriptDrawer } from './TranscriptDrawer'
import { LiveTranscript } from './LiveTranscript'
import { UserVoicePulse } from './UserVoicePulse'
import { ModelDetailsModal } from '@/components/models/ModelDetailsModal'
import type { VoiceRoom } from '@/types/voiceRoom'
import type { ModelCatalogEntry } from '@/types/models'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'

interface VoiceSettings {
  silenceTimeout: number // seconds before processing (1-5)
  interruptionThreshold: number // 0-100, higher = harder to interrupt
  allowInterruptions: boolean
  showTranscript: boolean // show live transcript display
}

const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  silenceTimeout: 2,
  interruptionThreshold: 50,
  allowInterruptions: true,
  showTranscript: true,
}

interface VoiceSessionProps {
  room: VoiceRoom
  onEnd: () => void
}

export function VoiceSession({ room, onEnd }: VoiceSessionProps) {
  const { isDark } = useTheme()
  const accessToken = getAccessToken()
  const [agentAudioLevel, setAgentAudioLevel] = useState(0)
  const [micError, setMicError] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [transcriptOpen, setTranscriptOpen] = useState(false)
  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const [isFullScreen, setIsFullScreen] = useState(false)
  const [headerHovered, setHeaderHovered] = useState(false)
  const [footerHovered, setFooterHovered] = useState(false)
  const [selectedModelForDetails, setSelectedModelForDetails] = useState<ModelCatalogEntry | null>(null)
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>(() => {
    // Load from localStorage if available
    const saved = localStorage.getItem('voice-room-settings')
    return saved ? { ...DEFAULT_VOICE_SETTINGS, ...JSON.parse(saved) } : DEFAULT_VOICE_SETTINGS
  })

  // Save settings to localStorage when they change
  useEffect(() => {
    localStorage.setItem('voice-room-settings', JSON.stringify(voiceSettings))
  }, [voiceSettings])

  // Get room ID safely
  const roomId = room?.id || ''

  const {
    sessionState,
    isConnected,
    isRecording,
    audioLevel,
    streamingMessage,
    waitingForNextAudio,
  } = useVoiceRoomStore()

  const { allModels } = useModelStore()

  const {
    connect,
    disconnect,
    startRecording,
    stopRecording,
    interrupt,
    endSession,
    updateSettings,
    error,
  } = useVoiceRoomSocket({
    roomId,
    token: accessToken || '',
    onConnected: () => {
      
    },
    onDisconnected: () => {
      
    },
    onError: (err) => {
      console.error('Voice room error:', err)
    },
  })

  const status = sessionState?.status || 'idle'
  const currentSpeaker = sessionState?.current_speaker

  // Simulate agent audio level when speaking
  // NOTE: All hooks must be called unconditionally before any early returns
  useEffect(() => {
    if (!room?.id) return
    if (status === 'speaking') {
      const interval = setInterval(() => {
        setAgentAudioLevel(0.3 + Math.random() * 0.5)
      }, 100)
      return () => {
        clearInterval(interval)
        setAgentAudioLevel(0)
      }
    } else {
      setAgentAudioLevel(0)
    }
  }, [status, room?.id])

  // Connect on mount (only if roomId is valid)
  useEffect(() => {
    if (!roomId) {
      console.warn('No room ID available, skipping connection')
      return
    }
    const token = getAccessToken()
    if (!token) {
      console.warn('No access token available')
      return
    }
    connect()
    return () => {
      disconnect()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId])

  // Auto-start recording when connected
  useEffect(() => {
    if (!room?.id) return
    if (isConnected && !isRecording) {
      
      startRecording().catch((err) => {
        console.error('Failed to auto-start recording:', err)
        setMicError('Failed to access microphone. Please allow microphone access.')
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected, room?.id])

  // Send settings to backend when connected or settings change
  useEffect(() => {
    if (!room?.id) return
    if (isConnected) {
      
      updateSettings(voiceSettings)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected, voiceSettings, room?.id])

  // Mic button toggles mute (mic stays on, just muted)
  const handleMicClick = useCallback(async () => {
    
    setMicError(null)

    if (isRecording) {
      // Mute - stop recording
      
      stopRecording()
    } else {
      // Unmute - start recording again
      
      try {
        await startRecording()
        
      } catch (err) {
        console.error('Failed to unmute:', err)
        setMicError(err instanceof Error ? err.message : 'Failed to access microphone')
      }
    }
  }, [isRecording, startRecording, stopRecording])

  const handleEndSession = useCallback(() => {
    endSession()
    onEnd()
  }, [endSession, onEnd])

  // Handle clicking model icon to view details
  const handleViewModelDetails = useCallback((modelId: string) => {
    const model = allModels.find(m => m.model_id === modelId)
    if (model) {
      setSelectedModelForDetails(model as ModelCatalogEntry)
      setDetailsModalOpen(true)
    }
  }, [allModels])

  // Guard: ensure room and room.id exist (AFTER all hooks)
  if (!room?.id) {
    console.error('[VoiceSession] Room or room.id is undefined:', room)
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#1a1a1a]">
        <p className="text-white">Error: Invalid room configuration</p>
      </div>
    )
  }

  // Priority: speaking > processing > listening
  // Even if mic is recording, if AI is speaking, show speaking state
  const isSpeaking = status === 'speaking'
  const isProcessing = status === 'processing'
  const isListening = !isSpeaking && !isProcessing && (status === 'listening' || isRecording)

  // Check if any agent uses OpenAI TTS (for tip message)
  // Check explicit provider setting, or fallback to known OpenAI voice IDs for older rooms
  const OPENAI_VOICE_IDS = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
  const usesOpenAITTS = room.agents?.some(agent =>
    agent.voice_settings?.tts_provider === 'openai' ||
    (!agent.voice_settings?.tts_provider && OPENAI_VOICE_IDS.includes(agent.voice_id))
  ) ?? false
  // Use agent's simulated audio when speaking, user's mic level otherwise
  const effectiveAudioLevel = isSpeaking ? agentAudioLevel : audioLevel

  // Calculate next agent ID for waiting state (when current agent finishes, show thinking for next)
  const nextAgentId = (() => {
    if (!currentSpeaker || !room.agents?.length) return room.agents?.[0]?.id
    const currentIndex = room.agents.findIndex(a => a.id === currentSpeaker)
    if (currentIndex < 0) return room.agents[0]?.id
    const nextIndex = (currentIndex + 1) % room.agents.length
    return room.agents[nextIndex].id
  })()

  // Find the active speaker's name and color for the presence display
  const { activeSpeakerName, activeSpeakerColor } = (() => {
    if (isListening) return { activeSpeakerName: 'You', activeSpeakerColor: undefined }
    if ((isSpeaking || isProcessing) && currentSpeaker) {
      const agentIndex = room.agents?.findIndex(a => a.id === currentSpeaker) ?? -1
      const agent = agentIndex >= 0 ? room.agents?.[agentIndex] : undefined

      // Use custom color if set, otherwise fall back to auto-assigned
      let color: { r: number; g: number; b: number } | undefined
      if (agent?.color) {
        const hex = agent.color.replace('#', '')
        color = {
          r: parseInt(hex.substring(0, 2), 16),
          g: parseInt(hex.substring(2, 4), 16),
          b: parseInt(hex.substring(4, 6), 16)
        }
      } else if (agentIndex >= 0) {
        color = getAgentColor(currentSpeaker, agentIndex)
      }

      return {
        activeSpeakerName: agent?.display_name,
        activeSpeakerColor: color
      }
    }
    return { activeSpeakerName: undefined, activeSpeakerColor: undefined }
  })()

  const showHeader = !isFullScreen || headerHovered
  const showFooter = !isFullScreen || footerHovered

  return (
    <div className={cn(
      "fixed inset-0 z-50 flex flex-col overflow-hidden",
      isDark ? "bg-[#0c0c0c]" : "bg-slate-50"
    )}>
      {/* Main content area - spatial presence, adjusts with header/footer */}
      <div
        className="flex-1 min-h-0 relative overflow-hidden transition-all duration-500 ease-out"
        style={{
          marginTop: isFullScreen && !headerHovered ? 0 : undefined,
          marginBottom: isFullScreen && !footerHovered ? 0 : undefined,
        }}
      >
        {/* Absolute positioned wrapper ensures SpatialPresence fills the flex container */}
        <div className="absolute inset-0">
          <SpatialPresence
            agents={room.agents || []}
            isListening={isListening}
            isSpeaking={isSpeaking && !waitingForNextAudio}
            isProcessing={isProcessing || waitingForNextAudio}
            audioLevel={effectiveAudioLevel}
            currentSpeaker={waitingForNextAudio ? nextAgentId : currentSpeaker}
            className="w-full h-full transition-all duration-500"
            paddingTop={isFullScreen && !headerHovered ? 0 : 70}
            paddingBottom={isFullScreen && !footerHovered ? 0 : 90}
          />
        </div>

        {/* User voice pulse - subtle glow responding to user's audio input */}
        <UserVoicePulse
          audioLevel={audioLevel}
          isListening={isRecording}
          isDark={isDark}
        />

        {/* Centered transcript - mobile only, multi-agent only */}
        {voiceSettings.showTranscript && room.agents && room.agents.length > 1 && (
          <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none md:hidden">
            <LiveTranscript isDark={isDark} agents={room.agents} />
          </div>
        )}

        {/* Error display */}
        {(error || micError) && (
          <div className="absolute top-8 left-0 right-0 flex justify-center z-20">
            <div className={cn(
              'px-4 py-2 rounded-xl backdrop-blur-md',
              isDark ? 'bg-red-500/10 border border-red-500/20' : 'bg-red-50 border border-red-200'
            )}>
              <p className="text-red-400 text-sm max-w-md text-center">
                {error || micError}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Header - overlays with gradient fade */}
      <div
        className={cn(
          "absolute top-0 left-0 right-0 z-20 transition-all duration-500 ease-out",
          isFullScreen && !headerHovered ? "-translate-y-full opacity-0" : "translate-y-0 opacity-100"
        )}
        onMouseEnter={() => isFullScreen && setHeaderHovered(true)}
        onMouseLeave={() => setHeaderHovered(false)}
      >
        {/* Gradient fade background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: isDark
              ? 'linear-gradient(to bottom, rgba(12,12,12,0.9) 0%, rgba(12,12,12,0.6) 60%, transparent 100%)'
              : 'linear-gradient(to bottom, rgba(248,250,252,0.9) 0%, rgba(248,250,252,0.6) 60%, transparent 100%)',
          }}
        />
        <div className="relative px-5 py-4 pb-8 flex items-center justify-between">
          {/* Transcript button */}
          <Button
            size="icon"
            variant="ghost"
            className={cn(
              'h-9 w-9 rounded-xl transition-all duration-200',
              isDark
                ? 'text-white/50 hover:text-white/80 hover:bg-white/5'
                : 'text-gray-500 hover:text-gray-700 hover:bg-black/5'
            )}
            onClick={() => setTranscriptOpen(true)}
            title="Transcript"
          >
            <MessageSquareText className="h-4 w-4" />
          </Button>

          {/* Room name */}
          <span className={cn(
            'text-xs font-medium tracking-wider uppercase',
            isDark ? 'text-white/50' : 'text-gray-500'
          )}>
            {room.name}
          </span>

          {/* Settings button */}
          <Button
            size="icon"
            variant="ghost"
            className={cn(
              'h-9 w-9 rounded-xl transition-all duration-200',
              isDark
                ? 'text-white/50 hover:text-white/80 hover:bg-white/5'
                : 'text-gray-500 hover:text-gray-700 hover:bg-black/5'
            )}
            onClick={() => setSettingsOpen(true)}
          >
            <Settings className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Hover zone for header in fullscreen */}
      {isFullScreen && !headerHovered && (
        <div
          className="absolute top-0 left-0 right-0 h-16 z-10"
          onMouseEnter={() => setHeaderHovered(true)}
        />
      )}

      {/* Hover zone for footer in fullscreen */}
      {isFullScreen && !footerHovered && (
        <div
          className="absolute bottom-0 left-0 right-0 h-16 z-10"
          onMouseEnter={() => setFooterHovered(true)}
        />
      )}

      {/* Footer - overlays with gradient fade */}
      <div
        className={cn(
          "absolute bottom-0 left-0 right-0 z-20 transition-all duration-500 ease-out",
          isFullScreen && !footerHovered ? "translate-y-full opacity-0" : "translate-y-0 opacity-100"
        )}
        onMouseEnter={() => isFullScreen && setFooterHovered(true)}
        onMouseLeave={() => setFooterHovered(false)}
      >
        {/* Gradient fade background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: isDark
              ? 'linear-gradient(to top, rgba(12,12,12,0.9) 0%, rgba(12,12,12,0.6) 60%, transparent 100%)'
              : 'linear-gradient(to top, rgba(248,250,252,0.9) 0%, rgba(248,250,252,0.6) 60%, transparent 100%)',
          }}
        />
        <div className="relative px-4 md:px-5 pt-3 md:pt-4 pb-2 md:pb-3 flex flex-col items-center gap-2 md:gap-3">
          {/* Live transcript - above controls (always for single-agent, desktop-only for multi-agent) */}
          {voiceSettings.showTranscript && (
            <LiveTranscript
              isDark={isDark}
              className={cn("mb-2", room.agents?.length === 1 ? "flex" : "hidden md:flex")}
              agents={room.agents}
            />
          )}

          <div className="flex items-center justify-center gap-4">
            {/* Fullscreen toggle */}
            <Button
              size="icon"
              variant="ghost"
              className={cn(
                'h-11 w-11 rounded-2xl transition-all duration-200',
                isDark
                  ? 'text-white/50 hover:text-white/80 hover:bg-white/10'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-black/5'
              )}
              onClick={() => setIsFullScreen(!isFullScreen)}
              title={isFullScreen ? "Exit fullscreen" : "Fullscreen"}
            >
              {isFullScreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </Button>

            {/* Interrupt button - shows when AI is speaking */}
            {isSpeaking && (
              <Button
                size="icon"
                className="h-11 w-11 rounded-2xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/20 transition-all duration-200"
                onClick={interrupt}
                title="Interrupt"
              >
                <Hand className="h-5 w-5" />
              </Button>
            )}

            {/* Mic button - central, prominent */}
            <Button
              size="icon"
              className={cn(
                'h-14 w-14 rounded-2xl transition-all duration-300 shadow-lg',
                isRecording
                  ? isDark
                    ? 'bg-white/10 text-white border border-white/20 hover:bg-white/15'
                    : 'bg-black/5 text-gray-800 border border-black/10 hover:bg-black/10'
                  : 'bg-red-500/90 text-white border border-red-400/30 hover:bg-red-500'
              )}
              onClick={handleMicClick}
              disabled={!isConnected}
            >
              {isRecording ? (
                <Mic className="h-6 w-6" />
              ) : (
                <MicOff className="h-6 w-6" />
              )}
            </Button>

            {/* Close button */}
            <Button
              size="icon"
              variant="ghost"
              className={cn(
                'h-11 w-11 rounded-2xl transition-all duration-200',
                isDark
                  ? 'text-white/50 hover:text-white/80 hover:bg-white/10'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-black/5'
              )}
              onClick={handleEndSession}
            >
              <X className="h-5 w-5" />
            </Button>
          </div>

          {/* OpenAI TTS tip - shown discreetly when using OpenAI voices */}
          {usesOpenAITTS && isConnected && (
            <span className={cn(
              'text-[9px] md:text-[10px] tracking-wide text-center max-w-[280px] md:max-w-none leading-tight',
              isDark ? 'text-white/30' : 'text-gray-400'
            )}>
              For faster responses and smoother captions, try ElevenLabs voices in room settings
            </span>
          )}
        </div>
      </div>

      {/* Settings Modal */}
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className={cn(
          'max-w-md',
          isDark ? 'bg-[#1a1a1a] border-white/10 text-white' : 'bg-white border-gray-200 text-gray-900'
        )}>
          <DialogHeader>
            <DialogTitle className={isDark ? 'text-white' : 'text-gray-900'}>Voice Settings</DialogTitle>
            <DialogDescription className={isDark ? 'text-white/60' : 'text-gray-500'}>
              Adjust voice interaction settings
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-6 py-4">
            {/* Silence Timeout */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className={isDark ? 'text-white/80' : 'text-gray-700'}>Silence Detection</Label>
                <span className={cn('text-sm', isDark ? 'text-white/50' : 'text-gray-500')}>{voiceSettings.silenceTimeout}s</span>
              </div>
              <Slider
                value={[voiceSettings.silenceTimeout]}
                onValueChange={([value]) => setVoiceSettings(s => ({ ...s, silenceTimeout: value }))}
                min={1}
                max={5}
                step={0.5}
                className="w-full"
              />
              <p className={cn('text-xs', isDark ? 'text-white/40' : 'text-gray-400')}>
                How long to wait after you stop speaking before processing
              </p>
            </div>

            {/* Interruption Threshold */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className={isDark ? 'text-white/80' : 'text-gray-700'}>Echo Sensitivity</Label>
                <span className={cn('text-sm', isDark ? 'text-white/50' : 'text-gray-500')}>{voiceSettings.interruptionThreshold}%</span>
              </div>
              <Slider
                value={[voiceSettings.interruptionThreshold]}
                onValueChange={([value]) => setVoiceSettings(s => ({ ...s, interruptionThreshold: value }))}
                min={0}
                max={100}
                step={5}
                className="w-full"
              />
              <p className={cn('text-xs', isDark ? 'text-white/40' : 'text-gray-400')}>
                Higher = less likely to pick up AI voice as your speech. Lower if using headphones.
              </p>
            </div>

            {/* Allow Interruptions */}
            <div className="flex items-center justify-between">
              <div>
                <Label className={isDark ? 'text-white/80' : 'text-gray-700'}>Allow Interruptions</Label>
                <p className={cn('text-xs mt-1', isDark ? 'text-white/40' : 'text-gray-400')}>
                  Speak over the AI to interrupt its response
                </p>
              </div>
              <Switch
                checked={voiceSettings.allowInterruptions}
                onCheckedChange={(checked) => setVoiceSettings(s => ({ ...s, allowInterruptions: checked }))}
              />
            </div>

            {/* Show Live Transcript */}
            <div className="flex items-center justify-between">
              <div>
                <Label className={isDark ? 'text-white/80' : 'text-gray-700'}>Live Transcript</Label>
                <p className={cn('text-xs mt-1', isDark ? 'text-white/40' : 'text-gray-400')}>
                  Show real-time captions of the conversation
                </p>
              </div>
              <Switch
                checked={voiceSettings.showTranscript}
                onCheckedChange={(checked) => setVoiceSettings(s => ({ ...s, showTranscript: checked }))}
              />
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Connection indicator */}
      {!isConnected && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20">
          <div className={cn(
            'flex items-center gap-2 px-3 py-1.5 rounded-xl backdrop-blur-sm border',
            isDark ? 'bg-white/5 border-white/10' : 'bg-black/5 border-black/10'
          )}>
            <div className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
            <span className={cn('text-xs', isDark ? 'text-white/40' : 'text-gray-500')}>Connecting</span>
          </div>
        </div>
      )}


      {/* Debug info */}
      {process.env.NODE_ENV === 'development' && (
        <div className={cn('absolute bottom-24 left-4 text-[10px] font-mono z-10', isDark ? 'text-white/10' : 'text-gray-300')}>
          <p>{isConnected ? '●' : '○'} {status} | lvl: {effectiveAudioLevel.toFixed(2)}</p>
        </div>
      )}

      {/* Transcript Drawer */}
      <TranscriptDrawer
        open={transcriptOpen}
        onOpenChange={setTranscriptOpen}
        messages={sessionState?.conversation || []}
        agents={room.agents || []}
        roomName={room.name}
        onViewModelDetails={handleViewModelDetails}
        streamingMessage={streamingMessage}
        thinkingAgentId={(isProcessing || waitingForNextAudio) && !streamingMessage ? (waitingForNextAudio ? nextAgentId : currentSpeaker) : undefined}
      />

      {/* Model Details Modal */}
      <ModelDetailsModal
        model={selectedModelForDetails}
        isOpen={detailsModalOpen}
        onClose={() => setDetailsModalOpen(false)}
      />
    </div>
  )
}
