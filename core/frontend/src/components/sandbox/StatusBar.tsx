/**
 * StatusBar - IDE status bar showing file information
 */

import { memo } from 'react'
import { cn } from '@/lib/utils'

interface StatusBarProps {
  language?: string
  lineCount?: number
  cursorLine?: number
  cursorColumn?: number
  selectedText?: number
  encoding?: string
  indentSize?: number
  indentType?: 'spaces' | 'tabs'
  className?: string
}

export const StatusBar = memo(function StatusBar({
  language = 'Plain Text',
  lineCount = 0,
  cursorLine = 1,
  cursorColumn = 1,
  selectedText = 0,
  encoding = 'UTF-8',
  indentSize = 2,
  indentType = 'spaces',
  className,
}: StatusBarProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between px-3 py-1 text-xs text-muted-foreground bg-muted/30 border-t border-border/50 select-none",
        className
      )}
    >
      {/* Left side */}
      <div className="flex items-center gap-4">
        {/* Cursor position */}
        <span className="tabular-nums">
          Ln {cursorLine}, Col {cursorColumn}
        </span>

        {/* Selection info */}
        {selectedText > 0 && (
          <span className="text-accent-brand tabular-nums">
            {selectedText} selected
          </span>
        )}
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Line count */}
        <span className="tabular-nums">{lineCount} lines</span>

        {/* Indentation */}
        <span>
          {indentType === 'spaces' ? `Spaces: ${indentSize}` : `Tab Size: ${indentSize}`}
        </span>

        {/* Encoding */}
        <span>{encoding}</span>

        {/* Language */}
        <span className="font-medium text-foreground/80">{language}</span>
      </div>
    </div>
  )
})
