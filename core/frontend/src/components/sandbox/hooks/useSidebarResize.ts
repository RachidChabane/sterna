/**
 * Custom hook for dragging the file-tree sidebar wider/narrower.
 */

import { useEffect, useState } from 'react'

const MIN_SIDEBAR_WIDTH = 180
const MAX_SIDEBAR_WIDTH = 800
const MAX_SIDEBAR_WIDTH_RATIO = 0.5

interface UseSidebarResizeParams {
  rootRef: React.RefObject<HTMLDivElement | null>
}

export function useSidebarResize({ rootRef }: UseSidebarResizeParams) {
  const [sidebarWidth, setSidebarWidth] = useState(256)
  const [isResizing, setIsResizing] = useState(false)

  // Handle sidebar resize
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return

      // Compute width relative to the IDE container, not the viewport
      const containerLeft = rootRef.current?.getBoundingClientRect().left ?? 0
      const newWidth = e.clientX - containerLeft
      const minWidth = MIN_SIDEBAR_WIDTH
      const maxWidth = Math.min(window.innerWidth * MAX_SIDEBAR_WIDTH_RATIO, MAX_SIDEBAR_WIDTH)

      if (newWidth >= minWidth && newWidth <= maxWidth) {
        setSidebarWidth(newWidth)
      }
    }

    const handleMouseUp = () => {
      setIsResizing(false)
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
  }, [isResizing])

  return {
    sidebarWidth,
    isResizing,
    setIsResizing,
  }
}
