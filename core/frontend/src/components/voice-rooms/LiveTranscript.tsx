/**
 * LiveTranscript - Real-time synced transcript display for voice rooms
 *
 * Shows words as they're being spoken, synced with audio playback.
 * Displays one line at a time, sliding up when the line is full.
 * Uses alignment data from ElevenLabs TTS for precise word timing.
 * Supports basic inline markdown (bold, italic, code).
 */

import { useEffect, useState, useRef, useMemo } from 'react'
import { cn } from '@/lib/utils'
import useVoiceRoomStore from '@/store/voiceRoomStore'
import { getAgentColor } from './AgentPresence'
import type { VoiceAgent } from '@/types/voiceRoom'

/**
 * Parses inline markdown and returns React elements
 * Supports: **bold**, *italic*, `code`
 */
function parseInlineMarkdown(text: string, baseClassName: string): React.ReactNode {
  const elements: React.ReactNode[] = []
  let remaining = text
  let key = 0

  while (remaining.length > 0) {
    // Check for **bold**
    const boldMatch = remaining.match(/^\*\*(.+?)\*\*/)
    if (boldMatch) {
      elements.push(
        <strong key={key++} className={baseClassName}>
          {boldMatch[1]}
        </strong>
      )
      remaining = remaining.slice(boldMatch[0].length)
      continue
    }

    // Check for *italic* (but not **)
    const italicMatch = remaining.match(/^\*([^*]+?)\*/)
    if (italicMatch) {
      elements.push(
        <em key={key++} className={baseClassName}>
          {italicMatch[1]}
        </em>
      )
      remaining = remaining.slice(italicMatch[0].length)
      continue
    }

    // Check for `code`
    const codeMatch = remaining.match(/^`([^`]+?)`/)
    if (codeMatch) {
      elements.push(
        <code key={key++} className={cn(baseClassName, 'bg-white/10 px-1 rounded text-xs')}>
          {codeMatch[1]}
        </code>
      )
      remaining = remaining.slice(codeMatch[0].length)
      continue
    }

    // No match - take the next character as plain text
    // Batch consecutive plain characters
    let plainEnd = 1
    while (plainEnd < remaining.length) {
      const next = remaining[plainEnd]
      if (next === '*' || next === '`') break
      plainEnd++
    }
    elements.push(
      <span key={key++} className={baseClassName}>
        {remaining.slice(0, plainEnd)}
      </span>
    )
    remaining = remaining.slice(plainEnd)
  }

  return elements.length === 1 ? elements[0] : <>{elements}</>
}

interface LiveTranscriptProps {
  className?: string
  isDark?: boolean
  wordsPerLine?: number
  agents?: VoiceAgent[]
}

