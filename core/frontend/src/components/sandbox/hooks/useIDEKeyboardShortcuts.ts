/**
 * Custom hook for the IDE's global keyboard shortcuts: quick file
 * search, global search, in-file search, save, and run.
 */

import { useEffect } from 'react'
import type { useMonacoEditor } from './useMonacoEditor'

interface UseIDEKeyboardShortcutsParams {
  isMac: boolean
  activeFilePath: string | null
  activeFile: unknown
  isExecuting: boolean
  editorHook: ReturnType<typeof useMonacoEditor>
  saveFile: (path: string) => void
  handleRunFile: () => void
  setQuickSearchOpen: (open: boolean) => void
  setGlobalSearchOpen: (open: boolean) => void
}

export function useIDEKeyboardShortcuts({
  isMac,
  activeFilePath,
  activeFile,
  isExecuting,
  editorHook,
  saveFile,
  handleRunFile,
  setQuickSearchOpen,
  setGlobalSearchOpen,
}: UseIDEKeyboardShortcutsParams) {
  // Keyboard shortcuts (Ctrl+P / Cmd+P for quick search, Cmd+Enter to run)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isMod = isMac ? e.metaKey : e.ctrlKey

      // Cmd/Ctrl + P - Quick file search
      if (isMod && e.key === 'p') {
        e.preventDefault()
        setQuickSearchOpen(true)
      }

      // Cmd/Ctrl + Shift + F - Global search in all files
      if (isMod && e.shiftKey && e.key.toLowerCase() === 'f') {
        e.preventDefault()
        setGlobalSearchOpen(true)
      }

      // Cmd/Ctrl + F - Search in current file (trigger Monaco's built-in search)
      if (isMod && !e.shiftKey && e.key.toLowerCase() === 'f') {
        e.preventDefault()
        const editor = editorHook.editorRef?.current
        if (editor) {
          // Trigger Monaco's find action
          editor.trigger('keyboard', 'actions.find', null)
        }
      }

      // Cmd/Ctrl + S - Save file
      if (isMod && e.key === 's') {
        e.preventDefault()
        if (activeFilePath) {
          saveFile(activeFilePath)
        }
      }

      // Cmd/Ctrl + Enter - Run file
      if (isMod && e.key === 'Enter') {
        e.preventDefault()
        if (activeFile && !isExecuting) {
          handleRunFile()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isMac, activeFilePath, activeFile, isExecuting, editorHook.editorRef])
}
