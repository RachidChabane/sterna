/**
 * write_file body: an expandable, syntax-highlighted view of the content
 * that was written.
 */
import { memo, useState } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { ChevronRight } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { isRecord, asString } from './shared'
import type { ToolRenderContext } from './types'
import type { ToolResult } from '@/api/llm'

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

export function WriteFileBody({ execution, filePath }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting) return null

  const args: { path?: string; content?: string } = (() => {
    try { return JSON.parse(execution.tool_call.function.arguments) } catch { return {} }
  })()

  return <WriteFileContentResult result={execution.result} filePath={filePath || undefined} args={args} />
}

const WriteFileContentResult = memo(({ result, filePath, args }: {
  result: ToolResult
  filePath?: string
  args?: { path?: string; content?: string }
}) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const { isDark } = useTheme()
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  // Get content from args (what was written) or try to extract from result
  let content = args?.content || ''

  // If no content in args, try to extract from result
  if (!content && result) {
    try {
      const parsed: unknown = typeof result === 'string' ? JSON.parse(result) : result
      const data = isRecord(parsed) ? parsed.data : undefined
      content = (isRecord(data) ? asString(data.content) : undefined) || (isRecord(parsed) ? asString(parsed.content) : undefined) || ''
    } catch {
      // ignore
    }
  }

  if (!content) return null

  const filename = filePath || args?.path || 'file'
  const lineCount = content.split('\n').length

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="ml-5">
      {/* Header - clickable to expand */}
      <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
        <ChevronRight className={cn(
          "h-3 w-3 transition-transform duration-200",
          isExpanded && "rotate-90"
        )} />
        <span className="text-emerald-500">+ {lineCount} lines written</span>
        <span className="text-muted-foreground/40">·</span>
        <span>{isExpanded ? 'Hide' : 'View content'}</span>
      </CollapsibleTrigger>

      {/* Content - animated */}
      <CollapsibleContent>
        <div className={cn(
          "mt-1.5 pl-3 border-l border-border/40 max-h-[300px] overflow-y-auto rounded-r",
          isDark ? "bg-card/30" : "bg-slate-50/50"
        )}>
          <SyntaxHighlighter
            language={getLanguage(filename)}
            style={codeTheme.style}
            showLineNumbers={true}
            wrapLongLines={true}
            customStyle={{
              margin: 0,
              padding: '0.5rem',
              background: 'transparent',
              fontSize: '0.65rem',
              lineHeight: '1.4',
            }}
            lineNumberStyle={{
              minWidth: '2em',
              paddingRight: '0.5em',
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