export function LiveTranscript({ className, isDark = true, wordsPerLine = 8, agents = [] }: LiveTranscriptProps) {
  const { liveTranscript } = useVoiceRoomStore()
  const [currentWordIndex, setCurrentWordIndex] = useState(-1)
  const [currentLineStart, setCurrentLineStart] = useState(0)
  const [isExiting, setIsExiting] = useState(false)
  const animationFrameRef = useRef<number | undefined>(undefined)
  const prevLineStartRef = useRef(0)

  // Get current agent info and color
  const currentAgent = useMemo(() => {
    if (!liveTranscript?.agentId || agents.length === 0) return null
    const agentIndex = agents.findIndex(a => a.id === liveTranscript.agentId)
    if (agentIndex < 0) return null
    const agent = agents[agentIndex]

    // Use custom color if set, otherwise use auto-assigned color
    let colorHex: string
    if (agent.color) {
      colorHex = agent.color
    } else {
      const rgb = getAgentColor(agent.id, agentIndex)
      colorHex = `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`
    }

    return { name: agent.display_name, color: colorHex }
  }, [liveTranscript?.agentId, agents])

  // Update current word based on playback time
  useEffect(() => {
    // Skip word tracking if no transcript or no word timing (OpenAI case)
    if (!liveTranscript || liveTranscript.words.length === 0) {
      setCurrentWordIndex(-1)
      setCurrentLineStart(0)
      prevLineStartRef.current = 0
      setIsExiting(false)
      return
    }

    const updateCurrentWord = () => {
      const elapsed = Date.now() - liveTranscript.audioStartTime

      // Find the current word based on elapsed time
      let newIndex = -1
      for (let i = 0; i < liveTranscript.words.length; i++) {
        const word = liveTranscript.words[i]
        if (elapsed >= word.startMs - 50) { // Slightly ahead for smoother display
          newIndex = i
        }
      }

      setCurrentWordIndex(newIndex)

      // Calculate which line we should be on
      if (newIndex >= 0) {
        const newLineStart = Math.floor(newIndex / wordsPerLine) * wordsPerLine

        // Check if we need to transition to a new line
        if (newLineStart > prevLineStartRef.current) {
          // Trigger exit animation
          setIsExiting(true)
          setTimeout(() => {
            setCurrentLineStart(newLineStart)
            setIsExiting(false)
            prevLineStartRef.current = newLineStart
          }, 250) // Animation duration
        }
      }

      animationFrameRef.current = requestAnimationFrame(updateCurrentWord)
    }

    animationFrameRef.current = requestAnimationFrame(updateCurrentWord)

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
    }
  }, [liveTranscript, wordsPerLine])

  // Reset when transcript changes (new agent)
  useEffect(() => {
    setCurrentLineStart(0)
    prevLineStartRef.current = 0
    setIsExiting(false)
  }, [liveTranscript?.agentId])

  // Check if timing is estimated (OpenAI) - show all words as spoken, no individual highlighting
  const isEstimated = liveTranscript?.estimated ?? false

  // Get words for the current line
  const lineWords = liveTranscript?.words.slice(currentLineStart, currentLineStart + wordsPerLine) || []

  if (lineWords.length === 0) {
    return null
  }

  // Helper to format word with proper spacing
  const formatWord = (word: string, isLast: boolean) => {
    const trimmed = word.trim()
    if (isLast) return trimmed
    // Add space after word, unless it ends with punctuation that shouldn't have trailing space
    return trimmed + ' '
  }

  return (
    <div
      className={cn(
        'px-4 max-w-xl mx-auto flex items-center justify-center gap-2',
        className
      )}
    >
      {/* Agent's synced transcript - one line at a time with slide animation */}
      {/* Mobile: vertical stack (name above), Desktop: horizontal (name left) */}
      {lineWords.length > 0 && (
        <div className="flex flex-col md:flex-row items-center gap-1 md:gap-2 text-center md:text-left">
          {/* Agent name with color - stays stable, doesn't animate */}
          {currentAgent && (
            <span
              className="text-[10px] md:text-xs font-semibold whitespace-nowrap"
              style={{ color: currentAgent.color }}
            >
              {currentAgent.name}:
            </span>
          )}
          {/* Transcript words - animated container */}
          <div className="overflow-hidden">
            <p
              className={cn(
                'text-sm font-medium transition-all duration-250 ease-out text-center md:text-left',
                isExiting
                  ? 'opacity-0 -translate-y-3'
                  : 'opacity-100 translate-y-0',
                isDark ? 'text-white/80' : 'text-gray-700'
              )}
            >
              {lineWords.map((word, i) => {
                const globalIndex = currentLineStart + i
                const isCurrentWord = globalIndex === currentWordIndex
                const isSpoken = globalIndex <= currentWordIndex
                const isLast = i === lineWords.length - 1

                // For estimated timing (OpenAI): show all words as spoken (no highlighting)
                // For precise timing (ElevenLabs): highlight current word
                const wordClassName = cn(
                  'transition-opacity duration-100',
                  isEstimated
                    // Estimated: all visible words shown as spoken
                    ? isDark ? 'text-white/80' : 'text-gray-700'
                    // Precise: highlight current word, dim unspoken
                    : isCurrentWord
                      ? isDark ? 'text-white font-medium' : 'text-gray-900 font-medium'
                      : isSpoken
                        ? isDark ? 'text-white/70' : 'text-gray-600'
                        : isDark ? 'text-white/25' : 'text-gray-300'
                )

                const formattedWord = formatWord(word.word, isLast)

                return (
                  <span key={`${globalIndex}-${word.word}`}>
                    {parseInlineMarkdown(formattedWord, wordClassName)}
                  </span>
                )
              })}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
