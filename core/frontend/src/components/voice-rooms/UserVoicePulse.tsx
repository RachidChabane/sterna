/**
 * UserVoicePulse - Subtle ambient glow responding to user's voice
 *
 * A discreet visual indicator that pulses with the user's audio input.
 * Creates an atmospheric presence at the bottom of the voice room,
 * confirming mic activity without being distracting.
 */

import { useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'

interface UserVoicePulseProps {
  audioLevel: number // 0-1 normalized audio level
  isListening: boolean // whether mic is active
  isDark?: boolean
  className?: string
}

export function UserVoicePulse({
  audioLevel,
  isListening,
  isDark = true,
  className,
}: UserVoicePulseProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | undefined>(undefined)
  const smoothedLevelRef = useRef(0)
  const glowIntensityRef = useRef(0)
  const audioLevelRef = useRef(audioLevel)
  const isListeningRef = useRef(isListening)
  const isDarkRef = useRef(isDark)
  const timeRef = useRef(0)

  // Update refs when props change (no re-render of effect)
  useEffect(() => {
    audioLevelRef.current = audioLevel
  }, [audioLevel])

  useEffect(() => {
    isListeningRef.current = isListening
  }, [isListening])

  useEffect(() => {
    isDarkRef.current = isDark
  }, [isDark])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let currentWidth = 0
    let currentHeight = 0

    const resize = () => {
      const dpr = window.devicePixelRatio || 1
      const rect = canvas.getBoundingClientRect()

      // Only resize if dimensions actually changed
      if (rect.width === currentWidth && rect.height === currentHeight) return
      currentWidth = rect.width
      currentHeight = rect.height

      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      ctx.setTransform(1, 0, 0, 1, 0, 0) // Reset transform before scaling
      ctx.scale(dpr, dpr)
    }

    // Use ResizeObserver for reliable sizing
    const resizeObserver = new ResizeObserver(() => {
      resize()
    })
    resizeObserver.observe(canvas)

    resize()
    window.addEventListener('resize', resize)

    const animate = () => {
      const width = canvas.clientWidth
      const height = canvas.clientHeight

      // Clear
      ctx.clearRect(0, 0, width, height)

      if (!isListeningRef.current) {
        // Fade out when not listening
        glowIntensityRef.current *= 0.92
        if (glowIntensityRef.current < 0.01) {
          animationRef.current = requestAnimationFrame(animate)
          return
        }
      } else {
        // AUDIO REACTIVITY
        const rawLevel = audioLevelRef.current
        const currentSmoothed = smoothedLevelRef.current

        // Threshold for "sound is present"
        const soundThreshold = 0.02

        if (rawLevel > currentSmoothed) {
          // Attack: snap quickly to loud sounds
          smoothedLevelRef.current += (rawLevel - currentSmoothed) * 0.6
        } else if (rawLevel > soundThreshold) {
          // Sound still present but quieter - hold level, very slow decay
          // This keeps waves up during sustained sounds
          smoothedLevelRef.current += (rawLevel - currentSmoothed) * 0.02
        } else {
          // Sound stopped - decay gradually
          smoothedLevelRef.current *= 0.95
        }

        // Base glow + audio response
        const baseGlow = 0.1
        const audioGlow = smoothedLevelRef.current * 2.0

        // Extra punch for transients
        const transientBoost = Math.max(0, rawLevel - currentSmoothed) * 1.5
        const targetIntensity = Math.min(1, baseGlow + audioGlow + transientBoost)

        // Intensity smoothing
        const currentIntensity = glowIntensityRef.current
        if (targetIntensity > currentIntensity) {
          // Rise fast
          glowIntensityRef.current += (targetIntensity - currentIntensity) * 0.5
        } else if (rawLevel > soundThreshold) {
          // Sound present - hold intensity, minimal decay
          glowIntensityRef.current += (targetIntensity - currentIntensity) * 0.03
        } else {
          // Sound stopped - fall slower
          glowIntensityRef.current += (targetIntensity - currentIntensity) * 0.08
        }
      }

      const intensity = glowIntensityRef.current

      // Slow, gentle time progression
      timeRef.current += 0.006

      // Only draw if there's something to show
      if (intensity > 0.01) {
        const dark = isDarkRef.current
        const time = timeRef.current

        // Muted sandy tones - subtle and ambient
        const sandColor = dark
          ? { r: 210, g: 185, b: 150 }
          : { r: 160, g: 135, b: 100 }

        // 2 subtle layers
        const numLayers = 2

        for (let layer = 0; layer < numLayers; layer++) {
          const color = sandColor

          // Visible but subtle wave properties
          const baseY = height - layer * 40
          const waveAmplitude = (20 + layer * 15) * intensity
          const waveFrequency = 2 + layer * 0.3
          const phaseOffset = layer * 1.2
          const speed = 0.15 + layer * 0.05

          // Visible opacity - subtle but present
          const layerOpacity = (0.25 + layer * 0.1) * intensity

          ctx.beginPath()
          ctx.moveTo(0, height)

          // Draw gentle dune curve
          for (let x = 0; x <= width; x += 4) {
            const t = x / width

            // Simple, gentle wave combination
            const wave1 = Math.sin((t * waveFrequency + time * speed + phaseOffset) * Math.PI * 2)
            const wave2 = Math.sin((t * waveFrequency * 1.5 + time * speed * 0.6) * Math.PI * 2) * 0.3

            // Soft edge falloff
            const edgeFalloff = 4 * t * (1 - t)
            const waveHeight = (wave1 + wave2) * waveAmplitude * edgeFalloff

            // Taller arc
            const y = baseY - waveHeight - (80 * edgeFalloff * intensity)

            ctx.lineTo(x, y)
          }

          ctx.lineTo(width, height)
          ctx.closePath()

          // Soft gradient fill
          const gradient = ctx.createLinearGradient(0, baseY - 30, 0, height)
          gradient.addColorStop(0, `rgba(${color.r}, ${color.g}, ${color.b}, ${layerOpacity})`)
          gradient.addColorStop(0.6, `rgba(${color.r}, ${color.g}, ${color.b}, ${layerOpacity * 0.4})`)
          gradient.addColorStop(1, `rgba(${color.r}, ${color.g}, ${color.b}, 0)`)

          ctx.fillStyle = gradient
          ctx.fill()
        }
      }

      animationRef.current = requestAnimationFrame(animate)
    }

    animationRef.current = requestAnimationFrame(animate)

    return () => {
      window.removeEventListener('resize', resize)
      resizeObserver.disconnect()
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, []) // No dependencies - uses refs for reactive values

  return (
    <canvas
      ref={canvasRef}
      className={cn(
        'absolute bottom-0 left-0 w-full h-96 pointer-events-none z-[15]',
        className
      )}
    />
  )
}
