import { useState, useRef, useEffect } from 'react'

/**
 * Smooth streaming text hook - buffers incoming text and reveals it
 * character-by-character for a typewriter effect.
 *
 * Returns { displayedText, isRevealing } so the parent can know
 * when there's still buffered text being revealed after streaming ends.
 *
 * Accepts an optional stopRef — when set to true, the typewriter
 * freezes at the current position (used for the stop button).
 */
export function useStreamingText(
  targetText: string,
  isStreaming: boolean,
  stopRef?: { current: boolean },
  tickInterval: number = 6
) {
  const [displayedText, setDisplayedText] = useState(targetText)
  const [isRevealing, setIsRevealing] = useState(false)
  const displayedRef = useRef(targetText)
  const targetRef = useRef(targetText)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isStreamingRef = useRef(isStreaming)
  const wasStreamingRef = useRef(false)

  // Keep refs in sync
  targetRef.current = targetText
  isStreamingRef.current = isStreaming
  if (isStreaming) wasStreamingRef.current = true

  // Single reveal loop — runs while streaming OR catching up after streaming ends
  useEffect(() => {
    // Never streamed → nothing to reveal
    if (!isStreaming && !wasStreamingRef.current) return

    const tick = () => {
      // Stop button pressed → freeze at current position
      if (stopRef?.current) {
        setIsRevealing(false)
        timerRef.current = null
        return
      }

      const target = targetRef.current
      const current = displayedRef.current

      if (current.length < target.length) {
        const newText = target.slice(0, current.length + 1)
        displayedRef.current = newText
        setDisplayedText(newText)
        setIsRevealing(true)
        timerRef.current = setTimeout(tick, tickInterval)
      } else if (!isStreamingRef.current) {
        // Caught up and streaming is done — stop
        setIsRevealing(false)
        timerRef.current = null
      } else {
        // Caught up but still streaming — keep polling
        setIsRevealing(false)
        timerRef.current = setTimeout(tick, tickInterval)
      }
    }

    timerRef.current = setTimeout(tick, tickInterval)
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [isStreaming, tickInterval])

  return { displayedText, isRevealing }
}
