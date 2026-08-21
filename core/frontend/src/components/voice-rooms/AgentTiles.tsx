/**
 * AgentTiles - Horizontal row of agent cards
 *
 * Clean, modern display of all participants.
 * Active speaker gets highlighted with glow and scale.
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

interface AgentTilesProps {
  agents: VoiceAgent[]
  currentSpeaker: string | null | undefined
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  className?: string
}

export function AgentTiles({
  agents,
  currentSpeaker,
  isListening,
  isSpeaking,
  isProcessing,
  className,
}: AgentTilesProps) {
  const { isDark } = useTheme()
  const { allModels } = useModelStore()
  const { user } = useAuthStore()

  // Helper to find model info by model_id
  const getModelInfo = (modelId: string) => {
    return allModels.find((m) => m.model_id === modelId)
  }

  // Get the icon component for a model
  const getModelIcon = (modelId: string, size: number = 20) => {
    const model = getModelInfo(modelId)
    const iconSlug = model?.model_icon_slug || model?.provider_icon_slug
    const iconComponent = getColoredIconComponent(iconSlug)

    if (!iconComponent) {
      return <Package size={size} className="text-white/50" />
    }

    const RenderIcon = getIconRenderComponent(iconComponent)
    const isMonochrome = !iconComponent.Color
    const adaptiveColor = isMonochrome ? getAdaptiveIconColor(iconSlug, isDark, iconComponent) : undefined

    return RenderIcon ? (
      <RenderIcon size={size} {...(adaptiveColor && { style: { color: adaptiveColor } })} />
    ) : (
      <Package size={size} className="text-white/50" />
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

  return (
    <div className={cn('flex items-center justify-center gap-3', className)}>
      {participants.map((participant) => {
        const state = getState(participant)
        const isActive = state !== 'idle'

        return (
          <div
            key={participant.id}
            className={cn(
              'relative flex items-center gap-3 px-4 py-3 rounded-2xl transition-all duration-500 ease-out',
              'border backdrop-blur-md',
              isActive
                ? isDark
                  ? 'bg-white/10 border-white/20 scale-105'
                  : 'bg-black/5 border-black/10 scale-105'
                : isDark
                  ? 'bg-white/[0.03] border-white/[0.06] scale-100'
                  : 'bg-black/[0.02] border-black/[0.05] scale-100',
            )}
          >
            {/* Glow effect */}
            {isActive && (
              <div
                className={cn(
                  'absolute inset-0 rounded-2xl blur-xl -z-10 transition-opacity duration-500',
                  state === 'listening' && 'bg-emerald-500/20',
                  state === 'speaking' && 'bg-sky-500/20',
                  state === 'processing' && 'bg-violet-500/20',
                )}
              />
            )}

            {/* Avatar */}
            <div
              className={cn(
                'relative h-10 w-10 rounded-xl flex items-center justify-center transition-all duration-300',
                isActive
                  ? isDark ? 'bg-white/10' : 'bg-black/5'
                  : isDark ? 'bg-white/5' : 'bg-black/[0.03]',
              )}
            >
              {participant.isUser ? (
                <Avatar className={cn(
                  'h-7 w-7 transition-all duration-300',
                  state === 'listening' && 'ring-2 ring-emerald-400/50'
                )}>
                  <AvatarImage src={user?.avatar_url ?? undefined} alt="You" />
                  <AvatarFallback className={cn(
                    'text-xs',
                    isDark ? 'bg-white/10 text-white/80' : 'bg-black/5 text-gray-600'
                  )}>
                    {user?.first_name?.charAt(0) || user?.email?.charAt(0)?.toUpperCase() || 'U'}
                  </AvatarFallback>
                </Avatar>
              ) : (
                <div className={cn(
                  'transition-opacity duration-300',
                  isActive ? 'opacity-100' : 'opacity-70'
                )}>
                  {getModelIcon(participant.modelId || '', 20)}
                </div>
              )}

              {/* Active indicator dot */}
              {isActive && (
                <div
                  className={cn(
                    'absolute -top-1 -right-1 h-3 w-3 rounded-full border-2',
                    isDark ? 'border-[#111]' : 'border-white',
                    state === 'listening' && 'bg-emerald-400',
                    state === 'speaking' && 'bg-sky-400',
                    state === 'processing' && 'bg-violet-400',
                  )}
                >
                  <div
                    className={cn(
                      'absolute inset-0 rounded-full animate-ping',
                      state === 'listening' && 'bg-emerald-400',
                      state === 'speaking' && 'bg-sky-400',
                      state === 'processing' && 'bg-violet-400',
                    )}
                    style={{ animationDuration: '1.5s' }}
                  />
                </div>
              )}
            </div>

            {/* Name and status */}
            <div className="flex flex-col min-w-0">
              <span
                className={cn(
                  'text-sm font-medium transition-colors duration-300 truncate',
                  isActive
                    ? isDark ? 'text-white' : 'text-gray-900'
                    : isDark ? 'text-white/50' : 'text-gray-500'
                )}
              >
                {participant.name}
              </span>
              <span
                className={cn(
                  'text-[10px] uppercase tracking-wider transition-colors duration-300',
                  state === 'listening' && 'text-emerald-500',
                  state === 'speaking' && 'text-sky-500',
                  state === 'processing' && 'text-violet-500',
                  state === 'idle' && (isDark ? 'text-white/20' : 'text-gray-400'),
                )}
              >
                {state === 'listening' ? 'listening' : state === 'speaking' ? 'speaking' : state === 'processing' ? 'thinking...' : 'idle'}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
