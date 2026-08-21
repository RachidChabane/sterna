/**
 * MarkdownTextarea Component
 *
 * A textarea with markdown syntax highlighting using the transparent overlay technique.
 * This technique is used by Google (search suggestions) and Facebook (tag friends).
 *
 * Architecture:
 * - Transparent textarea (foreground, z-1) for native editing
 * - Syntax-highlighted pre/code (background, z-0) for display
 * - Both elements perfectly aligned with identical styles
 * - Native cursor, selection, copy/paste, undo/redo
 * - No contenteditable, no cursor jumping issues
 * - Uses Prism.js for language-specific code highlighting
 */

import { forwardRef, useRef, useEffect, useCallback, useMemo, useState } from 'react'
import { cn } from '@/lib/utils'
import Prism from 'prismjs'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'

// Import common languages
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-typescript'
import 'prismjs/components/prism-jsx'
import 'prismjs/components/prism-tsx'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-java'
import 'prismjs/components/prism-c'
import 'prismjs/components/prism-cpp'
import 'prismjs/components/prism-csharp'
import 'prismjs/components/prism-go'
import 'prismjs/components/prism-rust'
import 'prismjs/components/prism-ruby'
import 'prismjs/components/prism-php'
import 'prismjs/components/prism-swift'
import 'prismjs/components/prism-kotlin'
import 'prismjs/components/prism-sql'
import 'prismjs/components/prism-json'
import 'prismjs/components/prism-yaml'
import 'prismjs/components/prism-markdown'
import 'prismjs/components/prism-bash'
import 'prismjs/components/prism-shell-session'
import 'prismjs/components/prism-css'
import 'prismjs/components/prism-scss'
import 'prismjs/components/prism-less'
import 'prismjs/components/prism-xml-doc'
import 'prismjs/components/prism-markup'

interface MarkdownTextareaProps extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange'> {
  value: string
  onChange?: (value: string) => void
  enableMarkdownRender?: boolean
  disabled?: boolean
  placeholder?: string
}

// Token colors are now centralized in @/constants/codeThemes

/**
 * Parse a code fence block and return highlighted React elements using Prism
 */
const highlightCodeBlock = (
  code: string,
  language: string,
  keyPrefix: string,
  tokenColors: Record<string, string>,
  defaultColor: string
): React.ReactNode[] => {
  const lang = language.toLowerCase()
  const grammar = Prism.languages[lang]

  if (!grammar) {
    // Language not supported, return plain text
    return code.split('\n').flatMap((line, i) => {
      const elements = []
      if (i > 0) elements.push(<br key={`${keyPrefix}-br-${i}`} />)
      elements.push(
        <span key={`${keyPrefix}-line-${i}`} style={{ color: defaultColor }}>
          {line || '\u200B'}
        </span>
      )
      return elements
    })
  }

  // Tokenize the code
  const tokens = Prism.tokenize(code, grammar)

  // Convert tokens to React elements
  const elements: React.ReactNode[] = []
  let tokenIndex = 0

  const processToken = (token: string | Prism.Token, prefix: string): React.ReactNode => {
    if (typeof token === 'string') {
      // Plain text - split by newlines and preserve them
      return token.split('\n').flatMap((part, i) => {
        const els = []
        if (i > 0) els.push(<br key={`${prefix}-br-${i}`} />)
        if (part || i === 0) {
          els.push(
            <span key={`${prefix}-text-${i}`} style={{ color: defaultColor }}>
              {part || '\u200B'}
            </span>
          )
        }
        return els
      })
    }

    // Token object
    const tokenType = typeof token.type === 'string' ? token.type : Array.isArray(token.type) ? token.type[0] : 'plain'
    const color = tokenColors[tokenType] || defaultColor

    // Handle nested tokens (recursive)
    if (Array.isArray(token.content)) {
      return token.content.map((t, i) => processToken(t, `${prefix}-${i}`))
    }

    // String content - split by newlines
    const content = String(token.content)
    return content.split('\n').flatMap((part, i) => {
      const els = []
      if (i > 0) els.push(<br key={`${prefix}-${tokenType}-br-${i}`} />)
      if (part || i === 0) {
        els.push(
          <span
            key={`${prefix}-${tokenType}-${i}`}
            style={{ color }}
            className="token"
          >
            {part || '\u200B'}
          </span>
        )
      }
      return els
    })
  }

  tokens.forEach((token) => {
    const processed = processToken(token, `${keyPrefix}-token-${tokenIndex}`)
    if (Array.isArray(processed)) {
      elements.push(...processed)
    } else {
      elements.push(processed)
    }
    tokenIndex++
  })

  return elements
}

