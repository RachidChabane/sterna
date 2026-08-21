/**
 * useAttachmentManagement Hook
 *
 * Manages file and image attachments for chat input
 * Handles adding, removing, and validating attachments
 */

import { useState, useCallback } from 'react'
import type { Attachment } from '@/components/models/types'

export function useAttachmentManagement() {
  const [attachments, setAttachments] = useState<Attachment[]>([])

  /**
   * Add a new attachment
   */
  const addAttachment = useCallback((attachment: Attachment) => {
    setAttachments(prev => [...prev, attachment])
  }, [])

  /**
   * Add multiple attachments
   */
  const addAttachments = useCallback((newAttachments: Attachment[]) => {
    setAttachments(prev => [...prev, ...newAttachments])
  }, [])

  /**
   * Remove an attachment by ID
   */
  const removeAttachment = useCallback((attachmentId: string) => {
    setAttachments(prev => prev.filter(att => att.id !== attachmentId))
  }, [])

  /**
   * Clear all attachments
   */
  const clearAttachments = useCallback(() => {
    setAttachments([])
  }, [])

  /**
   * Check if there are any attachments
   */
  const hasAttachments = attachments.length > 0

  /**
   * Get attachments by type
   */
  const getAttachmentsByType = useCallback((type: 'image' | 'file') => {
    return attachments.filter(att => att.type === type)
  }, [attachments])

  /**
   * Check if attachment type is present
   */
  const hasAttachmentType = useCallback((type: 'image' | 'file') => {
    return attachments.some(att => att.type === type)
  }, [attachments])

  return {
    attachments,
    setAttachments,
    addAttachment,
    addAttachments,
    removeAttachment,
    clearAttachments,
    hasAttachments,
    getAttachmentsByType,
    hasAttachmentType,
  }
}
