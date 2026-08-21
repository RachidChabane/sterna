/**
 * AutoResizeTextarea Component
 *
 * A simple textarea that automatically resizes based on content.
 * No markdown, no highlighting, just clean auto-resize behavior.
 */

import { forwardRef, useLayoutEffect, useRef } from 'react'
import { cn } from '@/lib/utils'

interface AutoResizeTextareaProps extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange'> {
  value: string
  onChange?: (value: string) => void
  minHeight?: number
  maxHeight?: number
  onLineCountChange?: (lineCount: number) => void
}

export const AutoResizeTextarea = forwardRef<HTMLTextAreaElement, AutoResizeTextareaProps>(
  ({ value, onChange, className, minHeight = 48, maxHeight = 200, onLineCountChange, ...props }, forwardedRef) => {
    const textareaRef = useRef<HTMLTextAreaElement>(null)

    // Combine refs
    useLayoutEffect(() => {
      if (typeof forwardedRef === 'function') {
        forwardedRef(textareaRef.current)
      } else if (forwardedRef) {
        forwardedRef.current = textareaRef.current
      }
    }, [forwardedRef])

    // Auto-resize using useLayoutEffect to avoid flicker
    useLayoutEffect(() => {
      const textarea = textareaRef.current
      if (!textarea) return

      // Save the current height
      const currentHeight = textarea.style.height || `${minHeight}px`

      // Disable transition temporarily for the calculation
      textarea.style.transition = 'none'

      // Reset height to auto to get the real scroll height
      textarea.style.height = 'auto'

      // Get the scroll height
      const scrollHeight = textarea.scrollHeight

      // Apply constraints
      const newHeight = Math.min(Math.max(scrollHeight, minHeight), maxHeight)

      // Calculate approximate line count based on height
      if (onLineCountChange) {
        const lineHeight = 24 // Approximate line height in pixels
        const estimatedLines = Math.ceil(scrollHeight / lineHeight)
        onLineCountChange(estimatedLines)
      }

      // Restore the current height (before animation)
      textarea.style.height = currentHeight

      // Force a reflow - critical for the browser to register the current state
      void textarea.offsetHeight

      // Re-enable transition by removing the inline style (CSS class takes over)
      textarea.style.transition = ''

      // Use requestAnimationFrame to apply the new height in the NEXT frame
      // This ensures the browser can interpolate between currentHeight and newHeight
      requestAnimationFrame(() => {
        if (textarea) {
          textarea.style.height = `${newHeight}px`
        }
      })
    }, [value, minHeight, maxHeight, onLineCountChange])

    // Handle change
    const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onChange?.(e.target.value)
    }

    return (
      <>
        {/* Hide scrollbar with CSS */}
        <style>{`
          .auto-resize-textarea {
            scrollbar-width: none; /* Firefox */
            -ms-overflow-style: none; /* IE/Edge */

            /* Smooth height animation - faster and snappier */
            transition: height 0.25s cubic-bezier(0.4, 0.0, 0.2, 1);

            /* Performance optimizations for smooth typing */
            will-change: height;
            contain: layout style;
            transform: translateZ(0); /* Force GPU acceleration */
            backface-visibility: hidden; /* Prevent flickering */

            /* Smooth text rendering - optimized for typing */
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            text-rendering: optimizeSpeed; /* Changed from optimizeLegibility for typing performance */

            /* Prevent any inherited transitions from affecting text */
            caret-color: currentColor;

            /* Hardware acceleration for smoother cursor movement */
            -webkit-transform: translateZ(0);
            -webkit-perspective: 1000;
            -webkit-backface-visibility: hidden;
          }

          .auto-resize-textarea::-webkit-scrollbar {
            display: none; /* Chrome/Safari */
          }
        `}</style>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          className={cn(
            "w-full resize-none overflow-y-auto auto-resize-textarea",
            "focus:outline-none",
            className
          )}
          style={{
            minHeight: `${minHeight}px`,
            maxHeight: `${maxHeight}px`,
          }}
          {...props}
        />
      </>
    )
  }
)

AutoResizeTextarea.displayName = 'AutoResizeTextarea'
