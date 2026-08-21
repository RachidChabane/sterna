/**
 * ChatGPT-style microphone button with waveform visualization.
 *
 * States:
 * - Idle: Shows microphone icon button
 * - Recording: Shows full-width waveform with cancel (X) and confirm (✓) buttons
 * - Transcribing: Shows loading spinner
 */

import { memo, useState, useRef, useEffect } from 'react'
import { Mic, X, Check, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { AudioLevelEntry } from '@/hooks/useSpeechToText'

interface MicrophoneButtonProps {
  /** Whether currently recording */
  isRecording: boolean
  /** Whether waiting for transcription */
  isTranscribing: boolean
  /** Array of audio levels for waveform visualization (with unique IDs) */
  audioLevels: AudioLevelEntry[]
  /** Start recording handler */
  onStartRecording: () => void
  /** Stop recording and transcribe handler */
  onStopRecording: () => void
  /** Cancel recording handler */
  onCancelRecording: () => void
  /** Whether the button should be disabled */
  disabled?: boolean
  /** Additional CSS classes */
  className?: string
}

// Waveform dot/bar component - height is set once based on audio level and never changes
const WaveformDot = memo<{ level: number }>(({ level }) => {
  // Map level to height - minimum 3px (dot), max 40px (full bar)
  const minHeight = 3
  const maxHeight = 40
  const height = minHeight + level * (maxHeight - minHeight)

  // Silent dots (no sound captured) are grey, active dots are foreground color
  const isSilent = level < 0.01

  return (
    <div
      className={cn(
        "waveform-dot w-[3px] rounded-full",
        isSilent ? "bg-muted-foreground/50" : "bg-foreground"
      )}
      style={{
        height: `${height}px`,
      }}
    />
  )
})
WaveformDot.displayName = 'WaveformDot'

// Full-width waveform visualization - dots flow from right to left with 60fps smooth scrolling
const WaveformVisualizer = memo<{ levels: AudioLevelEntry[] }>(({ levels }) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const animationRef = useRef<number | null>(null)
  const startTimeRef = useRef<number>(performance.now())
  const lastIdRef = useRef<number>(levels[levels.length - 1]?.id ?? 0)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    // Dot width (3px) + gap (3px) = 6px total per dot
    const DOT_STEP = 6
    // Time between data updates
    const UPDATE_INTERVAL = 150

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTimeRef.current
      // Calculate smooth offset based on time
      const progress = Math.min(elapsed / UPDATE_INTERVAL, 1)
      const offset = DOT_STEP * (1 - progress)

      container.style.transform = `translateX(${offset}px)`

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate)
      }
    }

    // Check if new dot was added
    const currentId = levels[levels.length - 1]?.id ?? 0
    if (currentId !== lastIdRef.current) {
      lastIdRef.current = currentId
      startTimeRef.current = performance.now()

      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
      animationRef.current = requestAnimationFrame(animate)
    }

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [levels])

  return (
    <div className="relative h-10 w-full overflow-hidden">
      {/* Dots container with hardware-accelerated transform */}
      <div
        ref={containerRef}
        className="absolute inset-y-0 right-0 flex items-center gap-[3px] will-change-transform"
      >
        {levels.map((entry) => (
          <WaveformDot key={entry.id} level={entry.level} />
        ))}
      </div>
      {/* Subtle gradient fade on the right edge */}
      <div className="absolute inset-y-0 right-0 w-8 pointer-events-none bg-gradient-to-l from-background to-transparent z-10" />
    </div>
  )
})
WaveformVisualizer.displayName = 'WaveformVisualizer'

export const MicrophoneButton = memo<MicrophoneButtonProps>(({
  isRecording,
  isTranscribing,
  audioLevels,
  onStartRecording,
  onStopRecording,
  onCancelRecording,
  disabled = false,
  className,
}) => {
  const isDisabled = disabled || isTranscribing

  // Transcribing state - show loading (full width)
  if (isTranscribing) {
    return (
      <div className={cn(
        "flex items-center justify-center gap-2 w-full py-2",
        className
      )}>
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Transcribing...</span>
      </div>
    )
  }

  // Recording state - full-width waveform with cancel/confirm buttons
  if (isRecording) {
    return (
      <div className={cn(
        "flex items-center gap-3 w-full",
        "animate-in fade-in duration-200",
        className
      )}>
        {/* Cancel button */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              onClick={onCancelRecording}
              className={cn(
                "h-8 w-8 rounded-full flex-shrink-0",
                "text-muted-foreground hover:text-foreground hover:bg-muted",
                "transition-colors duration-150"
              )}
            >
              <X className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-xs">
            Cancel
          </TooltipContent>
        </Tooltip>

        {/* Waveform visualizer - takes remaining space */}
        <div className="flex-1 min-w-0">
          <WaveformVisualizer levels={audioLevels} />
        </div>

        {/* Confirm button */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              onClick={onStopRecording}
              className={cn(
                "h-8 w-8 rounded-full flex-shrink-0",
                "text-muted-foreground hover:text-foreground hover:bg-muted",
                "transition-colors duration-150"
              )}
            >
              <Check className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-xs">
            Send
          </TooltipContent>
        </Tooltip>
      </div>
    )
  }

  // Idle state - show mic button
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-block">
          <Button
            size="icon"
            variant="outline"
            onClick={onStartRecording}
            disabled={isDisabled}
            className={cn(
              "h-9 w-9 rounded-full transition-all duration-200",
              "hover:scale-105 hover:bg-accent/50",
              className
            )}
          >
            <Mic className="h-4 w-4" />
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="text-xs">
        Voice input
      </TooltipContent>
    </Tooltip>
  )
})

MicrophoneButton.displayName = 'MicrophoneButton'
