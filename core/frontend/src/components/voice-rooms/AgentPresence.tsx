/**
 * AgentPresence - Minimal floating agent indicators
 *
 * Agents exist as subtle presences in the space - not avatars.
 * When active, they're just a soft glow with identity.
 * When idle, they're barely-there hints of existence.
 * Each agent has a unique color signature.
 */

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import useModelStore from '@/store/modelStore'
import { getColoredIconComponent, getIconRenderComponent, getAdaptiveIconColor } from '@/lib/provider-icons'
import type { VoiceAgent } from '@/types/voiceRoom'

// Premium color palette for agents
const AGENT_COLORS = [
  { r: 56, g: 189, b: 248 },   // sky-400
  { r: 167, g: 139, b: 250 },  // violet-400
  { r: 251, g: 146, b: 60 },   // orange-400
  { r: 244, g: 114, b: 182 },  // pink-400
  { r: 45, g: 212, b: 191 },   // teal-400
  { r: 250, g: 204, b: 21 },   // yellow-400
  { r: 129, g: 140, b: 248 },  // indigo-400
  { r: 74, g: 222, b: 128 },   // green-400
]

// Convert RGB to CSS color string
export const rgbToString = (color: { r: number; g: number; b: number }, alpha = 1) =>
  alpha === 1
    ? `rgb(${color.r}, ${color.g}, ${color.b})`
    : `rgba(${color.r}, ${color.g}, ${color.b}, ${alpha})`

// Get a consistent color for an agent based on their ID
export const getAgentColor = (agentId: string, index: number) => {
  // Use index for consistent ordering within a session
  return AGENT_COLORS[index % AGENT_COLORS.length]
}

interface AgentPresenceProps {
  agents: VoiceAgent[]
  currentSpeaker: string | null | undefined
  isSpeaking: boolean
  isProcessing: boolean
  className?: string
  onActiveColorChange?: (color: { r: number; g: number; b: number } | null) => void
}

export function AgentPresence({
  agents,
  currentSpeaker,
  isSpeaking,
  isProcessing,
  className,
  onActiveColorChange,
}: AgentPresenceProps) {
  const { isDark } = useTheme()
  const { allModels } = useModelStore()

  // Create a map of agent ID to color (use custom color if set, otherwise auto-assign)
  const agentColorMap = useMemo(() => {
    const map = new Map<string, { r: number; g: number; b: number }>()
    agents.forEach((agent, index) => {
      if (agent.color) {
        // Parse hex color to RGB
        const hex = agent.color.replace('#', '')
        const r = parseInt(hex.substring(0, 2), 16)
        const g = parseInt(hex.substring(2, 4), 16)
        const b = parseInt(hex.substring(4, 6), 16)
        map.set(agent.id, { r, g, b })
      } else {
        map.set(agent.id, getAgentColor(agent.id, index))
      }
    })
    return map
  }, [agents])

  const getModelInfo = (modelId: string) => {
    return allModels.find((m) => m.model_id === modelId)
  }

  const getModelIcon = (modelId: string, size: number = 16) => {
    const model = getModelInfo(modelId)
    const iconSlug = model?.model_icon_slug || model?.provider_icon_slug
    const iconComponent = getColoredIconComponent(iconSlug)

    if (!iconComponent) return null

    const RenderIcon = getIconRenderComponent(iconComponent)
    const isMonochrome = !iconComponent.Color
    const adaptiveColor = isMonochrome ? getAdaptiveIconColor(iconSlug, isDark, iconComponent) : undefined

    return RenderIcon ? (
      <RenderIcon size={size} {...(adaptiveColor && { style: { color: adaptiveColor } })} />
    ) : null
  }

  const getAgentState = (agentId: string) => {
    if ((isSpeaking || isProcessing) && currentSpeaker === agentId) {
      return isSpeaking ? 'speaking' : 'processing'
    }
    return 'idle'
  }

  // Position agents in a gentle arc at the bottom
  const getPosition = (index: number, total: number) => {
    const spread = Math.min(total * 80, 400) // Max spread of 400px
    const startX = -spread / 2
    const spacing = total > 1 ? spread / (total - 1) : 0
    return {
      x: total === 1 ? 0 : startX + spacing * index,
    }
  }

  const activeAgent = agents.find(a => getAgentState(a.id) !== 'idle')
  const idleAgents = agents.filter(a => getAgentState(a.id) === 'idle')

  // Get color for active agent
  const activeAgentColor = activeAgent ? agentColorMap.get(activeAgent.id) : null

  return (
    <div className={cn('flex flex-col items-center gap-6', className)}>
      {/* Active agent - just icon, name, status. No containers. */}
      {activeAgent && activeAgentColor && (
        <div className="flex flex-col items-center gap-3 animate-in fade-in duration-500">
          {/* Icon - naked, just the icon */}
          <div className="relative">
            {getModelIcon(activeAgent.model_id, 36)}
          </div>

          {/* Name + status */}
          <div className="text-center">
            <div
              className="text-base font-medium transition-colors duration-500"
              style={{ color: rgbToString(activeAgentColor) }}
            >
              {activeAgent.display_name}
            </div>
            <div
              className="text-[10px] uppercase tracking-[0.25em] mt-0.5"
              style={{ color: rgbToString(activeAgentColor, 0.5) }}
            >
              {getAgentState(activeAgent.id) === 'speaking' ? 'Speaking' : 'Thinking'}
            </div>
          </div>
        </div>
      )}

      {/* Idle agents - just icons and names, no containers, no dots */}
      {idleAgents.length > 0 && (
        <div className="relative flex items-center justify-center h-12">
          {idleAgents.map((agent, index) => {
            const position = getPosition(index, idleAgents.length)
            return (
              <div
                key={agent.id}
                className={cn(
                  'absolute flex flex-col items-center gap-1.5 transition-all duration-700',
                  activeAgent ? 'opacity-30' : 'opacity-50 hover:opacity-80',
                )}
                style={{
                  transform: `translateX(${position.x}px)`,
                }}
              >
                {/* Icon - naked */}
                <div className="opacity-70">
                  {getModelIcon(agent.model_id, 20)}
                </div>

                {/* Name */}
                <span
                  className={cn(
                    'text-[10px] tracking-wide',
                    isDark ? 'text-white/25' : 'text-gray-400',
                  )}
                >
                  {agent.display_name}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
