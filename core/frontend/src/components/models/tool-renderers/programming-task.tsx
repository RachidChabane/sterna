/** execute_programming_task body: a compact result summary with an optional code/output drill-down. */
import { memo, useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { ChevronRight, Code2, Copy, Check } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { sanitizeOutput, isRecord } from './shared'
import type { ToolRenderContext } from './types'
import type { ToolResult } from '@/api/llm'

const WRAPPER_KEYS = new Set(['success', 'error', 'output', 'data', 'result', '_truncated', '_summary', 'status', 'task'])

/** Like `isRecord`, but (matching this file's original loose checks) also accepts arrays. */
const isObjectLike = (val: unknown): val is Record<string, unknown> => typeof val === 'object' && val !== null

/** Returns the first truthy value, or `null` if none — the unknown-shaped equivalent of `a || b || c || null`. */
const firstTruthy = (...vals: unknown[]): unknown => vals.find(Boolean) ?? null

// Recursively parse JSON strings until we get a non-string value.
const deepJsonParse = (val: unknown): unknown => {
  if (typeof val !== 'string') return val
  try { return deepJsonParse(JSON.parse(val)) } catch { return val }
}

// Recursively unwrap common wrapper objects (`{ data: { result: ... } }` etc.) to reach the actual payload.
const unwrapResult = (obj: unknown): unknown => {
  if (!isObjectLike(obj) || Array.isArray(obj)) return obj
  const dataResult = isObjectLike(obj.data) ? obj.data.result : undefined
  if (dataResult) return unwrapResult(dataResult)
  if (isObjectLike(obj.result)) return unwrapResult(obj.result)
  if (isRecord(obj.data)) return unwrapResult(obj.data)
  return obj
}

// Get useful keys from an object (exclude wrapper keys)
const getDataKeys = (obj: unknown): string[] => {
  if (!isObjectLike(obj)) return []
  return Object.keys(obj).filter((k) => !WRAPPER_KEYS.has(k))
}

// Extract useful data from a parsed result, unwrapping common wrappers first. `includeOutputFallback`
// additionally falls back to `{ output }` when no other data keys were found (used by the expanded view only).
const extractUsefulFields = (obj: unknown, includeOutputFallback = false): Record<string, unknown> | null => {
  if (!isObjectLike(obj) || Array.isArray(obj)) return null
  const dataResult = isObjectLike(obj.data) ? obj.data.result : undefined
  if (dataResult) return extractUsefulFields(dataResult, includeOutputFallback)
  if (isObjectLike(obj.result)) return extractUsefulFields(obj.result, includeOutputFallback)
  if (isObjectLike(obj.data)) return extractUsefulFields(obj.data, includeOutputFallback)
  const keys = Object.keys(obj).filter((k) => !WRAPPER_KEYS.has(k))
  if (keys.length > 0) {
    const extracted: Record<string, unknown> = {}
    keys.forEach((k) => { extracted[k] = obj[k] })
    return extracted
  }
  if (includeOutputFallback && typeof obj.output === 'string') {
    return { output: obj.output }
  }
  return null
}

export function ProgrammingTaskBody({ execution }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting) return null

  const code: string | undefined = (() => {
    try { return JSON.parse(execution.tool_call.function.arguments)?.code } catch { return undefined }
  })()

  return <ProgrammingTaskResult result={execution.result} code={code} />
}

