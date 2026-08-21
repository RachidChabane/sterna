/**
 * useComparisonInput Hook
 *
 * Manages shared input state for ModelComparisonPage:
 * - Shared input text and history navigation
 * - Drag & drop file handling
 * - Paste event handling
 * - Keyboard shortcuts
 */

import { useState, useRef, useCallback } from 'react'
import type { Attachment } from '@/components/models/types'
import { buildAttachmentsFromFiles, extractFilesFromClipboard, extractFilesFromDataTransfer } from '@/utils/attachmentHandlers'
import { useToast } from './use-toast'
import { isPDFFile, isOfficeFile } from '@/utils/fileUtils'

interface UseComparisonInputProps {
  userMessageHistory?: string[]
  onAddAttachments: (newAttachments: Attachment[]) => void
  currentAttachmentsCount?: number
  hasVisionSupport?: boolean  // At least one active model supports vision
  hasPDFSupport?: boolean      // At least one active model supports PDF
  firstVisionModelName?: string  // Name of first model with vision (even if disabled)
  firstPDFModelName?: string     // Name of first model with PDF support (even if disabled)
  isFirstVisionModelDisabled?: boolean
  isFirstPDFModelDisabled?: boolean
}

interface UseComparisonInputReturn {
  // Input state
  sharedInput: string
  setSharedInput: (input: string) => void
  sharedInputRef: React.RefObject<HTMLTextAreaElement | null>

  // History navigation
  historyIndex: number
  tempInput: string
  navigateHistoryUp: () => void
  navigateHistoryDown: () => void

  // Clear input
  clearInput: () => void

  // Drag & drop state
  isDropOverInput: boolean
  handleSharedDragOver: (e: React.DragEvent<HTMLDivElement>) => void
  handleSharedDragLeave: (e: React.DragEvent<HTMLDivElement>) => void
  handleSharedDrop: (e: React.DragEvent<HTMLDivElement>) => Promise<void>

  // Paste handling
  handleSharedPaste: (e: React.ClipboardEvent<HTMLTextAreaElement>) => Promise<void>

  // Keyboard handling
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>, onSend: () => void) => void
}

