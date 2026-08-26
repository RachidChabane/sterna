/**
 * BottomPanel - Unified panel with Output, Terminal, and Git tabs
 * Uses GitPanel's design language for consistency
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { Terminal, ChevronDown, Loader2, Play, Trash2, GitCommit, GitCompare, Globe, Square, Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import axios from 'axios'
import { getAccessToken, orchestratorClient } from '@/api/client'
import { fsAPI } from '@/api/fs'
import type { ExecutionResult } from './types'
import { CommitHistory } from '@/components/sandbox/CommitHistory'
import {
  startProcess,
  listProcesses,
  stopProcess,
  type ProcessInfo,
} from '@/api/sandbox'

type TabType = 'output' | 'terminal' | 'commits' | 'changes' | 'ports'

interface TerminalEntry {
  id: string
  command: string
  output: string
  error?: string
  exitCode?: number
  timestamp: Date
  isRunning: boolean
  cwd: string  // Working directory when command was executed
}

interface BottomPanelProps {
  open: boolean
  onClose: () => void
  activeTab: TabType
  onTabChange: (tab: TabType) => void
  height?: number
  maxHeight?: number
  onHeightChange?: (height: number) => void
  // Output props
  result?: ExecutionResult | null
  onClearOutput?: () => void
  // Terminal props
  userId?: string
  conversationId?: string
  chatId?: string
  mode?: 'chat' | 'code'  // For code sessions, terminal starts in repo/ directory
  // Git props (optional - for code sessions)
  gitModifiedFiles?: string[]
  gitCurrentBranch?: string
  // Ports tab callback
  onPreviewPort?: (port: number) => void
}

export function BottomPanel({
  open,
  onClose,
  activeTab,
  onTabChange,
  height = 250,
  maxHeight,
  onHeightChange,
  result,
  onClearOutput,
  userId,
  conversationId,
  chatId,
  mode = 'chat',
  // Git props
  gitModifiedFiles,
  gitCurrentBranch,
  // Ports
  onPreviewPort,
}: BottomPanelProps) {
  // Use chatId first for isolation (consistent with FullIDE.tsx)
  const projectId = chatId || conversationId || ''

  // For code sessions, start in the repo/ directory where the cloned repo lives
  const initialCwd = mode === 'code' ? 'repo' : '.'

  // Terminal state - cwd is relative to the chat workspace (backend handles the actual workspace path)
  const [entries, setEntries] = useState<TerminalEntry[]>([])
  const [command, setCommand] = useState('')
  const [isExecuting, setIsExecuting] = useState(false)
  const [historyIndex, setHistoryIndex] = useState(-1)
  const [commandHistory, setCommandHistory] = useState<string[]>([])
  const [cwd, setCwd] = useState(initialCwd)  // Current working directory relative to chat workspace
  const cwdRef = useRef(cwd)  // Ref to always get latest cwd value
  const inputRef = useRef<HTMLInputElement>(null)
  const terminalScrollRef = useRef<HTMLDivElement>(null)
  const outputScrollRef = useRef<HTMLDivElement>(null)

  // Ports state
  const [processes, setProcesses] = useState<ProcessInfo[]>([])
  const [portCommand, setPortCommand] = useState('npm run dev')
  const [portNumber, setPortNumber] = useState('3000')
  const [isStartingProcess, setIsStartingProcess] = useState(false)
  const [portError, setPortError] = useState<string | null>(null)

  // Poll processes when ports tab is active
  useEffect(() => {
    if (activeTab !== 'ports' || !userId || !projectId) return
    let cancelled = false
    const poll = async () => {
      try {
        const list = await listProcesses(userId, projectId)
        if (!cancelled) setProcesses(list)
      } catch { /* ignore */ }
    }
    poll()
    const interval = setInterval(poll, 5000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [activeTab, userId, projectId])

  const handleStartProcess = useCallback(async () => {
    if (!userId || !portCommand.trim() || isStartingProcess) return
    const port = parseInt(portNumber, 10)
    if (isNaN(port) || port < 3000 || port > 9999) {
      setPortError('Port must be between 3000 and 9999')
      return
    }
    setPortError(null)
    setIsStartingProcess(true)
    try {
      const proc = await startProcess({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        command: portCommand.trim(),
        port,
      })
      setProcesses(prev => [...prev, proc])
    } catch (e) {
      setPortError(e instanceof Error ? e.message : 'Failed to start process')
    } finally {
      setIsStartingProcess(false)
    }
  }, [userId, projectId, portCommand, portNumber, isStartingProcess])

  const handleStopProcess = useCallback(async (pid: number) => {
    if (!userId) return
    try {
      await stopProcess({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        pid,
      })
      setProcesses(prev => prev.filter(p => p.pid !== pid))
    } catch { /* ignore */ }
  }, [userId, projectId])

  // Keep cwdRef in sync with cwd state
  useEffect(() => {
    cwdRef.current = cwd
  }, [cwd])

  // Reset terminal when chat changes
  useEffect(() => {
    setCwd(initialCwd)
    cwdRef.current = initialCwd
    setEntries([])
  }, [projectId, initialCwd])

  // Resize state
  const resizeRef = useRef<{ startY: number; startHeight: number } | null>(null)
  const [isResizing, setIsResizing] = useState(false)

  // Auto-scroll terminal when new entries are added
  useEffect(() => {
    if (terminalScrollRef.current && activeTab === 'terminal') {
      terminalScrollRef.current.scrollTop = terminalScrollRef.current.scrollHeight
    }
  }, [entries, activeTab])

  // Focus input when terminal tab is active
  useEffect(() => {
    if (open && activeTab === 'terminal') {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [open, activeTab])

  // Resize handlers
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
    resizeRef.current = { startY: e.clientY, startHeight: height }
  }, [height])

  useEffect(() => {
    if (!isResizing) return

    const handleMouseMove = (e: MouseEvent) => {
      if (!resizeRef.current) return
      const delta = resizeRef.current.startY - e.clientY
      // Use maxHeight prop if provided, otherwise default to 500
      const effectiveMaxHeight = maxHeight || 500
      const newHeight = Math.min(Math.max(150, resizeRef.current.startHeight + delta), effectiveMaxHeight)
      onHeightChange?.(newHeight)
    }

    const handleMouseUp = () => {
      setIsResizing(false)
      resizeRef.current = null
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizing, onHeightChange, maxHeight])

  const executeCommand = async () => {
    if (!command.trim() || !userId || isExecuting) return

    const entryId = Date.now().toString()
    const trimmedCommand = command.trim()

    // Add to history
    setCommandHistory(prev => [trimmedCommand, ...prev.filter(c => c !== trimmedCommand)].slice(0, 50))
    setHistoryIndex(-1)

    // Create entry with current working directory
    const newEntry: TerminalEntry = {
      id: entryId,
      command: trimmedCommand,
      output: '',
      timestamp: new Date(),
      isRunning: true,
      cwd,
    }

    setEntries(prev => [...prev, newEntry])
    setCommand('')
    setIsExecuting(true)

    try {
      const token = getAccessToken()
      if (!token) {
        throw new Error('Not authenticated')
      }

      // Backend already sets workdir to /workspace/chat-{chatId}
      // We track relative cwd for subdirectory navigation
      // Use ref to get latest cwd value (avoids stale closure issues)
      const currentCwd = cwdRef.current
      // SECURITY: Escape double quotes to prevent command injection
      const escapedCwd = currentCwd.replace(/"/g, '\\"').replace(/\$/g, '\\$').replace(/`/g, '\\`')
      const cdPrefix = currentCwd === '.' ? '' : `cd "${escapedCwd}" && `

      // Check if this is a cd command - we need to track directory changes
      const isCdCommand = /^\s*cd(\s|$)/.test(trimmedCommand)

      // For cd commands, append pwd to get new directory
      // For other commands, just run them normally
      const wrappedCommand = isCdCommand
        ? `${cdPrefix}${trimmedCommand} && pwd`
        : `${cdPrefix}${trimmedCommand}`

      let result: ExecutionResult
      try {
        const response = await orchestratorClient.post<ExecutionResult>('/execute', {
          code: wrappedCommand,
          language: 'bash',
          user_id: userId,
          conversation_id: projectId,
          chat_id: projectId,
          sync_mode: true,
          project_id: projectId,
          timeout: 30,
        })
        result = response.data
      } catch (err) {
        if (axios.isAxiosError(err) && err.response) {
          throw new Error(`Execution failed: ${err.response.statusText}`)
        }
        throw err
      }

      let output: string = result.output || ''

      // Check if the cwd directory doesn't exist (sandbox expired)
      // Reset to root if we get "No such file or directory" for our cwd
      const cwdNotFound = result.exit_code !== 0 &&
        (output.includes('No such file or directory') ||
         result.error?.includes('No such file or directory'))

      if (cwdNotFound && currentCwd !== '.') {
        // The working directory no longer exists, reset to root
        setCwd('.')
        // Re-run the command from root
        setEntries(prev => prev.map(e =>
          e.id === entryId
            ? {
                ...e,
                output: '',
                error: `Directory "${currentCwd}" no longer exists. Session may have expired. Reset to workspace root.`,
                exitCode: 1,
                isRunning: false,
                cwd: '.',
              }
            : e
        ))
        setIsExecuting(false)
        setTimeout(() => inputRef.current?.focus(), 50)
        return
      }

      // For cd commands, extract new working directory from pwd output (last line)
      // Do this BEFORE sanitizing so we can parse the real path
      if (isCdCommand && result.exit_code === 0 && output) {
        // Filter out empty lines and get the last non-empty line (pwd output)
        const pwdLine = output.trim().split('\n').filter(l => l.trim()).pop()?.trim() || ''
        // Don't show pwd output to user
        output = ''

        // Convert absolute path to relative path from chat workspace
        // Only update cwd if still within chat workspace (prevent escape)
        if (pwdLine) {
          const match = pwdLine.match(/\/workspace\/chat-[^/]+(.*)$/)
          if (match) {
            const relativePath = match[1] || ''
            setCwd(relativePath === '' ? '.' : relativePath.replace(/^\//, ''))
          } else {
            // User tried to cd outside workspace (e.g., cd ..) - keep at root
            setCwd('.')
          }
        }
      } else {
        // Sanitize output: hide chat ID from paths for cleaner display
        // Replace /workspace/chat-{uuid} with ~ (home-like notation)
        output = output.replace(/\/workspace\/chat-[a-f0-9-]*/gi, '~')
      }

      setEntries(prev => prev.map(e =>
        e.id === entryId
          ? {
              ...e,
              output,
              error: result.error || undefined,
              exitCode: result.exit_code,
              isRunning: false,
            }
          : e
      ))
    } catch (error) {
      setEntries(prev => prev.map(e =>
        e.id === entryId
          ? {
              ...e,
              error: error instanceof Error ? error.message : 'Execution failed',
              isRunning: false,
            }
          : e
      ))
    } finally {
      setIsExecuting(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Tab') {
      e.preventDefault()
      e.stopPropagation()
      handleTabComplete()
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      executeCommand()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (commandHistory.length > 0) {
        const newIndex = Math.min(historyIndex + 1, commandHistory.length - 1)
        setHistoryIndex(newIndex)
        setCommand(commandHistory[newIndex])
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (historyIndex > 0) {
        const newIndex = historyIndex - 1
        setHistoryIndex(newIndex)
        setCommand(commandHistory[newIndex])
      } else if (historyIndex === 0) {
        setHistoryIndex(-1)
        setCommand('')
      }
    } else if (e.key === 'c' && e.ctrlKey) {
      setCommand('')
      setHistoryIndex(-1)
    } else if (e.key === 'l' && e.ctrlKey) {
      e.preventDefault()
      setEntries([])
    }
  }

  const clearTerminal = () => {
    setEntries([])
    setCwd(initialCwd)  // Reset to initial directory
  }

  // Tab completion for file/directory names
  const handleTabComplete = useCallback(async () => {
    if (!userId || !command.trim()) return

    // Get the last word being typed (potential file/dir name)
    const words = command.split(/\s+/)
    const lastWord = words[words.length - 1] || ''

    // Determine the directory to search and the prefix to match
    let searchDir = cwd === '.' ? '/workspace' : `/workspace/${cwd}`
    let prefix = lastWord

    // If lastWord contains a path separator, split into dir and prefix
    const lastSlash = lastWord.lastIndexOf('/')
    if (lastSlash !== -1) {
      const pathPart = lastWord.substring(0, lastSlash) || '/'
      prefix = lastWord.substring(lastSlash + 1)
      // Resolve relative to current directory
      if (pathPart.startsWith('/')) {
        searchDir = `/workspace${pathPart}`
      } else {
        searchDir = cwd === '.' ? `/workspace/${pathPart}` : `/workspace/${cwd}/${pathPart}`
      }
    }

    try {
      const result = await fsAPI.listFiles({
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        project_id: projectId,
        path: searchDir,
      })

      if (!result.success || !result.files) return

      // Filter files that start with the prefix
      const matches = result.files
        .filter(f => f.name.toLowerCase().startsWith(prefix.toLowerCase()))
        .map(f => f.type === 'directory' ? f.name + '/' : f.name)

      if (matches.length === 0) return

      if (matches.length === 1) {
        // Single match - complete it
        const completion = matches[0]
        const newLastWord = lastSlash !== -1
          ? lastWord.substring(0, lastSlash + 1) + completion
          : completion
        words[words.length - 1] = newLastWord
        setCommand(words.join(' '))
      } else {
        // Multiple matches - find common prefix
        const commonPrefix = matches.reduce((acc, match) => {
          let i = 0
          while (i < acc.length && i < match.length && acc[i].toLowerCase() === match[i].toLowerCase()) {
            i++
          }
          return acc.substring(0, i)
        })

        if (commonPrefix.length > prefix.length) {
          // Complete to common prefix
          const newLastWord = lastSlash !== -1
            ? lastWord.substring(0, lastSlash + 1) + commonPrefix
            : commonPrefix
          words[words.length - 1] = newLastWord
          setCommand(words.join(' '))
        }

        // Show available options in a temporary entry
        const optionsEntry: TerminalEntry = {
          id: `tab-${Date.now()}`,
          command: '',
          output: matches.join('  '),
          timestamp: new Date(),
          isRunning: false,
          cwd,
        }
        setEntries(prev => [...prev, optionsEntry])
      }
    } catch (error) {
      console.error('Tab completion error:', error)
    }
  }, [command, cwd, userId, projectId])

  if (!open) return null

  // Check if we have git data (modified files)
  const hasGitData = !!gitModifiedFiles

  return (
    <div
      className="flex flex-col border-t border-border bg-card"
      style={{ height }}
    >
      {/* Resize handle */}
      <div
        className="h-1 cursor-row-resize hover:bg-primary/30 active:bg-primary/50 transition-colors group shrink-0"
        onMouseDown={handleResizeStart}
      >
        <div className="h-full flex items-center justify-center">
          <div className="w-8 h-0.5 rounded-full bg-muted-foreground/20 group-hover:bg-primary/50" />
        </div>
      </div>

      {/* Header */}
      <div className="flex items-center justify-end px-3 py-2 border-b border-border/50">
        <div className="flex items-center gap-1">
          {/* Clear button (only for output/terminal) */}
          {(activeTab === 'output' || activeTab === 'terminal') && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={activeTab === 'terminal' ? clearTerminal : onClearOutput}
              title={activeTab === 'terminal' ? 'Clear terminal' : 'Clear output'}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={onClose}
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Tabs - GitPanel style */}
      <Tabs
        value={activeTab}
        onValueChange={(v) => onTabChange(v as TabType)}
        className="flex-1 flex flex-col min-h-0"
      >
        <TabsList className="h-9 w-full justify-start rounded-none border-b bg-transparent px-1 shrink-0">
          {/* Git tabs (only show when git data is available) */}
          {hasGitData && (
            <>
              <TabsTrigger
                value="commits"
                className="h-9 px-3 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
              >
                <GitCommit className="h-3.5 w-3.5 mr-1.5" />
                <span className="text-xs">Commits</span>
              </TabsTrigger>
              <TabsTrigger
                value="changes"
                className="h-9 px-3 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
              >
                <GitCompare className="h-3.5 w-3.5 mr-1.5" />
                <span className="text-xs">Changes</span>
                {gitModifiedFiles && gitModifiedFiles.length > 0 && (
                  <span className="ml-1.5 px-1.5 text-[10px] bg-primary/20 text-primary rounded">
                    {gitModifiedFiles.length}
                  </span>
                )}
              </TabsTrigger>
            </>
          )}

          {/* Output tab */}
          <TabsTrigger
            value="output"
            className="h-9 px-3 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            <Play className="h-3.5 w-3.5 mr-1.5" />
            <span className="text-xs">Output</span>
            {result && (
              <span
                className={cn(
                  'ml-1.5 w-2 h-2 rounded-full',
                  result.exit_code === 0 ? 'bg-emerald-500' : 'bg-red-500'
                )}
              />
            )}
          </TabsTrigger>

          {/* Terminal tab */}
          <TabsTrigger
            value="terminal"
            className="h-9 px-3 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            <Terminal className="h-3.5 w-3.5 mr-1.5" />
            <span className="text-xs">Terminal</span>
          </TabsTrigger>

          {/* Ports tab */}
          <TabsTrigger
            value="ports"
            className="h-9 px-3 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            <Globe className="h-3.5 w-3.5 mr-1.5" />
            <span className="text-xs">Ports</span>
            {processes.length > 0 && (
              <span className="ml-1.5 px-1.5 text-[10px] bg-primary/20 text-primary rounded">
                {processes.length}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Commits content */}
        <TabsContent value="commits" className="flex-1 m-0 min-h-0 data-[state=inactive]:hidden">
          <CommitHistory
            userId={userId}
            projectId={projectId}
            currentBranch={gitCurrentBranch}
          />
        </TabsContent>

        {/* Changes content */}
        <TabsContent value="changes" className="flex-1 m-0 min-h-0 data-[state=inactive]:hidden">
          {gitModifiedFiles && gitModifiedFiles.length > 0 ? (
            <ScrollArea className="h-full">
              <div className="p-2 space-y-1">
                {gitModifiedFiles.map((file, index) => (
                  <div
                    key={index}
                    className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50 cursor-pointer text-xs"
                  >
                    <span className="w-4 h-4 flex items-center justify-center rounded text-[9px] bg-emerald-500/20 text-emerald-500">
                      M
                    </span>
                    <span className="font-mono truncate">{file}</span>
                  </div>
                ))}
              </div>
              <ScrollBar orientation="vertical" />
            </ScrollArea>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <GitCompare className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-xs">No changes detected</p>
            </div>
          )}
        </TabsContent>

        {/* Output content */}
        <TabsContent value="output" className="flex-1 m-0 min-h-0 data-[state=inactive]:hidden">
          {result ? (
            <ScrollArea className="h-full" ref={outputScrollRef}>
              <div className="p-3">
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className={cn(
                      'text-xs px-2 py-0.5 rounded font-medium',
                      result.exit_code === 0
                        ? 'bg-emerald-900/30 text-emerald-400'
                        : 'bg-red-900/30 text-red-400'
                    )}
                  >
                    {result.exit_code === 0 ? 'Success' : 'Failed'}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {result.execution_time.toFixed(3)}s
                  </span>
                </div>
                {result.output && (
                  <pre className="text-xs font-mono whitespace-pre-wrap break-words leading-relaxed">
                    {result.output}
                  </pre>
                )}
                {result.error && (
                  <pre className="text-xs font-mono text-red-400 whitespace-pre-wrap break-words mt-2 leading-relaxed bg-red-900/20 p-2 rounded border border-red-800/50">
                    {result.error}
                  </pre>
                )}
              </div>
              <ScrollBar orientation="vertical" />
            </ScrollArea>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground/50 text-xs">
              Run code to see output
            </div>
          )}
        </TabsContent>

        {/* Terminal content */}
        <TabsContent value="terminal" className="flex-1 m-0 min-h-0 flex flex-col data-[state=inactive]:hidden">
          <ScrollArea className="flex-1" ref={terminalScrollRef}>
            <div className="font-mono text-xs p-2 space-y-2">
              {entries.length === 0 ? (
                <div className="text-muted-foreground/50 py-4 text-center">
                  Type a command and press Enter to execute
                </div>
              ) : (
                entries.map((entry) => (
                  <div key={entry.id} className="space-y-0.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-blue-400 text-[10px]">~{entry.cwd === '.' ? '' : `/${entry.cwd}`}</span>
                      <span className="text-primary">$</span>
                      <span>{entry.command}</span>
                      {entry.isRunning && (
                        <Loader2 className="h-3 w-3 animate-spin text-primary" />
                      )}
                    </div>
                    {entry.output && (
                      <pre className="text-muted-foreground whitespace-pre-wrap pl-4 text-[11px] leading-relaxed">
                        {entry.output}
                      </pre>
                    )}
                    {entry.error && (
                      <pre className="text-red-400 whitespace-pre-wrap pl-4 text-[11px] leading-relaxed">
                        {entry.error}
                      </pre>
                    )}
                    {entry.exitCode !== undefined && entry.exitCode !== 0 && (
                      <div className="text-red-400/70 pl-4 text-[10px]">
                        Exit code: {entry.exitCode}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
            <ScrollBar orientation="vertical" />
          </ScrollArea>

          {/* Terminal input */}
          <div className="flex items-center gap-2 px-2 py-1.5 border-t border-border/30 bg-muted/20 shrink-0">
            <span className="text-blue-400 text-[10px] font-mono shrink-0">~{cwd === '.' ? '' : `/${cwd}`}</span>
            <span className="text-primary text-xs font-mono">$</span>
            <Input
              ref={inputRef}
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter command..."
              disabled={isExecuting}
              className="h-7 text-xs font-mono bg-transparent border-0 focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-muted-foreground/30"
            />
            {isExecuting && (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />
            )}
          </div>
        </TabsContent>

        {/* Ports content */}
        <TabsContent value="ports" className="flex-1 m-0 min-h-0 flex flex-col data-[state=inactive]:hidden">
          {/* Start form */}
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border/30 bg-muted/20 shrink-0">
            <Input
              value={portCommand}
              onChange={(e) => setPortCommand(e.target.value)}
              placeholder="Command (e.g. npm run dev)"
              className="h-7 text-xs font-mono flex-1 bg-transparent"
              onKeyDown={(e) => e.key === 'Enter' && handleStartProcess()}
            />
            <Input
              value={portNumber}
              onChange={(e) => setPortNumber(e.target.value.replace(/\D/g, ''))}
              placeholder="Port"
              className="h-7 text-xs font-mono w-20 bg-transparent"
              onKeyDown={(e) => e.key === 'Enter' && handleStartProcess()}
            />
            <Button
              size="sm"
              className="h-7 px-3 gap-1.5"
              onClick={handleStartProcess}
              disabled={isStartingProcess || !portCommand.trim()}
            >
              {isStartingProcess ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Play className="h-3 w-3" />
              )}
              <span className="text-xs">Start</span>
            </Button>
          </div>
          {portError && (
            <div className="px-3 py-1 text-xs text-red-400 bg-red-900/20 border-b border-red-800/30">
              {portError}
            </div>
          )}

          {/* Process list */}
          <ScrollArea className="flex-1">
            {processes.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground py-8">
                <Globe className="h-8 w-8 mb-2 opacity-50" />
                <p className="text-xs">No running processes</p>
                <p className="text-[10px] text-muted-foreground/60 mt-1">Start a dev server to preview it here</p>
              </div>
            ) : (
              <div className="p-2">
                <div className="grid grid-cols-[60px_1fr_60px_80px_auto] gap-x-3 px-2 py-1 text-[10px] text-muted-foreground/60 uppercase tracking-wider border-b border-border/30 mb-1">
                  <span>Port</span>
                  <span>Command</span>
                  <span>PID</span>
                  <span>Status</span>
                  <span>Actions</span>
                </div>
                {processes.map((proc) => (
                  <div
                    key={proc.pid}
                    className="grid grid-cols-[60px_1fr_60px_80px_auto] gap-x-3 items-center px-2 py-1.5 rounded hover:bg-muted/50 text-xs"
                  >
                    <span className="font-mono text-primary">{proc.port}</span>
                    <span className="font-mono truncate">{proc.command}</span>
                    <span className="font-mono text-muted-foreground">{proc.pid}</span>
                    <span className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      <span className="text-emerald-400 text-[11px]">Running</span>
                    </span>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 gap-1 text-[11px]"
                        onClick={() => onPreviewPort?.(proc.port)}
                      >
                        <Eye className="h-3 w-3" />
                        Preview
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 gap-1 text-[11px] text-red-400 hover:text-red-300 hover:bg-red-900/30"
                        onClick={() => handleStopProcess(proc.pid)}
                      >
                        <Square className="h-3 w-3" />
                        Stop
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <ScrollBar orientation="vertical" />
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  )
}
