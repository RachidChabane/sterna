/**
 * ThinkingIndicator - A mesmerizing visual indicator for AI processing state
 *
 * Design: Orbital rings with particles that pulse and rotate,
 * inspired by atomic models and neural network visualizations.
 * Pure CSS animations - no external dependencies.
 */

import { cn } from '@/lib/utils'

interface ThinkingIndicatorProps {
  isVisible: boolean
  color?: { r: number; g: number; b: number }
  agentName?: string
  className?: string
}

export function ThinkingIndicator({
  isVisible,
  color = { r: 167, g: 139, b: 250 },
  agentName,
  className,
}: ThinkingIndicatorProps) {
  if (!isVisible) return null

  const colorStr = `rgb(${color.r}, ${color.g}, ${color.b})`
  const colorStrDim = `rgba(${color.r}, ${color.g}, ${color.b}, 0.3)`
  const colorStrGlow = `rgba(${color.r}, ${color.g}, ${color.b}, 0.6)`

  return (
    <div
      className={cn(
        'relative flex flex-col items-center justify-center animate-fade-in',
        className
      )}
      style={{
        // Custom animation for fade in
        animation: 'thinking-fade-in 0.4s cubic-bezier(0.23, 1, 0.32, 1) forwards',
      }}
    >
      {/* CSS Keyframes injected via style tag */}
      <style>{`
        @keyframes thinking-fade-in {
          from { opacity: 0; transform: scale(0.8); }
          to { opacity: 1; transform: scale(1); }
        }
        @keyframes thinking-glow-pulse {
          0%, 100% { transform: scale(1); opacity: 0.3; }
          50% { transform: scale(1.3); opacity: 0.5; }
        }
        @keyframes thinking-ring-rotate-1 {
          from { transform: rotateX(70deg) rotateZ(0deg); }
          to { transform: rotateX(70deg) rotateZ(360deg); }
        }
        @keyframes thinking-ring-rotate-2 {
          from { transform: rotateX(75deg) rotateZ(0deg); }
          to { transform: rotateX(75deg) rotateZ(-360deg); }
        }
        @keyframes thinking-ring-rotate-3 {
          from { transform: rotateX(65deg) rotateZ(0deg); }
          to { transform: rotateX(65deg) rotateZ(360deg); }
        }
        @keyframes thinking-core-pulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.15); }
        }
        @keyframes thinking-orbit {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes thinking-particle-pulse {
          0%, 100% { opacity: 0.4; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1.2); }
        }
        @keyframes thinking-dot-bounce {
          0%, 100% { opacity: 0.3; transform: translateY(0); }
          50% { opacity: 1; transform: translateY(-3px); }
        }
        @keyframes thinking-label-slide {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      {/* Outer glow pulse */}
      <div
        className="absolute rounded-full blur-xl"
        style={{
          width: '140px',
          height: '140px',
          backgroundColor: colorStrDim,
          animation: 'thinking-glow-pulse 2s ease-in-out infinite',
        }}
      />

      {/* Orbital container */}
      <div className="relative w-24 h-24" style={{ perspective: '200px' }}>
        {/* Ring 1 - Primary orbit */}
        <div
          className="absolute inset-2 rounded-full border-2"
          style={{
            borderColor: colorStrDim,
            animation: 'thinking-ring-rotate-1 3s linear infinite',
            transformStyle: 'preserve-3d',
          }}
        />

        {/* Ring 2 - Secondary orbit (counter-rotating) */}
        <div
          className="absolute inset-4 rounded-full border"
          style={{
            borderColor: colorStrGlow,
            animation: 'thinking-ring-rotate-2 4s linear infinite',
            transformStyle: 'preserve-3d',
          }}
        />

        {/* Ring 3 - Tertiary orbit */}
        <div
          className="absolute inset-6 rounded-full border"
          style={{
            borderColor: colorStrDim,
            animation: 'thinking-ring-rotate-3 5s linear infinite',
            transformStyle: 'preserve-3d',
          }}
        />

        {/* Center core - pulsing */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div
            className="w-3 h-3 rounded-full"
            style={{
              backgroundColor: colorStr,
              boxShadow: `0 0 20px ${colorStrGlow}, 0 0 40px ${colorStrDim}`,
              animation: 'thinking-core-pulse 1.5s ease-in-out infinite',
            }}
          />
        </div>

        {/* Orbiting particles */}
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="absolute inset-0"
            style={{
              animation: `thinking-orbit ${2 + i * 0.5}s linear infinite`,
              animationDelay: `${i * 0.3}s`,
            }}
          >
            <div
              className="absolute w-1.5 h-1.5 rounded-full"
              style={{
                backgroundColor: colorStr,
                top: '50%',
                left: i === 0 ? '0%' : i === 1 ? '10%' : '5%',
                marginTop: '-3px',
                boxShadow: `0 0 8px ${colorStrGlow}`,
                animation: `thinking-particle-pulse 1.5s ease-in-out infinite`,
                animationDelay: `${i * 0.2}s`,
              }}
            />
          </div>
        ))}
      </div>

      {/* Label */}
      <div
        className="mt-4 flex flex-col items-center gap-1"
        style={{
          animation: 'thinking-label-slide 0.4s ease-out 0.2s both',
        }}
      >
        {agentName && (
          <span
            className="text-sm font-medium tracking-wide"
            style={{ color: colorStr }}
          >
            {agentName}
          </span>
        )}
        <div className="flex items-center gap-1.5">
          <span
            className="text-xs uppercase tracking-[0.2em]"
            style={{ color: colorStr, opacity: 0.7 }}
          >
            Thinking
          </span>
          {/* Animated dots */}
          <span className="flex gap-0.5">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="w-1 h-1 rounded-full"
                style={{
                  backgroundColor: colorStr,
                  animation: `thinking-dot-bounce 0.8s ease-in-out infinite`,
                  animationDelay: `${i * 0.15}s`,
                }}
              />
            ))}
          </span>
        </div>
      </div>
    </div>
  )
}

/**
 * Compact version for inline use next to agent icons
 */
export function ThinkingDots({
  isVisible,
  color = { r: 167, g: 139, b: 250 },
}: {
  isVisible: boolean
  color?: { r: number; g: number; b: number }
}) {
  if (!isVisible) return null

  const colorStr = `rgb(${color.r}, ${color.g}, ${color.b})`

  return (
    <span className="flex items-center gap-0.5">
      <style>{`
        @keyframes thinking-inline-dot {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1.2); }
        }
      `}</style>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1 h-1 rounded-full"
          style={{
            backgroundColor: colorStr,
            animation: `thinking-inline-dot 0.6s ease-in-out infinite`,
            animationDelay: `${i * 0.15}s`,
          }}
        />
      ))}
    </span>
  )
}
