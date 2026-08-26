/**
 * CommitHistory - IntelliJ-style commit explorer with branch visualization
 *
 * Features:
 * - Visual branch graph with colored lines
 * - Branch filtering
 * - Search by commit message or hash
 * - Branch tags showing position in history
 * - Expandable commit details
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  GitCommit,
  GitBranch,
  Search,
  Filter,
  Loader2,
  ChevronDown,
  ChevronRight,
  Tag,
  User,
  Clock,
  Copy,
  Check,
  RefreshCw,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import axios from 'axios'
import { getAccessToken, orchestratorClient } from '@/api/client'

// Branch colors - inspired by IntelliJ/GitKraken
const BRANCH_COLORS = [
  { name: 'teal', bg: 'bg-teal-500', text: 'text-teal-500', border: 'border-teal-500', hex: '#14b8a6' },
  { name: 'violet', bg: 'bg-violet-500', text: 'text-violet-500', border: 'border-violet-500', hex: '#8b5cf6' },
  { name: 'amber', bg: 'bg-amber-500', text: 'text-amber-500', border: 'border-amber-500', hex: '#f59e0b' },
  { name: 'rose', bg: 'bg-rose-500', text: 'text-rose-500', border: 'border-rose-500', hex: '#f43f5e' },
  { name: 'cyan', bg: 'bg-cyan-500', text: 'text-cyan-500', border: 'border-cyan-500', hex: '#06b6d4' },
  { name: 'lime', bg: 'bg-lime-500', text: 'text-lime-500', border: 'border-lime-500', hex: '#84cc16' },
  { name: 'fuchsia', bg: 'bg-fuchsia-500', text: 'text-fuchsia-500', border: 'border-fuchsia-500', hex: '#d946ef' },
  { name: 'orange', bg: 'bg-orange-500', text: 'text-orange-500', border: 'border-orange-500', hex: '#f97316' },
  { name: 'sky', bg: 'bg-sky-500', text: 'text-sky-500', border: 'border-sky-500', hex: '#0ea5e9' },
  { name: 'emerald', bg: 'bg-emerald-500', text: 'text-emerald-500', border: 'border-emerald-500', hex: '#10b981' },
]

interface Commit {
  hash: string
  shortHash: string
  message: string
  author: string
  authorEmail: string
  date: Date
  relativeDate: string
  branches: string[]
  tags: string[]
  parents: string[]
  isHead: boolean
}

interface BranchInfo {
  name: string
  color: typeof BRANCH_COLORS[number]
  isRemote: boolean
  isCurrent: boolean
}

interface CommitHistoryProps {
  userId?: string
  projectId: string
  currentBranch?: string
  className?: string
}

export function CommitHistory({
  userId,
  projectId,
  currentBranch,
  className,
}: CommitHistoryProps) {
  const [commits, setCommits] = useState<Commit[]>([])
  const [branches, setBranches] = useState<BranchInfo[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedBranches, setSelectedBranches] = useState<Set<string>>(new Set())
  const [expandedCommits, setExpandedCommits] = useState<Set<string>>(new Set())
  const [copiedHash, setCopiedHash] = useState<string | null>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  // Assign colors to branches consistently
  const branchColorMap = useMemo(() => {
    const map = new Map<string, typeof BRANCH_COLORS[number]>()
    branches.forEach((branch, index) => {
      map.set(branch.name, BRANCH_COLORS[index % BRANCH_COLORS.length])
    })
    return map
  }, [branches])

  // Execute git command via orchestrator
  const executeGitCommand = useCallback(async (command: string): Promise<{ success: boolean; output: string; error?: string }> => {
    if (!userId) return { success: false, output: '', error: 'Not authenticated' }

    const token = getAccessToken()
    if (!token) return { success: false, output: '', error: 'Not authenticated' }

    try {
      const response = await orchestratorClient.post('/execute', {
        code: `cd repo && ${command}`,
        language: 'bash',
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        sync_mode: true,
        project_id: projectId,
        timeout: 30,
      })

      const result = response.data
      return {
        success: result.exit_code === 0,
        output: result.output || '',
        error: result.error || (result.exit_code !== 0 ? result.output : undefined),
      }
    } catch (error) {
      if (axios.isAxiosError(error) && error.response) {
        return { success: false, output: '', error: `Request failed: ${error.response.statusText}` }
      }
      return { success: false, output: '', error: error instanceof Error ? error.message : 'Unknown error' }
    }
  }, [userId, projectId])

  // Fetch branches
  const fetchBranches = useCallback(async (): Promise<BranchInfo[]> => {
    const result = await executeGitCommand('git branch -a --format="%(refname:short)|%(HEAD)"')
    if (!result.success) return []

    const branchList: BranchInfo[] = []
    const lines = result.output.trim().split('\n').filter(Boolean)
    const seenNames = new Set<string>()

    lines.forEach((line, index) => {
      const [name, isHead] = line.split('|')
      if (!name || name.includes('HEAD') || name.includes('->')) return

      const isRemote = name.startsWith('remotes/') || name.startsWith('origin/')
      const cleanName = name.replace(/^remotes\/origin\//, '').replace(/^origin\//, '')

      // Skip duplicates
      if (seenNames.has(cleanName)) return
      seenNames.add(cleanName)

      branchList.push({
        name: cleanName,
        color: BRANCH_COLORS[branchList.length % BRANCH_COLORS.length],
        isRemote,
        isCurrent: isHead === '*',
      })
    })

    return branchList
  }, [executeGitCommand])

  // Fetch commits with graph info
  const fetchCommits = useCallback(async () => {
    if (!userId || !projectId) return

    setIsLoading(true)
    setError(null)

    try {
      // Fetch branches first
      const branchList = await fetchBranches()
      setBranches(branchList)

      // Build branch filter for git log
      const branchArgs = selectedBranches.size > 0
        ? Array.from(selectedBranches).map(b => b).join(' ')
        : '--all'

      // Get commit log with decoration and parent info
      // Using %x00 as field separator to handle special characters in messages
      const logCommand = `git log ${branchArgs} --format="%H%x00%h%x00%an%x00%ae%x00%ci%x00%cr%x00%s%x00%D%x00%P" -150 2>/dev/null || git log --format="%H%x00%h%x00%an%x00%ae%x00%ci%x00%cr%x00%s%x00%D%x00%P" -150`

      const logResult = await executeGitCommand(logCommand)

      if (!logResult.success) {
        setError(logResult.error || 'Failed to fetch commits')
        setCommits([])
        return
      }

      const lines = logResult.output.trim().split('\n').filter(Boolean)
      const commitList: Commit[] = []
      const branchHeads = new Map<string, number>() // Map branch name to commit index

      lines.forEach((line, index) => {
        const parts = line.split('\x00')
        if (parts.length < 7) return

        const [hash, shortHash, author, authorEmail, dateStr, relativeDate, message, decorations = '', parentStr = ''] = parts

        // Parse decorations to extract branches and tags
        const commitBranches: string[] = []
        const commitTags: string[] = []
        let isHead = false

        if (decorations) {
          const decParts = decorations.split(', ')
          decParts.forEach(dec => {
            const trimmed = dec.trim()
            if (trimmed.startsWith('HEAD')) {
              isHead = true
              const match = trimmed.match(/HEAD -> (.+)/)
              if (match) commitBranches.push(match[1].replace('origin/', ''))
            } else if (trimmed.startsWith('tag:')) {
              commitTags.push(trimmed.replace('tag: ', ''))
            } else if (trimmed.startsWith('origin/') && !trimmed.includes('HEAD')) {
              commitBranches.push(trimmed.replace('origin/', ''))
            } else if (!trimmed.includes('/') && trimmed.length > 0) {
              commitBranches.push(trimmed)
            }
          })
        }

        // Track which branches have this as their head commit
        commitBranches.forEach(b => {
          if (!branchHeads.has(b)) {
            branchHeads.set(b, index)
          }
        })

        commitList.push({
          hash,
          shortHash,
          author,
          authorEmail,
          date: new Date(dateStr),
          relativeDate,
          message,
          branches: [...new Set(commitBranches)],
          tags: commitTags,
          parents: parentStr ? parentStr.split(' ').filter(Boolean) : [],
          isHead,
        })
      })

      setCommits(commitList)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setCommits([])
    } finally {
      setIsLoading(false)
    }
  }, [userId, projectId, executeGitCommand, fetchBranches, selectedBranches])

  // Load commits on mount and when dependencies change
  useEffect(() => {
    fetchCommits()
  }, [fetchCommits])

  // Filter commits based on search and branch selection
  const filteredCommits = useMemo(() => {
    let result = commits

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      result = result.filter(commit =>
        commit.message.toLowerCase().includes(query) ||
        commit.hash.toLowerCase().startsWith(query) ||
        commit.shortHash.toLowerCase().startsWith(query) ||
        commit.author.toLowerCase().includes(query) ||
        commit.branches.some(b => b.toLowerCase().includes(query)) ||
        commit.tags.some(t => t.toLowerCase().includes(query))
      )
    }

    return result
  }, [commits, searchQuery])

  // Toggle branch filter
  const toggleBranchFilter = (branchName: string) => {
    setSelectedBranches(prev => {
      const next = new Set(prev)
      if (next.has(branchName)) {
        next.delete(branchName)
      } else {
        next.add(branchName)
      }
      return next
    })
  }

  // Toggle commit expansion
  const toggleCommitExpansion = (hash: string) => {
    setExpandedCommits(prev => {
      const next = new Set(prev)
      if (next.has(hash)) {
        next.delete(hash)
      } else {
        next.add(hash)
      }
      return next
    })
  }

  // Copy hash to clipboard
  const copyHash = async (hash: string, e: React.MouseEvent) => {
    e.stopPropagation()
    await navigator.clipboard.writeText(hash)
    setCopiedHash(hash)
    setTimeout(() => setCopiedHash(null), 2000)
  }

  // Clear all filters
  const clearFilters = () => {
    setSearchQuery('')
    setSelectedBranches(new Set())
  }

  // Get color for a branch
  const getBranchColor = (branchName: string) => {
    return branchColorMap.get(branchName) || BRANCH_COLORS[0]
  }

  // Render branch/tag badges for a commit
  const renderBranchTags = (commit: Commit) => {
    const items = [
      ...commit.branches.map(b => ({ name: b, type: 'branch' as const })),
      ...commit.tags.map(t => ({ name: t, type: 'tag' as const })),
    ]

    if (items.length === 0) return null

    return (
      <div className="flex flex-wrap gap-1">
        {items.slice(0, 4).map((item) => {
          const color = item.type === 'branch' ? getBranchColor(item.name) : BRANCH_COLORS[0]
          const isCurrent = item.type === 'branch' && item.name === currentBranch

          return (
            <TooltipProvider key={`${item.type}-${item.name}`}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge
                    variant="outline"
                    className={cn(
                      "h-[18px] px-1.5 text-[9px] font-medium gap-0.5 cursor-default shrink-0",
                      item.type === 'branch' && color.border,
                      item.type === 'branch' && color.text,
                      item.type === 'tag' && 'border-slate-500 text-slate-400',
                      isCurrent && `${color.bg} text-white border-transparent`
                    )}
                  >
                    {item.type === 'branch' ? (
                      <GitBranch className="h-2.5 w-2.5" />
                    ) : (
                      <Tag className="h-2.5 w-2.5" />
                    )}
                    <span className="max-w-[60px] truncate">{item.name}</span>
                  </Badge>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  {item.type === 'branch' ? 'Branch' : 'Tag'}: {item.name}
                  {isCurrent && ' (current)'}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )
        })}
        {items.length > 4 && (
          <Badge variant="outline" className="h-[18px] px-1 text-[9px] text-muted-foreground">
            +{items.length - 4}
          </Badge>
        )}
      </div>
    )
  }

  // Render the graph visualization for a commit
  const renderGraph = (commit: Commit, index: number) => {
    const color = commit.branches.length > 0 ? getBranchColor(commit.branches[0]) : BRANCH_COLORS[0]
    const isFirst = index === 0
    const isLast = index === filteredCommits.length - 1

    return (
      <div className="relative w-10 shrink-0 flex items-center justify-center">
        {/* Vertical line - top half */}
        {!isFirst && (
          <div
            className={cn("absolute top-0 left-1/2 -translate-x-1/2 w-[2px] h-1/2", color.bg)}
            style={{ opacity: 0.6 }}
          />
        )}

        {/* Vertical line - bottom half */}
        {!isLast && (
          <div
            className={cn("absolute bottom-0 left-1/2 -translate-x-1/2 w-[2px] h-1/2", color.bg)}
            style={{ opacity: 0.6 }}
          />
        )}

        {/* Commit node */}
        <div
          className={cn(
            "relative w-3 h-3 rounded-full border-2 z-10",
            "bg-background",
            color.border,
            commit.isHead && `${color.bg} border-transparent`
          )}
        />
      </div>
    )
  }

  if (!userId) {
    return (
      <div className={cn("flex items-center justify-center h-full text-muted-foreground text-sm", className)}>
        <User className="h-4 w-4 mr-2" />
        Sign in to view commit history
      </div>
    )
  }

  return (
    <div className={cn("flex flex-col h-full bg-background", className)}>
      {/* Header with search and filters */}
      <div className="flex items-center gap-2 px-3 py-2 border-b bg-muted/30 shrink-0">
        {/* Search */}
        <div className="relative flex-1 max-w-[200px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search commits..."
            className="h-7 pl-7 pr-7 text-xs bg-background"
          />
          {searchQuery && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-0 top-0 h-7 w-7"
              onClick={() => setSearchQuery('')}
            >
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>

        {/* Branch filter */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className={cn(
                "h-7 text-xs gap-1",
                selectedBranches.size > 0 && "border-primary text-primary"
              )}
            >
              <Filter className="h-3 w-3" />
              <span className="hidden sm:inline">Filter</span>
              {selectedBranches.size > 0 && (
                <Badge variant="secondary" className="h-4 px-1 text-[9px] ml-0.5">
                  {selectedBranches.size}
                </Badge>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="max-h-60 overflow-y-auto">
            <DropdownMenuLabel className="text-xs py-1">Filter by branch</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {branches.length === 0 ? (
              <div className="px-2 py-3 text-xs text-muted-foreground text-center">
                No branches found
              </div>
            ) : (
              branches.map(branch => (
                <DropdownMenuCheckboxItem
                  key={branch.name}
                  checked={selectedBranches.has(branch.name)}
                  onCheckedChange={() => toggleBranchFilter(branch.name)}
                  className="text-xs cursor-pointer py-1.5"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <div className={cn("w-2 h-2 rounded-full shrink-0", branch.color.bg)} />
                    <span className="min-w-0">{branch.name}</span>
                    {branch.name === currentBranch && (
                      <span className="text-[9px] text-primary shrink-0">HEAD</span>
                    )}
                  </div>
                </DropdownMenuCheckboxItem>
              ))
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Clear filters */}
        {(searchQuery || selectedBranches.size > 0) && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-muted-foreground"
            onClick={clearFilters}
          >
            <X className="h-3 w-3" />
          </Button>
        )}

        {/* Refresh */}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 ml-auto"
          onClick={fetchCommits}
          disabled={isLoading}
        >
          <RefreshCw className={cn("h-3 w-3", isLoading && "animate-spin")} />
        </Button>
      </div>

      {/* Branch legend */}
      {branches.length > 0 && !isLoading && (
        <div className="flex items-center gap-1.5 px-3 py-1.5 border-b bg-muted/20 overflow-x-auto shrink-0">
          <TooltipProvider delayDuration={200}>
            {branches.slice(0, 8).map(branch => (
              <Tooltip key={branch.name}>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => toggleBranchFilter(branch.name)}
                    className={cn(
                      "flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] transition-all shrink-0",
                      selectedBranches.has(branch.name)
                        ? `${branch.color.bg} text-white`
                        : "hover:bg-muted border border-transparent hover:border-border"
                    )}
                  >
                    <div className={cn(
                      "w-1.5 h-1.5 rounded-full shrink-0",
                      selectedBranches.has(branch.name) ? "bg-white" : branch.color.bg
                    )} />
                    <span className="truncate max-w-[70px]">{branch.name}</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="text-xs">
                  {branch.name}
                  {branch.name === currentBranch && ' (current)'}
                </TooltipContent>
              </Tooltip>
            ))}
          </TooltipProvider>
          {branches.length > 8 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="text-[10px] text-muted-foreground hover:text-foreground shrink-0 px-1.5 py-0.5 rounded hover:bg-muted transition-colors">
                  +{branches.length - 8}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="max-h-60 overflow-y-auto">
                <DropdownMenuLabel className="text-xs py-1">More branches</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {branches.slice(8).map(branch => (
                  <DropdownMenuCheckboxItem
                    key={branch.name}
                    checked={selectedBranches.has(branch.name)}
                    onCheckedChange={() => toggleBranchFilter(branch.name)}
                    className="text-xs cursor-pointer py-1.5"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <div className={cn("w-2 h-2 rounded-full shrink-0", branch.color.bg)} />
                      <span className="min-w-0">{branch.name}</span>
                      {branch.name === currentBranch && (
                        <span className="text-[9px] text-primary shrink-0">HEAD</span>
                      )}
                    </div>
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      )}

      {/* Commits list */}
      <div className="flex-1 overflow-y-auto" ref={scrollContainerRef}>
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="text-xs text-muted-foreground mt-2">Loading commits...</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground px-4">
            <GitCommit className="h-8 w-8 mb-2 opacity-50" />
            <p className="text-xs text-center">{error}</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3 text-xs h-7"
              onClick={fetchCommits}
            >
              Try again
            </Button>
          </div>
        ) : filteredCommits.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <GitCommit className="h-8 w-8 mb-2 opacity-50" />
            <p className="text-xs">
              {commits.length === 0 ? 'No commits found' : 'No matching commits'}
            </p>
          </div>
        ) : (
          <div>
            {filteredCommits.map((commit, index) => {
              const isExpanded = expandedCommits.has(commit.hash)
              const isCopied = copiedHash === commit.hash

              return (
                <div
                  key={commit.hash}
                  className={cn(
                    "group flex hover:bg-muted/30 transition-colors",
                    commit.isHead && "bg-primary/5"
                  )}
                >
                  {/* Graph */}
                  {renderGraph(commit, index)}

                  {/* Commit info */}
                  <div className="flex-1 py-2 pr-3 min-w-0">
                    {/* Main row */}
                    <div className="flex items-start gap-2">
                      {/* Expand button */}
                      <button
                        onClick={() => toggleCommitExpansion(commit.hash)}
                        className="p-0.5 rounded hover:bg-muted shrink-0 mt-0.5"
                      >
                        {isExpanded ? (
                          <ChevronDown className="h-3 w-3 text-muted-foreground" />
                        ) : (
                          <ChevronRight className="h-3 w-3 text-muted-foreground" />
                        )}
                      </button>

                      <div className="flex-1 min-w-0 space-y-1">
                        {/* Message and branches */}
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={cn(
                            "text-sm font-medium truncate",
                            commit.isHead && "text-primary"
                          )}>
                            {commit.message}
                          </span>
                          {renderBranchTags(commit)}
                        </div>

                        {/* Meta row */}
                        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                          {/* Hash with copy */}
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <button
                                  onClick={(e) => copyHash(commit.hash, e)}
                                  className="flex items-center gap-1 font-mono hover:text-foreground transition-colors"
                                >
                                  {isCopied ? (
                                    <Check className="h-2.5 w-2.5 text-green-500" />
                                  ) : (
                                    <Copy className="h-2.5 w-2.5 opacity-0 group-hover:opacity-100" />
                                  )}
                                  <span className="text-primary/70">{commit.shortHash}</span>
                                </button>
                              </TooltipTrigger>
                              <TooltipContent side="top" className="text-[10px]">
                                {isCopied ? 'Copied!' : 'Copy hash'}
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>

                          <span className="flex items-center gap-1 truncate">
                            <User className="h-2.5 w-2.5 shrink-0" />
                            <span className="truncate max-w-[100px]">{commit.author}</span>
                          </span>

                          <span className="flex items-center gap-1 shrink-0">
                            <Clock className="h-2.5 w-2.5" />
                            {commit.relativeDate}
                          </span>
                        </div>

                        {/* Expanded details */}
                        {isExpanded && (
                          <div className="mt-2 p-2 bg-muted/40 rounded text-[10px] space-y-1.5">
                            <div className="grid grid-cols-[70px,1fr] gap-1">
                              <span className="text-muted-foreground">Hash:</span>
                              <code className="font-mono break-all select-all">{commit.hash}</code>
                            </div>
                            <div className="grid grid-cols-[70px,1fr] gap-1">
                              <span className="text-muted-foreground">Author:</span>
                              <span>{commit.author} &lt;{commit.authorEmail}&gt;</span>
                            </div>
                            <div className="grid grid-cols-[70px,1fr] gap-1">
                              <span className="text-muted-foreground">Date:</span>
                              <span>{commit.date.toLocaleString()}</span>
                            </div>
                            {commit.parents.length > 0 && (
                              <div className="grid grid-cols-[70px,1fr] gap-1">
                                <span className="text-muted-foreground">Parents:</span>
                                <span className="font-mono">{commit.parents.map(p => p.slice(0, 7)).join(', ')}</span>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      {!isLoading && commits.length > 0 && (
        <div className="flex items-center justify-between px-3 py-1 border-t bg-muted/20 text-[10px] text-muted-foreground shrink-0">
          <span>
            {filteredCommits.length === commits.length
              ? `${commits.length} commits`
              : `${filteredCommits.length} / ${commits.length} commits`}
          </span>
          <span>{branches.length} branches</span>
        </div>
      )}
    </div>
  )
}
