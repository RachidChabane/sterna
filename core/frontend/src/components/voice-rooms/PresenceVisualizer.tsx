/**
 * PresenceVisualizer - The Horizon
 *
 * A single, living line that flows across the screen like a soundscape.
 * The voice IS the landscape. Ultra minimal, bold, unique.
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

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

// Smooth easing for natural movement
function ease(t: number): number {
  return t * t * (3 - 2 * t)
}

// Default colors
const LISTENING_COLOR = { r: 52, g: 211, b: 153 }  // emerald-400
const IDLE_COLOR_DARK = { r: 100, g: 116, b: 139 } // slate
const IDLE_COLOR_LIGHT = { r: 148, g: 163, b: 184 }

export function PresenceVisualizer({
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
  const smoothedAudioRef = useRef(0)
  const { isDark } = useTheme()

  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Set canvas size
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

    // Catmull-Rom spline for ultra-smooth curves
    const catmullRom = (
      p0: number, p1: number, p2: number, p3: number, t: number
    ): number => {
      const t2 = t * t
      const t3 = t2 * t
      return 0.5 * (
        2 * p1 +
        (-p0 + p2) * t +
        (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
        (-p0 + 3 * p1 - 3 * p2 + p3) * t3
      )
    }

    const animate = () => {
      const width = container.clientWidth
      const height = container.clientHeight
      const centerY = height / 2

      timeRef.current += 0.015 // Faster horizontal flow

      // Smooth audio level
      const targetAudio = (isListening || isSpeaking) ? audioLevel : 0
      smoothedAudioRef.current = lerp(smoothedAudioRef.current, targetAudio, 0.12)
      const smoothedAudio = smoothedAudioRef.current

      // Smooth color transition
      const targetColor = getTargetColor()
      colorRef.current.r = lerp(colorRef.current.r, targetColor.r, 0.05)
      colorRef.current.g = lerp(colorRef.current.g, targetColor.g, 0.05)
      colorRef.current.b = lerp(colorRef.current.b, targetColor.b, 0.05)
      const color = colorRef.current

      const isActive = isListening || isSpeaking || isProcessing

      // Clear
      ctx.fillStyle = isDark ? '#0c0c0c' : '#f8fafc'
      ctx.fillRect(0, 0, width, height)

      // Amplitude: completely flat when silent, alive with sound
      const baseAmplitude = smoothedAudio * 80

      // Draw flowing layers
      const layers = 3
      for (let layer = 0; layer < layers; layer++) {
        const layerPhase = layer * 0.3
        const layerAlpha = isActive
          ? (0.35 - layer * 0.08) + smoothedAudio * 0.35
          : 0.06 - layer * 0.015
        const layerAmplitude = baseAmplitude * (1 - layer * 0.15)
        const layerY = centerY + layer * 6

        // Anchor points with traveling wave
        const anchors = 6
        const anchorPoints: number[] = []

        for (let i = 0; i < anchors; i++) {
          const t = timeRef.current
          const xPos = i / (anchors - 1)

          // Traveling wave - moves left to right
          const travelingWave = Math.sin((xPos * 2 - t) * Math.PI + layerPhase)
          const secondWave = Math.sin((xPos * 3 - t * 0.7) * Math.PI + layerPhase) * 0.4

          // Center anchors move more
          const centerWeight = 1 - Math.abs(xPos - 0.5) * 0.5

          const displacement = (travelingWave + secondWave) * centerWeight
          anchorPoints.push(layerY + displacement * layerAmplitude)
        }

        // Draw smooth spline through anchors
        ctx.beginPath()

        const segments = 80
        for (let i = 0; i <= segments; i++) {
          const t = i / segments
          const scaledT = t * (anchors - 1)
          const index = Math.floor(scaledT)
          const localT = scaledT - index

          // Get 4 control points for Catmull-Rom
          const p0 = anchorPoints[Math.max(0, index - 1)]
          const p1 = anchorPoints[index]
          const p2 = anchorPoints[Math.min(anchors - 1, index + 1)]
          const p3 = anchorPoints[Math.min(anchors - 1, index + 2)]

          const x = t * width
          const y = catmullRom(p0, p1, p2, p3, localT)

          if (i === 0) {
            ctx.moveTo(x, y)
          } else {
            ctx.lineTo(x, y)
          }
        }

        ctx.strokeStyle = `rgba(${color.r}, ${color.g}, ${color.b}, ${layerAlpha})`
        ctx.lineWidth = isActive ? 1 + smoothedAudio * 1.5 - layer * 0.15 : 0.5
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
