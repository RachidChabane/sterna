import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'

interface AnimatedOrbProps {
  isActive: boolean
  isSpeaking: boolean
  isListening: boolean
  isProcessing?: boolean
  audioLevel: number
  className?: string
}

export function AnimatedOrb({
  isActive,
  isSpeaking,
  isListening,
  isProcessing = false,
  audioLevel,
  className,
}: AnimatedOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | undefined>(undefined)
  const timeRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // High DPI support
    const dpr = window.devicePixelRatio || 1
    const size = 200
    canvas.width = size * dpr
    canvas.height = size * dpr
    canvas.style.width = `${size}px`
    canvas.style.height = `${size}px`
    ctx.scale(dpr, dpr)

    const centerX = size / 2
    const centerY = size / 2
    const radius = size / 2 - 4

    const animate = () => {
      timeRef.current += 0.015
      const time = timeRef.current

      // Clear canvas
      ctx.clearRect(0, 0, size, size)

      // Create circular clipping path
      ctx.save()
      ctx.beginPath()
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2)
      ctx.clip()

      // Background
      ctx.fillStyle = '#1a1a2e'
      ctx.fillRect(0, 0, size, size)

      // Aurora effect - flowing gradients
      const intensity = isActive ? (isSpeaking || isListening || isProcessing ? 0.6 + audioLevel * 0.4 : 0.4) : 0.2
      const speed = isSpeaking ? 1.5 : isListening ? 1.2 : isProcessing ? 1.0 : 0.5

      // Draw multiple flowing blobs
      for (let i = 0; i < 5; i++) {
        const phase = (time * speed + i * 1.2) % (Math.PI * 2)
        const blobX = centerX + Math.sin(phase + i) * (30 + audioLevel * 20)
        const blobY = centerY + Math.cos(phase * 0.7 + i * 0.5) * (25 + audioLevel * 15)
        const blobRadius = 40 + Math.sin(time * 2 + i) * 15 + audioLevel * 30

        // Color based on state
        let hue: number
        if (isSpeaking) {
          // Blue/cyan for speaking
          hue = 200 + i * 15 + Math.sin(time + i) * 10
        } else if (isProcessing) {
          // Purple/pink for thinking/processing
          hue = 280 + i * 15 + Math.sin(time + i) * 15
        } else if (isListening) {
          // Green/teal for listening
          hue = 150 + i * 10 + Math.sin(time + i) * 10
        } else {
          // Gray/blue for idle
          hue = 220 + i * 5
        }

        const gradient = ctx.createRadialGradient(
          blobX, blobY, 0,
          blobX, blobY, blobRadius
        )
        gradient.addColorStop(0, `hsla(${hue}, 80%, 65%, ${intensity * 0.8})`)
        gradient.addColorStop(0.5, `hsla(${hue}, 70%, 50%, ${intensity * 0.4})`)
        gradient.addColorStop(1, `hsla(${hue}, 60%, 40%, 0)`)

        ctx.fillStyle = gradient
        ctx.beginPath()
        ctx.arc(blobX, blobY, blobRadius, 0, Math.PI * 2)
        ctx.fill()
      }

      // Add a subtle white glow in the center when active
      if (isActive && (isSpeaking || isListening || isProcessing)) {
        const glowGradient = ctx.createRadialGradient(
          centerX, centerY - 10, 0,
          centerX, centerY - 10, 60 + audioLevel * 20
        )
        glowGradient.addColorStop(0, `rgba(255, 255, 255, ${0.3 + audioLevel * 0.2})`)
        glowGradient.addColorStop(0.5, `rgba(255, 255, 255, ${0.1 + audioLevel * 0.1})`)
        glowGradient.addColorStop(1, 'rgba(255, 255, 255, 0)')
        ctx.fillStyle = glowGradient
        ctx.fillRect(0, 0, size, size)
      }

      ctx.restore()

      // Draw circle border
      ctx.beginPath()
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2)
      ctx.strokeStyle = isSpeaking
        ? `rgba(100, 200, 255, ${0.3 + audioLevel * 0.3})`
        : isProcessing
        ? `rgba(180, 100, 255, ${0.4 + Math.sin(time * 2) * 0.2})`
        : isListening
        ? `rgba(100, 255, 150, ${0.3 + audioLevel * 0.3})`
        : 'rgba(255, 255, 255, 0.1)'
      ctx.lineWidth = 2
      ctx.stroke()

      animationRef.current = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [isActive, isSpeaking, isListening, isProcessing, audioLevel])

  // Pulse animation scale based on audio level
  const pulseScale = 1 + (isSpeaking || isListening ? audioLevel * 0.08 : isProcessing ? 0.02 : 0)

  return (
    <div
      className={cn('relative flex items-center justify-center', className)}
      style={{
        transform: `scale(${pulseScale})`,
        transition: 'transform 0.1s ease-out',
      }}
    >
      {/* Outer glow */}
      {(isSpeaking || isListening || isProcessing) && (
        <div
          className="absolute rounded-full"
          style={{
            width: 240 + audioLevel * 40,
            height: 240 + audioLevel * 40,
            background: isSpeaking
              ? `radial-gradient(circle, rgba(100, 200, 255, ${0.15 + audioLevel * 0.1}) 0%, transparent 70%)`
              : isProcessing
              ? `radial-gradient(circle, rgba(180, 100, 255, 0.15) 0%, transparent 70%)`
              : `radial-gradient(circle, rgba(100, 255, 150, ${0.15 + audioLevel * 0.1}) 0%, transparent 70%)`,
            transition: 'all 0.15s ease-out',
          }}
        />
      )}

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        className={cn(
          'rounded-full',
          !isActive && 'opacity-50'
        )}
        style={{
          boxShadow: isSpeaking
            ? `0 0 ${30 + audioLevel * 30}px rgba(100, 200, 255, 0.3)`
            : isProcessing
            ? '0 0 30px rgba(180, 100, 255, 0.3)'
            : isListening
            ? `0 0 ${30 + audioLevel * 30}px rgba(100, 255, 150, 0.3)`
            : '0 0 20px rgba(100, 100, 120, 0.2)',
        }}
      />
    </div>
  )
}
