/**
 * Custom hook for file tree operations
 */

import { useState, useCallback } from 'react'
import { useToast } from '@/hooks/use-toast'
import { fsAPI } from '@/api/fs'
import { codeSessionApi } from '@/api/codeSession'
import type { FileNode } from '../types'
import { toErrorMessage } from '@/utils/errorMessages'

// Files and directories to hide from the file tree
const HIDDEN_FILES = new Set([
  '.DS_Store',
  '.ds_store',
  'Thumbs.db',
  'thumbs.db',
  'desktop.ini',
  '.git',
  '__pycache__',
  '.pytest_cache',
  '.mypy_cache',
  '.ruff_cache',
  '__MACOSX',
  '.idea',
  '.vscode',
  'node_modules',
  '.next',
  '.nuxt',
  '.cache',
  '.parcel-cache',
  '.turbo',
])

// File prefixes to hide (internal/system files)
const HIDDEN_PREFIXES = [
  '.exec_marker',  // Sandbox execution marker files
]

// File extensions to hide
const HIDDEN_EXTENSIONS = new Set([
  '.pyc',
  '.pyo',
  '.swp',
  '.swo',
  '.swn',
])

// Filter out system/hidden files from the file tree
const filterHiddenFiles = (files: FileNode[], showHidden: boolean): FileNode[] => {
  if (showHidden) {
    // Still need to recursively process children even when showing hidden
    return files.map(file => {
      if (file.children) {
        return { ...file, children: filterHiddenFiles(file.children, showHidden) }
      }
      return file
    })
  }

  return files.filter(file => {
    const fileName = file.name

    // Check exact filename matches
    if (HIDDEN_FILES.has(fileName)) {
      return false
    }

    // Check prefix matches (e.g., .exec_marker*)
    if (HIDDEN_PREFIXES.some(prefix => fileName.startsWith(prefix))) {
      return false
    }

    // Check extensions
    const ext = fileName.includes('.') ? fileName.substring(fileName.lastIndexOf('.')) : ''
    if (HIDDEN_EXTENSIONS.has(ext)) {
      return false
    }

    return true
  }).map(file => {
    // Recursively filter children
    if (file.children) {
      return { ...file, children: filterHiddenFiles(file.children, showHidden) }
    }
    return file
  })
}

interface UseFileTreeOptions {
  userId?: string
  conversationId?: string
  chatId?: string
  sessionId?: string  // Code session ID for code sessions mode
  mode?: 'chat' | 'code'  // Operation mode
  workspacePath?: string  // Custom workspace path
}

interface RestoreResult {
  success: boolean
  files_synced: number
  bytes_synced: number
  errors: string[]
  was_restored?: boolean  // True if files were actually restored from storage
}

