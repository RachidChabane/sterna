/**
 * SpatialPresence - Agents positioned around the screen perimeter
 *
 * Each agent has their place in the space. When they speak,
 * light emanates from their direction. Like sitting in a circle.
 * User's presence comes from the bottom.
 */

import { useEffect, useRef, useMemo, useState } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import useModelStore from '@/store/modelStore'
import { getColoredIconComponent, getIconRenderComponent, getAdaptiveIconColor } from '@/lib/provider-icons'
import { ThinkingDots } from './ThinkingIndicator'
import type { VoiceAgent } from '@/types/voiceRoom'

// Colors
const AGENT_COLORS = [
  { r: 56, g: 189, b: 248 },   // sky
  { r: 167, g: 139, b: 250 },  // violet
  { r: 251, g: 146, b: 60 },   // orange
  { r: 244, g: 114, b: 182 },  // pink
  { r: 45, g: 212, b: 191 },   // teal
  { r: 250, g: 204, b: 21 },   // yellow
]

interface SpatialPresenceProps {
  agents: VoiceAgent[]
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  audioLevel: number
  currentSpeaker: string | null | undefined
  className?: string
  paddingTop?: number
  paddingBottom?: number
}

// Calculate position on screen edge given an angle (0 = top, 90 = right, -90 = left)
function getEdgePosition(
  angle: number,
  width: number,
  height: number,
  margin: number = 60,
  paddingTop: number = 0,
  paddingBottom: number = 0
) {
  const radians = (angle - 90) * (Math.PI / 180) // Adjust so 0 = top

  // Adjust available height based on padding
  const effectiveHeight = height - paddingTop - paddingBottom
  const centerX = width / 2
  const centerY = paddingTop + effectiveHeight / 2

  // Use a large radius and clamp to screen bounds
  const dx = Math.cos(radians)
  const dy = Math.sin(radians)

  // Find intersection with screen rectangle
  let x, y

  // Check which edge we hit - use effective dimensions
  const halfW = width / 2 - margin
  const halfH = effectiveHeight / 2 - margin

  if (Math.abs(dx) * halfH > Math.abs(dy) * halfW) {
    // Hit left or right edge
    x = dx > 0 ? centerX + halfW : centerX - halfW
    y = centerY + dy * (halfW / Math.abs(dx))
  } else {
    // Hit top or bottom edge
    y = dy > 0 ? centerY + halfH : centerY - halfH
    x = centerX + dx * (halfH / Math.abs(dy))
  }

  return { x, y, angle }
}

// Distribute N agents around the perimeter, excluding bottom (where user is)
// Single agent gets centered position for focused conversation
function distributeAgents(
  count: number,
  width: number,
  height: number,
  paddingTop: number = 0,
  paddingBottom: number = 0
) {
  const positions: Array<{ x: number; y: number; angle: number; isCentered?: boolean }> = []

  // Single agent: position at true center of screen
  if (count === 1) {
    const effectiveHeight = height - paddingTop - paddingBottom
    const centerX = width / 2
    const centerY = paddingTop + effectiveHeight / 2
    positions.push({ x: centerX, y: centerY, angle: 0, isCentered: true })
    return positions
  }

  // Multi-agent: Arc from -135° to +135° (270° total, positions calculated within padded area)
  const startAngle = -135
  const endAngle = 135
  const arcSpan = endAngle - startAngle

  for (let i = 0; i < count; i++) {
    // Distribute evenly across the arc
    const angle = startAngle + (arcSpan / (count - 1)) * i
    positions.push(getEdgePosition(angle, width, height, 60, paddingTop, paddingBottom))
  }

  return positions
}

