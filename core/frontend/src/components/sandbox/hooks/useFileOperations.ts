/**
 * Custom hook for open-file (tab) state and all file/directory CRUD:
 * opening, closing, saving, creating, deleting, renaming, moving, and
 * downloading files, plus the dialog state that drives those flows.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { fsAPI } from '@/api/fs'
import { toErrorMessage } from '@/utils/errorMessages'
import type {
  CloseFileDialogState,
  DeleteDialogState,
  FileNode,
  NewItemDialogState,
  OpenFile,
  RenameDialogState,
} from '../types'
import { getLanguageFromPath } from '../types'
import { validateFileType } from '../fileUploadUtils'

interface ToastFn {
  (options: { title: string; description?: string; variant?: 'default' | 'destructive' }): void
}

// Narrow slices of useFileTree/useMonacoEditor — only what file operations need.
interface FileTreeOps {
  fileTree: FileNode[]
  setSelectedPath: (path: string | null) => void
  loadFileTree: (preserveOpenState?: boolean, additionalOpenPaths?: string[]) => Promise<void>
}

interface EditorModelOps {
  disposeModel: (path: string) => void
  getCurrentContent: () => string | null
  isSavingRef: React.MutableRefObject<boolean>
  renameModel: (oldPath: string, newPath: string, newLanguage: string) => unknown
}

interface UseFileOperationsParams {
  userId?: string
  projectId: string
  toast: ToastFn
  fileTreeHook: FileTreeOps
  editorHook: EditorModelOps
}

export function useFileOperations({ userId, projectId, toast, fileTreeHook, editorHook }: UseFileOperationsParams) {
  // File management
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([])
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null)
  const openFilesRef = useRef<OpenFile[]>([])

  useEffect(() => {
    openFilesRef.current = openFiles
  }, [openFiles])

  const activeFile = openFiles.find(f => f.path === activeFilePath)

  // Track recent files
  const [recentFilePaths, setRecentFilePaths] = useState<string[]>([])
  const trackRecentFile = useCallback((path: string) => {
    setRecentFilePaths(prev => {
      const filtered = prev.filter(p => p !== path)
      return [path, ...filtered].slice(0, 10)
    })
  }, [])

  // Dialog state
  const [newItemDialog, setNewItemDialog] = useState<NewItemDialogState | null>(null)
  const [newItemName, setNewItemName] = useState('')
  const [deleteDialog, setDeleteDialog] = useState<DeleteDialogState | null>(null)
  const [renameDialog, setRenameDialog] = useState<RenameDialogState | null>(null)
  const [renameName, setRenameName] = useState('')
  const [closeFileDialog, setCloseFileDialog] = useState<CloseFileDialogState | null>(null)
  const [fileDetailsModal, setFileDetailsModal] = useState<{ open: boolean; path: string; name: string } | null>(null)

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

  return {
    openFiles,
    setOpenFiles,
    activeFilePath,
    setActiveFilePath,
    openFilesRef,
    activeFile,
    recentFilePaths,
    newItemDialog,
    setNewItemDialog,
    newItemName,
    setNewItemName,
    deleteDialog,
    setDeleteDialog,
    renameDialog,
    setRenameDialog,
    renameName,
    setRenameName,
    closeFileDialog,
    setCloseFileDialog,
    fileDetailsModal,
    setFileDetailsModal,
    openFile,
    closeFile,
    performCloseFile,
    saveFile,
    createNewItem,
    deleteItem,
    renameItem,
    moveItem,
    showFileDetails,
    downloadFile,
    downloadWorkspace,
  }
}
