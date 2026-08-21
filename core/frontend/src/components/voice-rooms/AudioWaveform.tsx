import { useMemo } from 'react'
import { cn } from '@/lib/utils'

interface AudioWaveformProps {
  level: number // 0-1 normalized audio level
  isActive: boolean
  barCount?: number
}

export function AudioWaveform({ level, isActive, barCount = 32 }: AudioWaveformProps) {
  const bars = useMemo(() => {
    return Array.from({ length: barCount }, (_, i) => {
      // Create a wave pattern based on position and level
      const position = i / barCount
      const wave = Math.sin(position * Math.PI) // Bell curve across bars
      const randomFactor = 0.3 + Math.random() * 0.7 // Add some randomness
      const height = isActive
        ? Math.max(0.1, level * wave * randomFactor)
        : 0.1
      return height
    })
  }, [level, barCount, isActive])

  return (
    <div className="flex items-center justify-center gap-[2px] h-8">
      {bars.map((height, i) => (
        <div
          key={i}
          className={cn(
            'w-1 rounded-full transition-all duration-75',
            isActive ? 'bg-primary' : 'bg-muted-foreground/30'
          )}
          style={{
            height: `${Math.max(4, height * 32)}px`,
            transform: isActive ? `scaleY(${0.5 + height * 0.5})` : 'scaleY(1)',
          }}
        />
      ))}
    </div>
  )
}
