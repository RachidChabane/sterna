/**
 * VoiceOrb - Organic, living orb visualization for voice rooms
 *
 * Inspired by GPT/Gemini voice interfaces - a single focal point
 * that embodies the conversation's presence.
 *
 * The orb breathes, morphs, and shifts color based on state,
 * creating an immersive, almost intimate experience.
 */

import { useEffect, useRef, useCallback } from 'react'
import { cn } from '@/lib/utils'

interface VoiceOrbProps {
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  audioLevel: number
  className?: string
}

// Color palettes for different states
const COLORS = {
  idle: {
    primary: [100, 116, 139],    // Slate
    secondary: [71, 85, 105],
    glow: [100, 116, 139, 0.1],
  },
  listening: {
    primary: [34, 197, 94],      // Green
    secondary: [22, 163, 74],
    glow: [34, 197, 94, 0.3],
  },
  speaking: {
    primary: [59, 130, 246],     // Blue
    secondary: [37, 99, 235],
    glow: [59, 130, 246, 0.3],
  },
  processing: {
    primary: [168, 85, 247],     // Purple
    secondary: [147, 51, 234],
    glow: [168, 85, 247, 0.25],
  },
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

function lerpColor(a: number[], b: number[], t: number): number[] {
  return a.map((v, i) => lerp(v, b[i], t))
}

export function VoiceOrb({
  isListening,
  isSpeaking,
  isProcessing,
  audioLevel,
  className,
}: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | undefined>(undefined)
  const timeRef = useRef(0)

  // Smoothed values for fluid animation
  const smoothedRef = useRef({
    audioLevel: 0,
    primary: [...COLORS.idle.primary],
    secondary: [...COLORS.idle.secondary],
    glow: [...COLORS.idle.glow],
  })

  const getTargetColors = useCallback(() => {
    if (isSpeaking) return COLORS.speaking
    if (isListening) return COLORS.listening
    if (isProcessing) return COLORS.processing
    return COLORS.idle
  }, [isSpeaking, isListening, isProcessing])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // High DPI support
    const dpr = window.devicePixelRatio || 1
    const size = 280
    canvas.width = size * dpr
    canvas.height = size * dpr
    canvas.style.width = `${size}px`
    canvas.style.height = `${size}px`
    ctx.scale(dpr, dpr)

    const centerX = size / 2
    const centerY = size / 2
    const baseRadius = 90

    const animate = () => {
      timeRef.current += 0.016 // ~60fps
      const time = timeRef.current

      // Smooth color transitions
      const targetColors = getTargetColors()
      const smoothing = 0.04
      smoothedRef.current.primary = lerpColor(
        smoothedRef.current.primary,
        targetColors.primary,
        smoothing
      )
      smoothedRef.current.secondary = lerpColor(
        smoothedRef.current.secondary,
        targetColors.secondary,
        smoothing
      )
      smoothedRef.current.glow = lerpColor(
        smoothedRef.current.glow,
        targetColors.glow,
        smoothing
      )

      // Smooth audio level
      const targetAudio = isSpeaking || isListening ? audioLevel : 0
      smoothedRef.current.audioLevel = lerp(
        smoothedRef.current.audioLevel,
        targetAudio,
        0.1
      )

      const smoothedAudio = smoothedRef.current.audioLevel
      const [r, g, b] = smoothedRef.current.primary
      const [r2, g2, b2] = smoothedRef.current.secondary
      const [gr, gg, gb, ga] = smoothedRef.current.glow

      // Clear canvas
      ctx.clearRect(0, 0, size, size)

      // Calculate organic distortion
      const breathe = Math.sin(time * 0.8) * 0.03 + 1
      const audioInfluence = 1 + smoothedAudio * 0.15

      // Processing has a subtle rotation feel
      const rotationOffset = isProcessing ? time * 0.5 : 0

      // Draw outer glow layers (multiple for depth)
      for (let i = 3; i >= 0; i--) {
        const glowRadius = baseRadius * (1.5 + i * 0.3) * breathe
        const glowAlpha = (ga || 0.2) * (0.3 - i * 0.07)

        const gradient = ctx.createRadialGradient(
          centerX, centerY, 0,
          centerX, centerY, glowRadius
        )
        gradient.addColorStop(0, `rgba(${gr}, ${gg}, ${gb}, ${glowAlpha})`)
        gradient.addColorStop(0.5, `rgba(${gr}, ${gg}, ${gb}, ${glowAlpha * 0.5})`)
        gradient.addColorStop(1, 'rgba(0, 0, 0, 0)')

        ctx.fillStyle = gradient
        ctx.beginPath()
        ctx.arc(centerX, centerY, glowRadius, 0, Math.PI * 2)
        ctx.fill()
      }

      // Draw the main orb with organic distortion
      ctx.save()
      ctx.translate(centerX, centerY)

      // Create organic shape using bezier curves
      const points = 64
      const radius = baseRadius * breathe * audioInfluence

      ctx.beginPath()
      for (let i = 0; i <= points; i++) {
        const angle = (i / points) * Math.PI * 2 + rotationOffset

        // Multiple wave frequencies for organic feel
        const wave1 = Math.sin(angle * 3 + time * 2) * 4 * (0.3 + smoothedAudio * 0.7)
        const wave2 = Math.sin(angle * 5 + time * 1.5) * 2 * (0.2 + smoothedAudio * 0.5)
        const wave3 = Math.sin(angle * 7 + time * 3) * 1.5 * smoothedAudio

        const distortion = wave1 + wave2 + wave3
        const r = radius + distortion

        const x = Math.cos(angle) * r
        const y = Math.sin(angle) * r

        if (i === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      }
      ctx.closePath()

      // Gradient fill
      const gradient = ctx.createRadialGradient(0, -radius * 0.3, 0, 0, 0, radius * 1.2)
      gradient.addColorStop(0, `rgba(${r + 40}, ${g + 40}, ${b + 40}, 0.95)`)
      gradient.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, 0.9)`)
      gradient.addColorStop(1, `rgba(${r2}, ${g2}, ${b2}, 0.85)`)

      ctx.fillStyle = gradient
      ctx.fill()

      // Inner highlight for depth
      const innerRadius = radius * 0.6
      const highlightGradient = ctx.createRadialGradient(
        -radius * 0.2, -radius * 0.2, 0,
        0, 0, innerRadius
      )
      highlightGradient.addColorStop(0, `rgba(255, 255, 255, 0.15)`)
      highlightGradient.addColorStop(0.5, `rgba(255, 255, 255, 0.05)`)
      highlightGradient.addColorStop(1, 'rgba(255, 255, 255, 0)')

      ctx.fillStyle = highlightGradient
      ctx.beginPath()
      ctx.arc(0, 0, innerRadius, 0, Math.PI * 2)
      ctx.fill()

      // Subtle edge glow
      ctx.strokeStyle = `rgba(${r + 60}, ${g + 60}, ${b + 60}, 0.3)`
      ctx.lineWidth = 2
      ctx.beginPath()
      for (let i = 0; i <= points; i++) {
        const angle = (i / points) * Math.PI * 2 + rotationOffset
        const wave1 = Math.sin(angle * 3 + time * 2) * 4 * (0.3 + smoothedAudio * 0.7)
        const wave2 = Math.sin(angle * 5 + time * 1.5) * 2 * (0.2 + smoothedAudio * 0.5)
        const wave3 = Math.sin(angle * 7 + time * 3) * 1.5 * smoothedAudio
        const distortion = wave1 + wave2 + wave3
        const r = radius + distortion
        const x = Math.cos(angle) * r
        const y = Math.sin(angle) * r
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.closePath()
      ctx.stroke()

      ctx.restore()

      animationRef.current = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [isListening, isSpeaking, isProcessing, audioLevel, getTargetColors])

  return (
    <div className={cn('relative flex items-center justify-center', className)}>
      <canvas
        ref={canvasRef}
        className="relative z-10"
      />
    </div>
  )
}
