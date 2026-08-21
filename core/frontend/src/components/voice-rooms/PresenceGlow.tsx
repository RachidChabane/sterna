/**
 * PresenceGlow - Intimate ambient presence
 *
 * Not a visualization. An atmosphere.
 * Like the warmth of a room when someone is speaking.
 * You don't watch it. You feel it.
 */

import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'

interface PresenceGlowProps {
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  audioLevel: number
  speakerColor?: { r: number; g: number; b: number }
  className?: string
}

const LISTENING_COLOR = { r: 52, g: 211, b: 153 }
const IDLE_COLOR_DARK = { r: 60, g: 60, b: 70 }
const IDLE_COLOR_LIGHT = { r: 180, g: 180, b: 190 }

export function PresenceGlow({
  isListening,
  isSpeaking,
  isProcessing,
  audioLevel,
  speakerColor,
  className,
}: PresenceGlowProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animationRef = useRef<number | undefined>(undefined)
  const { isDark } = useTheme()

  // Smooth state
  const glowIntensityRef = useRef(0)
  const glowSizeRef = useRef(0.3)
  const colorRef = useRef({ r: 60, g: 60, b: 70 })
  const breathRef = useRef(0)

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
      const centerX = width / 2
      // Glow emanates from lower area where agent cards are
      const glowY = height * 0.72

      const isActive = isListening || isSpeaking || isProcessing
      const currentAudio = (isListening || isSpeaking) ? audioLevel : 0

      // Natural breathing rhythm
      breathRef.current += 0.006
      const naturalBreath = Math.sin(breathRef.current) * 0.5 + 0.5

      // Target values
      const targetIntensity = isActive
        ? 0.2 + currentAudio * 0.5 + naturalBreath * 0.05
        : 0.04 + naturalBreath * 0.02

      const targetSize = isActive
        ? 0.5 + currentAudio * 0.25
        : 0.35

      // Smooth transitions
      const intensitySpeed = isActive ? 0.1 : 0.03
      const sizeSpeed = 0.05

      glowIntensityRef.current += (targetIntensity - glowIntensityRef.current) * intensitySpeed
      glowSizeRef.current += (targetSize - glowSizeRef.current) * sizeSpeed

      // Color target
      let targetColor = isDark ? IDLE_COLOR_DARK : IDLE_COLOR_LIGHT
      if (isListening) {
        targetColor = LISTENING_COLOR
      } else if ((isSpeaking || isProcessing) && speakerColor) {
        targetColor = speakerColor
      }

      // Smooth color transition
      colorRef.current.r += (targetColor.r - colorRef.current.r) * 0.05
      colorRef.current.g += (targetColor.g - colorRef.current.g) * 0.05
      colorRef.current.b += (targetColor.b - colorRef.current.b) * 0.05

      const color = colorRef.current
      const intensity = glowIntensityRef.current
      const size = glowSizeRef.current

      // Clear
      const bg = isDark ? '#0c0c0c' : '#f8fafc'
      ctx.fillStyle = bg
      ctx.fillRect(0, 0, width, height)

      // The glow - emanating upward from the speakers
      const glowRadius = height * size

      // Layered glow for softness
      const layers = [
        { size: 1.2, alpha: intensity * 0.12 },
        { size: 0.8, alpha: intensity * 0.2 },
        { size: 0.5, alpha: intensity * 0.3 },
        { size: 0.25, alpha: intensity * 0.45 },
      ]

      for (const layer of layers) {
        const gradient = ctx.createRadialGradient(
          centerX, glowY, 0,
          centerX, glowY, glowRadius * layer.size
        )

        gradient.addColorStop(0, `rgba(${color.r}, ${color.g}, ${color.b}, ${layer.alpha})`)
        gradient.addColorStop(0.4, `rgba(${color.r}, ${color.g}, ${color.b}, ${layer.alpha * 0.4})`)
        gradient.addColorStop(1, 'transparent')

        ctx.fillStyle = gradient
        ctx.fillRect(0, 0, width, height)
      }

      // Soft vignette at edges
      const vignetteGradient = ctx.createRadialGradient(
        centerX, height * 0.5, height * 0.2,
        centerX, height * 0.5, height * 0.9
      )
      const vignetteStrength = isDark ? 0.5 : 0.2
      vignetteGradient.addColorStop(0, 'transparent')
      vignetteGradient.addColorStop(1, `rgba(0, 0, 0, ${vignetteStrength})`)
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
  }, [isListening, isSpeaking, isProcessing, audioLevel, isDark, speakerColor])

  return (
    <div ref={containerRef} className={cn('relative w-full h-full', className)}>
      <canvas ref={canvasRef} className="absolute inset-0" />
    </div>
  )
}
