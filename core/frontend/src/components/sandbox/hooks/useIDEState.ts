/**
 * useIDEState - Persists and restores IDE state to/from localStorage
 *
 * NOTE: We only save file metadata (path, name, language) without content
 * to avoid QuotaExceededError with large/binary files. File contents will
 * be reloaded from the backend when restoring.
 */

import { useEffect, useRef } from 'react'
import type { OpenFile } from '../types'

// Lightweight file metadata for storage (no content)
interface FileMetadata {
  path: string
  name: string
  language: string
}

interface IDEState {
  openFiles: FileMetadata[]  // Store only metadata, not full content
  activeFilePath: string | null
  selectedPath: string | null
  openDirectoryPaths: string[]
}

// Full state with file contents (used internally)
interface FullIDEState {
  openFiles: OpenFile[]
  activeFilePath: string | null
  selectedPath: string | null
  openDirectoryPaths: string[]
}

interface UseIDEStateProps {
  projectId: string
  openFiles: OpenFile[]
  activeFilePath: string | null
  selectedPath: string | null
  fileTree: any[]
}

interface UseIDEStateReturn {
  saveState: () => void
  loadState: () => IDEState | null
}

const STORAGE_KEY_PREFIX = 'ide-state-'
const DEBOUNCE_DELAY = 500 // Save state 500ms after last change

/**
 * Recursively collects all open directory paths from the file tree
 */
function collectOpenDirectoryPaths(nodes: any[]): string[] {
  const openPaths: string[] = []

  const traverse = (nodes: any[]) => {
    nodes.forEach(node => {
      if (node.type === 'directory' && node.isOpen) {
        openPaths.push(node.path)
        if (node.children) {
          traverse(node.children)
        }
      }
    })
  }

  traverse(nodes)
  return openPaths
}

export function useIDEState({
  projectId,
  openFiles,
  activeFilePath,
  selectedPath,
  fileTree,
}: UseIDEStateProps): UseIDEStateReturn {
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const storageKey = `${STORAGE_KEY_PREFIX}${projectId}`

  /**
   * Save current IDE state to localStorage
   * Only saves metadata (path, name, language) - not file content!
   */
  const saveState = () => {
    try {
      const openDirectoryPaths = collectOpenDirectoryPaths(fileTree)

      const state: IDEState = {
        // Save only metadata - exclude content to avoid QuotaExceededError
        openFiles: openFiles.map(file => ({
          path: file.path,
          name: file.name,
          language: file.language,
        })),
        activeFilePath,
        selectedPath,
        openDirectoryPaths,
      }

      localStorage.setItem(storageKey, JSON.stringify(state))
    } catch (error) {
      // Handle QuotaExceededError gracefully
      if (error instanceof DOMException && error.name === 'QuotaExceededError') {
        console.warn('localStorage quota exceeded - IDE state not saved. Consider closing some files.')

        // Try to save a minimal state (only active file + selected path)
        try {
          const minimalState: IDEState = {
            openFiles: activeFilePath
              ? [openFiles.find(f => f.path === activeFilePath)].filter(Boolean).map(file => ({
                  path: file!.path,
                  name: file!.name,
                  language: file!.language,
                }))
              : [],
            activeFilePath,
            selectedPath,
            openDirectoryPaths: [],
          }
          localStorage.setItem(storageKey, JSON.stringify(minimalState))
        } catch {
          // If even minimal state fails, clear the storage for this project
          try {
            localStorage.removeItem(storageKey)
          } catch {
            // Ignore - localStorage might be completely blocked
          }
        }
      } else {
        console.error('Failed to save IDE state:', error)
      }
    }
  }

  /**
   * Load IDE state from localStorage
   */
  const loadState = (): IDEState | null => {
    try {
      const stored = localStorage.getItem(storageKey)
      if (!stored) return null

      const state: IDEState = JSON.parse(stored)
      return state
    } catch (error) {
      console.error('Failed to load IDE state:', error)
      return null
    }
  }

  /**
   * Auto-save state when dependencies change (debounced)
   */
  useEffect(() => {
    // Clear existing timeout
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current)
    }

    // Schedule save
    saveTimeoutRef.current = setTimeout(() => {
      saveState()
    }, DEBOUNCE_DELAY)

    // Cleanup
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
    }
  }, [openFiles, activeFilePath, selectedPath, fileTree])

  return {
    saveState,
    loadState,
  }
}
