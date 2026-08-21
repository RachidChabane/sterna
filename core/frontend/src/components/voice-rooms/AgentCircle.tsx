/**
 * AgentCircle - Agents arranged in an arc facing the user
 *
 * The user is behind the screen - they don't appear in the room.
 * Agents sit in a semi-circle like a panel discussion.
 * Active speaker is highlighted with glow and scale.
 */

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Package } from 'lucide-react'
import type { VoiceAgent } from '@/types/voiceRoom'
import { getColoredIconComponent, getIconRenderComponent, getAdaptiveIconColor } from '@/lib/provider-icons'
import { useTheme } from '@/hooks/useTheme'
import useModelStore from '@/store/modelStore'

interface AgentCircleProps {
  agents: VoiceAgent[]
  currentSpeaker: string | null | undefined
  isSpeaking: boolean
  isProcessing: boolean
  className?: string
}

export function AgentCircle({
  agents,
  currentSpeaker,
  isSpeaking,
  isProcessing,
  className,
}: AgentCircleProps) {
  const { isDark } = useTheme()
  const { allModels } = useModelStore()

  const getModelInfo = (modelId: string) => {
    return allModels.find((m) => m.model_id === modelId)
  }

  const getModelIcon = (modelId: string, size: number = 28) => {
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

  const getAgentState = (agentId: string) => {
    if ((isSpeaking || isProcessing) && currentSpeaker === agentId) {
      return isSpeaking ? 'speaking' : 'processing'
    }
    return 'idle'
  }

  // Calculate arc positions - agents spread in a semi-circle facing the user
  const getArcPosition = (index: number, total: number) => {
    // Spread from -60° to +60° (120° arc) - like sitting across a table
    const startAngle = -60
    const endAngle = 60
    const angleRange = endAngle - startAngle

    // For single agent, center it
    const angle = total === 1
      ? 0
      : startAngle + (angleRange / (total - 1)) * index

    const radians = (angle * Math.PI) / 180
    const radius = total <= 2 ? 100 : total <= 4 ? 140 : 180

    return {
      x: Math.sin(radians) * radius,
      y: -Math.cos(radians) * radius * 0.4, // Flatten the arc slightly
    }
  }

  return (
    <div className={cn('relative flex items-center justify-center', className)}>
      {/* Container for the arc */}
      <div className="relative h-48 w-full max-w-lg flex items-end justify-center">
        {agents.map((agent, index) => {
          const state = getAgentState(agent.id)
          const isActive = state !== 'idle'
          const position = getArcPosition(index, agents.length)

          return (
            <div
              key={agent.id}
              className="absolute transition-all duration-500 ease-out"
              style={{
                transform: `translate(${position.x}px, ${position.y}px) scale(${isActive ? 1.15 : 1})`,
                zIndex: isActive ? 10 : 1,
              }}
            >
              <div className="flex flex-col items-center gap-3">
                {/* Glow effect for active */}
                {isActive && (
                  <div
                    className={cn(
                      'absolute inset-0 rounded-full blur-2xl scale-150 -z-10',
                      state === 'speaking' && 'bg-sky-500/30',
                      state === 'processing' && 'bg-violet-500/30',
                    )}
                  />
                )}

                {/* Agent avatar */}
                <div
                  className={cn(
                    'relative h-16 w-16 rounded-2xl flex items-center justify-center transition-all duration-300',
                    'border-2',
                    isActive
                      ? isDark
                        ? 'bg-white/15 border-white/30'
                        : 'bg-white border-black/10 shadow-xl'
                      : isDark
                        ? 'bg-white/5 border-white/10'
                        : 'bg-white/80 border-black/5 shadow-md',
                  )}
                >
                  {getModelIcon(agent.model_id, isActive ? 32 : 28)}

                  {/* Active indicator */}
                  {isActive && (
                    <div
                      className={cn(
                        'absolute -top-1 -right-1 h-4 w-4 rounded-full border-2',
                        isDark ? 'border-[#0c0c0c]' : 'border-white',
                        state === 'speaking' && 'bg-sky-400',
                        state === 'processing' && 'bg-violet-400',
                      )}
                    >
                      <div
                        className={cn(
                          'absolute inset-0 rounded-full animate-ping',
                          state === 'speaking' && 'bg-sky-400',
                          state === 'processing' && 'bg-violet-400',
                        )}
                        style={{ animationDuration: '1.5s' }}
                      />
                    </div>
                  )}
                </div>

                {/* Agent name */}
                <span
                  className={cn(
                    'text-sm font-medium transition-all duration-300 text-center max-w-24 truncate',
                    isActive
                      ? isDark ? 'text-white' : 'text-gray-900'
                      : isDark ? 'text-white/40' : 'text-gray-400',
                  )}
                >
                  {agent.display_name}
                </span>

                {/* Status for active */}
                {isActive && (
                  <span
                    className={cn(
                      'text-xs uppercase tracking-wider -mt-1',
                      state === 'speaking' && 'text-sky-500',
                      state === 'processing' && 'text-violet-500',
                    )}
                  >
                    {state === 'speaking' ? 'speaking' : 'thinking...'}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
