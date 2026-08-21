/**
 * KeyboardShortcuts - Display common keyboard shortcuts
 */

import { memo } from 'react'
import { cn } from '@/lib/utils'

interface Shortcut {
  keys: string[]
  label: string
  action?: () => void
}

interface KeyboardShortcutsProps {
  shortcuts: Shortcut[]
  className?: string
}

export const KeyboardShortcuts = memo(function KeyboardShortcuts({
  shortcuts,
  className,
}: KeyboardShortcutsProps) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      {shortcuts.map((shortcut, index) => (
        <button
          key={index}
          onClick={shortcut.action}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <span className="flex items-center gap-0.5">
            {shortcut.keys.map((key, keyIndex) => (
              <kbd
                key={keyIndex}
                className="px-1.5 py-0.5 rounded bg-muted border border-border/50 text-[10px] font-medium font-mono"
              >
                {key}
              </kbd>
            ))}
          </span>
          <span>{shortcut.label}</span>
        </button>
      ))}
    </div>
  )
})

// Common IDE shortcuts
export const IDE_SHORTCUTS = {
  save: { keys: ['⌘', 'S'], label: 'Save' },
  saveAll: { keys: ['⌘', '⇧', 'S'], label: 'Save All' },
  find: { keys: ['⌘', 'F'], label: 'Find' },
  findFiles: { keys: ['⌘', 'P'], label: 'Find Files' },
  run: { keys: ['⌘', 'Enter'], label: 'Run' },
  closeTab: { keys: ['⌘', 'W'], label: 'Close' },
  newFile: { keys: ['⌘', 'N'], label: 'New' },
}

// Platform-aware shortcuts
export function getPlatformShortcuts(isMac: boolean) {
  const mod = isMac ? '⌘' : 'Ctrl'
  const shift = isMac ? '⇧' : 'Shift'

  return {
    save: { keys: [mod, 'S'], label: 'Save' },
    findFiles: { keys: [mod, 'P'], label: 'Go to File' },
    find: { keys: [mod, 'F'], label: 'Find' },
    findInFiles: { keys: [mod, shift, 'F'], label: 'Find in Files' },
    run: { keys: [mod, 'Enter'], label: 'Run' },
  }
}
