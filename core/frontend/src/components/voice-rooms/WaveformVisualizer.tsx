/**
 * WaveformVisualizer - Elegant flowing audio wave
 *
 * A smooth, organic waveform that responds to audio input.
 * Uses bezier curves for fluid, natural movement.
 */

import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'

interface WaveformVisualizerProps {
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  audioLevel: number
  className?: string
}

// Smooth interpolation
function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export function WaveformVisualizer({
  isListening,
  isSpeaking,
  isProcessing,
  audioLevel,
  className,
}: WaveformVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | undefined>(undefined)
  const timeRef = useRef(0)
  const smoothedAudioRef = useRef(0)
  const colorRef = useRef({ r: 100, g: 116, b: 139 })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // High DPI support
    const dpr = window.devicePixelRatio || 1
    const width = 400
    const height = 150
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    ctx.scale(dpr, dpr)

    // Target colors for different states
    const getTargetColor = () => {
      if (isSpeaking) return { r: 56, g: 189, b: 248 }  // sky-400
      if (isListening) return { r: 52, g: 211, b: 153 } // emerald-400
      if (isProcessing) return { r: 167, g: 139, b: 250 } // violet-400
      return { r: 100, g: 116, b: 139 } // slate-500
    }

    const animate = () => {
      timeRef.current += 0.02
      const time = timeRef.current

      // Smooth audio level
      const targetAudio = (isListening || isSpeaking) ? audioLevel : 0.1
      smoothedAudioRef.current = lerp(smoothedAudioRef.current, targetAudio, 0.1)
      const audio = smoothedAudioRef.current

      // Smooth color transition
      const targetColor = getTargetColor()
      colorRef.current.r = lerp(colorRef.current.r, targetColor.r, 0.05)
      colorRef.current.g = lerp(colorRef.current.g, targetColor.g, 0.05)
      colorRef.current.b = lerp(colorRef.current.b, targetColor.b, 0.05)
      const { r, g, b } = colorRef.current

      // Clear
      ctx.clearRect(0, 0, width, height)

      const centerY = height / 2
      const amplitude = 20 + audio * 40
      const isActive = isListening || isSpeaking || isProcessing

      // Draw multiple layered waves for depth
      const layers = [
        { alpha: 0.1, offset: 0, speed: 1, amp: 1.2 },
        { alpha: 0.2, offset: 2, speed: 0.8, amp: 1 },
        { alpha: 0.4, offset: 4, speed: 1.2, amp: 0.8 },
      ]

      layers.forEach(layer => {
        ctx.beginPath()
        ctx.moveTo(0, centerY)

        // Create smooth wave using quadratic curves
        const segments = 50
        const segmentWidth = width / segments

        for (let i = 0; i <= segments; i++) {
          const x = i * segmentWidth
          const progress = i / segments

          // Multiple frequencies for organic feel
          const wave1 = Math.sin(time * layer.speed + progress * 4 + layer.offset) * amplitude * layer.amp
          const wave2 = Math.sin(time * layer.speed * 1.5 + progress * 6 + layer.offset) * amplitude * 0.3 * layer.amp
          const wave3 = Math.sin(time * layer.speed * 0.5 + progress * 2 + layer.offset) * amplitude * 0.2 * layer.amp

          // Fade at edges
          const edgeFade = Math.sin(progress * Math.PI)
          const y = centerY + (wave1 + wave2 + wave3) * edgeFade * (isActive ? 1 : 0.3)

          if (i === 0) {
            ctx.moveTo(x, y)
          } else {
            const prevX = (i - 1) * segmentWidth
            const cpX = (prevX + x) / 2
            ctx.quadraticCurveTo(cpX, y, x, y)
          }
        }

        // Complete the shape for fill
        ctx.lineTo(width, height)
        ctx.lineTo(0, height)
        ctx.closePath()

        // Gradient fill
        const gradient = ctx.createLinearGradient(0, centerY - amplitude, 0, height)
        gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, ${layer.alpha})`)
        gradient.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, ${layer.alpha * 0.5})`)
        gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`)

        ctx.fillStyle = gradient
        ctx.fill()
      })

      // Draw the main line on top
      ctx.beginPath()
      const segments = 50
      const segmentWidth = width / segments

      for (let i = 0; i <= segments; i++) {
        const x = i * segmentWidth
        const progress = i / segments

        const wave1 = Math.sin(time + progress * 4) * amplitude
        const wave2 = Math.sin(time * 1.5 + progress * 6) * amplitude * 0.3
        const wave3 = Math.sin(time * 0.5 + progress * 2) * amplitude * 0.2

        const edgeFade = Math.sin(progress * Math.PI)
        const y = centerY + (wave1 + wave2 + wave3) * edgeFade * (isActive ? 1 : 0.3)

        if (i === 0) {
          ctx.moveTo(x, y)
        } else {
          const prevX = (i - 1) * segmentWidth
          const cpX = (prevX + x) / 2
          ctx.quadraticCurveTo(cpX, y, x, y)
        }
      }

      ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${isActive ? 0.8 : 0.3})`
      ctx.lineWidth = 2
      ctx.lineCap = 'round'
      ctx.stroke()

      // Glow effect for the line
      if (isActive) {
        ctx.shadowColor = `rgba(${r}, ${g}, ${b}, 0.5)`
        ctx.shadowBlur = 10
        ctx.stroke()
        ctx.shadowBlur = 0
      }

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
    <div className={cn('relative', className)}>
      {/* Ambient glow behind */}
      <div
        className={cn(
          'absolute inset-0 blur-3xl transition-opacity duration-700 -z-10',
          (isSpeaking || isListening || isProcessing) ? 'opacity-60' : 'opacity-0'
        )}
        style={{
          background: isSpeaking
            ? 'radial-gradient(ellipse at center, rgba(56, 189, 248, 0.15) 0%, transparent 70%)'
            : isListening
            ? 'radial-gradient(ellipse at center, rgba(52, 211, 153, 0.15) 0%, transparent 70%)'
            : 'radial-gradient(ellipse at center, rgba(167, 139, 250, 0.15) 0%, transparent 70%)',
        }}
      />
      <canvas ref={canvasRef} />
    </div>
  )
}
