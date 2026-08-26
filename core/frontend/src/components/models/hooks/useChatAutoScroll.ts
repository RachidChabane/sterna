/**
 * Ctrl+L scroll behaviour for the immersive chat transcript:
 * 1. User sends a message → reset view: user message pinned at the top,
 *    empty space below.
 * 2. Response streams in → view stays pinned (user msg at top) until
 *    content fills the viewport.
 * 3. Once content overflows the viewport → switch to follow-bottom
 *    (tracking real content).
 * 4. Generation ends → normal follow-bottom for subsequent interactions.
 *
 * Also owns the scroll clamp (never scroll past the last user message
 * unless the response overflows) and the dynamic spacer that makes the
 * pin-to-top behaviour possible without a layout jump.
 */
import { useCallback, useEffect, useLayoutEffect, useRef } from 'react'
import type { Message } from '../types'

interface UseChatAutoScrollParams {
  messages: Message[]
  isGenerating: boolean
  conversationId: string
}

export function useChatAutoScroll({ messages, isGenerating, conversationId }: UseChatAutoScrollParams) {
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const contentEndRef = useRef<HTMLDivElement>(null)
  const prevLastMsgKeyRef = useRef<string | null>(null)
  // 'pin' = user message pinned at top, 'follow' = auto-scroll to bottom
  const scrollModeRef = useRef<'pin' | 'follow'>('follow')
  const spacerActiveRef = useRef(false)
  const spacerRef = useRef<HTMLDivElement>(null)
  const pinnedScrollTopRef = useRef<number>(0)
  const pinAnimatingRef = useRef(false)
  const pinAnimFrameRef = useRef<number>(0)
  // User scroll detection — stops auto-scroll when user scrolls manually
  const userHasScrolledRef = useRef(false)

  // Detect user scroll via wheel/touch — these are always user-initiated (no race conditions)
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    const onUserScroll = () => { userHasScrolledRef.current = true }

    container.addEventListener('wheel', onUserScroll, { passive: true })
    container.addEventListener('touchmove', onUserScroll, { passive: true })
    return () => {
      container.removeEventListener('wheel', onUserScroll)
      container.removeEventListener('touchmove', onUserScroll)
    }
  }, [])

  // Scroll clamp: never allow scrolling past the last user message at top of visible area,
  // but allow normal scrolling when the assistant response overflows the viewport.
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    const paddingBottom = parseFloat(getComputedStyle(container).paddingBottom) || 0

    const clampScroll = () => {
      const userMsgs = container.querySelectorAll('[data-message-role="user"]')
      const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
      if (!lastUserEl) return

      const allMsgs = container.querySelectorAll('[data-message-role]')
      const lastMsgEl = allMsgs[allMsgs.length - 1] as HTMLElement | null
      if (!lastMsgEl) return

      const containerRect = container.getBoundingClientRect()
      const userMsgRect = lastUserEl.getBoundingClientRect()
      const lastMsgRect = lastMsgEl.getBoundingClientRect()

      const lastUserMsgAbsoluteTop = container.scrollTop + (userMsgRect.top - containerRect.top)
      const lastMessageBottom = container.scrollTop + (lastMsgRect.bottom - containerRect.top)
      const effectiveViewport = container.clientHeight - paddingBottom

      const maxScroll = Math.max(lastUserMsgAbsoluteTop, lastMessageBottom - effectiveViewport)

      if (container.scrollTop > maxScroll) {
        container.scrollTop = maxScroll
      }
    }

    container.addEventListener('scroll', clampScroll)
    return () => container.removeEventListener('scroll', clampScroll)
  }, [])

  // Reset spacer when switching conversations
  useEffect(() => {
    spacerActiveRef.current = false
    if (spacerRef.current) spacerRef.current.style.height = '0px'
  }, [conversationId])

  // Size the spacer so the user can scroll the last user message to the top
  // but never into empty space. As the response grows, spacer shrinks by
  // the same amount — keeping scrollHeight constant (no jumps).
  //
  // Formula: spacerH = max(0, visibleH - (contentBottom - lastUserMsgTop))
  //   visibleH = clientHeight - 176  (176 = pb-44, input zone overlap)
  //   When response overflows visibleH → spacer = 0 → normal scrolling
  const updateSpacerHeight = useCallback(() => {
    const container = scrollContainerRef.current
    const spacer = spacerRef.current
    if (!container || !spacer) return

    if (!spacerActiveRef.current) {
      spacer.style.height = '0px'
      return
    }

    const contentEndEl = contentEndRef.current
    if (!contentEndEl) return

    const containerRect = container.getBoundingClientRect()

    // Content bottom offset (where real content ends, before spacer)
    const endRect = contentEndEl.getBoundingClientRect()
    const contentBottomOffset = endRect.top - containerRect.top + container.scrollTop

    // Last user message top offset
    const userMsgs = container.querySelectorAll('[data-message-role="user"]')
    const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
    if (!lastUserEl) { spacer.style.height = '0px'; return }

    const userRect = lastUserEl.getBoundingClientRect()
    const lastUserOffset = userRect.top - containerRect.top + container.scrollTop

    // Height of content from user message top to content end
    const contentBelowUser = contentBottomOffset - lastUserOffset

    // Measure total bottom padding below the spacer:
    // scrollHeight = contentBottomOffset + currentSpacerH + totalBottomPadding
    const currentSpacerH = spacer.offsetHeight
    const totalBottomPadding = container.scrollHeight - contentBottomOffset - currentSpacerH
    const visibleHeight = container.clientHeight - totalBottomPadding

    const needed = visibleHeight - contentBelowUser
    spacer.style.height = `${Math.max(0, needed)}px`
  }, [])

  useLayoutEffect(() => {
    const container = scrollContainerRef.current
    if (!container || messages.length === 0) return

    const lastMsg = messages[messages.length - 1]
    const lastMsgKey = `${lastMsg.role}-${lastMsg.timestamp?.getTime()}`
    const isNewMessage = lastMsgKey !== prevLastMsgKeyRef.current
    prevLastMsgKeyRef.current = lastMsgKey

    // Detect new user message → enter pin mode with smooth animation
    if (isNewMessage && lastMsg.role === 'user') {
      spacerActiveRef.current = true
      updateSpacerHeight()
      scrollModeRef.current = 'pin'
      userHasScrolledRef.current = false

      // Cancel any existing animation
      if (pinAnimFrameRef.current) {
        cancelAnimationFrame(pinAnimFrameRef.current)
        pinAnimFrameRef.current = 0
      }

      // Start smooth rAF animation to scroll user message to top
      const userMsgs = container.querySelectorAll('[data-message-role="user"]')
      const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
      if (lastUserEl) {
        const cRect = container.getBoundingClientRect()
        const mRect = lastUserEl.getBoundingClientRect()
        const startScroll = container.scrollTop
        const targetScroll = startScroll + (mRect.top - cRect.top) - 16
        const duration = 350

        pinAnimatingRef.current = true
        const startTime = performance.now()

        const animate = (now: number) => {
          // If user scrolled during animation, cancel it
          if (userHasScrolledRef.current) {
            pinAnimatingRef.current = false
            pinAnimFrameRef.current = 0
            scrollModeRef.current = 'follow'
            return
          }
          const elapsed = now - startTime
          const progress = Math.min(1, elapsed / duration)
          const eased = 1 - Math.pow(1 - progress, 3)
          container.scrollTop = startScroll + (targetScroll - startScroll) * eased

          if (progress < 1) {
            pinAnimFrameRef.current = requestAnimationFrame(animate)
          } else {
            pinAnimatingRef.current = false
            pinnedScrollTopRef.current = targetScroll
            pinAnimFrameRef.current = 0
          }
        }

        pinAnimFrameRef.current = requestAnimationFrame(animate)
      }
      return
    }

    updateSpacerHeight()

    // --- PIN MODE: keep user message at top ---
    if (scrollModeRef.current === 'pin') {
      if (pinAnimatingRef.current) return
      // User scrolled manually → release pin
      if (userHasScrolledRef.current) {
        scrollModeRef.current = 'follow'
        return
      }

      const userMsgs = container.querySelectorAll('[data-message-role="user"]')
      const lastUserEl = userMsgs[userMsgs.length - 1] as HTMLElement | null
      if (lastUserEl) {
        const cRect = container.getBoundingClientRect()
        const mRect = lastUserEl.getBoundingClientRect()
        const distFromTop = mRect.top - cRect.top

        // Correct any drift (tight 1px threshold)
        if (Math.abs(distFromTop - 16) > 1) {
          const target = container.scrollTop + distFromTop - 16
          pinnedScrollTopRef.current = target
          container.scrollTop = target
          return
        }
      }

      // Check if real content has overflowed past the viewport → switch to follow
      const contentEnd = contentEndRef.current
      if (contentEnd) {
        const cRect = container.getBoundingClientRect()
        const endRect = contentEnd.getBoundingClientRect()
        if (endRect.top > cRect.bottom - 40) {
          scrollModeRef.current = 'follow'
          // Fall through to follow logic below
        } else {
          if (!isGenerating) scrollModeRef.current = 'follow'
          return
        }
      } else {
        if (!isGenerating) scrollModeRef.current = 'follow'
        return
      }
    }

    // --- FOLLOW MODE: keep content bottom visible ---
    // Skip if user has scrolled — let them read freely
    if (userHasScrolledRef.current) {
      // Re-enable if user scrolled back near bottom
      const distFromBottom = container.scrollHeight - container.clientHeight - container.scrollTop
      if (distFromBottom >= 50) return
      userHasScrolledRef.current = false
    }

    const contentEnd = contentEndRef.current
    if (isGenerating && contentEnd) {
      const cRect = container.getBoundingClientRect()
      const endRect = contentEnd.getBoundingClientRect()
      if (endRect.bottom > cRect.bottom) {
        container.scrollTop += (endRect.bottom - cRect.bottom) + 16
      }
    } else if (!isGenerating) {
      container.scrollTop = container.scrollHeight - container.clientHeight
    }
  }, [messages, isGenerating])

  return { scrollContainerRef, contentEndRef, spacerRef }
}
