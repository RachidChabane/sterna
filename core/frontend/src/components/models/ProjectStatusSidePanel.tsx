/**
 * ProjectStatusSidePanel Component
 *
 * Side panel for displaying cloned repository, agent plans, and pull requests.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  X,
  GitBranch,
  FileText,
  GitPullRequest,
  ExternalLink,
  FolderGit2,
  Loader2,
  GripVertical,
  ChevronRight,
  Github,
  Lock,
  CircleDot,
  Play,
  RefreshCw,
  Maximize2,
  Pencil,
  Import,
  Copy,
  Trash2,
  ChevronDown,
  ArrowLeftRight,
  Check,
  Code2,
  Clock,
  MessageSquare,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useProjectPanelStore, type AgentPlan, type ClonedRepo } from '@/store/projectPanelStore'
import { useConversationStore } from '@/store/conversationStore'
import { codeSessionApi, transformRepoStatus, type GitHubRepo, type GitHubIssue, type GitHubCommit } from '@/api/codeSession'
import { conversationsAPI } from '@/api/conversations'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useUIStore } from '@/store/uiStore'
import { useToast } from '@/hooks/use-toast'
import { Markdown } from '@/components/ui/markdown'
import { FilePreviewModal } from '@/components/models/FilePreviewModal'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useChatMessageDispatch } from '@/hooks/useChatMessageDispatch'
import { getDefaultModelParameters } from '@/config/modelParameters'
import { getApiErrorMessage, hasErrorResponse } from '@/utils/errorMessages'

interface ProjectStatusSidePanelProps {
  conversationId: string
  chatId?: string
  className?: string
}

// Panel size constants
const MIN_PANEL_WIDTH = 350
const MAX_PANEL_WIDTH = 600
const DEFAULT_PANEL_WIDTH = 400

// Status badge component
function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    creating: 'bg-yellow-500/10 text-yellow-500',
    ready: 'bg-blue-500/10 text-blue-500',
    in_progress: 'bg-purple-500/10 text-purple-500',
    completed: 'bg-green-500/10 text-green-500',
    failed: 'bg-red-500/10 text-red-500',
    pending: 'bg-muted text-muted-foreground',
  }

  return (
    <span className={cn('text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded', styles[status] || styles.pending)}>
      {status.replace('_', ' ')}
    </span>
  )
}

// Repo selector when no repo is cloned
function RepoSelector({ conversationId, chatId, onCloneSuccess }: { conversationId: string; chatId?: string; onCloneSuccess: () => void }) {
  const navigate = useNavigate()
  const { clonedRepo, setClonedRepo } = useProjectPanelStore()
  const activeConversation = useConversationStore((s) => s.activeConversation)

  const [githubLoading, setGithubLoading] = useState(true)
  const [githubConnected, setGithubConnected] = useState(false)
  const [githubUsername, setGithubUsername] = useState<string | null>(null)
  const [repos, setRepos] = useState<GitHubRepo[]>([])
  const [reposLoading, setReposLoading] = useState(false)
  const [cloningRepoId, setCloningRepoId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmRepo, setConfirmRepo] = useState<GitHubRepo | null>(null)

  // Check if the current conversation has messages
  const isConversationEmpty = !activeConversation?.chats?.some(
    (c) => c.messages && c.messages.length > 0
  )

  // Check GitHub status
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const response = await codeSessionApi.getGitHubStatus()
        setGithubConnected(response.data.connected)
        setGithubUsername(response.data.username)
        if (response.data.connected) {
          fetchRepos()
        }
      } catch {
        setGithubConnected(false)
      } finally {
        setGithubLoading(false)
      }
    }
    checkStatus()
  }, [])

  const fetchRepos = async () => {
    setReposLoading(true)
    try {
      const response = await codeSessionApi.getRepos(1, 50)
      const sorted = [...response.data.results].sort((a, b) => Number(a.private) - Number(b.private))
      setRepos(sorted)
    } catch {
      setRepos([])
    } finally {
      setReposLoading(false)
    }
  }

  const handleConnectGithub = async () => {
    try {
      const response = await codeSessionApi.connectGitHub()
      sessionStorage.setItem('github_oauth_state', response.data.state)
      sessionStorage.setItem('github_auth_return_url', window.location.pathname + window.location.search)
      window.location.href = response.data.authorization_url
    } catch {
      setError('Failed to connect to GitHub')
    }
  }

  const handleDisconnectGithub = async () => {
    try {
      await codeSessionApi.disconnectGitHub()
      setGithubConnected(false)
      setGithubUsername(null)
      setRepos([])
    } catch {
      setError('Failed to disconnect from GitHub')
    }
  }

  const handleRepoClick = (repo: GitHubRepo) => {
    // If there's already a cloned repo in this conversation, ask for confirmation
    if (clonedRepo) {
      setConfirmRepo(repo)
      return
    }
    handleClone(repo)
  }

  const handleClone = async (repo: GitHubRepo) => {
    setCloningRepoId(repo.id)
    setConfirmRepo(null)
    setError(null)

    try {
      let targetConversationId = conversationId
      let targetChatId = chatId

      // Reuse the current conversation if it's empty, otherwise create a new one
      if (!isConversationEmpty || !targetConversationId || !targetChatId) {
        const conversation = await conversationsAPI.createConversation({ name: `Coding: ${repo.full_name}` })
        targetConversationId = conversation.id
        const chat = await conversationsAPI.createChat(targetConversationId, { parameters: getDefaultModelParameters() })
        targetChatId = chat.id
      } else {
        // Rename the existing empty conversation
        await conversationsAPI.updateConversation(targetConversationId, { name: `Coding: ${repo.full_name}` })
      }

      const cloneResponse = await codeSessionApi.cloneRepo(targetConversationId, {
        repo_url: repo.full_name,
        branch: repo.default_branch,
      })

      if (!cloneResponse.data.success) {
        throw new Error(cloneResponse.data.error || 'Clone failed')
      }

      setClonedRepo({
        id: targetConversationId,
        full_name: cloneResponse.data.full_name || repo.full_name,
        clone_url: `https://github.com/${repo.full_name}`,
        default_branch: cloneResponse.data.branch || repo.default_branch,
        current_branch: cloneResponse.data.branch || repo.default_branch,
        workspace_path: cloneResponse.data.workspace_path || '',
        head_commit_sha: cloneResponse.data.head_commit_sha || '',
        head_commit_message: cloneResponse.data.head_commit_message || '',
        cloned_at: new Date().toISOString(),
      })

      onCloneSuccess()

      if (targetConversationId !== conversationId) {
        navigate({ to: '/chats', search: { conversation: targetConversationId } })
      }
    } catch (err) {
      setError(getApiErrorMessage(err, 'Clone failed'))
      setCloningRepoId(null)
    }
  }

  if (githubLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!githubConnected) {
    return (
      <div className="p-4 space-y-4">
        <div className="text-center py-8">
          <Github className="w-12 h-12 mx-auto mb-4 text-muted-foreground/50" />
          <p className="text-xs text-muted-foreground mb-4">
            Connect your GitHub account to clone repositories
          </p>
          <Button onClick={handleConnectGithub} className="gap-2">
            Connect GitHub
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-border/40">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Github className="w-4 h-4 text-accent-brand" />
            <span className="text-sm font-medium">Clone Repository</span>
          </div>
          <button
            onClick={handleDisconnectGithub}
            className="text-[10px] text-muted-foreground hover:text-destructive transition-colors"
          >
            Disconnect
          </button>
        </div>
        <p className="text-xs text-muted-foreground mt-1">{githubUsername}</p>
      </div>

      {reposLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : repos.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          <p className="text-sm">No repositories found</p>
        </div>
      ) : (
        <div className="flex-1 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="p-2 space-y-1">
              {repos.map((repo) => (
                <button
                  key={repo.id}
                  onClick={() => !repo.private && handleRepoClick(repo)}
                  disabled={cloningRepoId !== null || repo.private}
                  title={repo.private ? 'Private repositories are not supported yet' : undefined}
                  className={cn(
                    'grid grid-cols-[16px_1fr] gap-3 w-full p-3 rounded-lg text-left transition-colors',
                    repo.private
                      ? 'opacity-50 cursor-not-allowed'
                      : 'hover:bg-muted',
                    cloningRepoId === repo.id && 'bg-muted'
                  )}
                >
                  {cloningRepoId === repo.id ? (
                    <Loader2 className="w-4 h-4 animate-spin text-accent-brand" />
                  ) : repo.private ? (
                    <Lock className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <Github className="w-4 h-4 text-muted-foreground" />
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{repo.name}</p>
                    {repo.private ? (
                      <p className="text-xs text-muted-foreground truncate">Private — not supported yet</p>
                    ) : repo.description ? (
                      <p className="text-xs text-muted-foreground truncate">{repo.description}</p>
                    ) : null}
                  </div>
                </button>
              ))}
            </div>
          </ScrollArea>
        </div>
      )}

      {error && (
        <div className="px-4 py-2 border-t border-border/40">
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )}

      {/* Confirmation dialog for replacing existing repo */}
      <Dialog open={!!confirmRepo} onOpenChange={(open) => !open && setConfirmRepo(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Replace repository?</DialogTitle>
            <DialogDescription>
              This will replace <span className="font-medium text-foreground">{clonedRepo?.full_name}</span> with <span className="font-medium text-foreground">{confirmRepo?.full_name}</span>. The current workspace will be overwritten.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setConfirmRepo(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => confirmRepo && handleClone(confirmRepo)}>
              Replace
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// Branch section showing commits and Create PR button
function BranchSection({ plan, clonedRepo }: { plan: AgentPlan; clonedRepo: ClonedRepo }) {
  const [commits, setCommits] = useState<GitHubCommit[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isCreatingPR, setIsCreatingPR] = useState(false)
  const { pullRequests, addPullRequest } = useProjectPanelStore()
  const { toast } = useToast()

  const existingPR = pullRequests.find(pr => pr.head_branch === plan.implementation_branch)
  const [owner, repoName] = clonedRepo.full_name.split('/')

  useEffect(() => {
    if (!plan.implementation_branch || !owner || !repoName) return
    setIsLoading(true)
    codeSessionApi.getBranchCommits(owner, repoName, plan.implementation_branch, 10)
      .then(res => setCommits(res.data.results || []))
      .catch(() => setCommits([]))
      .finally(() => setIsLoading(false))
  }, [plan.implementation_branch, owner, repoName])

  const handleCreatePR = async () => {
    setIsCreatingPR(true)
    try {
      const res = await codeSessionApi.createPRFromPlan(plan.id)
      addPullRequest(res.data)
      toast({ title: 'Pull request created', description: `PR #${res.data.pr_number}` })
    } catch (err) {
      toast({ title: 'Failed to create PR', description: getApiErrorMessage(err, 'Failed to create PR'), variant: 'destructive' })
    } finally {
      setIsCreatingPR(false)
    }
  }

  return (
    <div className="p-3 rounded-xl border border-border/40 bg-card/50">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <GitBranch className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          <span className="text-xs font-mono truncate">{plan.implementation_branch}</span>
        </div>
        {existingPR ? (
          <a href={existingPR.pr_url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-green-500 hover:underline shrink-0">
            PR #{existingPR.pr_number}
          </a>
        ) : plan.status === 'completed' ? (
          <Button size="sm" variant="outline" className="h-6 text-xs gap-1 shrink-0"
            onClick={handleCreatePR} disabled={isCreatingPR}>
            {isCreatingPR ? <Loader2 className="w-3 h-3 animate-spin" /> : <GitPullRequest className="w-3 h-3" />}
            Create PR
          </Button>
        ) : plan.status === 'in_progress' ? (
          <span className="text-xs text-muted-foreground">In progress...</span>
        ) : null}
      </div>

      {/* Plan title — wraps rather than truncates. `truncate` implies
          `white-space: nowrap`, which gives this element a min-content width
          equal to the whole (often sentence-length) title; inside the side
          panel that raised the ScrollArea wrapper's shrink-to-fit floor and
          stretched the entire plan detail past the panel, clipping it. Beyond
          that layout hazard, an ellipsis here hid the end of the title with no
          way to reveal it, since this card has no tooltip or expansion. */}
      <div className="text-xs text-muted-foreground mt-1 break-words">{plan.title}</div>

      {/* Commits list */}
      {isLoading ? (
        <div className="flex justify-center py-2">
          <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
        </div>
      ) : commits.length > 0 ? (
        <div className="mt-2 space-y-1">
          {commits.slice(0, 5).map((c) => (
            <div key={c.sha} className="flex items-center gap-2 text-xs">
              <span className="font-mono text-muted-foreground shrink-0">{c.sha?.slice(0, 7)}</span>
              <span className="truncate">{c.commit?.message?.split('\n')[0]}</span>
            </div>
          ))}
          {commits.length > 5 && (
            <div className="text-xs text-muted-foreground">+{commits.length - 5} more commits</div>
          )}
        </div>
      ) : null}
    </div>
  )
}

// Compact repo header shown above tabs when a repo is cloned
function RepoHeader({ conversationId, onChangeRepo }: { conversationId: string; onChangeRepo: () => void }) {
  const { clonedRepo, setClonedRepo } = useProjectPanelStore()
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [branchesOpen, setBranchesOpen] = useState(false)
  const [branches, setBranches] = useState<{ name: string; protected: boolean }[]>([])
  const [branchesLoading, setBranchesLoading] = useState(false)
  const [switchingBranch, setSwitchingBranch] = useState<string | null>(null)
  const { toast } = useToast()

  if (!clonedRepo) return null

  const [owner, repoName] = clonedRepo.full_name.split('/')

  const handleRefresh = async () => {
    setIsRefreshing(true)
    try {
      const response = await codeSessionApi.cloneRepo(conversationId, {
        repo_url: clonedRepo.full_name,
        branch: clonedRepo.current_branch,
      })
      if (response.data.success) {
        setClonedRepo({
          ...clonedRepo,
          head_commit_sha: response.data.head_commit_sha || clonedRepo.head_commit_sha,
          head_commit_message: response.data.head_commit_message || clonedRepo.head_commit_message,
          workspace_path: response.data.workspace_path || clonedRepo.workspace_path,
        })
        toast({ title: 'Workspace refreshed' })
      }
    } catch (err) {
      const errData = hasErrorResponse(err) ? err.response?.data as { code?: string; error?: string } | undefined : undefined
      const description = errData?.code === 'github_not_connected' ? 'Connect your GitHub account to refresh this workspace.' : errData?.error
      toast({ title: 'Refresh failed', description, variant: 'destructive' })
    } finally {
      setIsRefreshing(false)
    }
  }

  const fetchBranches = async () => {
    if (!owner || !repoName) return
    setBranchesLoading(true)
    try {
      const res = await codeSessionApi.getBranches(owner, repoName)
      setBranches(res.data.branches || [])
    } catch {
      setBranches([])
    } finally {
      setBranchesLoading(false)
    }
  }

  const handleBranchSelect = async (branchName: string) => {
    if (branchName === clonedRepo.current_branch) {
      setBranchesOpen(false)
      return
    }
    setSwitchingBranch(branchName)
    try {
      const response = await codeSessionApi.cloneRepo(conversationId, {
        repo_url: clonedRepo.full_name,
        branch: branchName,
      })
      if (response.data.success) {
        setClonedRepo({
          ...clonedRepo,
          current_branch: branchName,
          head_commit_sha: response.data.head_commit_sha || '',
          head_commit_message: response.data.head_commit_message || '',
          workspace_path: response.data.workspace_path || clonedRepo.workspace_path,
        })
        toast({ title: `Switched to ${branchName}` })
      }
    } catch {
      toast({ title: 'Branch switch failed', variant: 'destructive' })
    } finally {
      setSwitchingBranch(null)
      setBranchesOpen(false)
    }
  }

  return (
    <div className="px-3 py-2.5 border-b border-border/40 space-y-2">
      {/* Repo name + branch */}
      <div className="flex items-center gap-2 min-w-0">
        <FolderGit2 className="w-4 h-4 text-primary shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{clonedRepo.full_name}</div>
        </div>
        {clonedRepo.head_commit_sha && (
          <span className="text-[11px] font-mono text-muted-foreground/60 shrink-0">{clonedRepo.head_commit_sha.slice(0, 7)}</span>
        )}
      </div>

      {/* Branch selector + action buttons */}
      <div className="flex items-center gap-2">
        <Popover open={branchesOpen} onOpenChange={(open) => {
          setBranchesOpen(open)
          if (open) fetchBranches()
        }}>
          <PopoverTrigger asChild>
            <button className="flex items-center gap-1.5 px-2 py-1 rounded-md border border-border/60 bg-muted/40 hover:bg-muted hover:border-border transition-colors text-xs text-foreground/80 max-w-[180px]">
              <GitBranch className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
              <span className="block overflow-hidden text-ellipsis whitespace-nowrap font-medium">{clonedRepo.current_branch}</span>
              <ChevronDown className="w-3 h-3 shrink-0 text-muted-foreground" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-56 p-0 max-h-[50vh] overflow-y-auto overscroll-contain" align="start" side="bottom">
            {branchesLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
              </div>
            ) : branches.length === 0 ? (
              <div className="py-3 px-3 text-xs text-muted-foreground text-center">No branches found</div>
            ) : (
              <div className="py-1">
                {branches.map((b) => {
                  const isCurrent = b.name === clonedRepo.current_branch
                  const isSwitching = switchingBranch === b.name
                  return (
                    <button
                      key={b.name}
                      onClick={() => handleBranchSelect(b.name)}
                      disabled={switchingBranch !== null}
                      className={cn(
                        'w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left transition-colors',
                        isCurrent ? 'bg-accent/50 font-medium' : 'hover:bg-muted',
                        switchingBranch !== null && !isSwitching && 'opacity-50'
                      )}
                    >
                      {isSwitching ? (
                        <Loader2 className="w-3 h-3 animate-spin shrink-0" />
                      ) : isCurrent ? (
                        <Check className="w-3 h-3 text-primary shrink-0" />
                      ) : (
                        <div className="w-3 shrink-0" />
                      )}
                      <span className="truncate">{b.name}</span>
                      {b.protected && (
                        <Lock className="w-3 h-3 text-muted-foreground/50 shrink-0 ml-auto" />
                      )}
                    </button>
                  )
                })}
              </div>
            )}
          </PopoverContent>
        </Popover>

        <div className="flex-1" />

        <TooltipProvider delayDuration={300}>
          <div className="flex items-center gap-1 shrink-0">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={handleRefresh}
                  disabled={isRefreshing}
                  className="p-1.5 rounded-md hover:bg-muted transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={cn("w-4 h-4 text-muted-foreground", isRefreshing && "animate-spin")} />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom"><p>Refresh workspace</p></TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <a
                  href={clonedRepo.clone_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 rounded-md hover:bg-muted transition-colors"
                >
                  <ExternalLink className="w-4 h-4 text-muted-foreground" />
                </a>
              </TooltipTrigger>
              <TooltipContent side="bottom"><p>Open on GitHub</p></TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={onChangeRepo}
                  className="p-1.5 rounded-md hover:bg-muted transition-colors"
                >
                  <ArrowLeftRight className="w-4 h-4 text-muted-foreground" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom"><p>Change repository</p></TooltipContent>
            </Tooltip>
          </div>
        </TooltipProvider>
      </div>
    </div>
  )
}

// Plan card component
function PlanCard({ plan, isSelected, onClick }: { plan: AgentPlan; isSelected: boolean; onClick: () => void }) {
  const statusAccent: Record<string, string> = {
    creating: 'border-l-yellow-500',
    ready: 'border-l-blue-500',
    in_progress: 'border-l-purple-500',
    completed: 'border-l-green-500',
    failed: 'border-l-red-500',
  }

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left p-3 rounded-lg border-l-2 border border-border/40 transition-all group',
        'hover:bg-accent/30 hover:border-border/60',
        isSelected ? 'bg-primary/5 border-primary/30' : 'bg-card/50',
        statusAccent[plan.status] || 'border-l-muted'
      )}
    >
      <div className="flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm truncate">{plan.title}</div>
          <div className="flex items-center gap-1.5 mt-1.5">
            <StatusBadge status={plan.status} />
            {plan.source_plan_id && (
              <span className="text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-500">
                Imported
              </span>
            )}
            {plan.total_steps > 0 && (
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {plan.progress.completed}/{plan.total_steps}
              </span>
            )}
          </div>
        </div>
        <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors shrink-0" />
      </div>
      {plan.total_steps > 0 && plan.status !== 'completed' && (
        <div className="mt-2 h-1 rounded-full bg-muted/50 overflow-hidden">
          <div
            className="h-full rounded-full bg-primary/50 transition-all duration-500"
            style={{ width: `${plan.progress.percentage}%` }}
          />
        </div>
      )}
    </button>
  )
}

