/**
 * useChatInputState Hook
 *
 * Manages chat input state including text, history navigation, and temporary storage
 * Provides helpers for input manipulation and history traversal
 */

import { useState, useCallback, useRef } from 'react'

interface UseChatInputStateProps {
  /**
   * Message history for up/down arrow navigation
   */
  messageHistory?: string[]
}

export function useChatInputState({ messageHistory = [] }: UseChatInputStateProps = {}) {
  const [input, setInput] = useState('')
  const [historyIndex, setHistoryIndex] = useState(-1)
  const [tempInput, setTempInput] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

  /**
   * Clear input and reset history navigation
   */
  const clearInput = useCallback(() => {
    setInput('')
    setHistoryIndex(-1)
    setTempInput('')
  }, [])

  /**
   * Navigate through message history (up arrow)
   */
  const navigateHistoryUp = useCallback(() => {
    if (messageHistory.length === 0) return

    if (historyIndex === -1) {
      // Save current input before navigating
      setTempInput(input)
      setHistoryIndex(0)
      setInput(messageHistory[0])
    } else if (historyIndex < messageHistory.length - 1) {
      const newIndex = historyIndex + 1
      setHistoryIndex(newIndex)
      setInput(messageHistory[newIndex])
    }
  }, [historyIndex, input, messageHistory])

  /**
   * Navigate through message history (down arrow)
   */
  const navigateHistoryDown = useCallback(() => {
    if (historyIndex === -1) return

    if (historyIndex === 0) {
      // Restore saved input
      setInput(tempInput)
      setHistoryIndex(-1)
      setTempInput('')
    } else {
      const newIndex = historyIndex - 1
      setHistoryIndex(newIndex)
      setInput(messageHistory[newIndex])
    }
  }, [historyIndex, tempInput, messageHistory])

  /**
   * Focus the input field
   */
  const focusInput = useCallback(() => {
    inputRef.current?.focus()
  }, [])

  /**
   * Check if input is empty
   */
  const isEmpty = input.trim().length === 0

  return {
    input,
    setInput,
    inputRef,
    historyIndex,
    clearInput,
    navigateHistoryUp,
    navigateHistoryDown,
    focusInput,
    isEmpty,
  }
}
