/**
 * Detects whether the current chat has workspace files, to drive the
 * "Open IDE" affordance in the header. A cloned repo counts immediately;
 * otherwise the workspace is probed after each new tool message.
 */
import { useEffect, useMemo, useState } from 'react'
import { fsAPI } from '@/api/fs'
import type { ClonedRepo } from '@/store/projectPanelStore'
import type { Message } from '../types'

interface UseWorkspaceDetectionParams {
  messages: Message[]
  clonedRepo: ClonedRepo | null
  userId: string | undefined
  chatId: string | undefined
}

export function useWorkspaceDetection({ messages, clonedRepo, userId, chatId }: UseWorkspaceDetectionParams): boolean {
  const [hasWorkspace, setHasWorkspace] = useState(false)

  const toolMessageCount = useMemo(
    () => messages.filter(m => m.role === 'tool').length,
    [messages]
  )

  useEffect(() => {
    setHasWorkspace(false)

    if (clonedRepo) {
      setHasWorkspace(true)
      return
    }

    if (!userId || !chatId) return
    let cancelled = false
    fsAPI.getWorkspaceInfo({ user_id: userId.toString(), chat_id: chatId })
      .then(info => {
        if (!cancelled) setHasWorkspace(info.exists && (info.file_count ?? 0) > 0)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [clonedRepo, userId, chatId, toolMessageCount])

  return hasWorkspace
}