export function useComparisonInput({
  userMessageHistory = [],
  onAddAttachments,
  currentAttachmentsCount = 0,
  hasVisionSupport = false,
  hasPDFSupport = false,
  firstVisionModelName,
  firstPDFModelName,
  isFirstVisionModelDisabled = false,
  isFirstPDFModelDisabled = false,
}: UseComparisonInputProps): UseComparisonInputReturn {
  const [sharedInput, setSharedInput] = useState('')
  const [historyIndex, setHistoryIndex] = useState(-1)
  const [tempInput, setTempInput] = useState('')
  const [isDropOverInput, setIsDropOverInput] = useState(false)
  const sharedInputRef = useRef<HTMLTextAreaElement>(null)
  const { toast } = useToast()

  // Navigate up in message history (older messages)
  const navigateHistoryUp = useCallback(() => {
    if (userMessageHistory.length === 0) return

    if (historyIndex === -1) {
      // First time navigating, save current input
      setTempInput(sharedInput)
      setHistoryIndex(0)
      setSharedInput(userMessageHistory[0])
    } else if (historyIndex < userMessageHistory.length - 1) {
      // Navigate to older message
      const newIndex = historyIndex + 1
      setHistoryIndex(newIndex)
      setSharedInput(userMessageHistory[newIndex])
    }
  }, [historyIndex, sharedInput, userMessageHistory])

  // Navigate down in message history (newer messages)
  const navigateHistoryDown = useCallback(() => {
    if (historyIndex === -1) return

    if (historyIndex > 0) {
      // Navigate to newer message
      const newIndex = historyIndex - 1
      setHistoryIndex(newIndex)
      setSharedInput(userMessageHistory[newIndex])
    } else {
      // Back to current input
      setHistoryIndex(-1)
      setSharedInput(tempInput)
      setTempInput('')
    }
  }, [historyIndex, tempInput, userMessageHistory])

  // Clear input and reset history
  const clearInput = useCallback(() => {
    setSharedInput('')
    setHistoryIndex(-1)
    setTempInput('')
  }, [])

  // Drag & drop handlers
  const handleSharedDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDropOverInput(true)
  }, [])

  const handleSharedDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDropOverInput(false)
  }, [])

  const handleSharedDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDropOverInput(false)

    const files = extractFilesFromDataTransfer(e.dataTransfer)
    if (files.length === 0) return

    // Check if any file type is unsupported by active models
    const hasImages = files.some(f => f.type.startsWith('image/'))
    const hasPDFs = files.some(f => isPDFFile(f))
    const hasOfficeFiles = files.some(f => isOfficeFile(f))
    const hasDocumentFiles = hasPDFs || hasOfficeFiles

    if (hasImages && !hasVisionSupport) {
      let description = 'None of the active models support image inputs.'
      if (isFirstVisionModelDisabled && firstVisionModelName) {
        description += ` ${firstVisionModelName} supports images but is currently disabled. Please enable it to use image inputs.`
      } else {
        description += ' Please select a model with vision support.'
      }
      toast({
        title: 'Images not supported',
        description,
        variant: 'destructive'
      })
      return
    }

    if (hasDocumentFiles && !hasPDFSupport) {
      // Determine the appropriate message based on file types
      let fileTypeDescription = ''
      let titleText = ''
      if (hasPDFs && hasOfficeFiles) {
        fileTypeDescription = 'document file inputs'
        titleText = 'Document files not supported'
      } else if (hasPDFs) {
        fileTypeDescription = 'PDF file inputs'
        titleText = 'PDFs not supported'
      } else {
        fileTypeDescription = 'Office document inputs'
        titleText = 'Office documents not supported'
      }

      let description = `None of the active models support ${fileTypeDescription}.`
      if (isFirstPDFModelDisabled && firstPDFModelName) {
        description += ` ${firstPDFModelName} supports these files but is currently disabled. Please enable it to use document files.`
      } else {
        description += ' Please select a model with file support.'
      }
      toast({
        title: titleText,
        description,
        variant: 'destructive'
      })
      return
    }

    const { attachments: newAttachments, counts } = await buildAttachmentsFromFiles(files, {
      currentCount: currentAttachmentsCount,
      maxCount: 8
    })

    // Show security warnings first
    if (counts.securityWarnings && counts.securityWarnings.length > 0) {
      for (const warning of counts.securityWarnings) {
        if (warning.startsWith('BLOCKED:')) {
          toast({
            title: 'Security Warning',
            description: warning.replace('BLOCKED: ', ''),
            variant: 'destructive'
          })
        } else if (warning.startsWith('INVALID:')) {
          toast({
            title: 'Invalid File',
            description: warning.replace('INVALID: ', ''),
            variant: 'destructive'
          })
        } else if (warning.startsWith('WARNING:')) {
          toast({
            title: 'File Type Warning',
            description: warning.replace('WARNING: ', ''),
            variant: 'default'
          })
        }
      }
    }

    if (newAttachments.length) onAddAttachments(newAttachments)
  }, [onAddAttachments, currentAttachmentsCount, hasVisionSupport, hasPDFSupport, toast, firstVisionModelName, firstPDFModelName, isFirstVisionModelDisabled, isFirstPDFModelDisabled])

  // Paste handler
  const handleSharedPaste = useCallback(async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = extractFilesFromClipboard(e)
    if (files.length === 0) return

    // Check if any file type is unsupported by active models
    const hasImages = files.some(f => f.type.startsWith('image/'))
    const hasPDFs = files.some(f => isPDFFile(f))
    const hasOfficeFiles = files.some(f => isOfficeFile(f))
    const hasDocumentFiles = hasPDFs || hasOfficeFiles

    if (hasImages && !hasVisionSupport) {
      e.preventDefault()
      let description = 'None of the active models support image inputs.'
      if (isFirstVisionModelDisabled && firstVisionModelName) {
        description += ` ${firstVisionModelName} supports images but is currently disabled. Please enable it to use image inputs.`
      } else {
        description += ' Please select a model with vision support.'
      }
      toast({
        title: 'Images not supported',
        description,
        variant: 'destructive'
      })
      return
    }

    if (hasDocumentFiles && !hasPDFSupport) {
      e.preventDefault()

      // Determine the appropriate message based on file types
      let fileTypeDescription = ''
      let titleText = ''
      if (hasPDFs && hasOfficeFiles) {
        fileTypeDescription = 'document file inputs'
        titleText = 'Document files not supported'
      } else if (hasPDFs) {
        fileTypeDescription = 'PDF file inputs'
        titleText = 'PDFs not supported'
      } else {
        fileTypeDescription = 'Office document inputs'
        titleText = 'Office documents not supported'
      }

      let description = `None of the active models support ${fileTypeDescription}.`
      if (isFirstPDFModelDisabled && firstPDFModelName) {
        description += ` ${firstPDFModelName} supports these files but is currently disabled. Please enable it to use document files.`
      } else {
        description += ' Please select a model with file support.'
      }
      toast({
        title: titleText,
        description,
        variant: 'destructive'
      })
      return
    }

    e.preventDefault()
    const { attachments: newAttachments, counts } = await buildAttachmentsFromFiles(files, {
      currentCount: currentAttachmentsCount,
      maxCount: 8
    })

    // Show security warnings first
    if (counts.securityWarnings && counts.securityWarnings.length > 0) {
      for (const warning of counts.securityWarnings) {
        if (warning.startsWith('BLOCKED:')) {
          toast({
            title: 'Security Warning',
            description: warning.replace('BLOCKED: ', ''),
            variant: 'destructive'
          })
        } else if (warning.startsWith('INVALID:')) {
          toast({
            title: 'Invalid File',
            description: warning.replace('INVALID: ', ''),
            variant: 'destructive'
          })
        } else if (warning.startsWith('WARNING:')) {
          toast({
            title: 'File Type Warning',
            description: warning.replace('WARNING: ', ''),
            variant: 'default'
          })
        }
      }
    }

    if (newAttachments.length) onAddAttachments(newAttachments)
  }, [onAddAttachments, currentAttachmentsCount, hasVisionSupport, hasPDFSupport, toast, firstVisionModelName, firstPDFModelName, isFirstVisionModelDisabled, isFirstPDFModelDisabled])

  // Keyboard handler
  const handleKeyDown = useCallback((
    e: React.KeyboardEvent<HTMLTextAreaElement>,
    onSend: () => void
  ) => {
    // Send on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
    // Navigate history with Up/Down arrows - only if cursor is on first/last line
    else if (e.key === 'ArrowUp' && !e.shiftKey) {
      const textarea = e.currentTarget
      const cursorPosition = textarea.selectionStart
      const textBeforeCursor = textarea.value.substring(0, cursorPosition)

      // Only navigate history if cursor is on the first line (no newlines before cursor)
      if (!textBeforeCursor.includes('\n')) {
        e.preventDefault()
        navigateHistoryUp()
      }
    }
    else if (e.key === 'ArrowDown' && !e.shiftKey) {
      const textarea = e.currentTarget
      const cursorPosition = textarea.selectionStart
      const textAfterCursor = textarea.value.substring(cursorPosition)

      // Only navigate history if cursor is on the last line (no newlines after cursor)
      if (!textAfterCursor.includes('\n')) {
        e.preventDefault()
        navigateHistoryDown()
      }
    }
  }, [navigateHistoryUp, navigateHistoryDown])

  return {
    sharedInput,
    setSharedInput,
    sharedInputRef,
    historyIndex,
    tempInput,
    navigateHistoryUp,
    navigateHistoryDown,
    clearInput,
    isDropOverInput,
    handleSharedDragOver,
    handleSharedDragLeave,
    handleSharedDrop,
    handleSharedPaste,
    handleKeyDown,
  }
}
