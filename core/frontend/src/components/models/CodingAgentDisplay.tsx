/**
 * CodingAgentDisplay Component
 *
 * Inline display for Coding Agent results - matches the style of other tools
 * like Tool Discovery, Notion Search, Write, etc.
 * File changes shown as inline collapsible diffs (like SparkUpdateDiff).
 */

import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  ChevronRight,
  Terminal,
  Clock,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { useUIStore } from '@/store/uiStore'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { versionsApi } from '@/api/versions'
import type { MessageFileChange, CompareVersionsResponse } from '@/api/versions'
import type { CodingAgentStep, CodingAgentResult, CodingAgentQuestion } from '@/api/llm'
import { Markdown } from '@/components/ui/markdown'
import { codeSessionApi, type CodingAgentProgressStep } from '@/api/codeSession'

interface CodingAgentDisplayProps {
  task: string
  jobId?: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  steps: CodingAgentStep[]
  result?: CodingAgentResult
  variant?: 'chat' | 'code'
  chatId?: string
  mode?: 'plan' | 'implement' | 'auto'
  pendingQuestion?: CodingAgentQuestion | null
  onAnswerQuestion?: (answer: string) => void
}

// Format duration for display
const formatDuration = (ms: number): string => {
  if (ms < 1000) return `${ms}ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.floor(seconds % 60)
  return `${minutes}m ${remainingSeconds}s`
}

// Strip workspace path prefix to show relative path
const getRelativePath = (fullPath: string): string => {
  const workspacePattern = /^\/workspace\/chat-[a-f0-9-]+\/?/
  const relativePath = fullPath.replace(workspacePattern, '')
  if (!relativePath || relativePath === '/') {
    return fullPath.split('/').pop() || fullPath
  }
  return relativePath
}

// Inline diff viewer component for a single file
const FileDiffViewer = React.memo(({
  file,
  isDark
}: {
  file: MessageFileChange
  isDark: boolean
}) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const [diffData, setDiffData] = useState<CompareVersionsResponse | null>(null)
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const MAX_VISIBLE_LINES = 15

  const loadContent = async () => {
    if (loading || (diffData !== null) || (content !== null)) return
    setLoading(true)

    try {
      if (file.change_type === 'modified' && file.versions.length >= 2) {
        // Load diff for modified files
        const versions = file.versions.sort((a, b) => a.version_number - b.version_number)
        const olderVersion = versions[versions.length - 2]
        const newerVersion = versions[versions.length - 1]

        if (olderVersion && newerVersion) {
          const response = await versionsApi.compareVersions(olderVersion.id, newerVersion.id)
          setDiffData(response.data)
        }
      } else if (file.versions.length > 0) {
        // Load content for created files
        const latestVersion = file.versions[file.versions.length - 1]
        if (latestVersion && !file.is_binary) {
          const response = await versionsApi.getVersionContent(latestVersion.id)
          setContent(response.data.content || '')
        }
      }
    } catch (err) {
      console.error('Failed to load file content:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isExpanded) {
      loadContent()
    }
  }, [isExpanded])

  // Generate diff lines from diffData
  type DiffLine = {
    type: 'header' | 'hunk' | 'added' | 'removed' | 'context'
    content: string
    oldLineNum?: number
    newLineNum?: number
  }

  const getDiffLines = () => {
    if (!diffData) return []

    const oldContent = diffData.original_content || ''
    const newContent = diffData.modified_content || ''
    const oldLines = oldContent.split('\n')
    const newLines = newContent.split('\n')

    const lines: DiffLine[] = []

    lines.push({ type: 'header', content: `--- a/${getRelativePath(file.path)}` })
    lines.push({ type: 'header', content: `+++ b/${getRelativePath(file.path)}` })
    lines.push({ type: 'hunk', content: `@@ -1,${oldLines.length} +1,${newLines.length} @@` })

    oldLines.forEach((line, i) => {
      lines.push({ type: 'removed', content: `-${line}`, oldLineNum: i + 1 })
    })
    newLines.forEach((line, i) => {
      lines.push({ type: 'added', content: `+${line}`, newLineNum: i + 1 })
    })

    return lines
  }

  // Get content lines for created files
  const getContentLines = (): DiffLine[] => {
    if (!content) return []
    return content.split('\n').map((line, i) => ({
      type: 'added' as const,
      content: `+${line}`,
      newLineNum: i + 1
    }))
  }

  const isModified = file.change_type === 'modified'
  const lines = isModified ? getDiffLines() : getContentLines()
  const visibleLines = isExpanded && lines.length > MAX_VISIBLE_LINES ? lines : lines.slice(0, MAX_VISIBLE_LINES)
  const hasMoreLines = lines.length > MAX_VISIBLE_LINES
  const addedCount = lines.filter(l => l.type === 'added').length
  const removedCount = lines.filter(l => l.type === 'removed').length

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
      <CollapsibleTrigger className="w-full flex items-center gap-2 py-0.5 text-xs hover:bg-muted/30 rounded px-1 -mx-1 transition-colors">
        <ChevronRight className={cn(
          "w-3 h-3 transition-transform duration-200 text-muted-foreground/50",
          isExpanded && "rotate-90"
        )} />
        <span className="font-mono text-muted-foreground/70 truncate flex-1 text-left">
          {getRelativePath(file.path)}
        </span>
        <span className="text-[10px] text-muted-foreground/50">
          {file.change_type}
        </span>
      </CollapsibleTrigger>

      <CollapsibleContent>
        {loading ? (
          <div className="ml-2 sm:ml-5 mt-1 text-[10px] text-muted-foreground/50">Loading...</div>
        ) : lines.length > 0 ? (
          <div className={cn(
            "mt-1.5 ml-2 sm:ml-5 border rounded-md overflow-hidden",
            isDark ? "border-border/60 bg-card/50" : "border-border bg-white"
          )}>
            {/* Diff header */}
            {isModified && (
              <div className={cn(
                "px-2 py-1 text-[10px] flex items-center gap-2 border-b",
                isDark ? "bg-amber-500/10 border-border/30" : "bg-amber-50 border-amber-200"
              )}>
                <span className={isDark ? "text-amber-400" : "text-amber-700"}>
                  {addedCount > 0 && <span className="text-emerald-500">+{addedCount}</span>}
                  {addedCount > 0 && removedCount > 0 && ' / '}
                  {removedCount > 0 && <span className="text-red-400">-{removedCount}</span>}
                </span>
              </div>
            )}

            {/* Diff lines */}
            <div className="text-[10px] font-mono leading-[1.5] max-h-[250px] overflow-y-auto">
              {visibleLines.map((line, index) => {
                let bgClass = ''
                let textClass = isDark ? 'text-muted-foreground' : 'text-foreground/80'

                switch (line.type) {
                  case 'header':
                    bgClass = isDark ? 'bg-muted/30' : 'bg-slate-100'
                    textClass = isDark ? 'text-muted-foreground/70' : 'text-slate-500'
                    break
                  case 'hunk':
                    bgClass = isDark ? 'bg-blue-500/10' : 'bg-blue-50'
                    textClass = isDark ? 'text-blue-400' : 'text-blue-700'
                    break
                  case 'removed':
                    bgClass = isDark ? 'bg-red-500/15' : 'bg-red-50'
                    textClass = isDark ? 'text-red-400' : 'text-red-700'
                    break
                  case 'added':
                    bgClass = isDark ? 'bg-emerald-500/15' : 'bg-emerald-50'
                    textClass = isDark ? 'text-emerald-400' : 'text-emerald-700'
                    break
                }

                return (
                  <div key={index} className={cn("flex", bgClass)}>
                    <span className={cn(
                      "flex-shrink-0 w-8 text-right pr-2 select-none border-r",
                      isDark ? "text-muted-foreground/40 border-border/30" : "text-slate-400 border-slate-200"
                    )}>
                      {line.newLineNum || line.oldLineNum || ''}
                    </span>
                    <pre className={cn("flex-1 px-2 whitespace-pre-wrap break-all", textClass)}>
                      {line.type === 'header' || line.type === 'hunk'
                        ? line.content
                        : line.content.slice(1) || ' '}
                    </pre>
                  </div>
                )
              })}
            </div>

            {/* Show more link */}
            {hasMoreLines && !isExpanded && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setIsExpanded(true)
                }}
                className={cn(
                  "w-full py-1 text-center text-[10px] transition-colors border-t",
                  isDark
                    ? "text-muted-foreground hover:text-foreground hover:bg-muted/30 border-border/30"
                    : "text-slate-500 hover:text-slate-700 hover:bg-slate-50 border-slate-200"
                )}
              >
                Show all ({lines.length} lines)
              </button>
            )}
          </div>
        ) : (
          <div className="ml-2 sm:ml-5 mt-1 text-[10px] text-muted-foreground/50">
            {file.is_binary ? 'Binary file' : 'No content available'}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
})

// ============================================================================
// STEP PARSING & GROUPING UTILITIES
// ============================================================================

// Step with extended fields from live progress
interface ExtendedStep {
  type: string
  tool?: string
  content?: string
  input?: Record<string, unknown>  // Tool parameters (file_path, command, etc.)
  output?: string
}

// Strip workspace prefix from paths
const shortPath = (path: string): string => {
  if (!path) return ''
  return path
    .replace(/^\/workspace\/chat-[a-f0-9-]+\/?/, '')
    .replace(/^\/workspace\/[^/]+\/?/, '')
    .replace(/^\/home\/[^/]+\//, '~/')
    || path.split('/').pop()
    || path
}

// Get file path from step (check input first, then content)
const getFilePath = (step: ExtendedStep): string | null => {
  // Check input object first (from live progress API)
  if (step.input) {
    if (step.input.file_path) return String(step.input.file_path)
    if (step.input.path) return String(step.input.path)
  }
  // Try parsing content as JSON
  if (step.content) {
    try {
      const parsed = JSON.parse(step.content)
      return parsed.file_path || parsed.path || null
    } catch {
      return null
    }
  }
  return null
}

// Get command from bash step
const getCommand = (step: ExtendedStep): string | null => {
  if (step.input?.command) return String(step.input.command)
  if (step.content) {
    try {
      const parsed = JSON.parse(step.content)
      return parsed.command || null
    } catch {
      if (!step.content.startsWith('{')) return step.content.trim()
    }
  }
  return null
}

// Get pattern from glob/grep step
const getPattern = (step: ExtendedStep): string | null => {
  if (step.input?.pattern) return String(step.input.pattern)
  if (step.content) {
    try {
      const parsed = JSON.parse(step.content)
      return parsed.pattern || null
    } catch {
      return null
    }
  }
  return null
}

// Get write content
const getWriteContent = (step: ExtendedStep): string | null => {
  if (step.input?.content) return String(step.input.content)
  if (step.content) {
    try {
      const parsed = JSON.parse(step.content)
      return parsed.content || null
    } catch {
      return null
    }
  }
  return null
}

// Count lines in result
const countLines = (content: string): number => {
  if (!content) return 0
  const match = content.match(/Read (\d+) lines?/i) || content.match(/(\d+) lines?/i)
  if (match) return parseInt(match[1], 10)
  return content.split('\n').length
}

// Count files in result
const countFiles = (content: string): number => {
  try {
    const parsed = JSON.parse(content)
    if (Array.isArray(parsed)) return parsed.length
  } catch {}
  return content.split('\n').filter(l => l.trim() && l.includes('/')).length
}

// Grouped step for display
interface GroupedStep {
  type: 'tool' | 'text'
  tool?: string
  filePath?: string
  command?: string
  pattern?: string
  content?: string
  result?: string
  lineCount?: number
  fileCount?: number
  success?: boolean
}

// Group steps into tool executions (call + result pairs)
const groupSteps = (steps: ExtendedStep[]): GroupedStep[] => {
  const grouped: GroupedStep[] = []
  const seenTexts = new Set<string>()

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i]
    const nextStep = steps[i + 1] as ExtendedStep | undefined

    // Skip system/thinking
    if (step.type === 'system' || step.type === 'thinking') continue

    // Tool call - pair with its result
    if (step.type === 'tool_call' && step.tool) {
      const tool = step.tool.toLowerCase()
      const grouped_step: GroupedStep = { type: 'tool', tool: step.tool }

      // Extract info based on tool type
      if (tool === 'read' || tool === 'write' || tool === 'edit') {
        grouped_step.filePath = getFilePath(step) || undefined
        if (tool === 'write') {
          grouped_step.content = getWriteContent(step) || undefined
        }
      } else if (tool === 'bash') {
        grouped_step.command = getCommand(step) || undefined
      } else if (tool === 'glob' || tool === 'grep') {
        grouped_step.pattern = getPattern(step) || undefined
      }

      // Look for result in next step OR in output field
      const resultContent = step.output || (nextStep?.type === 'tool_result' ? (nextStep.content || nextStep.output || '') : '')

      if (resultContent) {
        grouped_step.result = resultContent
        if (tool === 'read') {
          grouped_step.lineCount = countLines(resultContent)
        } else if (tool === 'glob' || tool === 'grep') {
          grouped_step.fileCount = countFiles(resultContent)
        } else if (tool === 'write' || tool === 'edit') {
          grouped_step.success = true
        }
      }

      // Skip next step if it was a tool_result we consumed
      if (nextStep?.type === 'tool_result') i++

      grouped.push(grouped_step)
      continue
    }

    // Skip standalone tool_result
    if (step.type === 'tool_result') continue

    // Text/result - deduplicate
    if (step.type === 'text' || step.type === 'result') {
      const content = step.content?.trim() || ''
      if (!content) continue
      const hash = content.slice(0, 50)
      if (seenTexts.has(hash)) continue
      seenTexts.add(hash)
      grouped.push({ type: 'text', content })
    }
  }

  return grouped
}

// ============================================================================
// STEP DISPLAY COMPONENTS - Clean, minimal design with subtle cards
// ============================================================================

// Compact step card for inline Activity section - each tool gets unique display
const CompactStepItem = React.memo(({
  step,
  isDark,
}: {
  step: GroupedStep
  isDark: boolean
}) => {
  if (step.type === 'tool' && step.tool) {
    const tool = step.tool.toLowerCase()

    // Read tool - show file path and line count
    if (tool === 'read') {
      return (
        <div className={cn(
          "px-2 sm:px-3 py-2 rounded-md text-xs overflow-hidden",
          isDark ? "bg-muted/20" : "bg-slate-50"
        )}>
          <span className="text-muted-foreground/60">Read </span>
          <code className="font-mono text-foreground/80 break-all">{shortPath(step.filePath || '')}</code>
          {step.lineCount !== undefined && (
            <span className="text-muted-foreground/50 ml-1">({step.lineCount} lines)</span>
          )}
        </div>
      )
    }

    // Write tool - show created file
    if (tool === 'write') {
      return (
        <div className={cn(
          "px-2 sm:px-3 py-2 rounded-md text-xs overflow-hidden",
          isDark ? "bg-muted/20" : "bg-slate-50"
        )}>
          <span className="text-muted-foreground/60">Created </span>
          <code className="font-mono text-foreground/80 break-all">{shortPath(step.filePath || '')}</code>
        </div>
      )
    }

    // Edit tool - show edited file
    if (tool === 'edit') {
      return (
        <div className={cn(
          "px-2 sm:px-3 py-2 rounded-md text-xs overflow-hidden",
          isDark ? "bg-muted/20" : "bg-slate-50"
        )}>
          <span className="text-muted-foreground/60">Edited </span>
          <code className="font-mono text-foreground/80 break-all">{shortPath(step.filePath || '')}</code>
        </div>
      )
    }

    // Bash tool - show command
    if (tool === 'bash') {
      return (
        <div className={cn(
          "px-2 sm:px-3 py-2 rounded-md text-xs overflow-hidden",
          isDark ? "bg-muted/20" : "bg-slate-50"
        )}>
          <span className="text-muted-foreground/60">$ </span>
          <code className="font-mono text-foreground/80 break-all">
            {step.command && step.command.length > 40 ? step.command.slice(0, 40) + '...' : step.command}
          </code>
        </div>
      )
    }

    // Glob/Grep - show pattern and count
    if (tool === 'glob' || tool === 'grep') {
      return (
        <div className={cn(
          "px-2 sm:px-3 py-2 rounded-md text-xs overflow-hidden",
          isDark ? "bg-muted/20" : "bg-slate-50"
        )}>
          <span className="text-muted-foreground/60">{tool === 'glob' ? 'Find ' : 'Search '}</span>
          <code className="font-mono text-foreground/80 break-all">{step.pattern}</code>
          {step.fileCount !== undefined && (
            <span className="text-muted-foreground/50 ml-1">→ {step.fileCount} file{step.fileCount !== 1 ? 's' : ''}</span>
          )}
        </div>
      )
    }

    // Generic tool fallback
    return (
      <div className={cn(
        "px-2 sm:px-3 py-2 rounded-md text-xs overflow-hidden",
        isDark ? "bg-muted/20" : "bg-slate-50"
      )}>
        <span className="text-muted-foreground/60">{step.tool} </span>
        {step.filePath && <code className="font-mono text-foreground/80 break-all">{shortPath(step.filePath)}</code>}
      </div>
    )
  }

  // Skip text steps in compact view - they're usually redundant
  return null
})

// Full step card for modal view - unique display per tool type
const FullStepItem = React.memo(({
  step,
  isDark
}: {
  step: GroupedStep
  isDark: boolean
}) => {
  const [isExpanded, setIsExpanded] = useState(false)

  if (step.type === 'tool' && step.tool) {
    const tool = step.tool.toLowerCase()
    const hasExpandableContent = (tool === 'write' && step.content) ||
                                  (tool === 'bash' && step.result && step.result.length > 60)

    // Read tool
    if (tool === 'read') {
      return (
        <div className={cn(
          "p-3 rounded-lg",
          isDark ? "bg-muted/20" : "bg-slate-50"
        )}>
          <div className="text-sm">
            <span className="text-muted-foreground/70">Read </span>
            <code className="font-mono text-foreground">{shortPath(step.filePath || '')}</code>
          </div>
          {step.lineCount !== undefined && (
            <div className="text-xs text-muted-foreground/50 mt-1">
              {step.lineCount} lines
            </div>
          )}
        </div>
      )
    }

    // Write tool
    if (tool === 'write') {
      return (
        <div className={cn(
          "p-3 rounded-lg",
          isDark ? "bg-muted/20" : "bg-slate-50"
        )}>
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <span className="text-muted-foreground/70">Created </span>
              <code className="font-mono text-foreground">{shortPath(step.filePath || '')}</code>
            </div>
            {hasExpandableContent && (
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {isExpanded ? 'Hide' : 'Show content'}
              </button>
            )}
          </div>
          {isExpanded && step.content && (
            <div className={cn(
              "mt-3 rounded-md overflow-hidden border max-h-[200px] overflow-auto",
              isDark ? "border-border/30" : "border-slate-200"
            )}>
              <pre className="p-3 text-xs font-mono text-foreground/80 whitespace-pre-wrap">
                {step.content}
              </pre>
            </div>
          )}
        </div>
      )
    }

    // Edit tool
    if (tool === 'edit') {
      return (
        <div className={cn(
          "p-3 rounded-lg",
          isDark ? "bg-muted/20" : "bg-slate-50"
        )}>
          <div className="text-sm">
            <span className="text-muted-foreground/70">Edited </span>
            <code className="font-mono text-foreground">{shortPath(step.filePath || '')}</code>
          </div>
        </div>
      )
    }

    // Bash tool
    if (tool === 'bash') {
      return (
        <div className={cn(
          "p-3 rounded-lg",
          isDark ? "bg-muted/20" : "bg-slate-50"
        )}>
          <div className="flex items-center justify-between">
            <div className="text-sm font-mono">
              <span className="text-muted-foreground/50">$ </span>
              <span className="text-foreground">{step.command}</span>
            </div>
            {hasExpandableContent && (
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {isExpanded ? 'Hide' : 'Show output'}
              </button>
            )}
          </div>
          {step.result && (
            <div className={cn(
              "mt-2 text-xs text-muted-foreground/70",
              isExpanded ? "" : "line-clamp-2"
            )}>
              <pre className="whitespace-pre-wrap font-mono">{step.result}</pre>
            </div>
          )}
        </div>
      )
    }

    // Glob/Grep tool
    if (tool === 'glob' || tool === 'grep') {
      return (
        <div className={cn(
          "p-3 rounded-lg",
          isDark ? "bg-muted/20" : "bg-slate-50"
        )}>
          <div className="text-sm">
            <span className="text-muted-foreground/70">{tool === 'glob' ? 'Find pattern ' : 'Search '}</span>
            <code className="font-mono text-foreground">{step.pattern}</code>
          </div>
          {step.fileCount !== undefined && (
            <div className="text-xs text-muted-foreground/50 mt-1">
              {step.fileCount} file{step.fileCount !== 1 ? 's' : ''} matched
            </div>
          )}
        </div>
      )
    }

    // Generic fallback
    return (
      <div className={cn(
        "p-3 rounded-lg",
        isDark ? "bg-muted/20" : "bg-slate-50"
      )}>
        <div className="text-sm">
          <span className="text-muted-foreground/70">{step.tool} </span>
          {step.filePath && <code className="font-mono text-foreground">{shortPath(step.filePath)}</code>}
        </div>
      </div>
    )
  }

  // Skip text steps - they're usually duplicates of the summary
  return null
})

export function CodingAgentDisplay({
  task,
  jobId,
  status,
  steps,
  result,
  variant = 'chat',
  chatId,
  mode,
  pendingQuestion,
  onAnswerQuestion,
}: CodingAgentDisplayProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [showFullOutput, setShowFullOutput] = useState(false)
  const [versionedFiles, setVersionedFiles] = useState<MessageFileChange[]>([])
  const [questionFromPoll, setQuestionFromPoll] = useState<CodingAgentQuestion | null>(null)
  const [questionInput, setQuestionInput] = useState('')
  const { isDark } = useTheme()
  const isMobile = useUIStore((state) => state.isMobile)
  const isCodeVariant = variant === 'code'

  // Live progress state for real-time updates
  const [liveSteps, setLiveSteps] = useState<CodingAgentProgressStep[]>([])
  const [liveStepCount, setLiveStepCount] = useState(0)
  const [liveFilesCreated, setLiveFilesCreated] = useState<string[]>([])
  const [liveFilesModified, setLiveFilesModified] = useState<string[]>([])
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Poll for progress when running
  const pollProgress = useCallback(async () => {
    if (!chatId) return

    try {
      // jobId is optional - backend will find the most recent job if not provided
      const response = await codeSessionApi.getCodingAgentProgress(chatId, jobId)
      if (response.data.found) {
        setLiveSteps(response.data.steps || [])
        setLiveStepCount(response.data.step_count)
        setLiveFilesCreated(response.data.files_created || [])
        setLiveFilesModified(response.data.files_modified || [])

        // Recover pending question from progress poll (handles SSE reconnection / page refresh)
        if (response.data.pending_question && onAnswerQuestion) {
          setQuestionFromPoll(response.data.pending_question)
        } else {
          setQuestionFromPoll(null)
        }

        // Auto-expand when we get real progress
        if (response.data.step_count > 0) {
          setIsExpanded(true)
        }
      }
    } catch (err) {
      // Silent fail - progress endpoint may not be available
    }
  }, [chatId, jobId])

  // Start/stop polling based on status
  useEffect(() => {
    if (status === 'running' && chatId) {
      // Start polling immediately
      pollProgress()
      // Then poll every 2 seconds
      pollIntervalRef.current = setInterval(pollProgress, 2000)
    } else {
      // Stop polling
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
      // NOTE: Don't clear live steps on completion - they should remain visible
      // The steps captured during real-time streaming are the user's feedback
      // Clearing them would make the UI flash empty before showing final results
    }

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }
  }, [status, chatId, jobId, pollProgress])

  // Auto-expand when running with progress
  useEffect(() => {
    if (status === 'running' && (steps.length > 0 || liveStepCount > 0)) {
      setIsExpanded(true)
    }
  }, [status, steps.length, liveStepCount])

  // Fetch file changes from versioning API when job completes
  useEffect(() => {
    if (status === 'completed' && jobId) {
      loadVersionedFiles()
    }
  }, [status, jobId])

  const loadVersionedFiles = async () => {
    if (!jobId) return
    try {
      const response = await versionsApi.getJobFileChanges(jobId)
      if (response.data.files?.length > 0) {
        setVersionedFiles(response.data.files)
      }
    } catch (err) {
      // Silent fallback
    }
  }

  const isRunning = status === 'running'
  const isCompleted = status === 'completed'
  const isFailed = status === 'failed'

  // Active question: prefer SSE-delivered prop, fall back to progress-poll recovery
  const activeQuestion = pendingQuestion || questionFromPoll

  // Use live steps if available, otherwise fall back to prop steps
  // IMPORTANT: Preserve the input field which contains tool parameters like file paths
  const displaySteps = liveSteps.length > 0 ? liveSteps.map((s, i) => ({
    job_id: jobId || '',
    step_index: i,
    type: s.type,
    tool: s.tool || undefined,
    content: s.content || undefined,
    input: s.input,  // Keep the input params!
    output: s.output,
  })) : steps

  // Use live file counts if available
  const displayFilesCreated = liveFilesCreated.length > 0 ? liveFilesCreated : result?.files_created || []
  const displayFilesModified = liveFilesModified.length > 0 ? liveFilesModified : result?.files_modified || []

  // Count files - use versionedFiles if available, otherwise fall back to display arrays
  const filesCreated = displayFilesCreated.length
  const filesModified = displayFilesModified.length
  const totalFiles = versionedFiles.length > 0
    ? versionedFiles.length
    : filesCreated + filesModified

  // Check if there's expandable content
  const hasExpandableContent = result?.error ||
    totalFiles > 0 ||
    result?.summary ||
    displaySteps.length > 0 ||
    liveStepCount > 0

  // Build summary text
  const getSummaryText = () => {
    if (isRunning) {
      const stepsToShow = liveSteps.length > 0 ? liveSteps : steps

      if (stepsToShow.length > 0) {
        // Find the latest text response from the agent (not tool calls/results)
        for (let i = stepsToShow.length - 1; i >= 0; i--) {
          const step = stepsToShow[i]
          if ((step.type === 'text' || step.type === 'result') && step.content?.trim()) {
            const text = step.content.trim()
            // Truncate to ~60 chars for display
            return text.length > 60 ? text.slice(0, 60) + '...' : text
          }
        }
        // Fallback: show what tool is being used
        const lastStep = stepsToShow[stepsToShow.length - 1]
        if (lastStep.type === 'tool_call' && lastStep.tool) {
          return `Using ${lastStep.tool}...`
        }
      }
      return 'Starting...'
    }
    if (isFailed) return result?.error ? 'Failed' : 'Failed'
    if (totalFiles > 0) {
      const parts: string[] = []
      if (filesCreated > 0) parts.push(`${filesCreated} created`)
      if (filesModified > 0) parts.push(`${filesModified} modified`)
      return parts.join(', ')
    }
    if (result?.summary && typeof result.summary === 'string') {
      const truncated = result.summary.slice(0, 60)
      return truncated + (result.summary.length > 60 ? '...' : '')
    }
    return 'Done'
  }

  return (
    <div className="min-w-0 overflow-hidden">
      {/* Main inline display - matches other tool displays exactly */}
      <div className="flex items-center gap-1.5 text-xs min-w-0">
        {/* Tool icon + name with running indicator */}
        <div className="relative shrink-0">
          <Terminal className={cn(
            "w-3.5 h-3.5",
            isRunning ? "text-accent-brand" : isCodeVariant ? "text-foreground/50" : "text-muted-foreground"
          )} />
          {isRunning && (
            <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 bg-accent-brand rounded-full animate-pulse" />
          )}
        </div>
        <span className={cn(
          "font-medium shrink-0",
          isRunning ? "text-accent-brand" : isCodeVariant ? "text-foreground/70" : "text-foreground"
        )}>
          Coding Agent
        </span>

        {/* Mode badge */}
        {mode && mode !== 'auto' && (
          <span className={cn(
            "text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded shrink-0",
            mode === 'plan'
              ? "bg-blue-500/10 text-blue-500"
              : "bg-purple-500/10 text-purple-500"
          )}>
            {mode === 'plan' ? 'Planning' : 'Implementing'}
          </span>
        )}

        {/* Duration badge */}
        {result?.duration_ms !== undefined && result.duration_ms > 0 && (
          <span className="flex items-center gap-0.5 font-mono text-muted-foreground/60 shrink-0">
            <Clock className="w-2.5 h-2.5" />
            {formatDuration(result.duration_ms)}
          </span>
        )}

        {/* Summary text */}
        <span className={cn(
          "truncate min-w-0",
          isFailed ? "text-red-400" : "text-muted-foreground/60"
        )}>
          {getSummaryText()}
        </span>
      </div>

      {/* Expandable details section */}
      {hasExpandableContent && (
        <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="ml-2 sm:ml-5 mt-1">
          <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
            <ChevronRight className={cn(
              "w-3 h-3 transition-transform duration-200",
              isExpanded && "rotate-90"
            )} />
            <span>
              {totalFiles > 0 ? `${totalFiles} file${totalFiles > 1 ? 's' : ''}` : 'Details'}
            </span>
            {(displaySteps.length > 0 || (result?.summary && typeof result.summary === 'string')) && (
              <>
                <span className="text-muted-foreground/30">·</span>
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation()
                    setShowFullOutput(true)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.stopPropagation()
                      setShowFullOutput(true)
                    }
                  }}
                  className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  View full output
                </span>
              </>
            )}
          </CollapsibleTrigger>

          <CollapsibleContent>
            <div className={cn(
              "mt-2 ml-2 sm:ml-5 pl-2 sm:pl-3 border-l space-y-2 min-w-0",
              isDark ? "border-border/30" : "border-slate-200"
            )}>
              {/* Error message */}
              {result?.error && (
                <div className={cn(
                  "text-xs p-2 rounded-md",
                  isDark ? "bg-red-500/10 text-red-400" : "bg-red-50 text-red-600"
                )}>
                  {result.error}
                </div>
              )}

              {/* File changes - inline collapsible diffs */}
              {(versionedFiles.length > 0 || totalFiles > 0) && !result?.error && (
                <div className="space-y-1">
                  <span className={cn(
                    "text-[10px] font-medium uppercase tracking-wider",
                    isDark ? "text-muted-foreground/50" : "text-slate-400"
                  )}>
                    Files
                  </span>

                  <div className="space-y-0.5">
                    {/* Versioned files with inline diff viewer */}
                    {versionedFiles.map((file, idx) => (
                      <FileDiffViewer key={`versioned-${idx}`} file={file} isDark={isDark} />
                    ))}

                    {/* Legacy file display (when no versioned files) */}
                    {versionedFiles.length === 0 && (
                      <>
                        {result?.files_created?.map((filePath, idx) => (
                          <div
                            key={`created-${idx}`}
                            className="flex items-center gap-2 py-0.5 text-xs min-w-0"
                          >
                            <span className="font-mono text-muted-foreground/70 truncate min-w-0">
                              {getRelativePath(filePath)}
                            </span>
                            <span className="text-muted-foreground/50 text-[10px] shrink-0">created</span>
                          </div>
                        ))}
                        {result?.files_modified?.map((filePath, idx) => (
                          <div
                            key={`modified-${idx}`}
                            className="flex items-center gap-2 py-0.5 text-xs min-w-0"
                          >
                            <span className="font-mono text-muted-foreground/70 truncate min-w-0">
                              {getRelativePath(filePath)}
                            </span>
                            <span className="text-muted-foreground/50 text-[10px] shrink-0">modified</span>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                </div>
              )}

              {/* Summary (when no files) */}
              {result?.summary && typeof result.summary === 'string' && !result?.error && totalFiles === 0 && (
                <div className="text-[11px] text-muted-foreground/70 leading-relaxed overflow-hidden [&_p]:my-0.5 [&_p]:text-[11px] [&_code]:text-[10px] [&_code]:break-all [&_pre]:overflow-x-auto [&_*]:text-[11px]">
                  <Markdown>{result.summary.slice(0, 300) + (result.summary.length > 300 ? '...' : '')}</Markdown>
                </div>
              )}

              {/* Activity (steps) - grouped, deduplicated, as subtle cards */}
              {displaySteps.length > 0 && (() => {
                const grouped = groupSteps(displaySteps as ExtendedStep[])
                // Filter out text steps and only show tool steps
                const toolSteps = grouped.filter(s => s.type === 'tool')
                if (toolSteps.length === 0) return null

                return (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-medium text-muted-foreground/50 uppercase tracking-wider">
                        Activity
                      </span>
                      {toolSteps.length > 4 && (
                        <button
                          onClick={() => setShowFullOutput(true)}
                          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                        >
                          +{toolSteps.length - 4} more
                        </button>
                      )}
                    </div>
                    <div className="space-y-1">
                      {toolSteps.slice(-4).map((step, index) => (
                        <CompactStepItem
                          key={index}
                          step={step}
                          isDark={isDark}
                        />
                      ))}
                    </div>
                  </div>
                )
              })()}

              {/* Coding Agent Question UI */}
              {isRunning && activeQuestion && chatId && (
                <div className="my-2 rounded-lg border-2 border-amber-500/50 bg-amber-500/5 p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                    </span>
                    <span className="text-xs font-medium text-amber-600 dark:text-amber-400">
                      Agent needs your input
                    </span>
                  </div>
                  <p className="text-sm text-foreground">{activeQuestion.question}</p>
                  {activeQuestion.options && activeQuestion.options.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {activeQuestion.options.map((opt) => (
                        <button
                          key={opt.label}
                          onClick={() => {
                            if (onAnswerQuestion) onAnswerQuestion(opt.label)
                            else codeSessionApi.sendCodingAgentAnswer(chatId, opt.label).catch(() => {})
                            setQuestionFromPoll(null)
                            setQuestionInput('')
                          }}
                          className="px-3 py-1.5 text-xs rounded-md border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-foreground transition-colors"
                          title={opt.description}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={questionInput}
                      onChange={(e) => setQuestionInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && questionInput.trim()) {
                          if (onAnswerQuestion) onAnswerQuestion(questionInput.trim())
                          else codeSessionApi.sendCodingAgentAnswer(chatId, questionInput.trim()).catch(() => {})
                          setQuestionFromPoll(null)
                          setQuestionInput('')
                        }
                      }}
                      placeholder="Type your answer..."
                      className="flex-1 text-xs px-2 py-1.5 rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-amber-500/50"
                    />
                    <button
                      onClick={() => {
                        if (questionInput.trim()) {
                          if (onAnswerQuestion) onAnswerQuestion(questionInput.trim())
                          else codeSessionApi.sendCodingAgentAnswer(chatId, questionInput.trim()).catch(() => {})
                          setQuestionFromPoll(null)
                          setQuestionInput('')
                        }
                      }}
                      disabled={!questionInput.trim()}
                      className="px-3 py-1.5 text-xs rounded-md bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      Send
                    </button>
                    <button
                      onClick={() => {
                        const skipAnswer = 'Proceed with your best judgment'
                        if (onAnswerQuestion) onAnswerQuestion(skipAnswer)
                        else codeSessionApi.sendCodingAgentAnswer(chatId, skipAnswer).catch(() => {})
                        setQuestionFromPoll(null)
                        setQuestionInput('')
                      }}
                      className="px-3 py-1.5 text-xs rounded-md border border-border hover:bg-muted text-muted-foreground transition-colors"
                    >
                      Skip
                    </button>
                  </div>
                </div>
              )}

              {/* Loading state */}
              {isRunning && !result && displaySteps.length === 0 && liveStepCount === 0 && (
                <div className="flex items-center gap-2 py-1">
                  <div className="flex gap-1">
                    <span className="w-1 h-1 rounded-full bg-accent-brand/60 animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1 h-1 rounded-full bg-accent-brand/60 animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1 h-1 rounded-full bg-accent-brand/60 animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                  <span className="text-[10px] text-muted-foreground/50">
                    Initializing...
                  </span>
                </div>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* Full Output Modal/Sheet */}
      {isMobile ? (
        <Sheet open={showFullOutput} onOpenChange={setShowFullOutput}>
          <SheetContent side="bottom" className="h-[85vh] rounded-t-2xl border-t-2 border-t-accent-brand p-0">
            <div className="flex justify-center pt-3 pb-2">
              <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
            </div>
            <SheetHeader className="px-4 pb-3 border-b border-border">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-accent-brand" />
                <SheetTitle className="text-base">Full Output</SheetTitle>
              </div>
              <SheetDescription className="text-xs text-muted-foreground">
                Complete activity log
              </SheetDescription>
            </SheetHeader>
            <div className="flex-1 h-[calc(85vh-100px)] overflow-y-auto overflow-x-hidden">
              <div className="p-4 space-y-4">
                {/* Summary */}
                {result?.summary && typeof result.summary === 'string' && (
                  <div className={cn(
                    "p-3 rounded-lg text-sm leading-relaxed [&_p]:my-1",
                    isDark ? "bg-muted/30" : "bg-slate-50"
                  )}>
                    <Markdown>{result.summary}</Markdown>
                  </div>
                )}

                {/* Steps - grouped, deduplicated, as individual cards */}
                {displaySteps.length > 0 && (() => {
                  const grouped = groupSteps(displaySteps as ExtendedStep[])
                  const toolSteps = grouped.filter(s => s.type === 'tool')
                  return toolSteps.length > 0 ? (
                    <div className="space-y-2">
                      {toolSteps.map((step, index) => (
                        <FullStepItem
                          key={index}
                          step={step}
                          isDark={isDark}
                        />
                      ))}
                    </div>
                  ) : null
                })()}
              </div>
            </div>
          </SheetContent>
        </Sheet>
      ) : (
        <Dialog open={showFullOutput} onOpenChange={setShowFullOutput}>
          <DialogContent className="max-w-2xl h-[80vh] flex flex-col p-0 gap-0">
            <DialogHeader className="px-4 py-3 border-b shrink-0">
              <DialogTitle className="flex items-center gap-2 text-sm font-medium">
                <Terminal className="w-4 h-4 text-accent-brand" />
                Execution Details
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                {displaySteps.length} step{displaySteps.length !== 1 ? 's' : ''} executed
              </DialogDescription>
            </DialogHeader>
            <ScrollArea className="flex-1 h-[calc(80vh-80px)]">
              <div className="p-4 space-y-4">
                {/* Summary */}
                {result?.summary && typeof result.summary === 'string' && (
                  <div className={cn(
                    "p-4 rounded-lg text-sm leading-relaxed [&_p]:my-1",
                    isDark ? "bg-muted/30" : "bg-slate-50"
                  )}>
                    <Markdown>{result.summary}</Markdown>
                  </div>
                )}

                {/* Steps - grouped, deduplicated, as individual cards */}
                {displaySteps.length > 0 && (() => {
                  const grouped = groupSteps(displaySteps as ExtendedStep[])
                  const toolSteps = grouped.filter(s => s.type === 'tool')
                  return toolSteps.length > 0 ? (
                    <div className="space-y-2">
                      {toolSteps.map((step, index) => (
                        <FullStepItem
                          key={index}
                          step={step}
                          isDark={isDark}
                        />
                      ))}
                    </div>
                  ) : null
                })()}
              </div>
            </ScrollArea>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}

export default CodingAgentDisplay
