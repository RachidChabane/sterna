/**
 * PresenceVisualizerV2 - Impulse-based visualization
 *
 * Sound creates impulses. Impulses ripple through the lines.
 * Silence is stillness. Sound is felt, not just seen.
 */

import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'

interface PresenceVisualizerProps {
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  audioLevel: number
  speakerColor?: { r: number; g: number; b: number }
  className?: string
}

interface Impulse {
  birth: number      // When it was created (time units)
  intensity: number  // How strong (0-1)
  x: number         // Where it started (0-1 normalized)
}

// Colors
const LISTENING_COLOR = { r: 52, g: 211, b: 153 }
const IDLE_COLOR_DARK = { r: 100, g: 116, b: 139 }
const IDLE_COLOR_LIGHT = { r: 148, g: 163, b: 184 }

export function PresenceVisualizerV2({
  isListening,
  isSpeaking,
  isProcessing,
  audioLevel,
  speakerColor,
  className,
}: PresenceVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animationRef = useRef<number | undefined>(undefined)
  const timeRef = useRef(0)
  const colorRef = useRef({ r: 100, g: 116, b: 139 })
  const { isDark } = useTheme()

  // Impulse tracking
  const impulsesRef = useRef<Impulse[]>([])
  const prevAudioRef = useRef(0)
  const smoothedAudioRef = useRef(0)

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

    const getTargetColor = () => {
      if (isListening) return LISTENING_COLOR
      if ((isSpeaking || isProcessing) && speakerColor) return speakerColor
      return isDark ? IDLE_COLOR_DARK : IDLE_COLOR_LIGHT
    }

    // Track for impulse cooldown
    let lastImpulseTime = 0

    const animate = () => {
      const width = container.clientWidth
      const height = container.clientHeight
      const centerY = height / 2

      timeRef.current += 1

      const currentAudio = (isListening || isSpeaking) ? audioLevel : 0

      // Smooth audio for sustained response
      smoothedAudioRef.current += (currentAudio - smoothedAudioRef.current) * 0.15

      // IMPULSE DETECTION: Only on significant rises, with cooldown
      const audioRise = currentAudio - prevAudioRef.current
      const timeSinceLastImpulse = timeRef.current - lastImpulseTime
      const cooldown = 15 // Minimum frames between impulses

      if (audioRise > 0.15 && currentAudio > 0.2 && timeSinceLastImpulse > cooldown) {
        impulsesRef.current.push({
          birth: timeRef.current,
          intensity: Math.min(1, currentAudio),
          x: 0.5,
        })
        lastImpulseTime = timeRef.current
      }

      prevAudioRef.current = currentAudio

      // Clean old impulses
      impulsesRef.current = impulsesRef.current.filter(
        imp => timeRef.current - imp.birth < 180
      )

      // Color transition
      const targetColor = getTargetColor()
      colorRef.current.r += (targetColor.r - colorRef.current.r) * 0.05
      colorRef.current.g += (targetColor.g - colorRef.current.g) * 0.05
      colorRef.current.b += (targetColor.b - colorRef.current.b) * 0.05
      const color = colorRef.current

      const isActive = isListening || isSpeaking || isProcessing

      // Clear
      ctx.fillStyle = isDark ? '#0c0c0c' : '#f8fafc'
      ctx.fillRect(0, 0, width, height)

      // Calculate displacement at each point
      const getDisplacement = (xNorm: number): number => {
        let total = 0

        for (const impulse of impulsesRef.current) {
          const age = timeRef.current - impulse.birth

          // Slow expansion from center
          const speed = 0.008
          const radius = age * speed

          // Distance from center
          const dist = Math.abs(xNorm - impulse.x)

          // Smooth wave bump (no oscillation, just a traveling bump)
          const waveFrontDist = Math.abs(dist - radius)
          const waveWidth = 0.25

          if (waveFrontDist < waveWidth) {
            // Smooth bell curve shape
            const t = waveFrontDist / waveWidth
            const waveShape = Math.exp(-t * t * 3)

            // Gradual decay
            const decay = Math.exp(-age * 0.015)

            total += waveShape * decay * impulse.intensity
          }
        }

        // Gentle sustained movement when speaking
        if (smoothedAudioRef.current > 0.05) {
          const gentle = Math.sin(xNorm * Math.PI * 2 - timeRef.current * 0.02)
          total += gentle * smoothedAudioRef.current * 0.3
        }

        return total
      }

      // Draw layers
      const layers = 3
      for (let layer = 0; layer < layers; layer++) {
        const layerOffset = layer * 0.015
        const layerAlpha = isActive
          ? 0.4 - layer * 0.1 + smoothedAudioRef.current * 0.25
          : 0.07 - layer * 0.018
        const layerY = centerY + layer * 6

        ctx.beginPath()

        const segments = 120
        for (let i = 0; i <= segments; i++) {
          const xNorm = i / segments
          const x = xNorm * width

          const displacement = getDisplacement(xNorm + layerOffset)
          const maxAmplitude = 50 + smoothedAudioRef.current * 50
          const y = layerY + displacement * maxAmplitude

          if (i === 0) {
            ctx.moveTo(x, y)
          } else {
            ctx.lineTo(x, y)
          }
        }

        ctx.strokeStyle = `rgba(${color.r}, ${color.g}, ${color.b}, ${layerAlpha})`
        ctx.lineWidth = isActive ? 1.2 + smoothedAudioRef.current * 1.2 - layer * 0.15 : 0.5
        ctx.lineCap = 'round'
        ctx.lineJoin = 'round'
        ctx.stroke()
      }

      animationRef.current = requestAnimationFrame(animate)
    }

    animationRef.current = requestAnimationFrame(animate)

    return () => {
      window.removeEventListener('resize', resize)
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [isListening, isSpeaking, isProcessing, audioLevel, isDark, speakerColor])

  return (
    <div ref={containerRef} className={cn('relative w-full h-full', className)}>
      <canvas ref={canvasRef} className="absolute inset-0" />
    </div>
  )
}
