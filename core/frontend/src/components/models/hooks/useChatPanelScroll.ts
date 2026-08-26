/**
 * Independent-mode scroll behaviour for ChatPanel's Radix ScrollArea:
 * - Smart auto-scroll: positions a new user message at the top of the
 *   viewport when it is sent, then follows streaming content at the bottom.
 * - Scroll clamp: never allows scrolling past the last user message at the
 *   top of the visible area, while still allowing normal scrolling when the
 *   assistant response overflows the viewport.
 */
import { useEffect, useLayoutEffect, useRef } from 'react'
import type { RefObject } from 'react'
import type { Message } from '../types'

export function useChatPanelScroll(scrollAreaRef: RefObject<HTMLDivElement>, messages: Message[]) {
  const prevLastMsgKeyRef = useRef<string | null>(null)

  useLayoutEffect(() => {
    const viewport = scrollAreaRef.current?.querySelector(
      '[data-radix-scroll-area-viewport]'
    ) as HTMLElement | null
    if (!viewport || messages.length === 0) return

    const lastMsg = messages[messages.length - 1]
    const lastMsgKey = `${lastMsg.role}-${lastMsg.timestamp?.getTime()}`
    const isNewMessage = lastMsgKey !== prevLastMsgKeyRef.current
    prevLastMsgKeyRef.current = lastMsgKey

    if (isNewMessage && lastMsg.role === 'user') {
      // New user message — scroll it to the top of the visible area
      requestAnimationFrame(() => {
        const userMsgs = viewport.querySelectorAll('[data-message-role="user"]')
        const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
        if (lastUserEl) {
          const vRect = viewport.getBoundingClientRect()
          const mRect = lastUserEl.getBoundingClientRect()
          const target = viewport.scrollTop + (mRect.top - vRect.top) - 16
          viewport.scrollTo({ top: target, behavior: 'smooth' })
        } else {
          viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' })
        }
      })
    } else {
      // Streaming update or assistant message — keep scrolled to bottom
      viewport.scrollTop = viewport.scrollHeight
    }
  }, [messages, scrollAreaRef])

  useEffect(() => {
    const viewport = scrollAreaRef.current?.querySelector(
      '[data-radix-scroll-area-viewport]'
    ) as HTMLElement | null
    if (!viewport) return

    const paddingBottom = parseFloat(getComputedStyle(viewport).paddingBottom) || 0

    const clampScroll = () => {
      const userMsgs = viewport.querySelectorAll('[data-message-role="user"]')
      const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
      if (!lastUserEl) return

      const allMsgs = viewport.querySelectorAll('[data-message-role]')
      const lastMsgEl = allMsgs[allMsgs.length - 1] as HTMLElement | null
      if (!lastMsgEl) return

      const viewportRect = viewport.getBoundingClientRect()
      const userMsgRect = lastUserEl.getBoundingClientRect()
      const lastMsgRect = lastMsgEl.getBoundingClientRect()

      const lastUserMsgAbsoluteTop = viewport.scrollTop + (userMsgRect.top - viewportRect.top)
      const lastMessageBottom = viewport.scrollTop + (lastMsgRect.bottom - viewportRect.top)
      const effectiveViewport = viewport.clientHeight - paddingBottom

      const maxScroll = Math.max(lastUserMsgAbsoluteTop, lastMessageBottom - effectiveViewport)

      if (viewport.scrollTop > maxScroll) {
        viewport.scrollTop = maxScroll
      }
    }

    viewport.addEventListener('scroll', clampScroll)
    return () => viewport.removeEventListener('scroll', clampScroll)
  }, [scrollAreaRef])
}
