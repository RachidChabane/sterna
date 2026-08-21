/**
 * ParticipantStrip - Shows all participants in the voice room
 *
 * Horizontal strip showing user + all agents with clear
 * indication of who is currently speaking.
 */

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { ModelIcon } from '@/components/models/ModelIcon'
import { User } from 'lucide-react'
import useModelStore from '@/store/modelStore'
import type { VoiceAgent } from '@/types/voiceRoom'

interface ParticipantStripProps {
  agents: VoiceAgent[]
  currentSpeaker: string | null | undefined
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  className?: string
}

export function ParticipantStrip({
  agents,
  currentSpeaker,
  isListening,
  isSpeaking,
  isProcessing,
  className,
}: ParticipantStripProps) {
  const { allModels } = useModelStore()

  const participants = useMemo(() => {
    return [
      { id: 'user', name: 'You', isUser: true, modelId: null },
      ...agents.map(agent => ({
        id: agent.id,
        name: agent.display_name,
        isUser: false,
        modelId: agent.model_id,
      })),
    ]
  }, [agents])

  // Determine who is active
  const getParticipantState = (participant: typeof participants[0]) => {
    if (participant.isUser) {
      if (isListening) return 'active'
      return 'idle'
    } else {
      if ((isSpeaking || isProcessing) && currentSpeaker === participant.id) {
        return isSpeaking ? 'speaking' : 'processing'
      }
      return 'idle'
    }
  }

  return (
    <div className={cn('flex items-center justify-center gap-6', className)}>
      {participants.map((participant) => {
        const state = getParticipantState(participant)
        const isActive = state !== 'idle'

        return (
          <div
            key={participant.id}
            className={cn(
              'flex flex-col items-center gap-2 transition-all duration-300',
              isActive ? 'scale-110' : 'scale-100 opacity-50'
            )}
          >
            {/* Avatar with ring */}
            <div className="relative">
              {/* Glow effect for active */}
              {isActive && (
                <div
                  className={cn(
                    'absolute -inset-3 rounded-full blur-xl',
                    state === 'active' && 'bg-emerald-500/30',
                    state === 'speaking' && 'bg-blue-500/30',
                    state === 'processing' && 'bg-violet-500/30',
                  )}
                />
              )}

              {/* Ring */}
              <div
                className={cn(
                  'relative w-14 h-14 rounded-full flex items-center justify-center transition-all duration-300',
                  'ring-2 ring-offset-2 ring-offset-[#0a0a0a]',
                  state === 'idle' && 'bg-white/5 ring-white/10',
                  state === 'active' && 'bg-emerald-500/10 ring-emerald-500',
                  state === 'speaking' && 'bg-blue-500/10 ring-blue-500',
                  state === 'processing' && 'bg-violet-500/10 ring-violet-500',
                )}
              >
                {participant.isUser ? (
                  <User
                    className={cn(
                      'h-6 w-6 transition-colors duration-300',
                      isActive ? 'text-emerald-400' : 'text-white/40'
                    )}
                  />
                ) : (() => {
                  const model = allModels.find((m) => m.model_id === participant.modelId)
                  return (
                    <ModelIcon
                      modelName={model?.name || participant.name}
                      modelId={participant.modelId || ''}
                      provider={model?.provider || ''}
                      modelIconSlug={model?.model_icon_slug}
                      modelIconUrl={model?.model_icon_url}
                      providerIconSlug={model?.provider_icon_slug}
                      providerIconUrl={model?.provider_icon_url}
                      className={cn(
                        'h-7 w-7 transition-opacity duration-300',
                        isActive ? 'opacity-100' : 'opacity-50'
                      )}
                    />
                  )
                })()}
              </div>

              {/* Pulse animation for active speaker */}
              {isActive && (
                <div
                  className={cn(
                    'absolute inset-0 rounded-full animate-ping opacity-30',
                    state === 'active' && 'ring-2 ring-emerald-500',
                    state === 'speaking' && 'ring-2 ring-blue-500',
                    state === 'processing' && 'ring-2 ring-violet-500',
                  )}
                  style={{ animationDuration: '1.5s' }}
                />
              )}
            </div>

            {/* Name */}
            <span
              className={cn(
                'text-xs font-medium transition-all duration-300',
                state === 'idle' && 'text-white/30',
                state === 'active' && 'text-emerald-400',
                state === 'speaking' && 'text-blue-400',
                state === 'processing' && 'text-violet-400',
              )}
            >
              {participant.name}
            </span>

            {/* Status label for active */}
            {isActive && (
              <span
                className={cn(
                  'text-[10px] uppercase tracking-wider',
                  state === 'active' && 'text-emerald-500/60',
                  state === 'speaking' && 'text-blue-500/60',
                  state === 'processing' && 'text-violet-500/60',
                )}
              >
                {state === 'active' ? 'listening' : state}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
