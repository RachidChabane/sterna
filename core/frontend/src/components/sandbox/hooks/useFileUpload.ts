/**
 * Custom hook for file upload: drag & drop, the hidden file input, and
 * upload progress/cancellation. Owns the drag-counter, cancellation, and
 * uploaded-root-paths bookkeeping needed to roll back a cancelled upload.
 */

import { useRef, useState } from 'react'
import { fsAPI } from '@/api/fs'
import { toErrorMessage } from '@/utils/errorMessages'
import {
  MAX_FILE_SIZE_BYTES,
  MAX_FILE_SIZE_LABEL,
  getRootUploadPath,
  readDirectoryEntries,
  readFileContent,
  validateFileType,
} from '../fileUploadUtils'

interface ToastFn {
  (options: { title: string; description?: string; variant?: 'default' | 'destructive' }): void
}

interface UseFileUploadParams {
  userId?: string
  projectId: string
  toast: ToastFn
  loadFileTree: () => Promise<void>
}

export function useFileUpload({ userId, projectId, toast, loadFileTree }: UseFileUploadParams) {
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
      await loadFileTree()

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
      await loadFileTree()

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
        await loadFileTree()

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

  return {
    isDraggingFiles,
    isUploading,
    uploadProgress,
    fileInputRef,
    cancelUpload,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    handleImportClick,
    handleFileInputChange,
  }
}