// Plan detail view
function PlanDetail({ plan: summaryPlan, onBack }: { plan: AgentPlan; onBack: () => void }) {
  const { clonedRepo } = useProjectPanelStore()
  const { requestImplementPlan } = useChatMessageDispatch()
  const { toast } = useToast()
  const [fullPlan, setFullPlan] = useState<AgentPlan | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  // Fetch full plan with steps if not already loaded
  useEffect(() => {
    if (summaryPlan.steps && summaryPlan.steps.length >= 0) {
      setFullPlan(summaryPlan)
      return
    }
    setLoadingDetail(true)
    codeSessionApi.getPlan(summaryPlan.id)
      .then((res) => setFullPlan(res.data))
      .catch(console.error)
      .finally(() => setLoadingDetail(false))
  }, [summaryPlan])

  const plan = fullPlan || summaryPlan

  const startEditing = (content: string) => {
    setEditContent(content)
    setIsEditing(true)
  }

  const handleSave = async () => {
    setIsSaving(true)
    try {
      const res = await codeSessionApi.updatePlanContent(plan.id, editContent)
      useProjectPanelStore.getState().updatePlan(plan.id, res.data)
      setFullPlan(res.data)
      setIsEditing(false)
    } catch (err) {
      console.error('Failed to save plan:', err)
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    setIsDeleting(true)
    try {
      await codeSessionApi.deletePlan(plan.id)
      useProjectPanelStore.getState().removePlan(plan.id)
      toast({ title: 'Plan deleted' })
      onBack()
    } catch (err) {
      toast({ title: 'Delete failed', description: getApiErrorMessage(err, 'Delete failed'), variant: 'destructive' })
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border/40">
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-muted-foreground" onClick={onBack}>
          <ChevronRight className="w-3 h-3 rotate-180 mr-1" />
          Back
        </Button>
        <div className="flex-1" />
        <StatusBadge status={plan.status} />
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0 text-muted-foreground/50 hover:text-destructive"
                onClick={handleDelete}
                disabled={isDeleting}
              >
                {isDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>Delete plan</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          <div className="font-medium text-sm">{plan.title}</div>

          {plan.github_issue_number && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <CircleDot className="w-3 h-3 text-green-500" />
              <span>#{plan.github_issue_number} {plan.github_issue_title}</span>
            </div>
          )}

          {plan.task_description && (
            <div className="text-xs text-muted-foreground leading-relaxed">{plan.task_description}</div>
          )}

          {plan.status === 'ready' && (
            <Button
              onClick={() => requestImplementPlan(plan)}
              className="w-full gap-2 bg-accent-brand hover:bg-accent-brand/90 text-accent-brand-foreground"
            >
              <Play className="w-4 h-4" />
              Implement Plan
            </Button>
          )}

          {plan.implementation_branch && clonedRepo && (
            <BranchSection plan={plan} clonedRepo={clonedRepo} />
          )}

          {loadingDetail && (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          )}

          {plan.plan_content && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="text-[11px] uppercase tracking-wider font-medium text-muted-foreground/70">Plan</div>
                <TooltipProvider>
                  <div className="flex items-center gap-0.5">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-muted-foreground/50 hover:text-foreground" onClick={() => setShowPreview(true)}>
                          <Maximize2 className="w-3 h-3" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Expand</TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-muted-foreground/50 hover:text-foreground" onClick={() => startEditing(plan.plan_content)}>
                          <Pencil className="w-3 h-3" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Edit</TooltipContent>
                    </Tooltip>
                  </div>
                </TooltipProvider>
              </div>
              {/* Radix ScrollArea's Viewport wraps its children in an
                  internal `display: table` box that sizes to its widest
                  descendant (e.g. an unwrapped code block or a GFM table
                  from the markdown) rather than the panel's width — plain
                  `min-w-0`/`break-words` can't shrink that ancestor, since a
                  child can never constrain its own parent's box. `w-0
                  min-w-full` decouples this element's layout width from its
                  content (min-width wins over width:0, so it still fills
                  the available space), and `overflow-x-auto` gives any
                  content that still can't wrap (code, tables) its own
                  contained horizontal scrollbar instead of blowing out the
                  whole side panel. */}
              <div className="text-sm prose-sm w-0 min-w-full overflow-x-auto break-words">
                <Markdown>{plan.plan_content}</Markdown>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Full-screen preview modal using FilePreviewModal */}
      <FilePreviewModal
        isOpen={showPreview}
        onClose={() => setShowPreview(false)}
        fileName={`${plan.title}.md`}
        fileSize={new Blob([plan.plan_content || '']).size}
        textContent={plan.plan_content || ''}
      />

      {/* Edit plan modal — full-screen on mobile, centered dialog on desktop */}
      <Dialog open={isEditing} onOpenChange={(open) => !open && setIsEditing(false)}>
        <DialogContent className="!max-w-none !w-full !h-full sm:!max-w-3xl sm:!w-[90vw] sm:!h-[80vh] sm:rounded-lg rounded-none flex flex-col p-0 gap-0">
          <DialogHeader className="px-3 sm:px-4 py-3 border-b shrink-0">
            <DialogTitle className="text-base sm:text-lg pr-8">Edit Plan</DialogTitle>
            <DialogDescription className="truncate">{plan.title}</DialogDescription>
          </DialogHeader>
          <div className="flex-1 min-h-0 p-2 sm:p-4">
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full h-full p-2 sm:p-3 text-sm font-mono rounded-lg border border-border bg-background resize-none"
              autoFocus
            />
          </div>
          <div className="flex items-center justify-end gap-2 px-3 sm:px-4 py-3 border-t shrink-0">
            <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)}>Cancel</Button>
            <Button size="sm" onClick={handleSave} disabled={isSaving}>
              {isSaving ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}
              Save
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// Plans tab content
function PlansContent({ chatId }: { chatId?: string }) {
  const {
    clonedRepo, plans, selectedPlanId, selectPlan, isLoadingPlans,
    importablePlans, showImportModal, setImportablePlans, setShowImportModal,
    addPlan,
  } = useProjectPanelStore()
  const [isImporting, setIsImporting] = useState<string | null>(null)
  const [isLoadingImportable, setIsLoadingImportable] = useState(false)
  const { toast } = useToast()

  if (!clonedRepo) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
        <div className="w-10 h-10 rounded-lg bg-muted/50 flex items-center justify-center mb-3">
          <FileText className="w-5 h-5 text-muted-foreground/40" />
        </div>
        <p className="text-sm text-muted-foreground">Clone a repository first</p>
        <p className="text-xs text-muted-foreground/60 mt-1">Plans will appear here after cloning</p>
      </div>
    )
  }

  const selectedPlan = plans.find((p) => p.id === selectedPlanId)

  if (isLoadingPlans) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (selectedPlan) {
    return <PlanDetail plan={selectedPlan} onBack={() => selectPlan(null)} />
  }

  const handleOpenImport = async () => {
    if (!chatId || !clonedRepo?.full_name) return
    setShowImportModal(true)
    setIsLoadingImportable(true)
    setImportablePlans([])
    try {
      const res = await codeSessionApi.getImportablePlans(chatId, clonedRepo.full_name)
      setImportablePlans(res.data.results)
    } catch {
      setImportablePlans([])
    } finally {
      setIsLoadingImportable(false)
    }
  }

  const handleImport = async (planId: string) => {
    if (!chatId) return
    setIsImporting(planId)
    try {
      const res = await codeSessionApi.importPlan(planId, chatId)
      addPlan(res.data)
      toast({ title: 'Plan imported', description: res.data.title })
      setShowImportModal(false)
    } catch (err) {
      toast({ title: 'Import failed', description: getApiErrorMessage(err, 'Import failed'), variant: 'destructive' })
    } finally {
      setIsImporting(null)
    }
  }

  return (
    <>
      {plans.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
          <div className="w-10 h-10 rounded-lg bg-muted/50 flex items-center justify-center mb-3">
            <FileText className="w-5 h-5 text-muted-foreground/40" />
          </div>
          <p className="text-sm text-muted-foreground">No plans yet</p>
          <p className="text-xs text-muted-foreground/60 mt-1">Ask the agent to plan an implementation</p>
          {chatId && (
            <Button variant="outline" size="sm" className="mt-4 gap-1.5" onClick={handleOpenImport}>
              <Import className="w-3.5 h-3.5" />
              Import from another chat
            </Button>
          )}
        </div>
      ) : (
        <ScrollArea className="h-full">
          <div className="p-3 space-y-1.5">
            {chatId && (
              <Button variant="outline" size="sm" className="w-full gap-1.5 mb-1" onClick={handleOpenImport}>
                <Import className="w-3.5 h-3.5" />
                Import Plan
              </Button>
            )}
            {plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                isSelected={plan.id === selectedPlanId}
                onClick={() => selectPlan(plan.id)}
              />
            ))}
          </div>
        </ScrollArea>
      )}

      <ImportPlanModal
        open={showImportModal}
        onOpenChange={setShowImportModal}
        plans={importablePlans}
        isLoading={isLoadingImportable}
        isImporting={isImporting}
        onImport={handleImport}
      />
    </>
  )
}