/**
 * Highlights markdown syntax with language-specific code highlighting
 */
const highlightMarkdown = (
  text: string,
  tokenColors: Record<string, string>,
  defaultColor: string
): React.ReactNode[] => {
  if (!text) return []

  const elements: React.ReactNode[] = []
  let globalIndex = 0

  // Regex to match code fences: ```language\ncode\n```
  const codeFenceRegex = /^```(\w+)?\n([\s\S]*?)^```$/gm

  let lastIndex = 0
  let match: RegExpExecArray | null

  // Use keyword color for fence markers
  const fenceColor = tokenColors.keyword || defaultColor

  while ((match = codeFenceRegex.exec(text)) !== null) {
    const [fullMatch, language, code] = match
    const matchStart = match.index
    const matchEnd = matchStart + fullMatch.length

    // Process text before this code block
    if (matchStart > lastIndex) {
      const beforeText = text.substring(lastIndex, matchStart)
      elements.push(...highlightNonCodeMarkdown(beforeText, `before-${globalIndex}`))
      globalIndex++
    }

    // Highlight the code fence markers
    const lines = fullMatch.split('\n')
    const openFence = lines[0] // ```language
    const closeFence = lines[lines.length - 1] // ```

    // Opening fence
    elements.push(
      <span key={`fence-open-${globalIndex}`} style={{ color: fenceColor }} className="font-mono">
        {openFence}
      </span>
    )
    elements.push(<br key={`fence-open-br-${globalIndex}`} />)

    // Highlighted code
    if (code) {
      elements.push(...highlightCodeBlock(code, language || 'text', `code-${globalIndex}`, tokenColors, defaultColor))
    }

    // Closing fence
    if (code && !code.endsWith('\n')) {
      elements.push(<br key={`fence-close-br1-${globalIndex}`} />)
    }
    elements.push(
      <span key={`fence-close-${globalIndex}`} style={{ color: fenceColor }} className="font-mono">
        {closeFence}
      </span>
    )

    globalIndex++
    lastIndex = matchEnd
  }

  // Process remaining text after last code block
  if (lastIndex < text.length) {
    const afterText = text.substring(lastIndex)
    elements.push(...highlightNonCodeMarkdown(afterText, `after-${globalIndex}`))
  }

  return elements
}

/**
 * Highlight non-code markdown (headers, bold, italic, links, lists, inline code)
 */
