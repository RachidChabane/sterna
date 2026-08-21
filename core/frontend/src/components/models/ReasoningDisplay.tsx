import { useState } from 'react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Lightbulb, StopCircle, ChevronRight, ChevronDown, ShieldOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'

interface ReasoningDisplayProps {
  content: string
  isStreaming: boolean
  isInterrupted?: boolean
  className?: string
  compact?: boolean // For use inside master tool section - more subtle styling
  showStopped?: boolean // Explicitly control whether to show "stopped" (only for last item)
}

// Clean reasoning content by removing tags that shouldn't be displayed
const cleanReasoningContent = (content: string): string => {
  return content
    .replace(/<\/?thinking>/gi, '') // Remove <thinking> and </thinking> tags
    .replace(/\{\{ACTION:[^}]*\}\}/g, '') // Remove {{ACTION:...}} tags
    .trim()
}

// Check if content contains redacted sections
const hasRedactedContent = (content: string): boolean => {
  return content.includes('[...]')
}

// Append trailing [...] when filtered text ends abruptly (no terminal punctuation)
export const ensureTrailingRedaction = (content: string): string => {
  if (!content.includes('[...]')) return content
  const trimmed = content.trimEnd()
  if (trimmed.endsWith('[...]')) return content
  if (/[.!?:;")\]]\s*$/.test(trimmed)) return content
  return content + ' [...]'
}

// Inline badge for redacted content (exported for use in MessageSteps)
export function RedactedBadge() {
  return (
    <span
      className="inline-flex items-center gap-0.5 px-1.5 py-0.5 mx-0.5 rounded text-[10px] font-medium not-italic
        bg-amber-500/10 text-amber-600 border border-amber-500/20
        dark:bg-amber-400/10 dark:text-amber-400 dark:border-amber-400/20"
      title="Some internal reasoning was hidden for privacy"
    >
      <ShieldOff className="w-2.5 h-2.5" />
      hidden
    </span>
  )
}

// Replace [...] tokens in React children with RedactedBadge components (exported for use in MessageSteps)
export function replaceRedactedInChildren(children: React.ReactNode): React.ReactNode {
  if (typeof children === 'string') {
    if (!children.includes('[...]')) return children
    const parts = children.split('[...]')
    return parts.flatMap((part, i) =>
      i < parts.length - 1
        ? [part, <RedactedBadge key={`r-${i}`} />]
        : [part]
    )
  }
  if (Array.isArray(children)) {
    return children.flatMap((child, i) => {
      const replaced = replaceRedactedInChildren(child)
      return Array.isArray(replaced) ? replaced : [replaced]
    })
  }
  return children
}

export function ReasoningDisplay({ content, isStreaming, isInterrupted, className, compact, showStopped }: ReasoningDisplayProps) {
  const [isOpen, setIsOpen] = useState(false)
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  // Clean the content for display
  const cleanedContent = cleanReasoningContent(content)

  // Don't render if content is empty after cleaning
  if (!cleanedContent) return null

  // If text was filtered and ends abruptly, append trailing redaction marker
  const displayContent = ensureTrailingRedaction(cleanedContent)
  const contentWasFiltered = hasRedactedContent(displayContent)

  // Only show "stopped" if explicitly allowed (last item) and interrupted while streaming
  const wasStoppedWhileStreaming = showStopped && isInterrupted && isStreaming

  return (
    <div className={cn(
      compact
        ? "pl-0 py-0.5" // Subtle inside master section
        : "border-l-2 border-purple-400/40 pl-2 md:pl-3 py-1", // Normal styling
      className
    )}>
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <div className={cn(
            "flex items-center gap-1.5 flex-wrap cursor-pointer hover:opacity-80 transition-opacity",
            compact && "text-xs"
          )}>
            {compact ? (
              // Chevron for compact mode (inside master section)
              isOpen ? (
                <ChevronDown className="w-3 h-3 flex-shrink-0 text-purple-500/60 dark:text-purple-400/60" />
              ) : (
                <ChevronRight className="w-3 h-3 flex-shrink-0 text-purple-500/60 dark:text-purple-400/60" />
              )
            ) : (
              // Lightbulb for standalone mode
              <Lightbulb className="h-3 w-3 md:h-3.5 md:w-3.5 text-purple-500/70 dark:text-purple-400/70" />
            )}
            <span className={cn(
              "italic",
              compact
                ? "text-xs text-purple-500/60 dark:text-purple-400/60"
                : "text-sm text-purple-600/80 dark:text-purple-400/80"
            )}>
              Reasoning
            </span>
            {isStreaming && !isInterrupted && (
              <span className="flex items-center gap-1 text-xs italic text-purple-500/70 dark:text-purple-400/70">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-500/50 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-purple-500"></span>
                </span>
              </span>
            )}
            {wasStoppedWhileStreaming && (
              <span className="flex items-center gap-1 text-xs italic text-orange-500/70">
                <StopCircle className="h-2.5 w-2.5" />
                stopped
              </span>
            )}
            {contentWasFiltered && !isStreaming && (
              <span
                className="flex items-center gap-0.5 text-[10px] not-italic font-medium text-amber-600/70 dark:text-amber-400/60"
                title="Some internal reasoning was hidden for privacy"
              >
                <ShieldOff className="h-2.5 w-2.5" />
                partially hidden
              </span>
            )}
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
          <div className="pt-2 text-sm italic text-purple-600/70 dark:text-purple-400/70">
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p({ children }) {
                    return <p>{replaceRedactedInChildren(children)}</p>
                  },
                  li({ children }) {
                    return <li>{replaceRedactedInChildren(children)}</li>
                  },
                  // react-markdown v9 removed the `inline` prop; fenced code
                  // blocks are detected via the language-* className instead
                  // (inline code never carries one), matching the previous
                  // runtime behavior.
                  code({ node: _node, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '')
                    return match ? (
                      <SyntaxHighlighter
                        style={codeTheme.style}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{ fontSize: '0.8125rem' }}
                      >
                        {String(children).replace(/\n$/, '')}
                      </SyntaxHighlighter>
                    ) : (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    )
                  }
                }}
              >
                {displayContent}
              </ReactMarkdown>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
