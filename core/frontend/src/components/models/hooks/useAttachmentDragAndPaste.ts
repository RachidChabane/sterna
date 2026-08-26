/**
 * Drag-and-drop and clipboard-paste attachment intake for the message
 * composer: gates on auth/loading/disabled state, builds attachments from
 * the dropped/pasted files, and reports security warnings and a summary
 * toast for what was added.
 */
import { useCallback, useState } from 'react'
import { getAuthModalVariant } from '@/lib/sessionDetection'
import { buildAttachmentsFromFiles, extractFilesFromClipboard, extractFilesFromDataTransfer, type BuildResultCounts } from '@/utils/attachmentHandlers'
import type { useToast } from '@/hooks/use-toast'
import type { Attachment } from '../types'

type ToastFn = ReturnType<typeof useToast>['toast']

const MAX_ATTACHMENTS = 8

interface UseAttachmentDragAndPasteParams {
  isAuthenticated: boolean
  isLoading: boolean
  disabledChat: boolean
  attachmentCount: number
  addAttachments: (attachments: Attachment[]) => void
  toast: ToastFn
  openModal: (variant: 'session-expired' | 'sign-up-prompt', redirectPath: string) => void
}

function showSecurityWarnings(counts: BuildResultCounts, toast: ToastFn) {
  if (!counts.securityWarnings || counts.securityWarnings.length === 0) return
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

function summaryParts(counts: BuildResultCounts): string[] {
  const parts: string[] = []
  if (counts.imagesAdded) parts.push(`${counts.imagesAdded} image${counts.imagesAdded > 1 ? 's' : ''}`)
  if (counts.pdfsAdded) parts.push(`${counts.pdfsAdded} PDF${counts.pdfsAdded > 1 ? 's' : ''}`)
  if (counts.officeDocsAdded) parts.push(`${counts.officeDocsAdded} Office doc${counts.officeDocsAdded > 1 ? 's' : ''}`)
  if (counts.textsAdded) parts.push(`${counts.textsAdded} file${counts.textsAdded > 1 ? 's' : ''}`)
  return parts
}

export function useAttachmentDragAndPaste({
  isAuthenticated,
  isLoading,
  disabledChat,
  attachmentCount,
  addAttachments,
  toast,
  openModal,
}: UseAttachmentDragAndPasteParams) {
  const [isDragOver, setIsDragOver] = useState(false)

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    if (!isAuthenticated || isLoading || disabledChat) return
    setIsDragOver(true)
  }, [isAuthenticated, isLoading, disabledChat])

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragOver(false)
  }, [])

  const handleDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragOver(false)
    if (!isAuthenticated) {
      toast({ title: 'Authentication required', description: 'Please sign in to attach files', variant: 'destructive' })
      const variant = getAuthModalVariant()
      openModal(variant, window.location.pathname)
      return
    }
    if (isLoading || disabledChat) return
    const files = extractFilesFromDataTransfer(e.dataTransfer)
    if (!files.length) return
    const { attachments: newAtts, counts } = await buildAttachmentsFromFiles(files, { currentCount: attachmentCount, maxCount: MAX_ATTACHMENTS })
    if (newAtts.length) addAttachments(newAtts)

    showSecurityWarnings(counts, toast)

    // Show summary of successfully added files
    const total = newAtts.length
    if (total > 0 || counts.errors > 0 || counts.blocked > 0) {
      const parts = summaryParts(counts)

      if (parts.length > 0) {
        const totalFailed = counts.errors + counts.blocked
        const desc = `${parts.join(' + ')} added${totalFailed ? ` • ${totalFailed} failed` : ''}${counts.skippedOverflow ? ` • ${counts.skippedOverflow} skipped (limit)` : ''}`
        toast({ title: 'Attachments added', description: desc })
      }
    }
  }, [isAuthenticated, isLoading, disabledChat, attachmentCount, addAttachments, toast, openModal])

  const handlePaste = useCallback(async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!isAuthenticated || isLoading || disabledChat) return
    const files = extractFilesFromClipboard(e)
    if (!files.length) return
    // Prevent inserting binary data as text
    e.preventDefault()
    const { attachments: newAtts, counts } = await buildAttachmentsFromFiles(files, { currentCount: attachmentCount, maxCount: MAX_ATTACHMENTS })
    if (newAtts.length) addAttachments(newAtts)

    showSecurityWarnings(counts, toast)

    // Show summary of successfully added files
    const parts = summaryParts(counts)

    if (parts.length > 0 || (counts.errors + counts.blocked) > 0) {
      const totalFailed = counts.errors + counts.blocked
      toast({
        title: 'Attachments added',
        description: parts.length
          ? `${parts.join(' + ')} added${totalFailed ? ` • ${totalFailed} failed` : ''}`
          : 'No supported items found'
      })
    }
  }, [isAuthenticated, isLoading, disabledChat, attachmentCount, addAttachments, toast])

  return { isDragOver, handleDragOver, handleDragLeave, handleDrop, handlePaste }
}
