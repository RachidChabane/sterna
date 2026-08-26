/**
 * FullIDE Component - Refactored
 *
 * Complete IDE with file tree, multi-tab editor, and code execution.
 * Isolated per user × chat with persistent file system in sandbox container.
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import { FileCode, Play, StopCircle, Upload, X, FolderOpen, Search, Terminal, ChevronDown, ChevronUp, Globe, Loader2 } from 'lucide-react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { StatusBar } from './StatusBar'
import { Breadcrumbs } from './Breadcrumbs'
import { QuickFileSearch } from './QuickFileSearch'
import { GlobalSearch } from './GlobalSearch'
import { KeyboardShortcuts, getPlatformShortcuts } from './KeyboardShortcuts'
import { BottomPanel } from './BottomPanel'
import { cn } from '@/lib/utils'
import { useToast } from '@/hooks/use-toast'
import axios from 'axios'
import { toErrorMessage } from '@/utils/errorMessages'
import { getAccessToken, orchestratorClient } from '@/api/client'
import { fsAPI } from '@/api/fs'
import { getPreviewUrl, fetchPreviewToken } from '@/api/sandbox'
import { Button } from '@/components/ui/button'
import { useSettingsStore } from '@/store/settingsStore'
import { getMonacoThemeData } from '@/constants/codeThemes'

// Import types and utilities
import type {
  FileNode,
  OpenFile,
  ExecutionResult,
  NewItemDialogState,
  DeleteDialogState,
  RenameDialogState,
  CloseFileDialogState,
} from './types'
import { getLanguageFromPath, getExecutableLanguage, supportsPreview, isBinaryPreviewable } from './types'

// Import custom hooks
import { useFileTree, useMonacoEditor, useIDEState } from './hooks'

// Import components
import { EditorTabs } from './EditorTabs'
import { FileTreePanel } from './FileTreePanel'
import { FileDialogs } from './FileDialogs'
import { FileDetailsModal } from './FileDetailsModal'
import { MessageViewModal } from './MessageViewModal'
import { SplitView, type ViewMode } from './SplitView'
import { FilePreview } from './FilePreview'
import { ResourceBars } from './ResourceBars'
import type { Message } from '@/components/models/types'

// File upload size limit (300MB)
const MAX_FILE_SIZE_BYTES = 300 * 1024 * 1024
const MAX_FILE_SIZE_LABEL = '300MB'

export interface FullIDEProps {
  userId?: string
  chatId?: string
  conversationId?: string
  sessionId?: string  // Code session ID for code sessions mode
  className?: string
  messages?: Message[]  // Optional: messages from the chat to enable message navigation
  mode?: 'chat' | 'code'  // Operation mode: 'chat' for sandbox, 'code' for code sessions
  readOnly?: boolean  // For viewing diffs without editing
  workspacePath?: string  // Override workspace path (e.g., for code sessions)
  onFileChange?: (path: string, content: string) => void  // Callback when file changes
  // Git integration props (for code sessions)
  gitBranches?: Array<{ name: string; protected?: boolean }>
  gitCurrentBranch?: string
  gitIsLoadingBranches?: boolean
  gitModifiedFiles?: string[]
  onGitBranchSelect?: (branch: string) => void
  onGitCreateBranch?: (branchName: string, fromBranch: string) => Promise<void>
}

export function FullIDE({
  userId,
  chatId,
  conversationId,
  sessionId,
  className,
  messages = [],
  mode = 'chat',
  readOnly = false,
  workspacePath,
  onFileChange,
  // Git props
  gitBranches,
  gitCurrentBranch,
  gitIsLoadingBranches,
  gitModifiedFiles,
  onGitBranchSelect,
  onGitCreateBranch,
}: FullIDEProps) {
  const { toast } = useToast()
  // For code sessions, use sessionId as projectId; for chats, use chatId or conversationId
  const projectId = mode === 'code' && sessionId ? sessionId : (chatId || conversationId || 'default')
  // Workspace path - the orchestrator adds the chat workspace prefix automatically
  const effectiveWorkspacePath = workspacePath || '/workspace'

  // Custom hooks
  const fileTreeHook = useFileTree({
    userId,
    conversationId,
    chatId,
    sessionId,
    mode,
    workspacePath: effectiveWorkspacePath,
  })
  const editorHook = useMonacoEditor()

  // Execution state
  const [isExecuting, setIsExecuting] = useState(false)
  const [result, setResult] = useState<ExecutionResult | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const executionIdRef = useRef<string | null>(null)

  // File management
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([])
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null)
  const openFilesRef = useRef<OpenFile[]>([])
  const userIdRef = useRef<string | undefined>(userId)
  const projectIdRef = useRef<string>(projectId)
  const hasRestoredStateRef = useRef(false)

  // IDE state persistence
  const ideState = useIDEState({
    projectId,
    openFiles,
    activeFilePath,
    selectedPath: fileTreeHook.selectedPath,
    fileTree: fileTreeHook.fileTree,
  })

  // UI state
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(256)
  const [isResizing, setIsResizing] = useState(false)
  const [monacoReady, setMonacoReady] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('code')
  const [isMobile, setIsMobile] = useState(false)
  const [mobileExplorerOpen, setMobileExplorerOpen] = useState(false)
  const [quickSearchOpen, setQuickSearchOpen] = useState(false)
  const [globalSearchOpen, setGlobalSearchOpen] = useState(false)
  const [recentFilePaths, setRecentFilePaths] = useState<string[]>([])
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 })
  const [selectedTextLength, setSelectedTextLength] = useState(0)
  const [bottomPanelOpen, setBottomPanelOpen] = useState(false)
  const [bottomPanelHeight, setBottomPanelHeight] = useState(250)
  const [bottomPanelTab, setBottomPanelTab] = useState<'output' | 'terminal' | 'commits' | 'changes' | 'ports'>('output')
  const [previewPort, setPreviewPort] = useState<number | null>(null)
  const [previewToken, setPreviewToken] = useState<string | null>(null)
  const [previewTokenLoading, setPreviewTokenLoading] = useState(false)
  const [containerHeight, setContainerHeight] = useState(0)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const themeDefinedRef = useRef<Set<string>>(new Set())
  const codeThemeId = useSettingsStore((s) => s.codeTheme)

  // Apply code theme from settings when it changes
  useEffect(() => {
    const monaco = editorHook.monacoRef.current
    if (!monaco) return
    const themeName = `custom-${codeThemeId}`
    if (!themeDefinedRef.current.has(themeName)) {
      themeDefinedRef.current.add(themeName)
      monaco.editor.defineTheme(themeName, getMonacoThemeData(codeThemeId))
    }
    monaco.editor.setTheme(themeName)
  }, [codeThemeId])

  // Detect mobile via media query
  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 768px)')
    setIsMobile(mediaQuery.matches)

    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  // Track container height for bottom panel max height
  useEffect(() => {
    if (!rootRef.current) return

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height)
      }
    })

    observer.observe(rootRef.current)
    // Set initial height
    setContainerHeight(rootRef.current.clientHeight)

    return () => observer.disconnect()
  }, [])

  // Preview token lifecycle: fetch on port change, auto-refresh before expiry
  useEffect(() => {
    if (!previewPort || !userId) {
      setPreviewToken(null)
      setPreviewTokenLoading(false)
      return
    }

    let cancelled = false
    let refreshTimer: ReturnType<typeof setInterval> | null = null

    const fetchToken = async () => {
      try {
        setPreviewTokenLoading(true)
        const token = await fetchPreviewToken(userId, previewPort)
        if (!cancelled) {
          setPreviewToken(token)
          setPreviewTokenLoading(false)
        }
      } catch (e) {
        if (!cancelled) {
          console.error('Failed to fetch preview token:', e)
          setPreviewTokenLoading(false)
        }
      }
    }

    fetchToken()
    // Refresh token every 4 minutes (before 5-min expiry)
    refreshTimer = setInterval(fetchToken, 240_000)

    return () => {
      cancelled = true
      if (refreshTimer) clearInterval(refreshTimer)
    }
  }, [previewPort, userId])

  // Platform detection for shortcuts
  const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform)
  const platformShortcuts = getPlatformShortcuts(isMac)

  // Keyboard shortcuts are defined after handleRunFile to avoid TDZ issues

  // Track recent files
  const trackRecentFile = useCallback((path: string) => {
    setRecentFilePaths(prev => {
      const filtered = prev.filter(p => p !== path)
      return [path, ...filtered].slice(0, 10)
    })
  }, [])

  // Drag & Drop state
  const [isDraggingFiles, setIsDraggingFiles] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const dragCounterRef = useRef(0)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // Upload progress state
  const [uploadProgress, setUploadProgress] = useState<{
    current: number
    total: number
    currentFileName: string
  } | null>(null)
  const uploadCancelledRef = useRef(false)
  const uploadedRootPathsRef = useRef<Set<string>>(new Set())  // Track root paths for rollback (directories or files)

  // Dialog state
  const [newItemDialog, setNewItemDialog] = useState<NewItemDialogState | null>(null)
  const [newItemName, setNewItemName] = useState('')
  const [deleteDialog, setDeleteDialog] = useState<DeleteDialogState | null>(null)
  const [renameDialog, setRenameDialog] = useState<RenameDialogState | null>(null)
  const [renameName, setRenameName] = useState('')
  const [closeFileDialog, setCloseFileDialog] = useState<CloseFileDialogState | null>(null)
  const [fileDetailsModal, setFileDetailsModal] = useState<{ open: boolean; path: string; name: string } | null>(null)
  const [messageViewModal, setMessageViewModal] = useState<{ open: boolean; messageId: string } | null>(null)

  const activeFile = openFiles.find(f => f.path === activeFilePath)

  // Auto-switch view mode based on file type
  useEffect(() => {
    if (!activeFile) return

    // Binary files (images, PDFs) should auto-open in preview mode
    if (isBinaryPreviewable(activeFile.name)) {
      if (viewMode === 'code') {
        setViewMode('preview')
      }
    }
    // Files that don't support preview should stay in code mode
    else if (!supportsPreview(activeFile.name) && viewMode !== 'code') {
      setViewMode('code')
    }
    // SVG and other text-based files that support preview: allow split view, default to code
  }, [activeFile?.name])

  // Force Monaco layout recalculation when view mode changes
  useEffect(() => {
    // Small delay to ensure the transition animation completes
    const timer = setTimeout(() => {
      editorHook.forceLayout()
    }, 250)

    return () => clearTimeout(timer)
  }, [viewMode, editorHook.forceLayout])

  // Handle message navigation - find message by ID and show in modal
  const handleNavigateToMessage = (messageId: string) => {
    const message = messages.find(m => m.message_id === messageId)

    if (message) {
      setMessageViewModal({ open: true, messageId })
    } else {
      toast({
        title: 'Message not found',
        description: `Could not find message with ID "${messageId}". The message may not be loaded in the current view.`,
        variant: 'destructive',
      })
    }
  }

  // Get the message for the modal
  const selectedMessage = messageViewModal
    ? messages.find(m => m.message_id === messageViewModal.messageId) || null
    : null

  // Sync refs
  useEffect(() => {
    openFilesRef.current = openFiles
  }, [openFiles])

  useEffect(() => {
    userIdRef.current = userId
  }, [userId])

  useEffect(() => {
    projectIdRef.current = projectId
  }, [projectId])

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

  // Switch Monaco model when active file changes
  useEffect(() => {
    if (monacoReady && activeFilePath && activeFile) {
      editorHook.switchToFileModel(activeFilePath, activeFile.content, activeFile.language)
    }
  }, [monacoReady, activeFilePath, activeFile, editorHook.switchToFileModel])

  // Handle sidebar resize
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return

      // Compute width relative to the IDE container, not the viewport
      const containerLeft = rootRef.current?.getBoundingClientRect().left ?? 0
      const newWidth = e.clientX - containerLeft
      const minWidth = 180
      const maxWidth = Math.min(window.innerWidth * 0.5, 800)

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

  // File operations
  const openFile = async (path: string, name: string) => {
    // Track recent files
    trackRecentFile(path)

    // Use ref to avoid stale closure when this callback is passed to child components
    const existing = openFilesRef.current.find(f => f.path === path)
    if (existing) {
      setActiveFilePath(path)
      return
    }

    if (!userId) return

    // Check if file is a non-previewable binary (archives, executables, etc.)
    const isNonPreviewableBinary = (fileName: string): boolean => {
      const lowerName = fileName.toLowerCase()
      // Check for compound extensions like .tar.gz, .tar.bz2
      if (lowerName.endsWith('.tar.gz') || lowerName.endsWith('.tar.bz2') || lowerName.endsWith('.tar.xz')) {
        return true
      }
      const ext = lowerName.split('.').pop() || ''
      return ['zip', 'tar', 'gz', 'rar', '7z', 'bz2', 'xz', 'exe', 'dll', 'so', 'dylib', 'mp4', 'mp3', 'wav', 'avi', 'mov', 'bin', 'dat', 'iso'].includes(ext)
    }

    if (isNonPreviewableBinary(name)) {
      toast({
        title: 'Cannot Preview File',
        description: `${name} is a binary file that cannot be previewed. Use the context menu to download it.`,
        variant: 'default',
      })
      return
    }

    try {
      const result = await fsAPI.readFile({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        sync_mode: true,
        path,
      })

      if (result.success && result.content !== undefined) {
        const newFile: OpenFile = {
          path,
          name,
          content: result.content,
          language: getLanguageFromPath(path),
          isDirty: false,
        }

        setOpenFiles(prev => [...prev, newFile])
        setActiveFilePath(path)
      } else {
        toast({
          title: 'Failed to open file',
          description: result.error || 'Unknown error',
          variant: 'destructive',
        })
      }
    } catch (error) {
      console.error('Failed to open file:', error)
      toast({
        title: 'Error',
        description: toErrorMessage(error) || 'Failed to open file',
        variant: 'destructive',
      })
    }
  }

  const closeFile = (path: string) => {
    // Use ref to avoid stale closure
    const file = openFilesRef.current.find(f => f.path === path)
    if (file?.isDirty) {
      setCloseFileDialog({ open: true, path, name: file.name })
      return
    }

    performCloseFile(path)
  }

  const performCloseFile = (path: string) => {
    editorHook.disposeModel(path)

    // Use ref to avoid stale closure
    const remaining = openFilesRef.current.filter(f => f.path !== path)
    setOpenFiles(remaining)
    if (activeFilePath === path) {
      const newActivePath = remaining.length > 0 ? remaining[0].path : null
      setActiveFilePath(newActivePath)
      fileTreeHook.setSelectedPath(newActivePath)
    }
  }

  const saveFile = async (path: string, contentOverride?: string) => {
    // Use ref to avoid stale closure
    const file = openFilesRef.current.find(f => f.path === path)
    if (!file || !userId) return

    let contentToSave: string
    if (contentOverride === undefined) {
      if (path === activeFilePath) {
        contentToSave = editorHook.getCurrentContent() || file.content
      } else {
        contentToSave = file.content
      }
    } else {
      contentToSave = contentOverride
    }

    editorHook.isSavingRef.current = true

    try {
      const result = await fsAPI.writeFile({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        sync_mode: true,
        path,
        content: contentToSave,
      })

      if (result.success) {
        setOpenFiles(prevFiles => prevFiles.map(f =>
          f.path === path ? { ...f, content: contentToSave, isDirty: false } : f
        ))
      } else {
        toast({
          title: 'Failed to save file',
          description: result.error || 'Unknown error',
          variant: 'destructive',
        })
      }
    } catch (error) {
      console.error('Failed to save file:', error)
      toast({
        title: 'Error',
        description: toErrorMessage(error) || 'Failed to save file',
        variant: 'destructive',
      })
    } finally {
      setTimeout(() => {
        editorHook.isSavingRef.current = false
      }, 100)
    }
  }

  // File tree operations
  const createNewItem = async () => {
    if (!newItemDialog || !newItemName.trim() || !userId) return

    const { type, parentPath } = newItemDialog
    const newPath = `${parentPath}/${newItemName}`.replace('//', '/')

    try {
      if (type === 'file') {
        const result = await fsAPI.writeFile({
          user_id: userId,
          conversation_id: projectId,
          chat_id: projectId,
          sync_mode: true,
          path: newPath,
          content: '',
        })

        if (!result.success) {
          throw new Error(result.error || 'Failed to create file')
        }

        // Check if file was renamed due to conflict
        const actualPath = result.path || newPath
        const actualName = actualPath.split('/').pop() || newItemName

        // Show notification if file was renamed
        if (result.renamed) {
          toast({
            title: 'File created with different name',
            description: result.message || `A file named "${newItemName}" already exists. Created as "${actualName}" instead.`,
          })
        }

        const pathsToOpen = parentPath !== '/workspace' ? [parentPath] : undefined
        await fileTreeHook.loadFileTree(true, pathsToOpen)

        setNewItemDialog(null)
        setNewItemName('')

        // Open file with actual path (might be renamed)
        openFile(actualPath, actualName)
      } else {
        const result = await fsAPI.createDirectory({
          user_id: userId,
          conversation_id: projectId,
          chat_id: projectId,
          sync_mode: true,
          path: newPath,
        })

        if (!result.success) {
          throw new Error(result.error || 'Failed to create folder')
        }

        const pathsToOpen = parentPath !== '/workspace' ? [parentPath] : undefined
        await fileTreeHook.loadFileTree(true, pathsToOpen)

        setNewItemDialog(null)
        setNewItemName('')
      }
    } catch (error) {
      console.error('Failed to create item:', error)
      toast({
        title: 'Error',
        description: toErrorMessage(error) || 'Failed to create item',
        variant: 'destructive',
      })
    }
  }

  const deleteItem = async () => {
    if (!deleteDialog || !userId) return

    try {
      const result = await fsAPI.deleteFile({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        sync_mode: true,
        path: deleteDialog.path,
      })

      if (result.success) {
        // Close all open files that match the deleted path
        // This handles both single files and directories (closes all files inside)
        // Use ref to avoid stale closure
        const deletedPath = deleteDialog.path
        const filesToClose = openFilesRef.current.filter(f =>
          f.path === deletedPath || f.path.startsWith(deletedPath + '/')
        )
        filesToClose.forEach(f => performCloseFile(f.path))

        fileTreeHook.loadFileTree()
        setDeleteDialog(null)
      } else {
        throw new Error(result.error || 'Failed to delete')
      }
    } catch (error) {
      console.error('Failed to delete:', error)
      toast({
        title: 'Error',
        description: toErrorMessage(error) || 'Failed to delete',
        variant: 'destructive',
      })
    }
  }

  const renameItem = async () => {
    if (!renameDialog || !renameName.trim() || !userId) return

    const { path: oldPath } = renameDialog
    const parentDir = oldPath.substring(0, oldPath.lastIndexOf('/'))
    const newPath = `${parentDir}/${renameName}`.replace('//', '/')

    try {
      const result = await fsAPI.renameFile({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        sync_mode: true,
        old_path: oldPath,
        new_path: newPath,
      })

      if (result.success) {
        // Use ref to avoid stale closure
        const openFile = openFilesRef.current.find(f => f.path === oldPath)
        if (openFile) {
          const newLanguage = getLanguageFromPath(newPath)
          editorHook.renameModel(oldPath, newPath, newLanguage)

          setOpenFiles(prev => prev.map(f =>
            f.path === oldPath
              ? { ...f, path: newPath, name: renameName, language: newLanguage }
              : f
          ))
          if (activeFilePath === oldPath) {
            setActiveFilePath(newPath)
          }
        }

        fileTreeHook.loadFileTree()
        setRenameDialog(null)
        setRenameName('')
      } else {
        throw new Error(result.error || 'Failed to rename')
      }
    } catch (error) {
      console.error('Failed to rename:', error)
      toast({
        title: 'Error',
        description: toErrorMessage(error) || 'Failed to rename',
        variant: 'destructive',
      })
    }
  }

  const moveItem = async (draggedNode: FileNode, targetNode: FileNode) => {
    if (!userId) return

    if (draggedNode.path === targetNode.path) return
    if (targetNode.type !== 'directory') return
    if (targetNode.path.startsWith(draggedNode.path + '/')) {
      toast({
        title: 'Invalid Move',
        description: 'Cannot move a folder into itself',
        variant: 'destructive',
      })
      return
    }

    const newPath = `${targetNode.path}/${draggedNode.name}`.replace('//', '/')

    try {
      const result = await fsAPI.renameFile({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        sync_mode: true,
        old_path: draggedNode.path,
        new_path: newPath,
      })

      if (result.success) {
        // Use ref to avoid stale closure
        const openFile = openFilesRef.current.find(f => f.path === draggedNode.path)
        if (openFile) {
          editorHook.renameModel(draggedNode.path, newPath, openFile.language)

          setOpenFiles(prev => prev.map(f =>
            f.path === draggedNode.path
              ? { ...f, path: newPath }
              : f
          ))
          if (activeFilePath === draggedNode.path) {
            setActiveFilePath(newPath)
          }
        }

        await fileTreeHook.loadFileTree(true, [targetNode.path])
      } else {
        throw new Error(result.error || 'Failed to move')
      }
    } catch (error) {
      console.error('Failed to move:', error)
      toast({
        title: 'Error',
        description: toErrorMessage(error) || 'Failed to move item',
        variant: 'destructive',
      })
    }
  }

  const showFileDetails = (path: string, name: string) => {
    setFileDetailsModal({ open: true, path, name })
  }

  const downloadFile = async (path: string, name: string) => {
    if (!userId) return

    try {
      const result = await fsAPI.readFile({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        path,
      })

      if (result.success && result.content !== undefined) {
        // Convert content to blob for validation
        const blob = new Blob([result.content], { type: 'application/octet-stream' })

        // Validate file type (magic bytes) if possible
        const file = new File([blob], name)
        const validation = await validateFileType(file)

        // Warn if type mismatch or executable detected
        if (!validation.valid || validation.warning) {
          const proceed = window.confirm(
            `⚠️ SECURITY WARNING\n\n${validation.warning || 'Suspicious file detected'}\n\nDo you want to continue downloading this file?\n\nPlease verify the file source before opening it.`
          )

          if (!proceed) {
            toast({
              title: 'Download Cancelled',
              description: 'File download cancelled for security reasons',
            })
            return
          }
        }

        // Force download with application/octet-stream to prevent auto-execution
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = name
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)

        toast({
          title: 'File Downloaded',
          description: `${name} has been downloaded successfully`,
        })
      } else {
        throw new Error(result.error || 'Failed to read file')
      }
    } catch (error) {
      console.error('Failed to download file:', error)
      toast({
        title: 'Download Failed',
        description: toErrorMessage(error) || 'Failed to download file',
        variant: 'destructive',
      })
    }
  }

  const downloadWorkspace = async () => {
    if (!userId) return

    try {
      toast({
        title: 'Preparing Download',
        description: 'Collecting workspace files...',
      })

      // Collect all files recursively
      const collectFiles = async (nodes: FileNode[]): Promise<Array<{ path: string; name: string }>> => {
        const files: Array<{ path: string; name: string }> = []

        for (const node of nodes) {
          if (node.type === 'file') {
            files.push({ path: node.path, name: node.name })
          } else if (node.type === 'directory' && node.children) {
            files.push(...await collectFiles(node.children))
          }
        }

        return files
      }

      const allFiles = await collectFiles(fileTreeHook.fileTree)

      if (allFiles.length === 0) {
        toast({
          title: 'Workspace Empty',
          description: 'No files to download',
        })
        return
      }

      // Download all files and create ZIP
      // Using JSZip library (will need to be installed)
      const JSZip = (await import('jszip')).default
      const zip = new JSZip()

      for (const file of allFiles) {
        try {
          const result = await fsAPI.readFile({
            user_id: userId,
            conversation_id: projectId,
            chat_id: projectId,
            path: file.path,
          })

          if (result.success && result.content !== undefined) {
            // Remove /workspace prefix from path for ZIP structure
            const relativePath = file.path.replace(/^\/workspace\//, '')
            zip.file(relativePath, result.content)
          }
        } catch (error) {
          console.error(`Failed to read file ${file.path}:`, error)
        }
      }

      // Generate ZIP blob
      const blob = await zip.generateAsync({ type: 'blob' })

      // Download ZIP
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `workspace-${projectId}-${Date.now()}.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)

      toast({
        title: 'Download Complete',
        description: `Downloaded ${allFiles.length} files as ZIP`,
      })
    } catch (error) {
      console.error('Failed to download workspace:', error)
      toast({
        title: 'Download Failed',
        description: toErrorMessage(error) || 'Failed to download workspace',
        variant: 'destructive',
      })
    }
  }

  // Helper: Detect real file type using magic bytes (file signature)
  const detectRealFileType = async (file: File): Promise<{ mime: string; category: string }> => {
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = (e) => {
        const arr = new Uint8Array(e.target?.result as ArrayBuffer).subarray(0, 16)
        let header = ''
        for (let i = 0; i < arr.length && i < 8; i++) {
          header += arr[i].toString(16).padStart(2, '0')
        }

        // Magic bytes signatures (most common)
        const signatures: Record<string, { mime: string; category: string }> = {
          // Images
          '89504e47': { mime: 'image/png', category: 'image' },
          'ffd8ffe0': { mime: 'image/jpeg', category: 'image' },
          'ffd8ffe1': { mime: 'image/jpeg', category: 'image' },
          'ffd8ffe2': { mime: 'image/jpeg', category: 'image' },
          '47494638': { mime: 'image/gif', category: 'image' },
          '424d': { mime: 'image/bmp', category: 'image' },
          '00000100': { mime: 'image/x-icon', category: 'image' },

          // Documents
          '25504446': { mime: 'application/pdf', category: 'document' },
          '504b0304': { mime: 'application/zip', category: 'archive' }, // Also xlsx, docx
          'd0cf11e0': { mime: 'application/vnd.ms-office', category: 'document' }, // Old Office

          // Archives
          '1f8b': { mime: 'application/gzip', category: 'archive' },
          '526172': { mime: 'application/x-rar', category: 'archive' },
          '377abcaf': { mime: 'application/x-7z-compressed', category: 'archive' },
          '425a68': { mime: 'application/x-bzip2', category: 'archive' },

          // Executables
          '4d5a': { mime: 'application/x-msdownload', category: 'executable' }, // .exe, .dll
          '7f454c46': { mime: 'application/x-elf', category: 'executable' }, // Linux executable
          'cafebabe': { mime: 'application/java-vm', category: 'executable' }, // Java class
          'feedface': { mime: 'application/x-mach-binary', category: 'executable' }, // macOS binary
          'cefaedfe': { mime: 'application/x-mach-binary', category: 'executable' }, // macOS binary

          // Media
          '000001ba': { mime: 'video/mpeg', category: 'media' },
          '000001b3': { mime: 'video/mpeg', category: 'media' },
          '66747970': { mime: 'video/mp4', category: 'media' },
          '494433': { mime: 'audio/mpeg', category: 'media' }, // MP3
          '52494646': { mime: 'audio/wav', category: 'media' }, // WAV
        }

        // Check for matches (try different header lengths)
        for (let len = 8; len >= 2; len--) {
          const truncated = header.substring(0, len * 2)
          if (signatures[truncated]) {
            return resolve(signatures[truncated])
          }
        }

        resolve({ mime: 'application/octet-stream', category: 'unknown' })
      }
      reader.readAsArrayBuffer(file.slice(0, 16))
    })
  }

  // Helper: Validate file type matches extension
  const validateFileType = async (file: File): Promise<{ valid: boolean; warning?: string; shouldBlock?: boolean }> => {
    const declaredExt = file.name.split('.').pop()?.toLowerCase() || ''
    const realType = await detectRealFileType(file)

    // Define text/code file extensions (should NOT be binary)
    const textExtensions = ['txt', 'md', 'py', 'js', 'ts', 'tsx', 'jsx', 'java', 'cpp', 'c', 'h', 'css', 'scss', 'html', 'xml', 'json', 'yaml', 'yml', 'sh', 'bash', 'sql', 'rs', 'go', 'php', 'rb', 'swift', 'kt', 'cs', 'r', 'scala', 'dart']

    // Define expected MIME types for common extensions
    const expectedTypes: Record<string, string[]> = {
      'png': ['image/png'],
      'jpg': ['image/jpeg'],
      'jpeg': ['image/jpeg'],
      'gif': ['image/gif'],
      'bmp': ['image/bmp'],
      'ico': ['image/x-icon'],
      'pdf': ['application/pdf'],
      'zip': ['application/zip', 'application/octet-stream'], // ZIP or generic binary
      'gz': ['application/gzip', 'application/octet-stream'],
      'rar': ['application/x-rar', 'application/octet-stream'],
      '7z': ['application/x-7z-compressed', 'application/octet-stream'],
      'tar': ['application/x-tar', 'application/octet-stream'],
      'mp3': ['audio/mpeg', 'application/octet-stream'],
      'wav': ['audio/wav', 'application/octet-stream'],
      'mp4': ['video/mp4', 'application/octet-stream'],
      'xlsx': ['application/zip', 'application/octet-stream'], // Excel files are ZIP archives
      'xls': ['application/vnd.ms-office', 'application/octet-stream'],
    }

    // CRITICAL: Block executables masquerading as non-executable types
    if (realType.category === 'executable' && !['exe', 'dll', 'so', 'dylib', 'elf'].includes(declaredExt)) {
      return {
        valid: false,
        warning: `SECURITY WARNING: "${file.name}" appears to be an executable file (.${declaredExt} → ${realType.mime})`,
        shouldBlock: true
      }
    }

    // CRITICAL: Block binary files (images, PDFs, etc.) masquerading as text/code files
    if (textExtensions.includes(declaredExt)) {
      // Check if the real type is a known binary format
      const knownBinaryTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'application/pdf',
                                'application/zip', 'application/gzip', 'application/x-rar',
                                'application/vnd.ms-office', 'video/', 'audio/']

      const isBinary = knownBinaryTypes.some(type => realType.mime.startsWith(type))

      if (isBinary) {
        return {
          valid: false,
          warning: `SECURITY WARNING: "${file.name}" claims to be a text file (.${declaredExt}) but appears to be a binary file (${realType.mime})`,
          shouldBlock: true
        }
      }
    }

    // Only warn about SIGNIFICANT type mismatches (not generic binaries)
    if (expectedTypes[declaredExt]) {
      // Check if the detected type matches expectations
      if (!expectedTypes[declaredExt].includes(realType.mime)) {
        // Ignore warnings for unknown/generic binaries (application/octet-stream)
        // Only warn if we detected a SPECIFIC different type
        if (realType.mime !== 'application/octet-stream' && realType.category !== 'unknown') {
          // Example: .png file that is actually a .pdf
          return {
            valid: true,
            warning: `Type mismatch: "${file.name}" claims to be .${declaredExt} but appears to be ${realType.mime}`,
            shouldBlock: false
          }
        }
      }
    }

    return { valid: true }
  }

  // Helper: Read file content with proper encoding
  const readFileContent = async (file: File): Promise<{ content: string; isBinary: boolean }> => {
    const isBinary = /\.(png|jpg|jpeg|gif|webp|bmp|ico|pdf|xlsx|xls|xlsm|zip|tar|gz|mp4|mp3|wav)$/i.test(file.name)

    const content = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()

      if (isBinary) {
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1] // Remove data:... prefix
          resolve(base64)
        }
        reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
        reader.readAsDataURL(file)
      } else {
        reader.onload = () => resolve(reader.result as string)
        reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
        reader.readAsText(file)
      }
    })

    return { content, isBinary }
  }

  // Helper: Recursively read all files from directory entries
  const readDirectoryEntries = async (entry: FileSystemEntry): Promise<Array<{ file: File; relativePath: string }>> => {
    const results: Array<{ file: File; relativePath: string }> = []

    if (entry.isFile) {
      // It's a file - read it
      const file = await new Promise<File>((resolve, reject) => {
        ;(entry as FileSystemFileEntry).file(resolve, reject)
      })
      results.push({ file, relativePath: entry.fullPath.replace(/^\//, '') })
    } else if (entry.isDirectory) {
      // It's a directory - read all entries recursively
      const reader = (entry as FileSystemDirectoryEntry).createReader()
      const entries = await new Promise<FileSystemEntry[]>((resolve, reject) => {
        reader.readEntries(resolve, reject)
      })

      for (const childEntry of entries) {
        const childResults = await readDirectoryEntries(childEntry)
        results.push(...childResults)
      }
    }

    return results
  }

  // Cancel upload and rollback already uploaded files/directories
  const cancelUpload = async () => {
    uploadCancelledRef.current = true

    // Small delay to let current upload operation finish and update the ref
    await new Promise(resolve => setTimeout(resolve, 100))

    // Get root paths that were uploaded (directories or files at the top level)
    const rootPaths = [...uploadedRootPathsRef.current]

    if (rootPaths.length > 0) {
      toast({
        title: 'Cancelling Upload',
        description: `Rolling back ${rootPaths.length} item(s)...`,
      })

      // Delete each root path (will recursively delete directories)
      let deletedCount = 0
      for (const rootPath of rootPaths) {
        try {
          await fsAPI.deleteFile({
            user_id: userId!,
            conversation_id: projectId,
            chat_id: projectId,
            sync_mode: true,
            path: rootPath,
          })
          deletedCount++
        } catch (error) {
          console.error(`Failed to rollback ${rootPath}:`, error)
        }
      }

      // Refresh file tree after rollback
      await fileTreeHook.loadFileTree()

      toast({
        title: 'Upload Cancelled',
        description: `Rolled back ${deletedCount} item(s)`,
      })
    } else {
      toast({
        title: 'Upload Cancelled',
      })
    }

    // Reset state
    setIsUploading(false)
    setUploadProgress(null)
    uploadedRootPathsRef.current = new Set()
    uploadCancelledRef.current = false
  }

  // Helper to extract root path from a file path (first directory or file under /workspace)
  const getRootUploadPath = (filePath: string, relativePath: string): string => {
    // Get the first segment of the relative path (the dropped item name)
    const firstSegment = relativePath.split('/')[0]
    // Construct the full root path
    const basePath = filePath.substring(0, filePath.indexOf(relativePath))
    return `${basePath}${firstSegment}`.replace('//', '/')
  }

  // File upload (drag & drop) - supports files AND directories
  const uploadFiles = async (files: FileList, targetPath: string = '/workspace') => {
    if (!userId || files.length === 0) return

    // Reset cancellation flag and uploaded paths tracker
    uploadCancelledRef.current = false
    uploadedRootPathsRef.current = new Set()
    setIsUploading(true)

    try {
      let successCount = 0
      let failCount = 0
      const filesToUpload: Array<{ file: File; relativePath: string }> = []

      // Collect all files (including from directories)
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        filesToUpload.push({ file, relativePath: file.name })
      }

      // Validate file sizes
      const oversizedFiles = filesToUpload.filter(f => f.file.size > MAX_FILE_SIZE_BYTES)
      if (oversizedFiles.length > 0) {
        toast({
          title: 'File Too Large',
          description: `${oversizedFiles[0].relativePath} exceeds ${MAX_FILE_SIZE_LABEL} limit. Please upload smaller files.`,
          variant: 'destructive',
        })
        setIsUploading(false)
        return
      }

      // Initialize progress
      setUploadProgress({
        current: 0,
        total: filesToUpload.length,
        currentFileName: filesToUpload[0]?.relativePath || '',
      })

      // Upload all files
      for (let i = 0; i < filesToUpload.length; i++) {
        // Check for cancellation
        if (uploadCancelledRef.current) {
          return // cancelUpload handles cleanup
        }

        const { file, relativePath } = filesToUpload[i]

        // Update progress
        setUploadProgress(prev => prev ? {
          ...prev,
          current: i,
          currentFileName: relativePath,
        } : null)

        try {
          // Read file content
          const { content, isBinary } = await readFileContent(file)

          // Check for cancellation again after reading file
          if (uploadCancelledRef.current) {
            return
          }

          // Upload to workspace (preserve directory structure)
          const filePath = `${targetPath}/${relativePath}`.replace('//', '/')

          const result = await fsAPI.writeFile({
            user_id: userId,
            conversation_id: projectId,
            chat_id: projectId,
            sync_mode: true,
            path: filePath,
            content,
            is_base64: isBinary,
          })

          if (result.success) {
            successCount++
            // Track root path for rollback (use actual path if renamed)
            const actualPath = result.path || filePath
            const rootPath = getRootUploadPath(actualPath, relativePath)
            uploadedRootPathsRef.current.add(rootPath)

            // Show notification if file was renamed due to conflict
            if (result.renamed) {
              toast({
                title: 'File Renamed',
                description: result.message || `File "${relativePath}" already exists. Uploaded with different name.`,
              })
            }
          } else {
            failCount++
            console.error(`Failed to upload ${relativePath}:`, result.error)
          }
        } catch (error) {
          failCount++
          console.error(`Failed to upload ${relativePath}:`, error)
        }
      }

      // Check if cancelled before showing success
      if (uploadCancelledRef.current) {
        return
      }

      // Refresh file tree
      await fileTreeHook.loadFileTree()

      // Show summary toast
      if (successCount > 0) {
        toast({
          title: 'Upload Complete',
          description: `${successCount} file${successCount > 1 ? 's' : ''} uploaded successfully${failCount > 0 ? `, ${failCount} failed` : ''}`,
        })
      } else if (failCount > 0) {
        toast({
          title: 'Upload Failed',
          description: `Failed to upload ${failCount} file${failCount > 1 ? 's' : ''}`,
          variant: 'destructive',
        })
      }
    } catch (error) {
      console.error('Upload error:', error)
      toast({
        title: 'Upload Error',
        description: toErrorMessage(error) || 'An error occurred during upload',
        variant: 'destructive',
      })
    } finally {
      if (!uploadCancelledRef.current) {
        setIsUploading(false)
        setUploadProgress(null)
        uploadedRootPathsRef.current = new Set()
      }
    }
  }

  // Code execution
  const handleRunFile = async () => {
    if (!activeFile || !userId) return

    const execLang = getExecutableLanguage(activeFile.path)
    if (!execLang) {
      toast({
        title: 'Cannot Execute',
        description: 'Only Python (.py), JavaScript (.js), and Shell (.sh) files can be executed',
        variant: 'destructive',
      })
      return
    }

    if (activeFile.isDirty) {
      await saveFile(activeFile.path)
    }

    setIsExecuting(true)
    setResult(null)
    // Open bottom panel with output tab when running code
    setBottomPanelOpen(true)
    setBottomPanelTab('output')

    const executionId = `exec-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
    executionIdRef.current = executionId

    const abortController = new AbortController()
    abortControllerRef.current = abortController

    try {
      const token = getAccessToken()
      if (!token) {
        toast({
          title: 'Authentication Error',
          description: 'No authentication token found',
          variant: 'destructive',
        })
        return
      }

      const response = await orchestratorClient.post<ExecutionResult>('/execute', {
        code: activeFile.content,
        language: execLang,
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        sync_mode: true,
        project_id: projectId,
        timeout: 30,
        execution_id: executionId,
      }, { signal: abortController.signal })

      const data = response.data
      setResult(data)

      if (data.exit_code !== 0) {
        toast({
          title: 'Execution Failed',
          description: `Exit code: ${data.exit_code}`,
          variant: 'destructive',
        })
      }
    } catch (error) {
      // Don't show error if execution was aborted by user (axios raises
      // a CanceledError; a bare AbortError is also handled defensively)
      if (axios.isCancel(error) || (error instanceof Error && error.name === 'AbortError')) {
        setResult({
          output: '',
          error: 'Execution cancelled by user',
          exit_code: 1,
          execution_time: 0,
        })
      } else {
        const message = axios.isAxiosError(error) && error.response
          ? `HTTP ${error.response.status}`
          : toErrorMessage(error) || 'Execution failed'
        setResult({
          output: '',
          error: message,
          exit_code: 1,
          execution_time: 0,
        })
      }
    } finally {
      setIsExecuting(false)
      abortControllerRef.current = null
      executionIdRef.current = null
    }
  }

  const handleAbort = async () => {
    if (!executionIdRef.current) return

    const executionId = executionIdRef.current
    const token = getAccessToken()
    if (!token) return

    setIsExecuting(false)

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    try {
      orchestratorClient.post(`/cancel/${executionId}`)
    } finally {
      abortControllerRef.current = null
      executionIdRef.current = null
    }
  }

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

  // Drag & Drop handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()

    // Check if files are being dragged
    if (e.dataTransfer.types.includes('Files')) {
      dragCounterRef.current++
      setIsDraggingFiles(true)
    }
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()

    dragCounterRef.current--
    if (dragCounterRef.current === 0) {
      setIsDraggingFiles(false)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleImportClick = () => {
    // Trigger the hidden file input
    fileInputRef.current?.click()
  }

  const handleFileInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    // Reset cancellation flag and uploaded paths tracker
    uploadCancelledRef.current = false
    uploadedRootPathsRef.current = new Set()
    setIsUploading(true)

    const fileArray = Array.from(files)

    // Initialize progress
    setUploadProgress({
      current: 0,
      total: fileArray.length,
      currentFileName: fileArray[0]?.name || '',
    })

    try {
      let successCount = 0
      let failCount = 0

      for (let i = 0; i < fileArray.length; i++) {
        // Check for cancellation
        if (uploadCancelledRef.current) {
          return // cancelUpload handles cleanup
        }

        const file = fileArray[i]

        // Update progress
        setUploadProgress(prev => prev ? {
          ...prev,
          current: i,
          currentFileName: file.name,
        } : null)

        try {
          // Check file size
          if (file.size > MAX_FILE_SIZE_BYTES) {
            toast({
              title: 'File Too Large',
              description: `${file.name} exceeds ${MAX_FILE_SIZE_LABEL} limit`,
              variant: 'destructive',
            })
            failCount++
            continue
          }

          // Validate file type (magic bytes)
          const validation = await validateFileType(file)
          if (!validation.valid) {
            toast({
              title: 'Upload Blocked',
              description: validation.warning || 'Invalid file type',
              variant: 'destructive',
            })
            failCount++
            continue
          }

          // Note: Warnings are only shown during download, not upload
          // This prevents spam during bulk uploads

          // Read file content
          const { content, isBinary } = await readFileContent(file)

          // Check for cancellation again after reading file
          if (uploadCancelledRef.current) {
            return
          }

          // Upload to workspace root
          const filePath = `/workspace/${file.name}`.replace('//', '/')

          const result = await fsAPI.writeFile({
            user_id: userId!,
            conversation_id: projectId,
            chat_id: projectId,
            sync_mode: true,
            path: filePath,
            content,
            is_base64: isBinary,
          })

          if (result.success) {
            successCount++
            // Track uploaded file path for rollback (direct files, not directories)
            const actualPath = result.path || filePath
            uploadedRootPathsRef.current.add(actualPath)
          } else {
            failCount++
            console.error(`Failed to upload ${file.name}:`, result.error)
          }
        } catch (error) {
          failCount++
          console.error(`Failed to upload ${file.name}:`, error)
        }
      }

      // Check if cancelled before showing success
      if (uploadCancelledRef.current) {
        return
      }

      // Refresh file tree
      await fileTreeHook.loadFileTree()

      // Show summary toast
      if (successCount > 0) {
        toast({
          title: 'Upload Complete',
          description: `${successCount} file${successCount > 1 ? 's' : ''} uploaded successfully${failCount > 0 ? `, ${failCount} failed` : ''}`,
        })
      } else if (failCount > 0) {
        toast({
          title: 'Upload Failed',
          description: `Failed to upload ${failCount} file${failCount > 1 ? 's' : ''}`,
          variant: 'destructive',
        })
      }
    } finally {
      if (!uploadCancelledRef.current) {
        setIsUploading(false)
        setUploadProgress(null)
        uploadedRootPathsRef.current = new Set()
      }
      // Reset the input so the same file can be selected again
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()

    dragCounterRef.current = 0
    setIsDraggingFiles(false)

    // Use DataTransferItemList API to handle directories
    const items = e.dataTransfer.items
    if (items && items.length > 0) {
      // Reset cancellation flag and uploaded paths tracker
      uploadCancelledRef.current = false
      uploadedRootPathsRef.current = new Set()
      setIsUploading(true)

      try {
        let successCount = 0
        let failCount = 0
        const allFiles: Array<{ file: File; relativePath: string }> = []

        // Process each dropped item (file or directory)
        for (let i = 0; i < items.length; i++) {
          const item = items[i]
          if (item.kind === 'file') {
            const entry = item.webkitGetAsEntry()
            if (entry) {
              const files = await readDirectoryEntries(entry)
              allFiles.push(...files)
            }
          }
        }

        if (allFiles.length === 0) {
          setIsUploading(false)
          return
        }

        // Validate file sizes
        const oversizedFiles = allFiles.filter(f => f.file.size > MAX_FILE_SIZE_BYTES)
        if (oversizedFiles.length > 0) {
          toast({
            title: 'File Too Large',
            description: `${oversizedFiles[0].relativePath} exceeds ${MAX_FILE_SIZE_LABEL} limit. Please upload smaller files.`,
            variant: 'destructive',
          })
          setIsUploading(false)
          return
        }

        // Validate file types (magic bytes) and warn about suspicious files
        const typeValidations = await Promise.all(
          allFiles.map(async ({ file, relativePath }) => ({
            relativePath,
            validation: await validateFileType(file)
          }))
        )

        // Block any files that fail validation (executables masquerading as other types)
        const blockedFiles = typeValidations.filter(v => !v.validation.valid)
        if (blockedFiles.length > 0) {
          toast({
            title: 'Upload Blocked',
            description: blockedFiles[0].validation.warning || `${blockedFiles.length} file(s) blocked due to type mismatch`,
            variant: 'destructive',
          })
          setIsUploading(false)
          return
        }

        // Note: Type mismatch warnings are only shown during download, not upload
        // This prevents spam during bulk drag & drop uploads

        // Initialize progress
        setUploadProgress({
          current: 0,
          total: allFiles.length,
          currentFileName: allFiles[0]?.relativePath || '',
        })

        // Upload all files
        for (let i = 0; i < allFiles.length; i++) {
          // Check for cancellation
          if (uploadCancelledRef.current) {
            return // cancelUpload handles cleanup
          }

          const { file, relativePath } = allFiles[i]

          // Update progress
          setUploadProgress(prev => prev ? {
            ...prev,
            current: i,
            currentFileName: relativePath,
          } : null)

          try {
            // Read file content
            const { content, isBinary } = await readFileContent(file)

            // Check for cancellation again after reading file
            if (uploadCancelledRef.current) {
              return
            }

            // Upload to workspace (preserve directory structure)
            const filePath = `/workspace/${relativePath}`.replace('//', '/')

            const result = await fsAPI.writeFile({
              user_id: userId!,
              conversation_id: projectId,
              chat_id: projectId,
              sync_mode: true,
              path: filePath,
              content,
              is_base64: isBinary,
            })

            if (result.success) {
              successCount++
              // Track root path for rollback (first directory or file in the relative path)
              const actualPath = result.path || filePath
              const rootPath = getRootUploadPath(actualPath, relativePath)
              uploadedRootPathsRef.current.add(rootPath)

              // Show notification if file was renamed due to conflict
              if (result.renamed) {
                toast({
                  title: 'File Renamed',
                  description: result.message || `File "${relativePath}" already exists. Uploaded with different name.`,
                })
              }
            } else {
              failCount++
              console.error(`Failed to upload ${relativePath}:`, result.error)
            }
          } catch (error) {
            failCount++
            console.error(`Failed to upload ${relativePath}:`, error)
          }
        }

        // Check if cancelled before showing success
        if (uploadCancelledRef.current) {
          return
        }

        // Refresh file tree
        await fileTreeHook.loadFileTree()

        // Show summary toast
        if (successCount > 0) {
          toast({
            title: 'Upload Complete',
            description: `${successCount} file${successCount > 1 ? 's' : ''} uploaded successfully${failCount > 0 ? `, ${failCount} failed` : ''}`,
          })
        } else if (failCount > 0) {
          toast({
            title: 'Upload Failed',
            description: `Failed to upload ${failCount} file${failCount > 1 ? 's' : ''}`,
            variant: 'destructive',
          })
        }
      } catch (error) {
        console.error('Upload error:', error)
        toast({
          title: 'Upload Error',
          description: toErrorMessage(error) || 'An error occurred during upload',
          variant: 'destructive',
        })
      } finally {
        if (!uploadCancelledRef.current) {
          setIsUploading(false)
          setUploadProgress(null)
          uploadedRootPathsRef.current = new Set()
        }
      }
    }
  }

  // Monaco editor setup
  const handleEditorDidMount: OnMount = (editor, monacoInstance) => {
    editorHook.editorRef.current = editor
    editorHook.monacoRef.current = monacoInstance

    // Disable semantic validation — Monaco has no access to the sandbox's
    // node_modules or tsconfig, so every import would show as an error.
    const diagOpts = { noSemanticValidation: true, noSyntaxValidation: false }
    monacoInstance.languages.typescript.typescriptDefaults.setDiagnosticsOptions(diagOpts)
    monacoInstance.languages.typescript.javascriptDefaults.setDiagnosticsOptions(diagOpts)

    // Define and apply the selected code theme from settings
    const themeName = `custom-${codeThemeId}`
    if (!themeDefinedRef.current.has(themeName)) {
      themeDefinedRef.current.add(themeName)
      monacoInstance.editor.defineTheme(themeName, getMonacoThemeData(codeThemeId))
    }
    monacoInstance.editor.setTheme(themeName)

    editor.onDidChangeModelContent(() => {
      if (editorHook.isChangingFileRef.current || editorHook.isSavingRef.current) {
        return
      }

      const currentPath = editorHook.activeFilePathRef.current
      const currentModel = editor.getModel()

      if (currentPath && currentModel) {
        const currentContent = currentModel.getValue()

        setOpenFiles(prevFiles => prevFiles.map(f =>
          f.path === currentPath
            ? { ...f, content: currentContent, isDirty: true }
            : f
        ))
      }
    })

    editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.KeyS, () => {
      const currentActiveFilePath = editorHook.activeFilePathRef.current
      const currentUserId = userIdRef.current

      if (currentActiveFilePath && currentUserId) {
        const currentModel = editor.getModel()
        if (!currentModel) return

        const currentContent = currentModel.getValue()
        const file = openFilesRef.current.find(f => f.path === currentActiveFilePath)
        if (!file) return

        editorHook.isSavingRef.current = true

        fsAPI.writeFile({
          user_id: currentUserId,
          conversation_id: projectIdRef.current,
          chat_id: projectIdRef.current,
          sync_mode: true,
          path: currentActiveFilePath,
          content: currentContent,
        }).then(result => {
          if (result.success) {
            setOpenFiles(prevFiles => prevFiles.map(f =>
              f.path === currentActiveFilePath ? { ...f, content: currentContent, isDirty: false } : f
            ))
          } else {
            toast({
              title: 'Failed to save file',
              description: result.error || 'Unknown error',
              variant: 'destructive',
            })
          }
        }).catch(error => {
          toast({
            title: 'Error',
            description: toErrorMessage(error) || 'Failed to save file',
            variant: 'destructive',
          })
        }).finally(() => {
          setTimeout(() => {
            editorHook.isSavingRef.current = false
          }, 100)
        })
      }
    })

    // Track cursor position for status bar
    editor.onDidChangeCursorPosition((e) => {
      setCursorPosition({ line: e.position.lineNumber, column: e.position.column })
    })

    // Track selection for status bar
    editor.onDidChangeCursorSelection((e) => {
      const selection = e.selection
      if (selection.isEmpty()) {
        setSelectedTextLength(0)
      } else {
        const model = editor.getModel()
        if (model) {
          const selectedText = model.getValueInRange(selection)
          setSelectedTextLength(selectedText.length)
        }
      }
    })

    // Set Monaco ready state to trigger file loading
    setMonacoReady(true)
  }

  return (
    <div
      ref={rootRef}
      className={cn('flex flex-col h-full relative', className)}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Resource usage bars (storage + RAM) */}
      <ResourceBars userId={userId} chatId={projectId} />

      {/* Main content row - file tree + editor */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* Drag & Drop Overlay */}
      {isDraggingFiles && (
        <div className="absolute inset-0 z-50 bg-slate-950/90 backdrop-blur-sm flex items-center justify-center pointer-events-none">
          <div className="text-center space-y-4">
            <div className="mx-auto w-20 h-20 rounded-full bg-accent-brand/20 flex items-center justify-center">
              <Upload className="w-10 h-10 text-accent-brand" />
            </div>
            <div className="space-y-2">
              <p className="text-xl font-semibold text-white">Drop files to upload</p>
              <p className="text-sm text-slate-400">Files will be uploaded to /workspace</p>
              <p className="text-xs text-slate-500">Maximum file size: {MAX_FILE_SIZE_LABEL}</p>
            </div>
          </div>
        </div>
      )}

      {/* Upload Progress Overlay */}
      {isUploading && (
        <div className="absolute inset-0 z-50 bg-slate-950/90 backdrop-blur-sm flex items-center justify-center">
          <div className="text-center space-y-4 max-w-md w-full px-6">
            <div className="mx-auto w-16 h-16 rounded-full bg-accent-brand/20 flex items-center justify-center">
              <Upload className="w-8 h-8 text-accent-brand animate-bounce" />
            </div>

            <div className="space-y-3">
              <p className="text-lg font-semibold text-white">Uploading files...</p>

              {uploadProgress && (
                <>
                  {/* Progress bar */}
                  <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-accent-brand h-full transition-all duration-300 ease-out"
                      style={{
                        width: `${uploadProgress.total > 0 ? ((uploadProgress.current + 1) / uploadProgress.total) * 100 : 0}%`
                      }}
                    />
                  </div>

                  {/* Progress text */}
                  <div className="space-y-1">
                    <p className="text-sm text-slate-300">
                      {uploadProgress.current + 1} of {uploadProgress.total} files
                    </p>
                    <p className="text-xs text-slate-500 truncate max-w-full" title={uploadProgress.currentFileName}>
                      {uploadProgress.currentFileName}
                    </p>
                  </div>
                </>
              )}

              {/* Cancel button */}
              <Button
                variant="outline"
                size="sm"
                onClick={cancelUpload}
                className="mt-2 border-red-500/50 text-red-400 hover:bg-red-500/10 hover:border-red-500"
              >
                <X className="w-4 h-4 mr-1.5" />
                Cancel Upload
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Hidden file input for Import button */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        onChange={handleFileInputChange}
        className="hidden"
        accept="*/*"
      />

      {/* Mobile Explorer Sheet */}
      {isMobile && (
        <Sheet open={mobileExplorerOpen} onOpenChange={setMobileExplorerOpen}>
          <SheetContent side="left" className="w-[85vw] max-w-[320px] p-0">
            <SheetHeader className="px-4 py-3 border-b">
              <SheetTitle className="text-sm font-medium">Explorer</SheetTitle>
            </SheetHeader>
            <div className="h-[calc(100vh-60px)]">
              <FileTreePanel
                fileTree={fileTreeHook.fileTree}
                isLoadingTree={fileTreeHook.isLoadingTree}
                selectedPath={fileTreeHook.selectedPath}
                isSidebarCollapsed={false}
                sidebarWidth={320}
                isResizing={false}
                showHiddenFiles={fileTreeHook.showHiddenFiles}
                isMobileSheet={true}
                modifiedFilePaths={gitModifiedFiles}
                onSelectPath={fileTreeHook.setSelectedPath}
                onToggleDirectory={fileTreeHook.toggleDirectory}
                onOpenFile={(path, name) => {
                  openFile(path, name)
                  setMobileExplorerOpen(false)
                }}
                onNewFile={(parentPath) => {
                  setNewItemDialog({ open: true, type: 'file', parentPath })
                  setMobileExplorerOpen(false)
                }}
                onNewFolder={(parentPath) => {
                  setNewItemDialog({ open: true, type: 'folder', parentPath })
                  setMobileExplorerOpen(false)
                }}
                onRename={(path, oldName) => {
                  setRenameDialog({ open: true, path, oldName })
                  setRenameName(oldName)
                }}
                onDelete={(path) => setDeleteDialog({ open: true, path })}
                onShowDetails={showFileDetails}
                onDownload={downloadFile}
                onDownloadWorkspace={downloadWorkspace}
                onImport={handleImportClick}
                onMove={moveItem}
                onToggleSidebar={() => {}}
                onToggleShowHiddenFiles={() => {
                  fileTreeHook.setShowHiddenFiles(!fileTreeHook.showHiddenFiles)
                  setTimeout(() => fileTreeHook.loadFileTree(), 0)
                }}
                onStartResize={() => {}}
                getParentPathForNewItem={fileTreeHook.getParentPathForNewItem}
              />
            </div>
          </SheetContent>
        </Sheet>
      )}

      {/* Desktop File Tree Panel */}
      {!isMobile && (
        <FileTreePanel
          fileTree={fileTreeHook.fileTree}
          isLoadingTree={fileTreeHook.isLoadingTree}
          selectedPath={fileTreeHook.selectedPath}
          isSidebarCollapsed={isSidebarCollapsed}
          sidebarWidth={sidebarWidth}
          isResizing={isResizing}
          showHiddenFiles={fileTreeHook.showHiddenFiles}
          modifiedFilePaths={gitModifiedFiles}
          onSelectPath={fileTreeHook.setSelectedPath}
          onToggleDirectory={fileTreeHook.toggleDirectory}
          onOpenFile={openFile}
          onNewFile={(parentPath) => setNewItemDialog({ open: true, type: 'file', parentPath })}
          onNewFolder={(parentPath) => setNewItemDialog({ open: true, type: 'folder', parentPath })}
          onRename={(path, oldName) => {
            setRenameDialog({ open: true, path, oldName })
            setRenameName(oldName)
          }}
          onDelete={(path) => setDeleteDialog({ open: true, path })}
          onShowDetails={showFileDetails}
          onDownload={downloadFile}
          onDownloadWorkspace={downloadWorkspace}
          onImport={handleImportClick}
          onMove={moveItem}
          onToggleSidebar={setIsSidebarCollapsed}
          onToggleShowHiddenFiles={() => {
            fileTreeHook.setShowHiddenFiles(!fileTreeHook.showHiddenFiles)
            setTimeout(() => fileTreeHook.loadFileTree(), 0)
          }}
          onStartResize={() => setIsResizing(true)}
          getParentPathForNewItem={fileTreeHook.getParentPathForNewItem}
        />
      )}

      {/* Main Editor Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header bar - different for mobile vs desktop */}
        {isMobile ? (
          <div className="flex items-center gap-2 px-2 py-1.5 border-b border-border/50 bg-background">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setMobileExplorerOpen(true)}
              className="h-8 px-2"
            >
              <FolderOpen className="h-4 w-4 mr-1.5" />
              <span className="text-xs">Explorer</span>
            </Button>
            {activeFile && (
              <div className="flex-1 min-w-0 truncate text-xs text-muted-foreground">
                {activeFile.path}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/50 bg-muted/20">
            {/* Keyboard shortcuts */}
            <KeyboardShortcuts
              shortcuts={[
                { ...platformShortcuts.findFiles, action: () => setQuickSearchOpen(true) },
                { ...platformShortcuts.save, action: () => activeFilePath && saveFile(activeFilePath) },
                { ...platformShortcuts.run, action: handleRunFile },
              ]}
            />
            {/* Right side buttons */}
            <div className="flex items-center gap-2">
              {/* Terminal toggle */}
              <Button
                variant={bottomPanelOpen && bottomPanelTab === 'terminal' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => {
                  if (bottomPanelOpen && bottomPanelTab === 'terminal') {
                    setBottomPanelOpen(false)
                  } else {
                    setBottomPanelOpen(true)
                    setBottomPanelTab('terminal')
                  }
                }}
                className="h-7 px-2 gap-1.5"
              >
                <Terminal className="h-3.5 w-3.5" />
                <span className="text-xs">Terminal</span>
              </Button>
              {/* Quick search button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setQuickSearchOpen(true)}
                className="h-7 px-2 gap-1.5"
              >
                <Search className="h-3.5 w-3.5" />
                <span className="text-xs">Go to File</span>
              </Button>
            </div>
          </div>
        )}

        {/* Tabs */}
        <EditorTabs
          openFiles={openFiles}
          activeFilePath={activeFilePath}
          activeFile={activeFile}
          isExecuting={isExecuting}
          viewMode={viewMode}
          onReorder={setOpenFiles}
          onSelectFile={(path) => {
            setActiveFilePath(path)
            fileTreeHook.setSelectedPath(path)
          }}
          onCloseFile={closeFile}
          onSaveFile={saveFile}
          onRunFile={handleRunFile}
          onAbortExecution={handleAbort}
          onViewModeChange={setViewMode}
        />

        {/* Breadcrumbs - desktop only */}
        {!isMobile && activeFile && (
          <Breadcrumbs
            filePath={activeFile.path}
            onNavigate={(path) => {
              // Navigate to folder in file tree
              fileTreeHook.setSelectedPath(path)
            }}
          />
        )}

        {/* Editor */}
        <div className={cn(
          "flex-1 flex flex-col overflow-hidden min-w-0 relative",
          isMobile ? "p-2 pt-0" : "p-4 pt-0"
        )}>
          {/* Always render Editor to prevent Monaco unmount/remount issues */}
          <div className={cn(
                "group relative flex-1 overflow-hidden rounded-xl border border-slate-800 transition-colors duration-200 min-w-0",
                activeFile && !result && "hover:border-slate-700"
              )}
              style={{ visibility: (activeFile || previewPort != null) ? 'visible' : 'hidden', position: (activeFile || previewPort != null) ? 'relative' : 'absolute', width: '100%', height: '100%' }}
              >
                {/* Action buttons - appear on hover like CodeBlock (only in code mode) */}
                {activeFile && viewMode === 'code' && (
                  <div className="absolute top-4 right-4 z-10 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => saveFile(activeFile.path)}
                      disabled={!activeFile.isDirty}
                      className="bg-slate-800/95 hover:bg-slate-700 border-slate-600 text-slate-200 hover:text-white transition-all duration-200 pointer-events-auto focus:outline-none focus:ring-2 focus:ring-accent-brand/50 active:scale-95"
                    >
                      Save
                    </Button>
                    {getExecutableLanguage(activeFile.path) && (
                      !isExecuting ? (
                        <Button
                          size="sm"
                          onClick={handleRunFile}
                          className="gap-1.5 bg-accent-brand/90 hover:bg-accent-brand text-slate-900 hover:text-slate-950 font-medium transition-all duration-200 pointer-events-auto focus:outline-none focus:ring-2 focus:ring-accent-brand/50 active:scale-95 shadow-lg"
                        >
                          <Play className="h-3.5 w-3.5" />
                          Run
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={handleAbort}
                          className="gap-1.5 pointer-events-auto transition-all duration-200 active:scale-95 shadow-lg"
                        >
                          <StopCircle className="h-3.5 w-3.5" />
                          Stop
                        </Button>
                      )
                    )}
                  </div>
                )}

                <SplitView
                  viewMode={previewPort != null ? 'split' : (activeFile ? viewMode : 'code')}
                  onResizeEnd={() => editorHook.forceLayout()}
                  codeView={
                    <Editor
                      height="100%"
                      onMount={handleEditorDidMount}
                      theme={`custom-${codeThemeId}`}
                      options={{
                        minimap: { enabled: true },
                        fontSize: 14,
                        fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', ui-monospace, monospace",
                        fontLigatures: true,
                        lineNumbers: 'on',
                        lineHeight: 24,
                        letterSpacing: 0.5,
                        roundedSelection: false,
                        scrollBeyondLastLine: false,
                        automaticLayout: true,
                        tabSize: 2,
                        wordWrap: 'off',
                        scrollbar: {
                          horizontal: 'visible',
                          vertical: 'visible',
                          horizontalScrollbarSize: 10,
                          verticalScrollbarSize: 10,
                        },
                        cursorBlinking: 'smooth',
                        cursorSmoothCaretAnimation: 'on',
                        smoothScrolling: true,
                        padding: { top: 16, bottom: 16 },
                      }}
                    />
                  }
                  previewView={
                    previewPort != null && userId ? (
                      <div className="h-full flex flex-col">
                        <div className="flex items-center justify-between px-3 py-1.5 bg-muted/30 border-b border-border/50 shrink-0">
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Globe className="h-3.5 w-3.5" />
                            <span className="font-mono">localhost:{previewPort}</span>
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-[11px]"
                            onClick={() => setPreviewPort(null)}
                          >
                            <X className="h-3 w-3 mr-1" />
                            Close
                          </Button>
                        </div>
                        {previewTokenLoading || !previewToken ? (
                          <div className="flex-1 flex items-center justify-center">
                            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                          </div>
                        ) : (
                          <iframe
                            src={getPreviewUrl(userId, previewPort, previewToken)}
                            className="flex-1 w-full border-0 bg-white"
                            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                            title={`Preview port ${previewPort}`}
                          />
                        )}
                      </div>
                    ) : activeFile ? (
                      <FilePreview
                        fileName={activeFile.name}
                        filePath={activeFile.path}
                        content={activeFile.content}
                        language={activeFile.language}
                        userId={userId}
                        projectId={projectId}
                      />
                    ) : <div />
                  }
                />
              </div>

              {/* Restoring overlay */}
              {fileTreeHook.isRestoring && (
                <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-20">
                  <div className="text-center space-y-3">
                    <Loader2 className="h-8 w-8 mx-auto animate-spin text-primary" />
                    <p className="text-sm text-muted-foreground">Restoring workspace files...</p>
                  </div>
                </div>
              )}

              {/* Empty state overlay */}
              {!activeFile && !fileTreeHook.isRestoring && previewPort == null && (
                <div className="absolute inset-0 flex items-center justify-center text-muted-foreground bg-background">
                  <div className="text-center space-y-3">
                    <FileCode className="h-12 w-12 mx-auto text-muted-foreground/50" />
                    <p className="text-sm text-muted-foreground">No file selected</p>
                    <p className="text-xs text-muted-foreground/70">
                      {isMobile ? 'Tap the button below to browse files' : 'Open a file from the explorer to start editing'}
                    </p>
                    {isMobile && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setMobileExplorerOpen(true)}
                        className="mt-2"
                      >
                        <FolderOpen className="h-4 w-4 mr-2" />
                        Open Explorer
                      </Button>
                    )}
                  </div>
                </div>
              )}

        </div>

        {/* Status Bar - desktop only */}
        {!isMobile && activeFile && (
          <StatusBar
            language={activeFile.language || 'Plain Text'}
            lineCount={activeFile.content?.split('\n').length || 0}
            cursorLine={cursorPosition.line}
            cursorColumn={cursorPosition.column}
            selectedText={selectedTextLength}
          />
        )}
      </div>
      </div>
      {/* End of main content row */}

      {/* Bottom Panel (Output + Terminal + Git) - desktop only, spans full width */}
      {!isMobile && (
        <BottomPanel
          open={bottomPanelOpen}
          onClose={() => setBottomPanelOpen(false)}
          activeTab={bottomPanelTab}
          onTabChange={setBottomPanelTab}
          height={bottomPanelHeight}
          maxHeight={containerHeight > 0 ? containerHeight - 50 : undefined}
          onHeightChange={setBottomPanelHeight}
          result={result}
          onClearOutput={() => setResult(null)}
          userId={userId}
          // Use projectId for code sessions, otherwise original IDs
          conversationId={mode === 'code' ? projectId : conversationId}
          chatId={mode === 'code' ? projectId : chatId}
          mode={mode}
          // Git props (for code sessions)
          gitModifiedFiles={gitModifiedFiles}
          gitCurrentBranch={gitCurrentBranch}
          // Ports
          onPreviewPort={(port) => setPreviewPort(port)}
        />
      )}

      {/* Dialogs */}
      <FileDialogs
        newItemDialog={newItemDialog}
        newItemName={newItemName}
        onNewItemNameChange={setNewItemName}
        onCreateNewItem={createNewItem}
        onCancelNewItem={() => {
          setNewItemDialog(null)
          setNewItemName('')
        }}
        deleteDialog={deleteDialog}
        onConfirmDelete={deleteItem}
        onCancelDelete={() => setDeleteDialog(null)}
        renameDialog={renameDialog}
        renameName={renameName}
        onRenameNameChange={setRenameName}
        onConfirmRename={renameItem}
        onCancelRename={() => {
          setRenameDialog(null)
          setRenameName('')
        }}
        closeFileDialog={closeFileDialog}
        onConfirmCloseFile={() => {
          if (closeFileDialog) {
            performCloseFile(closeFileDialog.path)
            setCloseFileDialog(null)
          }
        }}
        onCancelCloseFile={() => setCloseFileDialog(null)}
      />

      {/* File Details Modal */}
      {fileDetailsModal && (
        <FileDetailsModal
          open={fileDetailsModal.open}
          onOpenChange={(open) => {
            if (!open) {
              setFileDetailsModal(null)
            }
          }}
          filePath={fileDetailsModal.path}
          fileName={fileDetailsModal.name}
          userId={userId}
          conversationId={conversationId}
          chatId={chatId}
          onNavigateToMessage={handleNavigateToMessage}
        />
      )}

      {/* Message View Modal */}
      <MessageViewModal
        open={messageViewModal?.open || false}
        onOpenChange={(open) => {
          if (!open) {
            setMessageViewModal(null)
          }
        }}
        message={selectedMessage}
        isLoading={false}
      />

      {/* Quick File Search */}
      <QuickFileSearch
        open={quickSearchOpen}
        onOpenChange={setQuickSearchOpen}
        fileTree={fileTreeHook.fileTree}
        recentFiles={recentFilePaths}
        onSelectFile={openFile}
      />

      {/* Global Search */}
      <GlobalSearch
        open={globalSearchOpen}
        onOpenChange={setGlobalSearchOpen}
        fileTree={fileTreeHook.fileTree}
        userId={userId}
        projectId={projectId}
        onSelectFile={(path, name, line) => {
          openFile(path, name)
          // Jump to line if specified
          if (line && editorHook.editorRef?.current) {
            setTimeout(() => {
              const editor = editorHook.editorRef?.current
              if (editor) {
                editor.revealLineInCenter(line)
                editor.setPosition({ lineNumber: line, column: 1 })
                editor.focus()
              }
            }, 100)
          }
        }}
      />
    </div>
  )
}