export function useFileTree({
  userId,
  conversationId,
  chatId,
  sessionId,
  mode = 'chat',
  workspacePath = '/workspace',
}: UseFileTreeOptions) {
  const { toast } = useToast()
  const [fileTree, setFileTree] = useState<FileNode[]>([])
  const [isLoadingTree, setIsLoadingTree] = useState(false)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [showHiddenFiles, setShowHiddenFiles] = useState(false)
  const [isRestoring, setIsRestoring] = useState(false)
  const [hasRestoredWorkspace, setHasRestoredWorkspace] = useState(false)

  // Consistent projectId calculation: for code sessions use sessionId, for chats use chatId/conversationId
  const projectId = mode === 'code' && sessionId ? sessionId : (chatId || conversationId || 'default')
  // Effective workspace path for code sessions vs chat sandboxes
  const effectiveWorkspacePath = workspacePath

  // Helper: collect all open directory paths
  const getOpenDirectoryPaths = useCallback((nodes: FileNode[]): Set<string> => {
    const openPaths = new Set<string>()
    const traverse = (nodes: FileNode[]) => {
      nodes.forEach(node => {
        if (node.type === 'directory' && node.isOpen) {
          openPaths.add(node.path)
          if (node.children) {
            traverse(node.children)
          }
        }
      })
    }
    traverse(nodes)
    return openPaths
  }, [])

  // Helper: restore open state to directories
  const restoreOpenState = useCallback((nodes: FileNode[], openPaths: Set<string>): FileNode[] => {
    return nodes.map(node => {
      if (node.type === 'directory') {
        const isOpen = openPaths.has(node.path)
        return {
          ...node,
          isOpen,
          children: node.children ? restoreOpenState(node.children, openPaths) : node.children
        }
      }
      return node
    })
  }, [])

  // Helper: find node by path
  const findNodeByPath = useCallback((nodes: FileNode[], targetPath: string): FileNode | null => {
    for (const node of nodes) {
      if (node.path === targetPath) return node
      if (node.children) {
        const found = findNodeByPath(node.children, targetPath)
        if (found) return found
      }
    }
    return null
  }, [])

  // Load directory contents
  const loadDirectoryContents = useCallback(async (path: string): Promise<FileNode[] | null> => {
    if (!userId) return null

    try {
      const result = await fsAPI.listFiles({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        project_id: projectId,
        sync_mode: true,
        path,
      })

      if (result.success && result.files) {
        return filterHiddenFiles(result.files, showHiddenFiles)
      }
    } catch (error) {
      console.error('Failed to load directory contents:', error)
      toast({
        title: 'Error',
        description: `Failed to load directory: ${toErrorMessage(error)}`,
        variant: 'destructive',
      })
    }
    return null
  }, [userId, projectId, toast, showHiddenFiles])

  // Load children for open directories
  const loadChildrenForOpenDirectories = useCallback(async (tree: FileNode[], openPaths: Set<string>) => {
    const loadChildren = async (nodes: FileNode[]): Promise<FileNode[]> => {
      const updatedNodes = await Promise.all(
        nodes.map(async (node) => {
          if (node.type === 'directory' && node.isOpen && openPaths.has(node.path)) {
            if (!node.children || node.children.length === 0) {
              const children = await loadDirectoryContents(node.path)
              if (children) {
                const childrenWithLoaded = await loadChildren(children)
                return { ...node, children: childrenWithLoaded }
              }
            } else {
              const childrenWithLoaded = await loadChildren(node.children)
              return { ...node, children: childrenWithLoaded }
            }
          }
          return node
        })
      )
      return updatedNodes
    }

    const updatedTree = await loadChildren(tree)
    setFileTree(updatedTree)
  }, [loadDirectoryContents])

  // Restore workspace files from persistent storage (PostgreSQL + R2)
  // This should be called once when the IDE opens to restore previously saved files
  const restoreWorkspace = useCallback(async (): Promise<RestoreResult | null> => {
    if (!userId || !projectId || projectId === 'default') {
      
      return null
    }

    // Only restore once per session
    if (hasRestoredWorkspace) {
      
      return null
    }

    setIsRestoring(true)
    try {
      
      const result = await fsAPI.restoreWorkspace({
        user_id: userId,
        chat_id: projectId,
      })

      setHasRestoredWorkspace(true)

      if (result.success) {
        // Only show notification if files were ACTUALLY restored from storage
        // (was_restored=false means files were already present in container)
        if (result.was_restored !== false && result.files_synced > 0) {
          
          toast({
            title: 'Workspace restored',
            description: `Restored ${result.files_synced} file${result.files_synced > 1 ? 's' : ''} from storage`,
          })
        } else if (result.was_restored === false) {
          
        } else {
          
        }
      } else if (result.errors?.length > 0) {
        console.warn('[useFileTree] Workspace restore had errors:', result.errors)
      }

      return result
    } catch (error) {
      console.error('[useFileTree] Failed to restore workspace:', error)
      // Don't show error toast - workspace might not exist yet, which is fine
      setHasRestoredWorkspace(true)
      return null
    } finally {
      setIsRestoring(false)
    }
  }, [userId, projectId, hasRestoredWorkspace, toast])

  // Load file tree
  const loadFileTree = useCallback(async (preserveOpenState: boolean = true, additionalOpenPaths?: string[]) => {
    if (!userId) return

    const openPaths = preserveOpenState ? getOpenDirectoryPaths(fileTree) : new Set<string>()

    if (additionalOpenPaths) {
      additionalOpenPaths.forEach(path => openPaths.add(path))
    }

    setIsLoadingTree(true)
    try {
      const result = await fsAPI.listFiles({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        project_id: projectId,
        sync_mode: true,
        path: effectiveWorkspacePath,
      })

      if (result.success && result.files) {
        const filteredFiles = filterHiddenFiles(result.files, showHiddenFiles)
        const restoredTree = openPaths.size > 0
          ? restoreOpenState(filteredFiles, openPaths)
          : filteredFiles
        setFileTree(restoredTree)

        if (openPaths.size > 0) {
          await loadChildrenForOpenDirectories(restoredTree, openPaths)
        }
      } else {
        toast({
          title: 'Failed to load files',
          description: result.error || 'Unknown error',
          variant: 'destructive',
        })
      }
    } catch (error) {
      console.error('Failed to load file tree:', error)
      toast({
        title: 'Error',
        description: toErrorMessage(error) || 'Failed to load files',
        variant: 'destructive',
      })
    } finally {
      setIsLoadingTree(false)
    }
  }, [userId, projectId, fileTree, toast, getOpenDirectoryPaths, restoreOpenState, loadChildrenForOpenDirectories, showHiddenFiles, effectiveWorkspacePath])

  // Toggle directory
  const toggleDirectory = useCallback(async (path: string) => {
    const toggleNode = (nodes: FileNode[]): FileNode[] => {
      return nodes.map(node => {
        if (node.path === path && node.type === 'directory') {
          return { ...node, isOpen: !node.isOpen }
        }
        if (node.children) {
          return { ...node, children: toggleNode(node.children) }
        }
        return node
      })
    }

    const updatedTree = toggleNode(fileTree)
    setFileTree(updatedTree)

    const node = findNodeByPath(updatedTree, path)

    if (node && node.isOpen && (!node.children || node.children.length === 0)) {
      const children = await loadDirectoryContents(path)
      if (children) {
        const addChildren = (nodes: FileNode[]): FileNode[] => {
          return nodes.map(n => {
            if (n.path === path) {
              return { ...n, children }
            }
            if (n.children) {
              return { ...n, children: addChildren(n.children) }
            }
            return n
          })
        }
        setFileTree(addChildren(updatedTree))
      }
    }
  }, [fileTree, findNodeByPath, loadDirectoryContents])

  // Get parent path for new items
  const getParentPathForNewItem = useCallback((): string => {
    if (!selectedPath || selectedPath === effectiveWorkspacePath) return effectiveWorkspacePath

    const selectedNode = findNodeByPath(fileTree, selectedPath)
    if (!selectedNode) return effectiveWorkspacePath

    if (selectedNode.type === 'directory') {
      return selectedPath
    }

    const parentPath = selectedPath.substring(0, selectedPath.lastIndexOf('/'))
    return parentPath || effectiveWorkspacePath
  }, [selectedPath, fileTree, findNodeByPath, effectiveWorkspacePath])

  // Initialize workspace: ensure repo, restore files, then load file tree
  // This is the main function to call when opening the IDE
  const initializeWorkspace = useCallback(async () => {
    // Step 0: Ensure git repo exists in sandbox (re-clone if container recycled)
    // This handles the case where tmpfs was wiped and only versioned files exist
    if (conversationId) {
      try {
        const result = await codeSessionApi.ensureRepo(conversationId)
        if (result.data?.action === 'restored') {
          toast({
            title: 'Workspace restored',
            description: `Repository re-cloned and git state reconciled${result.data.branch ? ` (branch: ${result.data.branch})` : ''}`,
          })
        }
      } catch (error) {
        // Non-fatal: workspace may not have a cloned repo
        console.warn('[useFileTree] ensure-repo check failed (non-fatal):', error)
      }
    }
    // Step 1: Restore versioned files from persistent storage
    await restoreWorkspace()
    // Step 2: Load the file tree to show the files
    await loadFileTree(false)
  }, [conversationId, restoreWorkspace, loadFileTree, toast])

  // Save workspace files to persistent storage (PostgreSQL + R2)
  // This should be called when closing IDE to persist files
  const saveWorkspace = useCallback(async (): Promise<RestoreResult | null> => {
    if (!userId || !projectId || projectId === 'default') {
      
      return null
    }

    try {
      
      const result = await fsAPI.saveWorkspace({
        user_id: userId,
        chat_id: projectId,
      })

      if (result.success) {
        if (result.files_synced > 0) {
          
        } else {
          
        }
      } else if (result.errors?.length > 0) {
        console.warn('[useFileTree] Workspace save had errors:', result.errors)
      }

      return result
    } catch (error) {
      console.error('[useFileTree] Failed to save workspace:', error)
      return null
    }
  }, [userId, projectId])

  return {
    fileTree,
    setFileTree,
    isLoadingTree,
    isRestoring,
    hasRestoredWorkspace,
    selectedPath,
    setSelectedPath,
    showHiddenFiles,
    setShowHiddenFiles,
    loadFileTree,
    initializeWorkspace,
    restoreWorkspace,
    saveWorkspace,
    toggleDirectory,
    findNodeByPath,
    getParentPathForNewItem,
    loadDirectoryContents,
    restoreOpenState,
    loadChildrenForOpenDirectories,
    workspacePath: effectiveWorkspacePath,  // Expose the workspace path
    mode,  // Expose mode for conditional logic
  }
}
