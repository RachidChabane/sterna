/**
 * AgentBar - Horizontal agent display for voice rooms
 *
 * Modern, minimal design inspired by contemporary voice interfaces.
 * Shows agents in a horizontal row with subtle animations.
 */

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { ModelIcon } from '@/components/models/ModelIcon'
import { User } from 'lucide-react'
import useModelStore from '@/store/modelStore'
import type { VoiceAgent } from '@/types/voiceRoom'

interface AgentBarProps {
  agents: VoiceAgent[]
  currentSpeaker: string | null | undefined
  isConnected: boolean
  className?: string
}

export function AgentBar({
  agents,
  currentSpeaker,
  isConnected,
  className,
}: AgentBarProps) {
  const { allModels } = useModelStore()

  // Include user as first participant
  const participants = useMemo(() => {
    return [
      { id: 'user', name: 'You', isUser: true, modelId: null },
      ...agents.map(agent => ({
        id: agent.id,
        name: agent.display_name,
        modelId: agent.model_id,
        isUser: false,
      })),
    ]
  }, [agents])

  return (
    <div className={cn('flex items-center justify-center gap-8', className)}>
      {participants.map((participant) => {
        const isActive = participant.isUser
          ? currentSpeaker === 'user'
          : currentSpeaker === participant.id

        return (
          <div
            key={participant.id}
            className="flex flex-col items-center gap-3"
          >
            {/* Avatar container */}
            <div className="relative">
              {/* Glow ring for active speaker */}
              <div
                className={cn(
                  'absolute -inset-2 rounded-full transition-all duration-500',
                  isActive && isConnected
                    ? participant.isUser
                      ? 'bg-green-500/20 blur-xl'
                      : 'bg-blue-500/20 blur-xl'
                    : 'opacity-0'
                )}
              />

              {/* Ring indicator */}
              <div
                className={cn(
                  'absolute -inset-1 rounded-full transition-all duration-300',
                  isActive && isConnected
                    ? participant.isUser
                      ? 'ring-2 ring-green-500/50'
                      : 'ring-2 ring-blue-500/50'
                    : 'ring-1 ring-white/10'
                )}
              />

              {/* Avatar */}
              <div
                className={cn(
                  'relative h-14 w-14 rounded-full flex items-center justify-center transition-all duration-300',
                  'bg-white/5 backdrop-blur-sm',
                  isActive && isConnected && 'scale-110'
                )}
              >
                {participant.isUser ? (
                  <User className="h-6 w-6 text-white/70" />
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
                      className="h-8 w-8"
                    />
                  )
                })()}
              </div>

              {/* Pulse animation for active speaker */}
              {isActive && isConnected && (
                <div
                  className={cn(
                    'absolute -inset-1 rounded-full animate-ping opacity-30',
                    participant.isUser ? 'bg-green-500' : 'bg-blue-500'
                  )}
                  style={{ animationDuration: '2s' }}
                />
              )}
            </div>

            {/* Name label */}
            <span
              className={cn(
                'text-xs font-medium transition-colors duration-300',
                isActive && isConnected
                  ? 'text-white'
                  : 'text-white/40'
              )}
            >
              {participant.name}
            </span>
          </div>
        )
      })}
    </div>
  )
}
