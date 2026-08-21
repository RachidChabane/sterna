/**
 * VoiceRings - Animated concentric rings visualization
 *
 * Multiple layered rings that pulse, rotate, and react to audio.
 * Clear state transitions with dramatic color shifts.
 */

import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'

interface VoiceRingsProps {
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  audioLevel: number
  className?: string
}

export function VoiceRings({
  isListening,
  isSpeaking,
  isProcessing,
  audioLevel,
  className,
}: VoiceRingsProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Determine current state for styling
  const state = isSpeaking
    ? 'speaking'
    : isListening
    ? 'listening'
    : isProcessing
    ? 'processing'
    : 'idle'

  // Scale based on audio level
  const audioScale = 1 + audioLevel * 0.15

  return (
    <div
      ref={containerRef}
      className={cn(
        'relative w-64 h-64 flex items-center justify-center',
        className
      )}
    >
      {/* Outer glow */}
      <div
        className={cn(
          'absolute inset-0 rounded-full blur-3xl transition-all duration-700',
          state === 'speaking' && 'bg-blue-500/20',
          state === 'listening' && 'bg-emerald-500/20',
          state === 'processing' && 'bg-violet-500/20',
          state === 'idle' && 'bg-slate-500/5',
        )}
        style={{ transform: `scale(${audioScale * 1.2})` }}
      />

      {/* Ring 4 - Outermost */}
      <div
        className={cn(
          'absolute w-56 h-56 rounded-full border-2 transition-all duration-500',
          'animate-[spin_20s_linear_infinite]',
          state === 'speaking' && 'border-blue-500/30',
          state === 'listening' && 'border-emerald-500/30',
          state === 'processing' && 'border-violet-500/30',
          state === 'idle' && 'border-white/5',
        )}
        style={{
          transform: `scale(${audioScale})`,
          animationDirection: 'reverse',
        }}
      />

      {/* Ring 3 */}
      <div
        className={cn(
          'absolute w-44 h-44 rounded-full border transition-all duration-500',
          'animate-[spin_15s_linear_infinite]',
          state === 'speaking' && 'border-blue-400/40',
          state === 'listening' && 'border-emerald-400/40',
          state === 'processing' && 'border-violet-400/40',
          state === 'idle' && 'border-white/5',
        )}
        style={{ transform: `scale(${audioScale * 1.05})` }}
      />

      {/* Ring 2 */}
      <div
        className={cn(
          'absolute w-32 h-32 rounded-full border-2 transition-all duration-500',
          'animate-[spin_10s_linear_infinite]',
          state === 'speaking' && 'border-blue-400/50',
          state === 'listening' && 'border-emerald-400/50',
          state === 'processing' && 'border-violet-400/50',
          state === 'idle' && 'border-white/10',
        )}
        style={{
          transform: `scale(${audioScale * 1.1})`,
          animationDirection: 'reverse',
        }}
      />

      {/* Ring 1 - Inner */}
      <div
        className={cn(
          'absolute w-20 h-20 rounded-full border transition-all duration-500',
          'animate-[spin_8s_linear_infinite]',
          state === 'speaking' && 'border-blue-300/60',
          state === 'listening' && 'border-emerald-300/60',
          state === 'processing' && 'border-violet-300/60',
          state === 'idle' && 'border-white/10',
        )}
        style={{ transform: `scale(${audioScale * 1.15})` }}
      />

      {/* Center core */}
      <div
        className={cn(
          'relative w-16 h-16 rounded-full transition-all duration-300',
          'flex items-center justify-center',
          state === 'speaking' && 'bg-gradient-to-br from-blue-400 to-blue-600 shadow-lg shadow-blue-500/30',
          state === 'listening' && 'bg-gradient-to-br from-emerald-400 to-emerald-600 shadow-lg shadow-emerald-500/30',
          state === 'processing' && 'bg-gradient-to-br from-violet-400 to-violet-600 shadow-lg shadow-violet-500/30',
          state === 'idle' && 'bg-gradient-to-br from-slate-600 to-slate-700',
        )}
        style={{ transform: `scale(${1 + audioLevel * 0.2})` }}
      >
        {/* Inner pulse */}
        <div
          className={cn(
            'absolute inset-0 rounded-full animate-ping',
            state === 'speaking' && 'bg-blue-400/30',
            state === 'listening' && 'bg-emerald-400/30',
            state === 'processing' && 'bg-violet-400/30',
            state === 'idle' && 'bg-transparent',
          )}
          style={{ animationDuration: '2s' }}
        />

        {/* Core highlight */}
        <div className="w-6 h-6 rounded-full bg-white/20" />
      </div>

      {/* Floating particles - only when active */}
      {(isListening || isSpeaking || isProcessing) && (
        <>
          {[...Array(8)].map((_, i) => (
            <div
              key={i}
              className={cn(
                'absolute w-1.5 h-1.5 rounded-full',
                'animate-[float_3s_ease-in-out_infinite]',
                state === 'speaking' && 'bg-blue-400/60',
                state === 'listening' && 'bg-emerald-400/60',
                state === 'processing' && 'bg-violet-400/60',
              )}
              style={{
                animationDelay: `${i * 0.3}s`,
                left: `${50 + Math.cos(i * Math.PI / 4) * 40}%`,
                top: `${50 + Math.sin(i * Math.PI / 4) * 40}%`,
                transform: `scale(${0.5 + audioLevel})`,
              }}
            />
          ))}
        </>
      )}
    </div>
  )
}