// Component for displaying file content in a collapsible section with syntax highlighting
const FileContentDisplay = memo(({ filename, content, isDark }: {
  filename: string
  content: string
  isDark: boolean
}) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  // Detect language from filename extension
  const getLanguage = (fname: string): string => {
    const ext = fname.split('.').pop()?.toLowerCase() || ''
    const langMap: Record<string, string> = {
      'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'tsx': 'tsx',
      'jsx': 'jsx', 'json': 'json', 'md': 'markdown', 'yml': 'yaml',
      'yaml': 'yaml', 'sh': 'bash', 'bash': 'bash', 'css': 'css',
      'html': 'html', 'sql': 'sql', 'go': 'go', 'rs': 'rust',
      'rb': 'ruby', 'java': 'java', 'cpp': 'cpp', 'c': 'c', 'h': 'c',
    }
    return langMap[ext] || 'text'
  }

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const lineCount = content.split('\n').length
  const charCount = content.length

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className={cn(
      "border rounded overflow-hidden",
      isDark ? "border-slate-700" : "border-slate-300"
    )}>
      <CollapsibleTrigger className={cn(
        "w-full flex items-center justify-between px-2 py-1.5 text-xs transition-colors",
        isDark ? "bg-slate-800/50 hover:bg-slate-800" : "bg-slate-100 hover:bg-slate-200"
      )}>
        <div className="flex items-center gap-2">
          <ChevronRight className={cn(
            "h-3 w-3 transition-transform duration-200",
            isExpanded && "rotate-90",
            isDark ? "text-slate-400" : "text-slate-500"
          )} />
          <span className={cn("font-mono font-medium", isDark ? "text-slate-300" : "text-slate-700")}>
            {filename}
          </span>
          <span className={cn("text-xs", isDark ? "text-slate-500" : "text-slate-400")}>
            ({lineCount} lines, {charCount > 1000 ? `${(charCount / 1000).toFixed(1)}K` : charCount} chars)
          </span>
        </div>
        {isExpanded && (
          <button
            onClick={(e) => { e.stopPropagation(); handleCopy() }}
            className={cn(
              "flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors",
              copied
                ? "text-emerald-500"
                : isDark
                  ? "text-slate-400 hover:text-slate-300 hover:bg-slate-700/50"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-200/50"
            )}
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          </button>
        )}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="max-h-[400px] overflow-y-auto">
          <SyntaxHighlighter
            language={getLanguage(filename)}
            style={codeTheme.style}
            showLineNumbers={true}
            wrapLongLines={true}
            customStyle={{
              margin: 0,
              padding: '0.5rem',
              background: isDark ? '#1a1a2e' : '#f8f8f8',
              fontSize: '0.7rem',
              lineHeight: '1.5',
            }}
            lineNumberStyle={{
              minWidth: '2.5em',
              paddingRight: '0.75em',
              color: isDark ? '#4a5568' : '#a0aec0',
              userSelect: 'none',
            }}
          >
            {content}
          </SyntaxHighlighter>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})

