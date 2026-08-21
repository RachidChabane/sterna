/**
 * ParticipantsRow - Dynamic participant display
 *
 * Active speaker gets prominent treatment (card with name/status).
 * Idle participants are minimal circular avatars.
 * Feels like a live conversation, not a static dashboard.
 */

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Package } from 'lucide-react'
import type { VoiceAgent } from '@/types/voiceRoom'
import { getColoredIconComponent, getIconRenderComponent, getAdaptiveIconColor } from '@/lib/provider-icons'
import { useTheme } from '@/hooks/useTheme'
import useModelStore from '@/store/modelStore'
import { useAuthStore } from '@/store/authStore'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

interface ParticipantsRowProps {
  agents: VoiceAgent[]
  currentSpeaker: string | null | undefined
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  className?: string
}

export function ParticipantsRow({
  agents,
  currentSpeaker,
  isListening,
  isSpeaking,
  isProcessing,
  className,
}: ParticipantsRowProps) {
  const { isDark } = useTheme()
  const { allModels } = useModelStore()
  const { user } = useAuthStore()

  const getModelInfo = (modelId: string) => {
    return allModels.find((m) => m.model_id === modelId)
  }

  const getModelIcon = (modelId: string, size: number = 20) => {
    const model = getModelInfo(modelId)
    const iconSlug = model?.model_icon_slug || model?.provider_icon_slug
    const iconComponent = getColoredIconComponent(iconSlug)

    if (!iconComponent) {
      return <Package size={size} className={isDark ? 'text-white/50' : 'text-gray-400'} />
    }

    const RenderIcon = getIconRenderComponent(iconComponent)
    const isMonochrome = !iconComponent.Color
    const adaptiveColor = isMonochrome ? getAdaptiveIconColor(iconSlug, isDark, iconComponent) : undefined

    return RenderIcon ? (
      <RenderIcon size={size} {...(adaptiveColor && { style: { color: adaptiveColor } })} />
    ) : (
      <Package size={size} className={isDark ? 'text-white/50' : 'text-gray-400'} />
    )
  }

  const participants = useMemo(() => {
    const userName = user?.first_name || user?.email?.split('@')[0] || 'You'
    return [
      { id: 'user', name: userName, isUser: true, modelId: null },
      ...agents.map(agent => ({
        id: agent.id,
        name: agent.display_name,
        isUser: false,
        modelId: agent.model_id,
      })),
    ]
  }, [agents, user])

  const getState = (participant: typeof participants[0]) => {
    if (participant.isUser && isListening) return 'listening'
    if (!participant.isUser && (isSpeaking || isProcessing) && currentSpeaker === participant.id) {
      return isSpeaking ? 'speaking' : 'processing'
    }
    return 'idle'
  }

  // Find active participant
  const activeParticipant = participants.find(p => getState(p) !== 'idle')
  const activeState = activeParticipant ? getState(activeParticipant) : null

  return (
    <div className={cn('flex flex-col items-center gap-6', className)}>
      {/* Active speaker - prominent card */}
      {activeParticipant && (
        <div
          className={cn(
            'flex items-center gap-4 px-6 py-4 rounded-2xl transition-all duration-500',
            'border backdrop-blur-md',
            isDark
              ? 'bg-white/10 border-white/20'
              : 'bg-white/80 border-black/10 shadow-lg',
          )}
        >
          {/* Glow effect */}
          <div
            className={cn(
              'absolute inset-0 rounded-2xl blur-2xl -z-10',
              activeState === 'listening' && 'bg-emerald-500/20',
              activeState === 'speaking' && 'bg-sky-500/20',
              activeState === 'processing' && 'bg-violet-500/20',
            )}
          />

          {/* Avatar */}
          <div
            className={cn(
              'relative h-12 w-12 rounded-xl flex items-center justify-center',
              isDark ? 'bg-white/10' : 'bg-black/5',
            )}
          >
            {activeParticipant.isUser ? (
              <Avatar className="h-9 w-9 ring-2 ring-emerald-400/50">
                <AvatarImage src={user?.avatar_url ?? undefined} alt="You" />
                <AvatarFallback className={cn(
                  'text-sm',
                  isDark ? 'bg-white/10 text-white/80' : 'bg-black/5 text-gray-600'
                )}>
                  {user?.first_name?.charAt(0) || user?.email?.charAt(0)?.toUpperCase() || 'U'}
                </AvatarFallback>
              </Avatar>
            ) : (
              getModelIcon(activeParticipant.modelId || '', 24)
            )}

            {/* Pulse indicator */}
            <div
              className={cn(
                'absolute -top-1 -right-1 h-3 w-3 rounded-full border-2',
                isDark ? 'border-[#111]' : 'border-white',
                activeState === 'listening' && 'bg-emerald-400',
                activeState === 'speaking' && 'bg-sky-400',
                activeState === 'processing' && 'bg-violet-400',
              )}
            >
              <div
                className={cn(
                  'absolute inset-0 rounded-full animate-ping',
                  activeState === 'listening' && 'bg-emerald-400',
                  activeState === 'speaking' && 'bg-sky-400',
                  activeState === 'processing' && 'bg-violet-400',
                )}
                style={{ animationDuration: '1.5s' }}
              />
            </div>
          </div>

          {/* Name and status */}
          <div className="flex flex-col">
            <span
              className={cn(
                'text-base font-medium',
                isDark ? 'text-white' : 'text-gray-900'
              )}
            >
              {activeParticipant.name}
            </span>
            <span
              className={cn(
                'text-xs uppercase tracking-wider',
                activeState === 'listening' && 'text-emerald-500',
                activeState === 'speaking' && 'text-sky-500',
                activeState === 'processing' && 'text-violet-500',
              )}
            >
              {activeState === 'listening' ? 'listening' : activeState === 'speaking' ? 'speaking' : 'thinking...'}
            </span>
          </div>
        </div>
      )}

      {/* Idle participants - minimal avatars */}
      <div className="flex items-center gap-2">
        {participants
          .filter(p => getState(p) === 'idle')
          .map((participant) => (
            <div
              key={participant.id}
              className={cn(
                'relative h-10 w-10 rounded-full flex items-center justify-center transition-all duration-300',
                'border',
                isDark
                  ? 'bg-white/5 border-white/10 hover:bg-white/10'
                  : 'bg-black/[0.02] border-black/5 hover:bg-black/5',
              )}
              title={participant.name}
            >
              {participant.isUser ? (
                <Avatar className="h-7 w-7">
                  <AvatarImage src={user?.avatar_url ?? undefined} alt="You" />
                  <AvatarFallback className={cn(
                    'text-xs',
                    isDark ? 'bg-white/10 text-white/60' : 'bg-black/5 text-gray-500'
                  )}>
                    {user?.first_name?.charAt(0) || user?.email?.charAt(0)?.toUpperCase() || 'U'}
                  </AvatarFallback>
                </Avatar>
              ) : (
                <div className="opacity-60">
                  {getModelIcon(participant.modelId || '', 18)}
                </div>
              )}
            </div>
          ))}
      </div>
    </div>
  )
}
