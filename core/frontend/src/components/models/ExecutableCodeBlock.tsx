/**
 * ExecutableCodeBlock Component
 *
 * Executable code block with run functionality for Python, JavaScript, and Bash.
 * Follows the same minimalist design as CodeBlock.
 */

import { useState, useRef } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { Check, Copy, Play, Loader2, ChevronDown, ChevronRight, StopCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/store/authStore'
import { useChatPanelContextSafe } from './ChatPanelContext'
import axios from 'axios'
import { toErrorMessage } from '@/utils/errorMessages'
import { getAccessToken, orchestratorClient } from '@/api/client'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'

interface ExecutableCodeBlockProps {
  code: string
  language: string
  className?: string
}

interface ExecutionResult {
  output: string
  error: string | null
  exit_code: number
  execution_time: number
  artifacts: any[]
}

// Map language aliases
const LANGUAGE_MAP: Record<string, string> = {
  'python': 'python',
  'py': 'python',
  'python3': 'python',
  'javascript': 'javascript',
  'js': 'javascript',
  'node': 'javascript',
  'bash': 'bash',
  'sh': 'bash',
  'shell': 'bash',
}

const getNormalizedLanguage = (lang: string): string => {
  return LANGUAGE_MAP[lang.toLowerCase()] || lang
}

export function ExecutableCodeBlock({ code, language, className }: ExecutableCodeBlockProps) {
  const { toast } = useToast()
  const { user } = useAuthStore()
  const { isDark } = useTheme()
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)
  const chatContext = useChatPanelContextSafe()

  // Extract values from context (may be undefined if outside ChatPanelProvider)
  const conversationId = chatContext?.conversationId
  const chatId = chatContext?.chatId
  const syncMode = chatContext?.syncMode

  // Execution is only available when context is present
  const canExecute = !!chatContext
  const [copied, setCopied] = useState(false)
  const [isExecuting, setIsExecuting] = useState(false)
  const [result, setResult] = useState<ExecutionResult | null>(null)
  const [isResultExpanded, setIsResultExpanded] = useState(true)
  const abortControllerRef = useRef<AbortController | null>(null)
  const executionIdRef = useRef<string | null>(null)

  const normalizedLanguage = getNormalizedLanguage(language)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleAbort = async () => {
    if (!executionIdRef.current) {
      return
    }

    const executionId = executionIdRef.current
    const token = getAccessToken()

    if (!token) {
      return
    }

    // Give immediate feedback to user - don't wait for backend response
    setIsExecuting(false)
    toast({
      title: 'Cancelling Execution',
      description: 'Stopping code execution...',
    })

    // Abort the HTTP request immediately
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    try {
      // Call cancel endpoint (fire and forget - cleanup happens in background)
      orchestratorClient.post(`/cancel/${executionId}`).catch(error => {
        console.error('[ABORT] Failed to cancel execution:', error)
      })
    } finally {
      abortControllerRef.current = null
      executionIdRef.current = null
    }
  }

  const handleExecute = async () => {
    if (!user) {
      toast({
        title: 'Authentication Required',
        description: 'Please sign in to execute code',
        variant: 'destructive',
      })
      return
    }

    // Get access token
    const token = getAccessToken()
    if (!token) {
      toast({
        title: 'Authentication Error',
        description: 'No authentication token found. Please sign in again.',
        variant: 'destructive',
      })
      return
    }

    setIsExecuting(true)
    setResult(null)

    // Generate unique execution ID
    const executionId = `exec-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
    executionIdRef.current = executionId

    // Create abort controller for this execution
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    try {
      const response = await orchestratorClient.post<ExecutionResult>('/execute', {
        code,
        language: normalizedLanguage,
        user_id: user.id.toString(),
        conversation_id: conversationId || 'default',
        chat_id: chatId,
        sync_mode: syncMode ?? true,
        project_id: 'default',
        timeout: 30,
        execution_id: executionId,
      }, { signal: abortController.signal })

      setResult(response.data)
    } catch (error) {
      // Don't show error if execution was aborted by user (axios raises
      // a CanceledError; a bare AbortError is also handled defensively)
      if (axios.isCancel(error) || (error instanceof Error && error.name === 'AbortError')) {
        setResult({
          output: '',
          error: 'Execution cancelled by user',
          exit_code: 1,
          execution_time: 0,
          artifacts: [],
        })
      } else {
        const message = axios.isAxiosError(error) && error.response
          ? `HTTP ${error.response.status}`
          : toErrorMessage(error) || 'Execution failed'
        setResult({
          output: '',
          error: message,
          exit_code: 1,
          execution_time: 0,
          artifacts: [],
        })
      }
    } finally {
      setIsExecuting(false)
      abortControllerRef.current = null
      executionIdRef.current = null
    }
  }

  // Custom Pre component
  const CustomPre = ({ children, ...props }: any) => (
    <pre {...props} style={{ ...props.style, margin: 0, padding: 0, background: 'transparent' }}>
      {children}
    </pre>
  )

  return (
    <div className={cn(
      "group relative my-4 rounded-xl overflow-hidden transition-all duration-200",
      isDark
        ? "bg-[#0d1117] border border-slate-800 hover:border-slate-700 hover:ring-1 hover:ring-slate-700/50"
        : "bg-[#1e1e1e] border border-slate-700 hover:border-slate-600 hover:ring-1 hover:ring-slate-600/50"
    )}>
      {/* Header */}
      <div className="flex items-center justify-between bg-transparent px-4 py-3">
        <span className="text-xs font-mono text-slate-400">{language}</span>

        <div className={cn(
          "flex items-center gap-2 transition-opacity duration-200",
          isExecuting ? "opacity-100" : "opacity-0 group-hover:opacity-100"
        )}>
          {/* Run/Stop buttons - only shown when context is available */}
          {canExecute && (
            isExecuting ? (
              <>
                <button
                  onClick={handleAbort}
                  className={cn(
                    'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium',
                    'transition-all duration-200',
                    'hover:bg-red-500/20',
                    'focus:outline-none focus:ring-2 focus:ring-red-500/50',
                    'text-red-400 hover:text-red-300'
                  )}
                >
                  <StopCircle className="h-3.5 w-3.5" />
                  <span>Stop</span>
                </button>
                <div className="flex items-center gap-1.5 px-2.5 py-1.5 text-slate-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span className="text-xs font-medium">Running...</span>
                </div>
              </>
            ) : (
              <button
                onClick={handleExecute}
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium',
                  'transition-all duration-200',
                  'hover:bg-slate-700/50',
                  'focus:outline-none focus:ring-2 focus:ring-accent-brand/50',
                  'text-slate-400 hover:text-slate-200'
                )}
              >
                <Play className="h-3.5 w-3.5" />
                <span>Run</span>
              </button>
            )
          )}

          {/* Copy button */}
          <button
            onClick={handleCopy}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium',
              'transition-all duration-200',
              'hover:bg-slate-700/50',
              'focus:outline-none focus:ring-2 focus:ring-accent-brand/50',
              copied
                ? 'text-accent-brand opacity-100'
                : 'text-slate-400 hover:text-slate-200'
            )}
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5" />
                <span>Copied!</span>
              </>
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Code */}
      <div className="overflow-x-auto px-4 pb-4 bg-transparent">
        <style>{`
          .codeblock-content * {
            background-color: transparent !important;
            border: none !important;
          }
        `}</style>
        <div className="codeblock-content">
          <SyntaxHighlighter
            language={normalizedLanguage}
            style={codeTheme.style}
            showLineNumbers={false}
            wrapLongLines={true}
            PreTag={CustomPre}
            lineProps={{
              style: {
                backgroundColor: 'transparent',
                display: 'block',
              },
            }}
            customStyle={{
              margin: 0,
              padding: 0,
              background: 'transparent',
              fontSize: '0.875rem',
              lineHeight: '1.7',
              letterSpacing: '0.01em',
              border: 'none',
              color: codeTheme.textColor,
            }}
            codeTagProps={{
              style: {
                fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                fontWeight: '400',
                letterSpacing: '0.01em',
                backgroundColor: 'transparent',
                color: codeTheme.textColor,
              },
            }}
          >
            {code.trim()}
          </SyntaxHighlighter>
        </div>
      </div>

      {/* Execution Result */}
      {result && (
        <div className="border-t border-slate-800 bg-transparent">
          {/* Result Header - Always visible, clickable to expand/collapse */}
          <button
            onClick={() => setIsResultExpanded(!isResultExpanded)}
            className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-slate-800/30 transition-colors"
          >
            <div className="flex items-center gap-2">
              {isResultExpanded ? (
                <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
              )}
              <span className={cn(
                "text-xs font-mono font-medium",
                result.exit_code === 0 ? "text-emerald-400" : "text-red-400"
              )}>
                {result.exit_code === 0 ? '✓ Success' : '✗ Error'}
              </span>
              <span className="text-xs font-mono text-slate-500">
                {result.execution_time.toFixed(3)}s
              </span>
            </div>
            <span className="text-xs text-slate-500">
              {isResultExpanded ? 'Collapse' : 'Expand'}
            </span>
          </button>

          {/* Result Content - Collapsible and scrollable */}
          {isResultExpanded && (
            <div className="px-4 pb-3 max-h-[400px] overflow-y-auto">
              {result.output && (
                <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap break-all">
                  {result.output}
                </pre>
              )}

              {result.error && (
                <pre className={cn(
                  "text-xs font-mono text-red-400 whitespace-pre-wrap break-all",
                  result.output && "mt-2"
                )}>
                  {result.error}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