export function SpatialPresence({
  agents,
  isListening,
  isSpeaking,
  isProcessing,
  audioLevel,
  currentSpeaker,
  className,
  paddingTop = 0,
  paddingBottom = 0,
}: SpatialPresenceProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animationRef = useRef<number | undefined>(undefined)
  const { isDark } = useTheme()
  const { allModels } = useModelStore()

  // Smooth values
  const breathRef = useRef(0)
  const glowStatesRef = useRef<Map<string, number>>(new Map())
  const smoothedAudioRef = useRef(0)

  // Refs to avoid useEffect re-running on every audio change
  const audioLevelRef = useRef(audioLevel)
  const isListeningRef = useRef(isListening)
  const isSpeakingRef = useRef(isSpeaking)
  const isProcessingRef = useRef(isProcessing)
  const currentSpeakerRef = useRef(currentSpeaker)
  const paddingTopRef = useRef(paddingTop)
  const paddingBottomRef = useRef(paddingBottom)
  // Smoothed padding for animation
  const smoothPaddingTopRef = useRef(paddingTop)
  const smoothPaddingBottomRef = useRef(paddingBottom)

  // Update refs on each render
  audioLevelRef.current = audioLevel
  isListeningRef.current = isListening
  isSpeakingRef.current = isSpeaking
  isProcessingRef.current = isProcessing
  currentSpeakerRef.current = currentSpeaker
  paddingTopRef.current = paddingTop
  paddingBottomRef.current = paddingBottom

  // Agent colors
  const agentColorMap = useMemo(() => {
    const map = new Map<string, { r: number; g: number; b: number }>()
    agents.forEach((agent, index) => {
      if (agent.color) {
        const hex = agent.color.replace('#', '')
        const r = parseInt(hex.substring(0, 2), 16)
        const g = parseInt(hex.substring(2, 4), 16)
        const b = parseInt(hex.substring(4, 6), 16)
        map.set(agent.id, { r, g, b })
      } else {
        map.set(agent.id, AGENT_COLORS[index % AGENT_COLORS.length])
      }
    })
    return map
  }, [agents])

  const getModelIcon = (modelId: string, size: number = 20) => {
    const model = allModels.find((m) => m.model_id === modelId)
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

  // Agent positions
  const [positions, setPositions] = useState<Array<{ x: number; y: number; angle: number }>>([])

  // Reveal states - for showing agents on entry and when speaking
  const [initialReveal, setInitialReveal] = useState(true)
  const [revealedAgents, setRevealedAgents] = useState<Set<string>>(new Set())
  const revealTimeoutsRef = useRef<Map<string, NodeJS.Timeout>>(new Map())

  // Initial reveal on mount - show all agents for 3 seconds
  useEffect(() => {
    const timeout = setTimeout(() => {
      setInitialReveal(false)
    }, 3000)
    return () => clearTimeout(timeout)
  }, [])

  // Reveal agent when their audio actually starts playing (not when processing starts)
  const prevSpeakingRef = useRef(false)

  useEffect(() => {
    // Only reveal when isSpeaking becomes true (audio starts playing)
    if (isSpeaking && currentSpeaker && !prevSpeakingRef.current) {
      // Audio just started - reveal the speaker
      setRevealedAgents(prev => new Set(prev).add(currentSpeaker))

      // Clear any existing timeout for this agent
      const existingTimeout = revealTimeoutsRef.current.get(currentSpeaker)
      if (existingTimeout) {
        clearTimeout(existingTimeout)
      }

      // Set timeout to hide after 3 seconds
      const timeout = setTimeout(() => {
        setRevealedAgents(prev => {
          const next = new Set(prev)
          next.delete(currentSpeaker)
          return next
        })
        revealTimeoutsRef.current.delete(currentSpeaker)
      }, 3000)

      revealTimeoutsRef.current.set(currentSpeaker, timeout)
    }

    prevSpeakingRef.current = isSpeaking

    // Cleanup timeouts on unmount
    return () => {
      revealTimeoutsRef.current.forEach(timeout => clearTimeout(timeout))
    }
  }, [isSpeaking, currentSpeaker])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const updatePositions = () => {
      const rect = container.getBoundingClientRect()
      setPositions(distributeAgents(agents.length, rect.width, rect.height, paddingTop, paddingBottom))
    }

    updatePositions()
    window.addEventListener('resize', updatePositions)
    return () => window.removeEventListener('resize', updatePositions)
  }, [agents.length, paddingTop, paddingBottom])

  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const resize = () => {
      const rect = container.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      canvas.style.width = `${rect.width}px`
      canvas.style.height = `${rect.height}px`
      ctx.scale(dpr, dpr)
    }
    resize()
    window.addEventListener('resize', resize)

    const animate = () => {
      const width = container.clientWidth
      const height = container.clientHeight

      // Skip complex rendering if container is too small, but still fill background
      if (width < 50 || height < 50) {
        const bg = isDark ? '#0c0c0c' : '#f8fafc'
        ctx.fillStyle = bg
        ctx.fillRect(0, 0, canvas.width, canvas.height)
        animationRef.current = requestAnimationFrame(animate)
        return
      }

      const centerX = width / 2

      breathRef.current += 0.008
      const breath = Math.sin(breathRef.current) * 0.5 + 0.5

      // Read from refs (updated every render, but don't cause effect restart)
      const listening = isListeningRef.current
      const speaking = isSpeakingRef.current
      const processing = isProcessingRef.current
      const speaker = currentSpeakerRef.current
      const audio = audioLevelRef.current

      // Smooth padding for animated transitions
      const targetPaddingTop = paddingTopRef.current
      const targetPaddingBottom = paddingBottomRef.current
      smoothPaddingTopRef.current += (targetPaddingTop - smoothPaddingTopRef.current) * 0.08
      smoothPaddingBottomRef.current += (targetPaddingBottom - smoothPaddingBottomRef.current) * 0.08
      const smoothPaddingTop = smoothPaddingTopRef.current
      const smoothPaddingBottom = smoothPaddingBottomRef.current

      // Calculate effective center with padding (ensure minimum positive value)
      const effectiveHeight = Math.max(100, height - smoothPaddingTop - smoothPaddingBottom)
      const centerY = smoothPaddingTop + effectiveHeight / 2

      const isActive = listening || speaking || processing

      // Smooth the raw audio level to prevent glitchy visuals
      const rawAudio = (listening || speaking) ? audio : 0
      smoothedAudioRef.current += (rawAudio - smoothedAudioRef.current) * 0.12
      const currentAudio = smoothedAudioRef.current

      // Clear
      const bg = isDark ? '#0c0c0c' : '#f8fafc'
      ctx.fillStyle = bg
      ctx.fillRect(0, 0, width, height)

      // Calculate agent positions for glow (using smoothed padding)
      const agentPositions = distributeAgents(agents.length, width, height, smoothPaddingTop, smoothPaddingBottom)

      // Update glow states for all agents
      const isSingleAgent = agents.length === 1
      const modeBoost = isDark ? 1.0 : 1.3

      agents.forEach((agent, index) => {
        const isActiveSpeaker = (speaking || processing) && speaker === agent.id
        const currentGlow = glowStatesRef.current.get(agent.id) || 0

        // Heartbeat pulse for idle state (staggered per agent)
        const agentPhase = index * 0.7
        const heartbeatTime = breathRef.current * 2 + agentPhase
        const heartbeat = Math.pow(Math.sin(heartbeatTime) * 0.5 + 0.5, 2)

        const idlePulse = (isSingleAgent ? 0.25 + heartbeat * 0.15 : 0.2 + heartbeat * 0.12) * modeBoost
        const activeGlow = (isSingleAgent ? 0.6 + currentAudio * 0.4 : 0.5 + currentAudio * 0.35) * modeBoost
        const targetGlow = isActiveSpeaker ? activeGlow : idlePulse
        const easeSpeed = isActiveSpeaker ? (targetGlow > currentGlow ? 0.03 : 0.02) : 0.06
        const newGlow = currentGlow + (targetGlow - currentGlow) * easeSpeed
        glowStatesRef.current.set(agent.id, newGlow)
      })

      const baseSize = Math.min(width, effectiveHeight)

      if (isSingleAgent) {
        // Single agent: elegant centered glow
        const agent = agents[0]
        const pos = agentPositions[0]
        if (agent && pos) {
          const color = agentColorMap.get(agent.id) || AGENT_COLORS[0]
          const newGlow = glowStatesRef.current.get(agent.id) || 0.2
          const isActiveSpeaker = (speaking || processing) && speaker === agent.id
          const glowRadius = isActiveSpeaker ? baseSize * 0.8 : baseSize * 0.6

          // Soft, diffused glow with natural falloff
          const gradient = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, glowRadius)
          gradient.addColorStop(0, `rgba(${color.r}, ${color.g}, ${color.b}, ${newGlow * 0.5})`)
          gradient.addColorStop(0.3, `rgba(${color.r}, ${color.g}, ${color.b}, ${newGlow * 0.25})`)
          gradient.addColorStop(0.6, `rgba(${color.r}, ${color.g}, ${color.b}, ${newGlow * 0.08})`)
          gradient.addColorStop(1, 'transparent')
          ctx.fillStyle = gradient
          ctx.fillRect(0, 0, width, height)
        }
      } else {
        // Multi-agent: soft ambient corner/edge glows
        // Each agent creates a large, soft glow from their corner - overlapping naturally

        agents.forEach((agent, index) => {
          const pos = agentPositions[index]
          if (!pos) return

          const color = agentColorMap.get(agent.id) || AGENT_COLORS[index % AGENT_COLORS.length]
          const glowIntensity = glowStatesRef.current.get(agent.id) || 0.15

          // Position glow origin at the screen edge/corner
          const angleRad = (pos.angle - 90) * (Math.PI / 180)
          const edgeX = pos.x + Math.cos(angleRad) * 100
          const edgeY = pos.y + Math.sin(angleRad) * 100

          // Large, soft radius for natural blending
          const glowRadius = baseSize * 0.8

          // Very soft gradient with gentle falloff
          const gradient = ctx.createRadialGradient(edgeX, edgeY, 0, edgeX, edgeY, glowRadius)
          gradient.addColorStop(0, `rgba(${color.r}, ${color.g}, ${color.b}, ${glowIntensity * 0.4})`)
          gradient.addColorStop(0.2, `rgba(${color.r}, ${color.g}, ${color.b}, ${glowIntensity * 0.25})`)
          gradient.addColorStop(0.4, `rgba(${color.r}, ${color.g}, ${color.b}, ${glowIntensity * 0.12})`)
          gradient.addColorStop(0.7, `rgba(${color.r}, ${color.g}, ${color.b}, ${glowIntensity * 0.04})`)
          gradient.addColorStop(1, 'transparent')

          ctx.fillStyle = gradient
          ctx.fillRect(0, 0, width, height)
        })
      }

      // Subtle vignette (centered in effective area)
      const vignetteGradient = ctx.createRadialGradient(
        centerX, centerY, effectiveHeight * 0.2,
        centerX, centerY, effectiveHeight * 0.9
      )
      vignetteGradient.addColorStop(0, 'transparent')
      vignetteGradient.addColorStop(1, `rgba(0, 0, 0, ${isDark ? 0.4 : 0.15})`)
      ctx.fillStyle = vignetteGradient
      ctx.fillRect(0, 0, width, height)

      animationRef.current = requestAnimationFrame(animate)
    }

    animationRef.current = requestAnimationFrame(animate)

    return () => {
      window.removeEventListener('resize', resize)
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [agents, isDark, agentColorMap])  // Removed frequently changing deps - using refs instead

  return (
    <div ref={containerRef} className={cn('relative w-full h-full', className)}>
      <canvas ref={canvasRef} className="absolute inset-0" />

      {/* Agent icons/names - no orbs, just positioned at edges/center */}
      {positions.map((pos, index) => {
        const agent = agents[index]
        if (!agent) return null

        const color = agentColorMap.get(agent.id) || AGENT_COLORS[index % AGENT_COLORS.length]
        const isThinking = isProcessing && currentSpeaker === agent.id
        const isSingleAgent = agents.length === 1

        // Show if: initial reveal, agent was recently revealed (started speaking), or hover
        const isRevealed = initialReveal || revealedAgents.has(agent.id)

        // For multi-agent, push the icon position toward the edge to be centered in the light
        const isCentered = 'isCentered' in pos && pos.isCentered
        let displayX = pos.x
        let displayY = pos.y
        if (!isCentered) {
          const angleRad = (pos.angle - 90) * (Math.PI / 180)
          // Push 40px toward edge to center in the light glow
          displayX = pos.x + Math.cos(angleRad) * 40
          displayY = pos.y + Math.sin(angleRad) * 40
        }

        return (
          <div
            key={agent.id}
            className="absolute group flex items-center justify-center cursor-default"
            style={{
              left: displayX,
              top: displayY,
              transform: 'translate(-50%, -50%)',
              // Large hover zone matching the glow area
              width: isSingleAgent ? '280px' : '200px',
              height: isSingleAgent ? '280px' : '200px',
            }}
          >
            {/* Centered content */}
            <div className="flex flex-col items-center">
              {/* Icon - visible on reveal or hover */}
              <div
                className={cn(
                  'flex items-center justify-center transition-opacity duration-500',
                  isRevealed ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                )}
              >
                {getModelIcon(agent.model_id, isSingleAgent ? 32 : 24)}
              </div>

              {/* Agent name - visible on reveal or hover, using contrasting color */}
              <span
                className={cn(
                  'mt-2 font-light tracking-widest uppercase transition-opacity duration-500',
                  isSingleAgent ? 'text-xs' : 'text-[10px]',
                  isRevealed ? 'opacity-90' : 'opacity-0 group-hover:opacity-90',
                  isDark ? 'text-white/80' : 'text-gray-800'
                )}
              >
                {agent.display_name}
              </span>

              {/* Thinking dots - using contrasting color */}
              {isThinking && (
                <div className="mt-2">
                  <ThinkingDots isVisible={true} color={isDark ? { r: 255, g: 255, b: 255 } : { r: 60, g: 60, b: 60 }} />
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