const highlightNonCodeMarkdown = (text: string, keyPrefix: string): React.ReactNode[] => {
  const elements: React.ReactNode[] = []
  const lines = text.split('\n')

  lines.forEach((line, lineIndex) => {
    if (lineIndex > 0) {
      elements.push(<br key={`${keyPrefix}-br-${lineIndex}`} />)
    }

    if (!line) {
      // Empty line
      elements.push(<span key={`${keyPrefix}-empty-${lineIndex}`}>{'\u200B'}</span>)
      return
    }

    let remaining = line
    let charIndex = 0

    while (remaining.length > 0) {
      let matched = false

      // Header (# text)
      if (remaining.match(/^#{1,6}\s/)) {
        const match = remaining.match(/^(#{1,6}\s)(.*)$/)!
        elements.push(
          <span key={`${keyPrefix}-h-${lineIndex}-${charIndex}`} className="text-blue-500 font-bold">
            {match[1]}
          </span>
        )
        remaining = match[2]
        charIndex += match[1].length
        matched = true
        continue
      }

      // Inline code (`text`)
      if (remaining.match(/^`[^`]+`/)) {
        const match = remaining.match(/^(`[^`]+`)(.*)$/)!
        elements.push(
          <span key={`${keyPrefix}-inline-${lineIndex}-${charIndex}`} className="text-purple-500 bg-purple-50 dark:bg-purple-950/30 px-1 rounded font-mono">
            {match[1]}
          </span>
        )
        remaining = match[2]
        charIndex += match[1].length
        matched = true
        continue
      }

      // Bold (**text**)
      if (remaining.match(/^\*\*[^*]+\*\*/)) {
        const match = remaining.match(/^(\*\*[^*]+\*\*)(.*)$/)!
        elements.push(
          <span key={`${keyPrefix}-bold-${lineIndex}-${charIndex}`} className="text-orange-500 font-bold">
            {match[1]}
          </span>
        )
        remaining = match[2]
        charIndex += match[1].length
        matched = true
        continue
      }

      // Italic (*text*)
      if (remaining.match(/^\*[^*]+\*/)) {
        const match = remaining.match(/^(\*[^*]+\*)(.*)$/)!
        elements.push(
          <span key={`${keyPrefix}-italic-${lineIndex}-${charIndex}`} className="text-orange-400 italic">
            {match[1]}
          </span>
        )
        remaining = match[2]
        charIndex += match[1].length
        matched = true
        continue
      }

      // Link ([text](url))
      if (remaining.match(/^\[([^\]]+)\]\(([^)]+)\)/)) {
        const match = remaining.match(/^(\[([^\]]+)\]\(([^)]+)\))(.*)$/)!
        elements.push(
          <span key={`${keyPrefix}-link-${lineIndex}-${charIndex}`} className="text-blue-400 underline">
            {match[1]}
          </span>
        )
        remaining = match[4]
        charIndex += match[1].length
        matched = true
        continue
      }

      // List item (- or * or +)
      if (remaining.match(/^(\s*)[-*+]\s/)) {
        const match = remaining.match(/^((\s*)[-*+]\s)(.*)$/)!
        elements.push(
          <span key={`${keyPrefix}-list-${lineIndex}-${charIndex}`} className="text-green-500">
            {match[1]}
          </span>
        )
        remaining = match[3]
        charIndex += match[1].length
        matched = true
        continue
      }

      // Numbered list (1. )
      if (remaining.match(/^(\s*)\d+\.\s/)) {
        const match = remaining.match(/^((\s*)\d+\.\s)(.*)$/)!
        elements.push(
          <span key={`${keyPrefix}-numlist-${lineIndex}-${charIndex}`} className="text-green-500">
            {match[1]}
          </span>
        )
        remaining = match[3]
        charIndex += match[1].length
        matched = true
        continue
      }

      // Blockquote (> )
      if (remaining.match(/^>\s/)) {
        const match = remaining.match(/^(>\s)(.*)$/)!
        elements.push(
          <span key={`${keyPrefix}-quote-${lineIndex}-${charIndex}`} className="text-gray-500">
            {match[1]}
          </span>
        )
        remaining = match[2]
        charIndex += match[1].length
        matched = true
        continue
      }

      // No match - take one character
      if (!matched) {
        elements.push(
          <span key={`${keyPrefix}-text-${lineIndex}-${charIndex}`} className="text-foreground">
            {remaining[0]}
          </span>
        )
        remaining = remaining.slice(1)
        charIndex += 1
      }
    }
  })

  return elements
}