// Relative time formatter for import modal
function formatRelativeTime(dateStr: string): string {
  const now = Date.now()
  const date = new Date(dateStr).getTime()
  const diff = now - date
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(dateStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// Import plan modal — Sheet on mobile, Dialog on desktop
function ImportPlanModal({
  open,
  onOpenChange,
  plans,
  isLoading,
  isImporting,
  onImport,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  plans: AgentPlan[]
  isLoading: boolean
  isImporting: string | null
  onImport: (planId: string) => void
}) {
  const isMobile = useUIStore((state) => state.isMobile)

  // Group plans by conversation
  const grouped = plans.reduce<Record<string, { name: string; plans: AgentPlan[] }>>((acc, plan) => {
    const key = plan.conversation_name || 'Unknown conversation'
    if (!acc[key]) acc[key] = { name: key, plans: [] }
    acc[key].plans.push(plan)
    return acc
  }, {})
  const groups = Object.values(grouped)
  const hasMultipleGroups = groups.length > 1

  const list = (
    <div className="space-y-3">
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-10">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground mb-2" />
          <p className="text-xs text-muted-foreground">Loading plans...</p>
        </div>
      ) : plans.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <div className="w-9 h-9 rounded-lg bg-muted/50 flex items-center justify-center mb-2.5">
            <FileText className="w-4 h-4 text-muted-foreground/40" />
          </div>
          <p className="text-sm text-muted-foreground">No plans to import</p>
          <p className="text-xs text-muted-foreground/60 mt-1 max-w-[220px]">
            Create plans in other chats with the same repository, then import them here
          </p>
        </div>
      ) : (
        groups.map((group) => (
          <div key={group.name}>
            {hasMultipleGroups && (
              <div className="flex items-center gap-1.5 mb-1.5 px-1">
                <MessageSquare className="w-3 h-3 text-muted-foreground/50" />
                <span className="text-[11px] font-medium text-muted-foreground truncate">
                  {group.name}
                </span>
              </div>
            )}
            <div className="space-y-1.5">
              {group.plans.map((plan) => (
                <button
                  key={plan.id}
                  onClick={() => onImport(plan.id)}
                  disabled={isImporting !== null}
                  className={cn(
                    'w-full text-left p-3 rounded-lg border border-border/40 bg-card/50 transition-all group',
                    'hover:bg-accent/30 hover:border-border/60',
                    isImporting === plan.id && 'opacity-70',
                    isImporting !== null && isImporting !== plan.id && 'opacity-50'
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium truncate">{plan.title}</div>
                      {plan.task_description && (
                        <p className="text-xs text-muted-foreground/70 mt-0.5 line-clamp-2">
                          {plan.task_description}
                        </p>
                      )}
                      <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                        <StatusBadge status={plan.status} />
                        {plan.total_steps > 0 && (
                          <span className="text-[11px] tabular-nums text-muted-foreground">
                            {plan.total_steps} steps
                          </span>
                        )}
                        {!hasMultipleGroups && plan.conversation_name && (
                          <span className="text-[11px] text-muted-foreground/60 truncate max-w-[120px]">
                            {plan.conversation_name}
                          </span>
                        )}
                        <span className="text-[11px] text-muted-foreground/50 flex items-center gap-0.5 ml-auto shrink-0">
                          <Clock className="w-2.5 h-2.5" />
                          {formatRelativeTime(plan.created_at)}
                        </span>
                      </div>
                    </div>
                    <div className="shrink-0 mt-0.5">
                      {isImporting === plan.id ? (
                        <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                      ) : (
                        <Import className="w-4 h-4 text-muted-foreground/40 group-hover:text-foreground transition-colors" />
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  )

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom" className="rounded-t-2xl border-t-2 p-0 flex flex-col h-[60vh]">
          <div className="flex justify-center pt-3 pb-2 shrink-0">
            <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
          </div>
          <SheetHeader className="px-4 pb-3 border-b shrink-0">
            <SheetTitle>Import Plan</SheetTitle>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto p-4">
            {list}
          </div>
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md max-h-[80vh] overflow-hidden p-0 gap-0">
        <DialogHeader className="p-6 pb-4">
          <DialogTitle>Import Plan</DialogTitle>
          <DialogDescription>
            Copy a plan from another chat into this one.
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto px-6 pb-6">
          {list}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// PRs tab content
function PRsContent() {
  const { clonedRepo, pullRequests, isLoadingPRs } = useProjectPanelStore()

  if (!clonedRepo) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <GitPullRequest className="w-10 h-10 mx-auto mb-3 opacity-30" />
        <p className="text-sm">Clone a repository first</p>
        <p className="text-xs mt-1 opacity-70">PRs will appear here after cloning</p>
      </div>
    )
  }

  if (isLoadingPRs) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (pullRequests.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <GitPullRequest className="w-10 h-10 mx-auto mb-3 opacity-30" />
        <p className="text-sm">No pull requests yet</p>
        <p className="text-xs mt-1 opacity-70">PRs will appear here when created</p>
      </div>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="p-3 space-y-2">
        {pullRequests.map((pr) => (
          <a
            key={pr.id}
            href={pr.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block p-3 rounded-xl border border-border/40 bg-card/50 hover:bg-accent/30 hover:border-green-500/30 transition-all"
          >
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-green-500/10 text-green-500 shrink-0">
                <GitPullRequest className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm truncate">{pr.pr_title}</div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-muted-foreground">#{pr.pr_number}</span>
                  <span className="text-xs text-muted-foreground">{pr.head_branch} → {pr.base_branch}</span>
                </div>
              </div>
              <ExternalLink className="w-4 h-4 text-muted-foreground shrink-0" />
            </div>
          </a>
        ))}
      </div>
    </ScrollArea>
  )
}

// Issues tab content
function IssuesContent() {
  const { clonedRepo } = useProjectPanelStore()
  const [issues, setIssues] = useState<GitHubIssue[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { requestPlanForIssue } = useChatMessageDispatch()

  useEffect(() => {
    if (!clonedRepo?.full_name) return

    const [owner, repo] = clonedRepo.full_name.split('/')
    if (!owner || !repo) return

    setIsLoading(true)
    setError(null)

    codeSessionApi.getIssues(owner, repo, 1, 30, 'open')
      .then((res) => setIssues(res.data.results))
      .catch((err) => {
        console.error('Failed to fetch issues:', err)
        setError('Failed to load issues')
      })
      .finally(() => setIsLoading(false))
  }, [clonedRepo?.full_name])

  if (!clonedRepo) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <CircleDot className="w-10 h-10 mx-auto mb-3 opacity-30" />
        <p className="text-sm">Clone a repository first</p>
        <p className="text-xs mt-1 opacity-70">Issues will appear here after cloning</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <CircleDot className="w-10 h-10 mx-auto mb-3 opacity-30" />
        <p className="text-sm text-destructive">{error}</p>
      </div>
    )
  }

  if (issues.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <CircleDot className="w-10 h-10 mx-auto mb-3 opacity-30" />
        <p className="text-sm">No open issues</p>
        <p className="text-xs mt-1 opacity-70">Open issues will appear here</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-hidden">
      <ScrollArea className="h-full">
        <div className="p-3 space-y-2">
          {issues.map((issue) => (
            <div
              key={issue.id}
              className="p-3 rounded-xl border border-border/40 bg-card/50 hover:bg-accent/30 transition-all overflow-hidden"
            >
              <div className="grid grid-cols-[32px_1fr] gap-3">
                <div className="p-2 rounded-lg bg-green-500/10 text-green-500 shrink-0 w-8 h-8 flex items-center justify-center">
                  <CircleDot className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <div className="font-medium text-sm line-clamp-2">{issue.title}</div>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    <span className="text-xs text-muted-foreground">#{issue.number}</span>
                    {issue.labels.slice(0, 3).map((label) => (
                      <span
                        key={label.name}
                        className="text-[10px] font-medium px-1.5 py-0.5 rounded-full text-foreground border border-border/60 whitespace-nowrap"
                        style={{ backgroundColor: `#${label.color}30` }}
                      >
                        {label.name}
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center gap-1 mt-2">
                    <a
                      href={issue.html_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1.5 rounded-md hover:bg-muted transition-colors"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
                    </a>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 px-2.5 gap-1.5 text-xs"
                      onClick={() => clonedRepo && requestPlanForIssue(issue, clonedRepo)}
                    >
                      <Play className="w-3 h-3" />
                      Plan Implementation
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

// Main component
export function ProjectStatusSidePanel({ conversationId, chatId, className }: ProjectStatusSidePanelProps) {
  const {
    isPanelOpen,
    activeSection,
    setActiveSection,
    closePanel,
    clonedRepo,
    isLoadingRepo,
    setClonedRepo,
    setPlans,
    setPullRequests,
    setLoadingRepo,
    setLoadingPlans,
    setLoadingPRs,
    selectPlan,
  } = useProjectPanelStore()

  const isMobile = useUIStore((state) => state.isMobile)

  // Resizable panel state
  const [panelWidth, setPanelWidth] = useState(DEFAULT_PANEL_WIDTH)
  const [isResizing, setIsResizing] = useState(false)
  const resizeRef = useRef<HTMLDivElement>(null)

  // Clear stale data when conversation changes
  useEffect(() => {
    setClonedRepo(null)
    setPlans([])
    setPullRequests([])
    selectPlan(null)
  }, [conversationId])

  // Clear plans when chat changes (plans are chat-scoped)
  useEffect(() => {
    setPlans([])
    selectPlan(null)
  }, [chatId])

  // Tracks which conversationId the repo-status fetch below has actually
  // resolved for. This is deliberately NOT a boolean ("isLoadingRepo"):
  // when conversationId changes, the "clear stale data" effect above and
  // the repo-status effect below both run in the same passive-effect
  // flush, before either's setState is visible to a same-flush read of
  // isLoadingRepo/clonedRepo — a boolean gate would read the *previous*
  // conversation's "not loading" state and its stale clonedRepo.full_name,
  // firing the plans/PRs effect once for the conversation being left (with
  // the old repo name) and again for the real one. Comparing against the
  // exact conversationId closes that window: the plans/PRs effect can only
  // proceed once repoResolvedFor has been updated to match, which only
  // happens together with clonedRepo in the same .then() callback.
  const [repoResolvedFor, setRepoResolvedFor] = useState<string | null>(null)
  // Tracks a conversationId whose repo-status fetch failed (network blip,
  // etc). Without this, a failed fetch would leave clonedRepo permanently
  // null with no retry path — the exact false "Connect your GitHub
  // account" prompt this fix exists to eliminate, just reached via a
  // failure instead of a skipped fetch. Opening the panel (isPanelOpen) is
  // the retry trigger, mirroring RepoHeader's manual refresh affordance.
  const [repoFetchFailedFor, setRepoFetchFailedFor] = useState<string | null>(null)

  // Fetch repo status as soon as the card mounts for this conversation —
  // NOT gated on isPanelOpen for the *first* attempt. The card
  // (RepoSelector's "Connect your GitHub account" prompt vs. the repo
  // header) renders unconditionally as soon as this component mounts,
  // since the panel is only ever hidden via CSS (width/translate), not
  // unmounted. Gating this fetch on isPanelOpen left clonedRepo stuck at
  // null — and the card showing a false "not connected" prompt — for any
  // conversation whose panel hadn't been opened yet, even when a repo was
  // already cloned. Once resolved (success or failure) for a conversation,
  // further isPanelOpen toggles are a no-op unless the previous attempt
  // failed, so this doesn't turn into a fetch storm.
  useEffect(() => {
    if (!conversationId) return
    if (repoResolvedFor === conversationId) return
    if (repoFetchFailedFor === conversationId && !isPanelOpen) return

    // Guards against out-of-order responses: if conversationId changes
    // again before this request resolves, the cleanup below marks it
    // cancelled so its (now stale) result can't overwrite the repo header
    // with the conversation the user already navigated away from. This
    // effect's own success/failure updates repoResolvedFor/
    // repoFetchFailedFor, which are also in its dependency list — so this
    // exact cleanup ALSO fires on the effect's own successful completion
    // (React tears down and re-runs the effect once those deps change).
    // setLoadingRepo(false) below is deliberately NOT guarded by
    // `cancelled` for that reason: gating it would leave isLoadingRepo
    // stuck true forever on every successful fetch, self-cancelling before
    // its own .finally() ever got a chance to clear it.
    let cancelled = false
    setLoadingRepo(true)
    codeSessionApi.getRepoStatus(conversationId)
      .then((res) => {
        if (cancelled) return
        setClonedRepo(transformRepoStatus(res.data))
        setRepoResolvedFor(conversationId)
        setRepoFetchFailedFor(null)
      })
      .catch((err) => {
        console.error(err)
        if (!cancelled) setRepoFetchFailedFor(conversationId)
      })
      .finally(() => setLoadingRepo(false))
    return () => {
      cancelled = true
    }
  }, [conversationId, isPanelOpen, repoResolvedFor, repoFetchFailedFor])

  // Fetch plans/PRs once the repo status above has resolved *for this exact
  // conversation* and the panel is actually open — these tabs are only
  // visible inside the open panel, so there is no need to pay for them
  // while it's closed.
  useEffect(() => {
    if (!isPanelOpen || !conversationId || repoResolvedFor !== conversationId) return

    const repoFullName = clonedRepo?.full_name

    setLoadingPlans(true)
    const planParams = chatId
      ? { chatId }
      : repoFullName
        ? { repoFullName }
        : { conversationId }
    codeSessionApi.getPlans(planParams)
      .then((res) => setPlans(res.data.results))
      .catch(console.error)
      .finally(() => setLoadingPlans(false))

    setLoadingPRs(true)
    codeSessionApi.getPullRequests(repoFullName ? { repoFullName } : { conversationId })
      .then((res) => setPullRequests(res.data.results))
      .catch(console.error)
      .finally(() => setLoadingPRs(false))
  }, [isPanelOpen, conversationId, chatId, repoResolvedFor, clonedRepo?.full_name])

  // Handle resize drag
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return
      const newWidth = window.innerWidth - e.clientX
      setPanelWidth(Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, newWidth)))
    }

    const handleMouseUp = () => {
      setIsResizing(false)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    if (isResizing) {
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizing])

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
  }, [])

  const [showRepoSelector, setShowRepoSelector] = useState(false)

  const tabs = [
    { id: 'issues' as const, label: 'Issues', icon: CircleDot },
    { id: 'plans' as const, label: 'Plans', icon: FileText },
    { id: 'prs' as const, label: 'PRs', icon: GitPullRequest },
  ]

  const renderContent = () => {
    // Show repo selector when explicitly requested or when no repo is cloned
    if (showRepoSelector || (!clonedRepo && !isLoadingRepo)) {
      return <RepoSelector conversationId={conversationId} chatId={chatId} onCloneSuccess={() => setShowRepoSelector(false)} />
    }
    if (isLoadingRepo && !clonedRepo) {
      return (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      )
    }

    switch (activeSection) {
      case 'issues':
        return <IssuesContent />
      case 'plans':
        return <PlansContent chatId={chatId} />
      case 'prs':
        return <PRsContent />
      default:
        return <IssuesContent />
    }
  }

  // Mobile: Use bottom sheet
  if (isMobile) {
    return (
      <Sheet open={isPanelOpen} onOpenChange={(open) => !open && closePanel()}>
        <SheetContent side="bottom" className="rounded-t-2xl border-t-2 p-0 flex flex-col h-[70vh]">
          <div className="flex justify-center pt-3 pb-2 shrink-0">
            <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
          </div>

          <SheetHeader className="px-4 pb-3 border-b shrink-0">
            <div className="flex items-center justify-between">
              <SheetTitle>Project</SheetTitle>
              <TooltipProvider delayDuration={300}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => window.dispatchEvent(new CustomEvent('openCodeEditor'))}
                      className="flex items-center gap-1.5 px-2 py-1 rounded-md border border-border/60 bg-muted/40 hover:bg-muted hover:border-border transition-colors text-xs text-foreground/80"
                    >
                      <Code2 className="w-3.5 h-3.5" />
                      <span className="font-medium">IDE</span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom"><p>Open IDE</p></TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </SheetHeader>

          {/* Repo header */}
          {clonedRepo && !showRepoSelector && <RepoHeader conversationId={conversationId} onChangeRepo={() => setShowRepoSelector(true)} />}

          {/* Tabs — only when repo is cloned and selector not showing */}
          {clonedRepo && !showRepoSelector && (
            <div className="px-4 py-2 border-b">
              <div className="flex gap-1">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => {
                      selectPlan(null)
                      setActiveSection(tab.id)
                    }}
                    className={cn(
                      'flex-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center justify-center gap-1.5',
                      activeSection === tab.id
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted/50 text-muted-foreground hover:bg-muted'
                    )}
                  >
                    <tab.icon className="w-3.5 h-3.5" />
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="flex-1 overflow-hidden">{renderContent()}</div>
        </SheetContent>
      </Sheet>
    )
  }

  // Desktop: Side panel
  return (
    <div
      className={cn(
        'h-full flex flex-col relative overflow-hidden',
        'transition-[width] duration-300 ease-in-out',
        className
      )}
      style={{ width: isPanelOpen ? panelWidth : 0 }}
    >
      <div
        className={cn(
          'h-full border-l border-border/40 bg-card flex flex-col relative',
          'transition-transform duration-300 ease-in-out',
          isPanelOpen ? 'translate-x-0' : 'translate-x-full'
        )}
        style={{ width: panelWidth }}
      >
        {/* Resize handle */}
        <div
          ref={resizeRef}
          onMouseDown={handleResizeStart}
          className={cn(
            'absolute left-0 top-0 bottom-0 w-1 cursor-col-resize z-10',
            'hover:bg-primary/20 transition-colors group flex items-center justify-center',
            isResizing && 'bg-primary/30'
          )}
        >
          <div
            className={cn(
              'absolute left-0 w-4 h-12 flex items-center justify-center',
              'opacity-0 group-hover:opacity-100 transition-opacity',
              isResizing && 'opacity-100'
            )}
          >
            <GripVertical className="w-3 h-3 text-muted-foreground" />
          </div>
        </div>

        {/* Header */}
        <div className="flex items-center justify-between p-3 border-b border-border/40">
          <span className="font-medium text-sm">Project</span>
          <TooltipProvider delayDuration={300}>
            <div className="flex items-center gap-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => window.dispatchEvent(new CustomEvent('openCodeEditor'))}
                    className="flex items-center gap-1.5 px-2 py-1 rounded-md border border-border/60 bg-muted/40 hover:bg-muted hover:border-border transition-colors text-xs text-foreground/80"
                  >
                    <Code2 className="w-3.5 h-3.5" />
                    <span className="font-medium">IDE</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom"><p>Open IDE</p></TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={closePanel}>
                    <X className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom"><p>Close panel</p></TooltipContent>
              </Tooltip>
            </div>
          </TooltipProvider>
        </div>

        {/* Repo header */}
        {clonedRepo && !showRepoSelector && <RepoHeader conversationId={conversationId} onChangeRepo={() => setShowRepoSelector(true)} />}

        {/* Tabs — only when repo is cloned and selector not showing */}
        {clonedRepo && !showRepoSelector && (
          <div className="px-3 py-2 border-b border-border/40">
            <div className="flex gap-1">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => {
                    selectPlan(null)
                    setActiveSection(tab.id)
                  }}
                  className={cn(
                    'flex-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center justify-center gap-1.5',
                    activeSection === tab.id
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted/50 text-muted-foreground hover:bg-muted'
                  )}
                >
                  <tab.icon className="w-3.5 h-3.5" />
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-hidden">{renderContent()}</div>
      </div>
    </div>
  )
}
