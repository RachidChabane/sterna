/**
 * VoiceVisualizer - Modern audio visualization component
 *
 * Inspired by GPT/Gemini/Claude voice interfaces:
 * - Central animated waveform/bars
 * - Smooth, fluid animations
 * - Color changes based on state
 */

import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'

interface VoiceVisualizerProps {
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  audioLevel: number
  className?: string
}

export function VoiceVisualizer({
  isListening,
  isSpeaking,
  isProcessing,
  audioLevel,
  className,
}: VoiceVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | undefined>(undefined)
  const timeRef = useRef(0)
  const barsRef = useRef<number[]>(Array(64).fill(0))

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // High DPI support
    const dpr = window.devicePixelRatio || 1
    const width = 300
    const height = 120
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    ctx.scale(dpr, dpr)

    const barCount = 64
    const barWidth = 3
    const gap = 1.5
    const totalWidth = barCount * (barWidth + gap) - gap
    const startX = (width - totalWidth) / 2

    const animate = () => {
      timeRef.current += 0.03
      const time = timeRef.current

      // Clear canvas
      ctx.clearRect(0, 0, width, height)

      // Update bar heights with smooth interpolation
      const targetBars = barsRef.current.map((_, i) => {
        if (isSpeaking || isListening) {
          // Active state - audio reactive with wave pattern
          const baseWave = Math.sin(time * 3 + i * 0.15) * 0.3
          const audioInfluence = audioLevel * (0.5 + Math.sin(time * 5 + i * 0.2) * 0.3)
          const centerFalloff = 1 - Math.abs(i - barCount / 2) / (barCount / 2) * 0.4
          return Math.max(0.05, (baseWave + 0.5 + audioInfluence) * centerFalloff)
        } else if (isProcessing) {
          // Processing - flowing wave
          const wave = Math.sin(time * 2 + i * 0.12) * 0.5 + 0.5
          const pulse = Math.sin(time * 4) * 0.1 + 0.9
          return wave * pulse * 0.7
        } else {
          // Idle - subtle ambient movement
          return Math.sin(time * 0.8 + i * 0.1) * 0.08 + 0.12
        }
      })

      // Smooth interpolation
      barsRef.current = barsRef.current.map((current, i) => {
        const target = targetBars[i]
        return current + (target - current) * 0.15
      })

      // Determine colors based on state
      let primaryColor: string
      let secondaryColor: string

      if (isSpeaking) {
        primaryColor = 'rgba(59, 130, 246, 0.9)' // Blue
        secondaryColor = 'rgba(147, 197, 253, 0.7)'
      } else if (isListening) {
        primaryColor = 'rgba(34, 197, 94, 0.9)' // Green
        secondaryColor = 'rgba(134, 239, 172, 0.7)'
      } else if (isProcessing) {
        primaryColor = 'rgba(168, 85, 247, 0.9)' // Purple
        secondaryColor = 'rgba(216, 180, 254, 0.7)'
      } else {
        primaryColor = 'rgba(148, 163, 184, 0.4)' // Gray
        secondaryColor = 'rgba(148, 163, 184, 0.2)'
      }

      // Draw bars
      const centerY = height / 2
      const maxBarHeight = height * 0.8

      barsRef.current.forEach((barHeight, i) => {
        const x = startX + i * (barWidth + gap)
        const h = barHeight * maxBarHeight

        // Create gradient for each bar
        const gradient = ctx.createLinearGradient(x, centerY - h / 2, x, centerY + h / 2)
        gradient.addColorStop(0, secondaryColor)
        gradient.addColorStop(0.5, primaryColor)
        gradient.addColorStop(1, secondaryColor)

        // Draw rounded bar
        ctx.fillStyle = gradient
        ctx.beginPath()
        const radius = barWidth / 2
        const y = centerY - h / 2

        // Rounded rectangle
        ctx.moveTo(x + radius, y)
        ctx.lineTo(x + barWidth - radius, y)
        ctx.quadraticCurveTo(x + barWidth, y, x + barWidth, y + radius)
        ctx.lineTo(x + barWidth, y + h - radius)
        ctx.quadraticCurveTo(x + barWidth, y + h, x + barWidth - radius, y + h)
        ctx.lineTo(x + radius, y + h)
        ctx.quadraticCurveTo(x, y + h, x, y + h - radius)
        ctx.lineTo(x, y + radius)
        ctx.quadraticCurveTo(x, y, x + radius, y)
        ctx.fill()
      })

      animationRef.current = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [isListening, isSpeaking, isProcessing, audioLevel])

  return (
    <div className={cn('relative flex items-center justify-center', className)}>
      {/* Glow effect behind */}
      <div
        className={cn(
          'absolute inset-0 blur-3xl transition-opacity duration-500',
          (isSpeaking || isListening || isProcessing) ? 'opacity-100' : 'opacity-0'
        )}
        style={{
          background: isSpeaking
            ? 'radial-gradient(ellipse at center, rgba(59, 130, 246, 0.15) 0%, transparent 70%)'
            : isListening
            ? 'radial-gradient(ellipse at center, rgba(34, 197, 94, 0.15) 0%, transparent 70%)'
            : 'radial-gradient(ellipse at center, rgba(168, 85, 247, 0.15) 0%, transparent 70%)',
        }}
      />

      <canvas
        ref={canvasRef}
        className="relative z-10"
      />
    </div>
  )
}