// Component for displaying execute_programming_task results - compact like other tools
const ProgrammingTaskResult = memo(({ result, code }: { result: ToolResult | string, code?: string }) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const [showCode, setShowCode] = useState(false)
  const { isDark } = useTheme()
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  // Parse the result - deeply unwrap nested JSON strings
  const parsed = useMemo(() => {
    const r = deepJsonParse(result)
    if (!isObjectLike(r)) {
      return { success: false as unknown, error: null as unknown, output: typeof result === 'string' ? result : null, data: null as Record<string, unknown> | null }
    }

    const rData = isObjectLike(r.data) ? r.data : undefined
    const rDataResult = isObjectLike(rData?.result) ? rData.result : undefined
    const success = r.success ?? true
    const error = firstTruthy(r.error, rData?.error, rDataResult?.error)

    // Unwrap to get the actual data
    const unwrapped = unwrapResult(r)
    const dataKeys = getDataKeys(unwrapped)

    // If we have actual data keys, use as structured data
    if (dataKeys.length > 0 && isObjectLike(unwrapped)) {
      // Filter to only include the actual data, not wrapper fields
      const cleanData: Record<string, unknown> = {}
      for (const key of dataKeys) {
        cleanData[key] = unwrapped[key]
      }
      return { success, error, output: null as unknown, data: cleanData }
    }

    // Otherwise check for output field
    const output = firstTruthy(r.output, rData?.output, rDataResult?.output)
    return { success, error, output, data: null as Record<string, unknown> | null }
  }, [result])

  const { success, error } = parsed

  // Get summary for collapsed view - extract useful info
  const summary = useMemo(() => {
    // Check for error first
    let raw: unknown = result
    if (typeof raw === 'string') {
      try { raw = JSON.parse(raw) } catch { /* keep string */ }
    }
    const rawData = isObjectLike(raw) ? raw.data : undefined
    const err = firstTruthy(isObjectLike(raw) ? raw.error : undefined, isObjectLike(rawData) ? rawData.error : undefined)
    if (err) {
      const lines = String(err).split('\n')
      const errorLine = lines.find(l => l.includes('Error:') || l.includes('Exception:')) || lines[lines.length - 1]
      return errorLine?.slice(0, 80) || 'Error'
    }

    // Try to extract data
    const extracted = extractUsefulFields(raw)
    if (extracted) {
      const keys = Object.keys(extracted)
      const firstValue = extracted[keys[0]]
      if (keys.length === 1 && Array.isArray(firstValue)) {
        return `${keys[0]}: ${firstValue.length} items`
      }
      const preview = keys.slice(0, 3).join(', ')
      return keys.length > 3 ? `${preview}, +${keys.length - 3} more` : preview
    }

    // Check for output
    const outputVal = firstTruthy(isObjectLike(raw) ? raw.output : undefined, isObjectLike(rawData) ? rawData.output : undefined)
    if (outputVal && typeof outputVal === 'string' && !outputVal.startsWith('{')) {
      return sanitizeOutput(outputVal).slice(0, 60)
    }

    return success ? 'Completed' : 'Failed'
  }, [result, success])

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="ml-5 mt-1">
      {/* Compact header */}
      <div className="flex items-center gap-2">
        <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
          <ChevronRight className={cn(
            "h-3 w-3 transition-transform duration-200",
            isExpanded && "rotate-90"
          )} />
          <span className="truncate max-w-[350px]">{isExpanded ? 'Hide output' : summary}</span>
        </CollapsibleTrigger>
        {code && (
          <button
            onClick={() => setShowCode(!showCode)}
            className="flex items-center gap-1 text-xs text-muted-foreground/40 hover:text-muted-foreground transition-colors"
          >
            <Code2 className="h-3 w-3" />
            <span>{showCode ? 'Hide' : 'View'} code</span>
          </button>
        )}
      </div>

      {/* Code display */}
      {showCode && code && (
        <div className="mt-1.5 ml-4 max-h-[200px] overflow-y-auto rounded bg-[#1e1e1e]">
          <SyntaxHighlighter
            language="python"
            style={codeTheme.style}
            showLineNumbers={true}
            wrapLongLines={true}
            customStyle={{ margin: 0, padding: '0.5rem', background: 'transparent', fontSize: '0.7rem' }}
          >
            {code}
          </SyntaxHighlighter>
        </div>
      )}

      {/* Expanded output */}
      <CollapsibleContent>
        <div className="mt-1.5 ml-4 max-h-[300px] overflow-y-auto space-y-2">
          {/* Error */}
          {Boolean(error) && (
            <pre className="text-xs font-mono whitespace-pre-wrap break-all text-red-400 bg-red-500/10 rounded p-2">
              {sanitizeOutput(String(error))}
            </pre>
          )}

          {/* Always try to extract and display useful data */}
          {!error && (() => {
            let raw: unknown = result
            if (typeof raw === 'string') {
              try { raw = JSON.parse(raw) } catch { /* keep as string */ }
            }
            const extracted = extractUsefulFields(raw, true)

            if (!extracted) {
              // Last resort: show raw output if it's a simple string
              if (typeof result === 'string' && !result.startsWith('{')) {
                return <pre className="text-xs font-mono text-muted-foreground">{sanitizeOutput(result)}</pre>
              }
              return <span className="text-xs text-muted-foreground/60">No data to display</span>
            }

            return (
              <div className="space-y-1.5">
                {Object.entries(extracted).map(([key, value]) => {
                  // File content
                  const isFile = key.includes('/') || (key.includes('.') && typeof value === 'string' && value.length > 100)
                  if (isFile && typeof value === 'string') {
                    return <FileContentDisplay key={key} filename={key} content={value} isDark={isDark} />
                  }
                  // Arrays
                  if (Array.isArray(value)) {
                    const preview = value.slice(0, 5).map(v => typeof v === 'string' ? v : JSON.stringify(v)).join(', ')
                    return (
                      <div key={key} className="text-xs">
                        <span className="text-muted-foreground/60 font-medium">{key}:</span>
                        <span className="ml-2 text-muted-foreground font-mono">
                          {value.length} items{value.length > 0 ? `: ${preview}${value.length > 5 ? '...' : ''}` : ''}
                        </span>
                      </div>
                    )
                  }
                  // Plain output
                  if (key === 'output' && typeof value === 'string') {
                    return (
                      <pre key={key} className="text-xs font-mono whitespace-pre-wrap text-muted-foreground">
                        {sanitizeOutput(value)}
                      </pre>
                    )
                  }
                  // Other values
                  return (
                    <div key={key} className="text-xs">
                      <span className="text-muted-foreground/60 font-medium">{key}:</span>
                      <span className="ml-2 text-muted-foreground font-mono">
                        {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )
          })()}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})