export const MarkdownTextarea = forwardRef<HTMLTextAreaElement, MarkdownTextareaProps>(
  ({ value, onChange, className, enableMarkdownRender = true, disabled = false, placeholder, ...props }, forwardedRef) => {
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const highlightingRef = useRef<HTMLPreElement>(null)

    // Get code theme from settings
    const codeThemeId = useSettingsStore((state) => state.codeTheme)
    const codeTheme = getCodeTheme(codeThemeId)

    // Debounced value for highlighting - updates only after user stops typing
    // This prevents expensive Prism.js tokenization from blocking the main thread during active typing
    const [debouncedValue, setDebouncedValue] = useState(value)

    // Debounce the value for highlighting to avoid blocking during active typing
    useEffect(() => {
      if (!enableMarkdownRender) return

      const timer = setTimeout(() => {
        setDebouncedValue(value)
      }, 150) // 150ms debounce for highlighting (shorter than resize to feel responsive)

      return () => clearTimeout(timer)
    }, [value, enableMarkdownRender])

    // Combine refs
    useEffect(() => {
      if (typeof forwardedRef === 'function') {
        forwardedRef(textareaRef.current)
      } else if (forwardedRef) {
        forwardedRef.current = textareaRef.current
      }
    }, [forwardedRef])

    // Handle change
    const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onChange?.(e.target.value)
    }, [onChange])

    // Sync scroll between textarea and highlighting
    const handleScroll = useCallback(() => {
      if (highlightingRef.current && textareaRef.current) {
        highlightingRef.current.scrollTop = textareaRef.current.scrollTop
        highlightingRef.current.scrollLeft = textareaRef.current.scrollLeft
      }
    }, [])

    // Auto-grow: adjust container height based on content
    // Optimized with debounce + RAF to avoid expensive DOM calculations on every keystroke
    useEffect(() => {
      if (!textareaRef.current) return

      let rafId: number | null = null

      // Debounce resize calculations to avoid lag during typing
      // 300ms ensures user finishes typing before expensive DOM calculations run
      const resizeTimer = setTimeout(() => {
        // Use requestAnimationFrame for smooth, frame-synced updates
        rafId = requestAnimationFrame(() => {
          if (!textareaRef.current) return

          // For simple mode (no highlighting), adjust textarea directly
          if (!enableMarkdownRender) {
            // Reset height to auto to get accurate scrollHeight
            textareaRef.current.style.height = 'auto'

            // Calculate required height based on content
            const scrollHeight = textareaRef.current.scrollHeight

            // Apply constraints: min 48px (3rem), max 200px
            const newHeight = Math.min(Math.max(scrollHeight, 48), 200)

            // Set textarea height
            textareaRef.current.style.height = `${newHeight}px`
            return
          }

          // For highlighting mode, adjust container
          const container = textareaRef.current.parentElement
          if (!container) return

          // When empty, use fixed default height (3rem = 48px)
          if (!value) {
            container.style.height = '48px'
            if (highlightingRef.current) {
              highlightingRef.current.style.height = '48px'
            }
            return
          }

          // Temporarily set height to auto to get accurate scrollHeight
          container.style.height = 'auto'

          // Calculate required height based on content
          const scrollHeight = textareaRef.current.scrollHeight

          // Apply constraints: min 48px (3rem), max 200px
          const newHeight = Math.min(Math.max(scrollHeight, 48), 200)

          // Set container height
          container.style.height = `${newHeight}px`

          // Ensure the highlighting layer also adjusts
          if (highlightingRef.current) {
            highlightingRef.current.style.height = `${newHeight}px`
          }
        })
      }, 300) // 300ms debounce prevents lag during active typing

      return () => {
        clearTimeout(resizeTimer)
        if (rafId !== null) {
          cancelAnimationFrame(rafId)
        }
      }
    }, [value, enableMarkdownRender])

    // Prepare highlighted text (add space if ends with newline to preserve height)
    // Use debouncedValue to avoid expensive re-highlighting during active typing
    const highlightedText = enableMarkdownRender
      ? (debouncedValue + (debouncedValue.endsWith('\n') ? ' ' : ''))
      : value

    // Memoize the highlighted markup to avoid re-parsing on every render
    // This now uses debouncedValue so it only re-calculates 150ms after user stops typing
    const highlightedMarkup = useMemo(() => {
      if (!enableMarkdownRender) return null
      return highlightMarkdown(highlightedText, codeTheme.tokenColors, codeTheme.textColor)
    }, [highlightedText, enableMarkdownRender, codeTheme.tokenColors, codeTheme.textColor])

    // Common styles for both textarea and highlighting (MUST be identical)
    const commonStyles = {
      margin: 0,
      padding: '12px',
      fontSize: '14px',
      fontFamily: enableMarkdownRender
        ? "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace"
        : "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', Arial, Tahoma, 'Helvetica Neue', sans-serif",
      lineHeight: '1.5',
      whiteSpace: 'pre-wrap' as const,
      wordWrap: 'break-word' as const,
      tabSize: 2,
      overflow: 'auto' as const,
    }

    if (!enableMarkdownRender) {
      // Simple mode without highlighting
      return (
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          placeholder={placeholder}
          disabled={disabled}
          className={cn(
            "w-full",
            "border border-border rounded-lg",
            "bg-input text-foreground",
            "focus:outline-none focus:ring-2 focus:ring-primary",
            "transition-colors resize-none",
            "min-h-[3rem] max-h-[200px]",
            disabled && "opacity-50 cursor-not-allowed",
            className
          )}
          style={commonStyles}
          {...props}
        />
      )
    }

    // Highlighted mode with transparent textarea + overlay
    return (
      <>
        {/* Force cursor and pointer-events with !important - guaranteed override */}
        <style>{`
          .markdown-textarea-force-cursor {
            cursor: text !important;
            scrollbar-width: none; /* Firefox */
            -ms-overflow-style: none; /* IE/Edge */
          }
          .markdown-textarea-force-cursor::-webkit-scrollbar {
            display: none; /* Chrome/Safari */
          }
          .markdown-textarea-force-cursor::placeholder {
            color: hsl(var(--muted-foreground)) !important;
            -webkit-text-fill-color: hsl(var(--muted-foreground)) !important;
            opacity: 0.5 !important;
          }
          .markdown-textarea-force-cursor:disabled {
            cursor: not-allowed !important;
          }
          .markdown-highlighting-layer,
          .markdown-highlighting-layer * {
            pointer-events: none !important;
          }
        `}</style>

        <div
          className={cn(
            "relative w-full",
            "border border-border rounded-lg",
            "bg-input",
            "focus-within:outline-none focus-within:ring-0",
            "transition-colors",
            disabled && "opacity-50",
            className
          )}
          style={{
            minHeight: '3rem',
            maxHeight: '200px',
            height: 'auto',
          }}
        >
        {/* Background layer: syntax highlighted */}
        <pre
          ref={highlightingRef}
          aria-hidden="true"
          className="absolute inset-0 z-0 pointer-events-none markdown-highlighting-layer"
          style={commonStyles}
        >
          {highlightedMarkup}
        </pre>

        {/* Foreground layer: transparent textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onScroll={handleScroll}
          placeholder={placeholder}
          disabled={disabled}
          className={cn(
            "absolute inset-0",
            "z-10",
            "bg-transparent",
            "markdown-textarea-force-cursor",
            "focus:outline-none",
            // Placeholder styling
            "placeholder:text-muted-foreground placeholder:opacity-50"
          )}
          style={{
            ...commonStyles,
            overflow: 'auto', // Scrollbar hidden by CSS - allows scroll events to trigger
            resize: 'none', // No resize handle - container handles auto-grow
            color: 'transparent',
            caretColor: 'hsl(var(--foreground))',
            WebkitTextFillColor: 'transparent', // For Safari
          }}
          {...props}
        />
        </div>
      </>
    )
  }
)

MarkdownTextarea.displayName = 'MarkdownTextarea'
