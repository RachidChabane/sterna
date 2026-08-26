/**
 * "Save conversation to knowledge base" flow: a confirmation dialog gate,
 * then the actual save call with success/error toasts.
 */
import { useCallback, useState } from 'react'
import { toast } from 'sonner'
import { conversationsAPI } from '@/api/conversations'
import { hasErrorResponse } from '@/utils/errorMessages'

export function useSaveToKnowledgeBase(conversationId: string) {
  const [isSavingToKnowledgeBase, setIsSavingToKnowledgeBase] = useState(false)
  const [showSaveToKBDialog, setShowSaveToKBDialog] = useState(false)

  // Open save to knowledge base confirmation dialog
  const handleSaveToKnowledgeBase = useCallback(() => {
    if (!conversationId) return
    setShowSaveToKBDialog(true)
  }, [conversationId])

  // Actually save conversation to knowledge base
  const confirmSaveToKnowledgeBase = useCallback(async () => {
    if (isSavingToKnowledgeBase || !conversationId) return

    setIsSavingToKnowledgeBase(true)
    try {
      const result = await conversationsAPI.saveToKnowledgeBase(conversationId)
      toast.success('Saved to knowledge base', {
        description: result.filename,
      })
      setShowSaveToKBDialog(false)
    } catch (error) {
      const errorData = hasErrorResponse(error) ? error.response?.data as { existing_document_id?: string; error?: string } | undefined : undefined
      if (errorData?.existing_document_id) {
        toast.error('Already saved', {
          description: errorData.error || 'This conversation is already in your knowledge base',
        })
      } else if (errorData?.error) {
        toast.error('Failed to save', {
          description: errorData.error,
        })
      } else {
        toast.error('Failed to save to knowledge base')
      }
    } finally {
      setIsSavingToKnowledgeBase(false)
    }
  }, [conversationId, isSavingToKnowledgeBase])

  return {
    isSavingToKnowledgeBase,
    showSaveToKBDialog,
    setShowSaveToKBDialog,
    handleSaveToKnowledgeBase,
    confirmSaveToKnowledgeBase,
  }
}
