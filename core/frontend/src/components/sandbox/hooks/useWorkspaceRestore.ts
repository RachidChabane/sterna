/**
 * Custom hook for the IDE's workspace persistence lifecycle: restoring
 * files from storage on mount, saving them back on unmount, and
 * re-opening the tabs/selection the user left open last time.
 */

import { useEffect, useRef } from 'react'
import { fsAPI } from '@/api/fs'
import type { OpenFile } from '../types'
import type { useFileTree } from './useFileTree'
import type { useIDEState } from './useIDEState'

interface UseWorkspaceRestoreParams {
  userId?: string
  projectId: string
  fileTreeHook: ReturnType<typeof useFileTree>
  ideState: ReturnType<typeof useIDEState>
  setOpenFiles: React.Dispatch<React.SetStateAction<OpenFile[]>>
  setActiveFilePath: React.Dispatch<React.SetStateAction<string | null>>
}

export function useWorkspaceRestore({
  userId,
  projectId,
  fileTreeHook,
  ideState,
  setOpenFiles,
  setActiveFilePath,
}: UseWorkspaceRestoreParams) {
  const hasRestoredStateRef = useRef(false)

  // Initialize workspace on mount: restore from storage then load file tree
  useEffect(() => {
    if (userId) {
      // Use initializeWorkspace to restore files from PostgreSQL/R2 storage first
      fileTreeHook.initializeWorkspace()
    }
  }, [userId, projectId])

  // Save workspace to persistent storage when IDE closes/unmounts
  useEffect(() => {
    return () => {
      // Save workspace to PostgreSQL/R2 storage on unmount
      if (userId && projectId && projectId !== 'default') {

        fileTreeHook.saveWorkspace()
      }
    }
  }, [userId, projectId])

  // Restore IDE state after file tree is loaded
  useEffect(() => {
    const restoreState = async () => {
      // Only restore once when tree is loaded
      if (hasRestoredStateRef.current || fileTreeHook.fileTree.length === 0 || !userId) {
        return
      }

      const savedState = ideState.loadState()
      if (!savedState) {
        hasRestoredStateRef.current = true
        return
      }

      try {
        // Restore open directories
        if (savedState.openDirectoryPaths.length > 0) {
          const openPaths = new Set(savedState.openDirectoryPaths)
          const treeWithOpenState = fileTreeHook.restoreOpenState(fileTreeHook.fileTree, openPaths)
          fileTreeHook.setFileTree(treeWithOpenState)

          // Load children for open directories
          await fileTreeHook.loadChildrenForOpenDirectories(treeWithOpenState, openPaths)
        }

        // Restore open files
        if (savedState.openFiles.length > 0) {
          // Reload file contents from backend to ensure they're up to date
          const restoredFiles = await Promise.all(
            savedState.openFiles.map(async (file) => {
              try {
                const result = await fsAPI.readFile({
                  user_id: userId,
                  conversation_id: projectId,
                  chat_id: projectId,
                  path: file.path,
                })

                if (result.success && result.content !== undefined) {
                  return {
                    ...file,
                    content: result.content,
                    isDirty: false,
                  }
                }
              } catch (error) {
                console.error(`Failed to restore file ${file.path}:`, error)
              }
              return null
            })
          )

          const validFiles = restoredFiles.filter((f): f is OpenFile => f !== null)
          setOpenFiles(validFiles)

          // Restore active file
          if (savedState.activeFilePath && validFiles.some(f => f.path === savedState.activeFilePath)) {
            setActiveFilePath(savedState.activeFilePath)
          } else if (validFiles.length > 0) {
            setActiveFilePath(validFiles[0].path)
          }
        }

        // Restore selected path
        if (savedState.selectedPath) {
          fileTreeHook.setSelectedPath(savedState.selectedPath)
        }

        hasRestoredStateRef.current = true
      } catch (error) {
        console.error('Failed to restore IDE state:', error)
        hasRestoredStateRef.current = true
      }
    }

    restoreState()
  }, [fileTreeHook.fileTree.length, userId, projectId])
}
