/**
 * Hydrates missing file/image attachment metadata and content from the
 * local attachment cache, so attachments survive a page refresh even when
 * their in-memory File/base64/preview data was stripped before persisting.
 * Re-runs whenever the compose-area attachments or the chat's own messages
 * change.
 */
import { useEffect, useState } from 'react'
import { cacheGet, type CachedAttachment } from '@/utils/attachmentCache'
import type { Attachment, Message } from '../types'

function needsHydration(att: Attachment): boolean {
  if (att.type === 'file') {
    return !att.file || (!att.base64 && !att.textContent)
  }
  if (att.type === 'image') {
    // After refresh, images may miss base64/preview (sanitized). Try to hydrate.
    return !(att as any).base64 && !(att as any).preview
  }
  return false
}

export function useAttachmentCacheHydration(messages: Message[], attachments: Attachment[]) {
  const [cachedAttachments, setCachedAttachments] = useState<Record<string, CachedAttachment>>({})

  useEffect(() => {
    const loadCache = async () => {
      const toCheck: string[] = []
      // attachments in compose area
      attachments.forEach(att => {
        if (needsHydration(att)) toCheck.push(att.id)
      })
      // attachments inside messages
      messages.forEach(m => {
        const atts = (m.attachments || []) as Attachment[]
        atts.forEach(att => {
          if (needsHydration(att)) toCheck.push(att.id)
        })
      })
      if (toCheck.length === 0) return
      const entries: Record<string, CachedAttachment> = {}
      for (const id of toCheck) {
        try {
          const cached = await cacheGet(id)
          if (cached) entries[id] = cached
        } catch {}
      }
      if (Object.keys(entries).length > 0) {
        setCachedAttachments(prev => ({ ...prev, ...entries }))
      }
    }
    loadCache()
    // Re-run when messages or attachments change
  }, [messages, attachments])

  return cachedAttachments
}
