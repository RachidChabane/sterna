/**
 * Agent Carousel component for Voice Rooms
 *
 * Displays all participants (user + agents) in a circular room layout:
 * - User and agents arranged in a circle
 * - Active speaker moves to the center
 * - Smooth animations when speaker changes
 * - User orb has distinct green color when listening
 */

import { useEffect, useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import type { VoiceAgent } from '@/types/voiceRoom'
import { AnimatedOrb } from './AnimatedOrb'
import { getColoredIconComponent, getIconRenderComponent, getAdaptiveIconColor } from '@/lib/provider-icons'
import { useTheme } from '@/hooks/useTheme'
import { Package } from 'lucide-react'
import useModelStore from '@/store/modelStore'
import { useAuthStore } from '@/store/authStore'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

interface AgentCarouselProps {
  agents: VoiceAgent[]
  currentSpeaker: string | null | undefined // 'user' or agent_id
  isConnected: boolean
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  audioLevel: number
  className?: string
}

// Participant type (user or agent)
interface Participant {
  id: string
  type: 'user' | 'agent'
  displayName: string
  modelId?: string
  agent?: VoiceAgent
}

export function AgentCarousel({
  agents,
  currentSpeaker,
  isConnected,
  isListening,
  isSpeaking,
  isProcessing,
  audioLevel,
  className,
}: AgentCarouselProps) {
  const { isDark } = useTheme()
  const { allModels } = useModelStore()
  const { user } = useAuthStore()
  const [activeSpeakerId, setActiveSpeakerId] = useState<string | null>(null)

  // Build participants list: user + agents
  const participants = useMemo<Participant[]>(() => {
    const userName = user?.first_name || user?.email?.split('@')[0] || 'You'
    const userParticipant: Participant = {
      id: 'user',
      type: 'user',
      displayName: userName,
    }
    const agentParticipants: Participant[] = agents.map((agent) => ({
      id: agent.id,
      type: 'agent',
      displayName: agent.display_name,
      modelId: agent.model_id,
      agent,
    }))
    return [userParticipant, ...agentParticipants]
  }, [agents, user])

  // Track active speaker
  useEffect(() => {
    if (!currentSpeaker) {
      // No one speaking, but if listening, user is active
      setActiveSpeakerId(isListening ? 'user' : null)
    } else if (currentSpeaker === 'user') {
      setActiveSpeakerId('user')
    } else {
      setActiveSpeakerId(currentSpeaker)
    }
  }, [currentSpeaker, isListening])

  // Helper to find model info by model_id
  const getModelInfo = (modelId: string) => {
    return allModels.find((m) => m.model_id === modelId)
  }

  // Get the icon component for a model
  const getModelIcon = (modelId: string, size: number = 16) => {
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

  // Calculate circle positions for participants
  // Returns positions for each participant when they're NOT the active speaker
  const getCirclePositions = (count: number, radius: number) => {
    const positions: { x: number; y: number; angle: number }[] = []
    // Start from top (-90 degrees) and go clockwise
    const startAngle = -90
    const angleStep = 360 / count

    for (let i = 0; i < count; i++) {
      const angle = startAngle + i * angleStep
      const radians = (angle * Math.PI) / 180
      positions.push({
        x: Math.cos(radians) * radius,
        y: Math.sin(radians) * radius,
        angle,
      })
    }
    return positions
  }

  // Get position for a participant
  const getParticipantPosition = (
    participantId: string,
    index: number,
    positions: { x: number; y: number }[]
  ) => {
    const isActive = participantId === activeSpeakerId

    if (isActive) {
      // Active speaker goes to center
      return { x: 0, y: 0, scale: 1, opacity: 1 }
    }

    // Find the active speaker's original index to redistribute other participants
    const activeIndex = participants.findIndex((p) => p.id === activeSpeakerId)

    if (activeIndex === -1 || activeSpeakerId === null) {
      // No active speaker, use normal position
      return { ...positions[index], scale: 0.7, opacity: 0.6 }
    }

    // Redistribute: skip the active speaker's position
    // Calculate new positions around the circle excluding center
    const remainingCount = participants.length - 1
    // Use same radius calculation as main circle
    const dynamicRadius = participants.length <= 3 ? 220 : participants.length <= 5 ? 260 : 300
    const remainingPositions = getCirclePositions(remainingCount, dynamicRadius)

    // Find this participant's index among non-active participants
    let nonActiveIndex = 0
    for (let i = 0; i < participants.length; i++) {
      if (participants[i].id === activeSpeakerId) continue
      if (participants[i].id === participantId) break
      nonActiveIndex++
    }

    return {
      ...remainingPositions[nonActiveIndex],
      scale: 0.65,
      opacity: 0.5,
    }
  }

  // Circle radius based on participant count - increased for better spacing
  const circleRadius = participants.length <= 3 ? 220 : participants.length <= 5 ? 260 : 300
  const basePositions = getCirclePositions(participants.length, circleRadius)

  return (
    <div className={cn('relative w-full h-[500px] flex items-center justify-center', className)}>
      {/* Circle container */}
      <div className="relative" style={{ width: circleRadius * 2 + 200, height: circleRadius * 2 + 200 }}>
        {/* Center point reference */}
        <div
          className="absolute"
          style={{
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
          }}
        >
          {participants.map((participant, index) => {
            const position = getParticipantPosition(participant.id, index, basePositions)
            const isActive = participant.id === activeSpeakerId
            const isUser = participant.type === 'user'

            // Determine orb states
            const isThisSpeaking = isActive && isSpeaking && !isUser
            const isThisProcessing = isActive && isProcessing && !isUser
            const isThisListening = isUser && isListening
            const effectiveAudioLevel = isActive ? audioLevel : 0

            return (
              <div
                key={participant.id}
                className="absolute transition-all duration-700 ease-out"
                style={{
                  transform: `translate(calc(-50% + ${position.x}px), calc(-50% + ${position.y}px)) scale(${position.scale})`,
                  opacity: position.opacity,
                  zIndex: isActive ? 10 : 1,
                }}
              >
                <div className="flex flex-col items-center">
                  {/* The animated orb */}
                  <div className="relative">
                    <AnimatedOrb
                      isActive={isConnected && (isActive || (isUser && isThisListening))}
                      isSpeaking={isThisSpeaking}
                      isListening={isUser && isThisListening}
                      audioLevel={effectiveAudioLevel}
                      isProcessing={isThisProcessing}
                    />
                  </div>

                  {/* Participant info below orb */}
                  <div className="mt-4 text-center">
                    <h3
                      className={cn(
                        'text-lg font-medium transition-colors whitespace-nowrap',
                        isActive ? 'text-white' : 'text-white/50'
                      )}
                    >
                      {participant.displayName}
                    </h3>
                    {/* User: show profile pic. Agent: show model icon */}
                    {isUser ? (
                      <div className="flex items-center justify-center gap-1.5 mt-1">
                        <Avatar className="h-5 w-5">
                          <AvatarImage src={user?.avatar_url ?? undefined} alt={participant.displayName} />
                          <AvatarFallback className="text-[10px] bg-white/10 text-white/60">
                            {participant.displayName.charAt(0).toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        <span
                          className={cn(
                            'text-xs transition-colors',
                            isActive ? 'text-white/60' : 'text-white/30'
                          )}
                        >
                          You
                        </span>
                      </div>
                    ) : participant.modelId ? (
                      <div className="flex items-center justify-center gap-1.5 mt-1">
                        {getModelIcon(participant.modelId, 14)}
                        <span
                          className={cn(
                            'text-xs transition-colors',
                            isActive ? 'text-white/60' : 'text-white/30'
                          )}
                        >
                          {getModelInfo(participant.modelId)?.name || participant.modelId}
                        </span>
                      </div>
                    ) : null}
                    {/* Status text */}
                    {isThisProcessing && (
                      <p className="text-purple-400/80 text-xs mt-1.5 animate-pulse">Thinking...</p>
                    )}
                    {isThisSpeaking && (
                      <p className="text-blue-400/80 text-xs mt-1.5">Speaking...</p>
                    )}
                    {isThisListening && isActive && (
                      <p className="text-green-400/80 text-xs mt-1.5">Listening...</p>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
