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
