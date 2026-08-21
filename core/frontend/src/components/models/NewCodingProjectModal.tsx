/**
 * NewCodingProjectModal Component
 *
 * Modal for starting a new coding project with GitHub integration.
 * Matches the app's visual identity with teal accents.
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Github,
  GitBranch,
  ExternalLink,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  FolderGit2,
} from 'lucide-react'
import { codeSessionApi } from '@/api/codeSession'
import { conversationsAPI } from '@/api/conversations'
import { useProjectPanelStore } from '@/store/projectPanelStore'
import { getDefaultModelParameters } from '@/config/modelParameters'

interface NewCodingProjectModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type Step = 'loading' | 'connect' | 'repo' | 'cloning'

export function NewCodingProjectModal({ open, onOpenChange }: NewCodingProjectModalProps) {
  const navigate = useNavigate()
  const { setClonedRepo } = useProjectPanelStore()

  const [step, setStep] = useState<Step>('loading')
  const [repoUrl, setRepoUrl] = useState('')
  const [branch, setBranch] = useState('')
  const [isConnecting, setIsConnecting] = useState(false)
  const [isCloning, setIsCloning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [githubUsername, setGithubUsername] = useState<string | null>(null)

  // Check GitHub connection status
  const checkGitHubStatus = useCallback(async () => {
    try {
      const response = await codeSessionApi.getGitHubStatus()
      if (response.data.connected) {
        setGithubUsername(response.data.username)
        setStep('repo')
      } else {
        setStep('connect')
      }
    } catch {
      setStep('connect')
    }
  }, [])

  // Check connection on modal open
  useEffect(() => {
    if (open) {
      setStep('loading')
      setError(null)
      checkGitHubStatus()
    }
  }, [open, checkGitHubStatus])

  // Parse repo URL to extract owner/repo format
  const parseRepoUrl = useCallback((url: string): string | null => {
    const trimmed = url.trim()
    if (!trimmed) return null

    const urlMatch = trimmed.match(/github\.com\/([^/]+\/[^/]+?)(?:\.git)?(?:\/.*)?$/)
    if (urlMatch) return urlMatch[1].replace(/\.git$/, '')

    const simpleMatch = trimmed.match(/^([a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+)$/)
    if (simpleMatch) return simpleMatch[1]

    return null
  }, [])

  const parsedRepo = repoUrl ? parseRepoUrl(repoUrl) : null
  const isValidRepo = !!parsedRepo

  // Handle GitHub OAuth connection
  const handleConnectGitHub = async () => {
    setIsConnecting(true)
    setError(null)

    try {
      const response = await codeSessionApi.connectGitHub()
      // Store state for OAuth callback validation
      sessionStorage.setItem('github_oauth_state', response.data.state)
      sessionStorage.setItem('github_auth_return_url', '/chats')
      window.location.href = response.data.authorization_url
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to connect to GitHub')
      setIsConnecting(false)
    }
  }

  // Handle cloning the repository
  const handleClone = async () => {
    if (!parsedRepo) return

    setIsCloning(true)
    setStep('cloning')
    setError(null)

    try {
      const conversation = await conversationsAPI.createConversation({
        name: `Coding: ${parsedRepo}`,
        parameters: getDefaultModelParameters(),
      })

      const conversationId = conversation.id

      const cloneResponse = await codeSessionApi.cloneRepo(conversationId, {
        repo_url: parsedRepo,
        branch: branch || undefined,
      })

      if (!cloneResponse.data.success) {
        throw new Error(cloneResponse.data.error || 'Clone failed')
      }

      setClonedRepo({
        id: conversationId,
        full_name: cloneResponse.data.full_name || parsedRepo,
        clone_url: `https://github.com/${parsedRepo}`,
        default_branch: cloneResponse.data.branch || 'main',
        current_branch: cloneResponse.data.branch || 'main',
        workspace_path: cloneResponse.data.workspace_path || '',
        head_commit_sha: cloneResponse.data.head_commit_sha || '',
        head_commit_message: cloneResponse.data.head_commit_message || '',
        cloned_at: new Date().toISOString(),
      })

      onOpenChange(false)

      navigate({
        to: '/chats',
        search: { conversation: conversationId },
      })
    } catch (err: any) {
      const errorMsg = err.response?.data?.error || err.message || 'Clone failed'
      setError(errorMsg)
      setStep('repo')
      setIsCloning(false)
    }
  }

  // Reset state when modal closes
  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      setRepoUrl('')
      setBranch('')
      setError(null)
      setIsCloning(false)
      setIsConnecting(false)
    }
    onOpenChange(newOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[420px] gap-0 p-0 overflow-hidden border-border/40">
        {/* Header */}
        <DialogHeader className="px-5 pt-5 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-accent-brand/10">
              <FolderGit2 className="h-5 w-5 text-accent-brand" />
            </div>
            <div>
              <DialogTitle className="text-lg">New Coding Project</DialogTitle>
              <DialogDescription className="text-xs mt-0.5">
                Clone a repo and start coding with AI
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Content */}
        <div className="px-5 pb-5">
          {/* Loading state */}
          {step === 'loading' && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-accent-brand" />
            </div>
          )}

          {/* Connect GitHub */}
          {step === 'connect' && (
            <div className="space-y-4">
              <div className="flex flex-col items-center text-center py-6">
                <div className="flex items-center justify-center w-14 h-14 rounded-full bg-muted/50 mb-4">
                </div>
                <h3 className="font-semibold mb-1">Connect GitHub</h3>
                <p className="text-xs text-muted-foreground max-w-[260px]">
                  Link your GitHub account to clone repositories
                </p>
              </div>

              {error && (
                <div className="flex items-center gap-2 p-2.5 rounded-lg bg-destructive/10 text-destructive text-xs">
                  <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <Button
                onClick={handleConnectGitHub}
                disabled={isConnecting}
                className="w-full h-10 gap-2 bg-accent-brand hover:bg-accent-brand/90 text-accent-brand-foreground"
              >
                {isConnecting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Connecting...
                  </>
                ) : (
                  <>
                    <Github className="h-4 w-4" />
                    Connect GitHub
                    <ExternalLink className="h-3 w-3 ml-0.5 opacity-70" />
                  </>
                )}
              </Button>
            </div>
          )}

          {/* Enter Repository */}
          {step === 'repo' && (
            <div className="space-y-4">
              {/* Connected badge */}
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-accent-brand/10">
                <CheckCircle2 className="h-3.5 w-3.5 text-accent-brand" />
                <span className="text-xs font-medium text-accent-brand">
                  {githubUsername || 'GitHub connected'}
                </span>
              </div>

              {/* Repo input */}
              <div className="space-y-1.5">
                <Label htmlFor="repo-url" className="text-xs font-medium">
                  Repository
                </Label>
                <Input
                  id="repo-url"
                  placeholder="owner/repo"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  className="h-10 text-sm border-border/40 focus-visible:ring-accent-brand"
                  autoFocus
                />
                {repoUrl && !isValidRepo && (
                  <p className="text-[10px] text-destructive">
                    Enter owner/repo format (e.g., facebook/react)
                  </p>
                )}
                {parsedRepo && (
                  <p className="text-[10px] text-muted-foreground">
                    <span className="font-mono text-foreground">{parsedRepo}</span>
                  </p>
                )}
              </div>

              {/* Branch input */}
              <div className="space-y-1.5">
                <Label htmlFor="branch" className="text-xs font-medium">
                  Branch <span className="text-muted-foreground font-normal">(optional)</span>
                </Label>
                <div className="relative">
                  <GitBranch className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    id="branch"
                    placeholder="main"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    className="h-10 pl-9 text-sm border-border/40 focus-visible:ring-accent-brand"
                  />
                </div>
              </div>

              {error && (
                <div className="flex items-center gap-2 p-2.5 rounded-lg bg-destructive/10 text-destructive text-xs">
                  <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <Button
                onClick={handleClone}
                disabled={!isValidRepo || isCloning}
                className="w-full h-10 gap-2 bg-accent-brand hover:bg-accent-brand/90 text-accent-brand-foreground"
              >
                Clone & Start
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          )}

          {/* Cloning */}
          {step === 'cloning' && (
            <div className="flex flex-col items-center text-center py-10">
              <div className="relative mb-5">
                <div className="flex items-center justify-center w-14 h-14 rounded-full bg-accent-brand/10">
                  <FolderGit2 className="h-7 w-7 text-accent-brand" />
                </div>
                <div className="absolute -bottom-1 -right-1 flex items-center justify-center w-6 h-6 rounded-full bg-background border border-border">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-accent-brand" />
                </div>
              </div>
              <h3 className="font-semibold mb-1">Cloning</h3>
              <p className="text-xs text-muted-foreground font-mono">
                {parsedRepo}
              </p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
