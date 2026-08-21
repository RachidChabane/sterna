import { useRef, useState, useEffect, useCallback } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface PullToRefreshProps {
  children: React.ReactNode
  onRefresh?: () => Promise<void>
  className?: string
  style?: React.CSSProperties
}

export function PullToRefresh({ children, onRefresh, className, style }: PullToRefreshProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [pullDistance, setPullDistance] = useState(0)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isPulling, setIsPulling] = useState(false)
  const startY = useRef(0)
  const currentY = useRef(0)

  const threshold = 80 // Distance needed to trigger refresh
  const maxPull = 120 // Maximum pull distance

  const handleTouchStart = useCallback((e: TouchEvent) => {
    const container = containerRef.current
    if (!container || isRefreshing) return

    // Only start pull if scrolled to top
    if (container.scrollTop <= 0) {
      startY.current = e.touches[0].clientY
      setIsPulling(true)
    }
  }, [isRefreshing])

  const handleTouchMove = useCallback((e: TouchEvent) => {
    if (!isPulling || isRefreshing) return

    const container = containerRef.current
    if (!container || container.scrollTop > 0) {
      setIsPulling(false)
      setPullDistance(0)
      return
    }

    currentY.current = e.touches[0].clientY
    const distance = Math.max(0, currentY.current - startY.current)

    if (distance > 0) {
      // Apply resistance to make it feel natural
      const resistedDistance = Math.min(maxPull, distance * 0.5)
      setPullDistance(resistedDistance)

      // Prevent default scroll when pulling
      if (resistedDistance > 10) {
        e.preventDefault()
      }
    }
  }, [isPulling, isRefreshing])

  const handleTouchEnd = useCallback(async () => {
    if (!isPulling) return

    setIsPulling(false)

    if (pullDistance >= threshold && onRefresh && !isRefreshing) {
      setIsRefreshing(true)
      setPullDistance(threshold) // Hold at threshold while refreshing

      try {
        await onRefresh()
      } finally {
        setIsRefreshing(false)
        setPullDistance(0)
      }
    } else {
      setPullDistance(0)
    }
  }, [isPulling, pullDistance, threshold, onRefresh, isRefreshing])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    container.addEventListener('touchstart', handleTouchStart, { passive: true })
    container.addEventListener('touchmove', handleTouchMove, { passive: false })
    container.addEventListener('touchend', handleTouchEnd, { passive: true })

    return () => {
      container.removeEventListener('touchstart', handleTouchStart)
      container.removeEventListener('touchmove', handleTouchMove)
      container.removeEventListener('touchend', handleTouchEnd)
    }
  }, [handleTouchStart, handleTouchMove, handleTouchEnd])

  const progress = Math.min(1, pullDistance / threshold)

  return (
    <div ref={containerRef} className={cn("relative overflow-auto flex flex-col", className)} style={style}>
      {/* Pull indicator - fixed position below mobile header */}
      <div
        className={cn(
          "fixed left-0 right-0 flex justify-center transition-all duration-200 pointer-events-none z-20",
          pullDistance > 10 || isRefreshing ? "opacity-100" : "opacity-0"
        )}
        style={{
          top: `${56 + Math.min(pullDistance, maxPull) - 20}px`, // 56px = mobile header height (h-14)
        }}
      >
        <div
          className={cn(
            "flex items-center justify-center w-10 h-10 rounded-full bg-background border border-border shadow-lg",
            isRefreshing && "animate-pulse"
          )}
          style={{
            transform: `rotate(${progress * 360}deg) scale(${0.8 + progress * 0.2})`,
            transition: isPulling ? 'none' : 'all 0.2s ease-out',
          }}
        >
          <Loader2
            className={cn(
              "h-5 w-5 text-accent-brand",
              isRefreshing && "animate-spin"
            )}
          />
        </div>
      </div>

      {/* Content with transform - only apply when pulling to avoid breaking fixed positioning */}
      <div
        className="flex flex-col h-full"
        style={{
          transform: pullDistance > 0 ? `translateY(${pullDistance}px)` : undefined,
          transition: isPulling ? 'none' : 'transform 0.2s ease-out',
        }}
      >
        {children}
      </div>
    </div>
  )
}
