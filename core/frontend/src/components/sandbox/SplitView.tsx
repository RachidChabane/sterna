/**
 * SplitView Component
 *
 * Provides a resizable split view container for displaying code editor and preview side by side.
 * Can also display only code or only preview based on viewMode.
 *
 * IMPORTANT: Both views remain mounted at all times to preserve editor state (like Monaco models).
 * We hide views with CSS instead of unmounting them.
 */

import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'

export type ViewMode = 'code' | 'preview' | 'split'

interface SplitViewProps {
  viewMode: ViewMode
  codeView: React.ReactNode
  previewView: React.ReactNode
  className?: string
  onResizeEnd?: () => void
}

export function SplitView({ viewMode, codeView, previewView, className, onResizeEnd }: SplitViewProps) {
  const [splitPosition, setSplitPosition] = useState(50) // percentage
  const [isResizing, setIsResizing] = useState(false)

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return

      const container = document.getElementById('split-view-container')
      if (!container) return

      const containerRect = container.getBoundingClientRect()
      const newPosition = ((e.clientX - containerRect.left) / containerRect.width) * 100

      // Limit between 20% and 80%
      const clampedPosition = Math.min(Math.max(newPosition, 20), 80)
      setSplitPosition(clampedPosition)
    }

    const handleMouseUp = () => {
      setIsResizing(false)
      // Notify parent that resize is complete (for editor layout recalculation)
      if (onResizeEnd) {
        setTimeout(onResizeEnd, 0)
      }
    }

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing, onResizeEnd])

  // We always render both views but hide them with CSS to preserve state
  return (
    <div id="split-view-container" className={cn('w-full h-full flex', className)}>
      {/* Code side */}
      <div
        style={{
          width: viewMode === 'preview' ? '0%' : viewMode === 'split' ? `${splitPosition}%` : '100%',
        }}
        className={cn(
          'h-full overflow-hidden transition-all duration-200',
          viewMode === 'preview' && 'hidden'
        )}
      >
        {codeView}
      </div>

      {/* Resizer - only visible in split mode */}
      {viewMode === 'split' && (
        <div
          className={cn(
            'w-1 h-full bg-border hover:bg-accent-brand/50 cursor-col-resize transition-colors flex-shrink-0',
            isResizing && 'bg-accent-brand'
          )}
          onMouseDown={() => setIsResizing(true)}
        />
      )}

      {/* Preview side */}
      <div
        style={{
          width: viewMode === 'code' ? '0%' : viewMode === 'split' ? `${100 - splitPosition}%` : '100%',
        }}
        className={cn(
          'h-full overflow-hidden transition-all duration-200',
          viewMode === 'code' && 'hidden'
        )}
      >
        {previewView}
      </div>
    </div>
  )
}
