/**
 * Ignite & Deploy — hook, dropdown menu items, and confirmation dialogs.
 *
 * useIgniteDeploy: manages all state (deployment polling, confirmation dialogs)
 * IgniteMenuItems: renders DropdownMenuItems for Ignite + Deploy
 * IgniteDialogs: renders AlertDialogs for confirmation
 * IgniteButton: legacy button component (used on SparksPage gallery cards)
 */
import { useState, useEffect, useRef, useCallback, type ReactNode } from 'react'
import { Flame, Upload, Loader2, ExternalLink, AlertTriangle } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { BetaBadge } from '@/components/feature-readiness/BetaBadge'
import { BetaDisclaimerModal, hasBetaDisclaimerBeenSeen } from '@/components/feature-readiness/BetaDisclaimerModal'
import { useFeatureFlags } from '@/hooks/useFeatureFlags'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { useToast } from '@/hooks/use-toast'
import { useUIStore } from '@/store/uiStore'
import { sparksAPI, type SparkDeployment } from '@/api/sparks'
import { getApiErrorMessage, hasErrorResponse } from '@/utils/errorMessages'

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseIgniteDeployOptions {
  sparkId: string
  sparkTitle?: string
  framework?: string
  conversationId?: string | null
  latestDeployment?: { id: string; status: string; preview_url: string; claim_url: string } | null
  isIgnited?: boolean
  onIgnite?: (sparkId: string, sparkTitle: string) => void
}

const POLL_INTERVAL = 5_000
const MAX_POLL_MS = 5 * 60_000

export function useIgniteDeploy({
  sparkId,
  sparkTitle,
  framework,
  conversationId,
  latestDeployment,
  isIgnited = false,
  onIgnite,
}: UseIgniteDeployOptions) {
  const { toast } = useToast()
  const navigate = useNavigate()

  const isReactSpark = !framework || framework === 'react'
  const canDeploy = isReactSpark && isIgnited

  // Confirmation dialog state
  const [confirmAction, setConfirmAction] = useState<'ignite' | 'deploy' | null>(null)

  // Beta disclaimer state
  const [showDisclaimer, setShowDisclaimer] = useState(false)
  const [pendingAction, setPendingAction] = useState<'ignite' | 'deploy' | null>(null)

  // Deployment state
  const [deployment, setDeployment] = useState<SparkDeployment | null>(null)
  const [isDeploying, setIsDeploying] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollStartRef = useRef<number>(0)

  const currentStatus = deployment?.status ?? latestDeployment?.status ?? null
  const previewUrl = deployment?.preview_url ?? latestDeployment?.preview_url ?? ''
  const isActive = currentStatus === 'pending' || currentStatus === 'deploying'
  const isDeployed = currentStatus === 'deployed'
  const isFailed = currentStatus === 'failed'

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback((deploymentId: string) => {
    stopPolling()
    pollStartRef.current = Date.now()

    pollRef.current = setInterval(async () => {
      if (Date.now() - pollStartRef.current > MAX_POLL_MS) {
        stopPolling()
        toast({
          title: 'Deployment status unknown',
          description: 'Deployment may have failed — check back later.',
          variant: 'destructive',
        })
        return
      }

      try {
        const deployments = await sparksAPI.getDeployments(sparkId)
        const current = deployments.find(d => d.id === deploymentId) ?? deployments[0]
        if (!current) return

        setDeployment(current)

        if (current.status === 'deployed') {
          stopPolling()
          toast({
            title: `${sparkTitle || 'Spark'} deployed!`,
            description: 'Your app is live on Vercel.',
          })
        } else if (current.status === 'failed') {
          stopPolling()
          toast({
            title: 'Deployment failed',
            description: current.error_message || 'Something went wrong.',
            variant: 'destructive',
          })
        }
      } catch {
        // Polling error — keep trying
      }
    }, POLL_INTERVAL)
  }, [sparkId, sparkTitle, stopPolling, toast])

  // Start polling on mount if there's an active deployment
  useEffect(() => {
    if (latestDeployment && ['pending', 'deploying'].includes(latestDeployment.status)) {
      startPolling(latestDeployment.id)
    }
    return stopPolling
  }, [latestDeployment?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Confirmation handlers
  const requestIgnite = useCallback(() => setConfirmAction('ignite'), [])
  const requestDeploy = useCallback(() => {
    if (isDeployed && previewUrl) {
      window.open(previewUrl, '_blank', 'noopener')
    } else {
      setConfirmAction('deploy')
    }
  }, [isDeployed, previewUrl])
  const cancelConfirm = useCallback(() => setConfirmAction(null), [])

  const _doIgnite = useCallback(() => {
    setConfirmAction(null)
    setShowDisclaimer(false)
    setPendingAction(null)
    if (onIgnite) {
      onIgnite(sparkId, sparkTitle || 'Spark')
    } else if (conversationId) {
      navigate({
        to: '/chats',
        search: { conversation: conversationId, ignite: sparkId },
      })
    }
  }, [onIgnite, sparkId, sparkTitle, conversationId, navigate])

  const _doDeploy = useCallback(async () => {
    setConfirmAction(null)
    setShowDisclaimer(false)
    setPendingAction(null)
    if (isDeploying || isActive) return

    setIsDeploying(true)
    try {
      const result = await sparksAPI.deploy(sparkId)
      setDeployment(result)
      startPolling(result.id)
      toast({
        title: 'Deploying to Vercel...',
        description: 'This takes about 15-30 seconds.',
      })
    } catch (error) {
      const status = hasErrorResponse(error) ? error.response?.status : undefined
      if (status === 409) {
        toast({ title: 'Deployment already in progress', variant: 'destructive' })
      } else if (status === 429) {
        toast({ title: 'Too many concurrent deployments', description: 'Max 2 at a time.', variant: 'destructive' })
      } else {
        toast({
          title: 'Failed to deploy',
          description: getApiErrorMessage(error, 'Deployment failed'),
          variant: 'destructive',
        })
      }
    } finally {
      setIsDeploying(false)
    }
  }, [isDeploying, isActive, sparkId, startPolling, toast])

  const executeIgnite = useCallback(() => {
    setConfirmAction(null)
    if (!hasBetaDisclaimerBeenSeen('ignite_deploy')) {
      setPendingAction('ignite')
      setShowDisclaimer(true)
      return
    }
    _doIgnite()
  }, [_doIgnite])

  const executeDeploy = useCallback(async () => {
    setConfirmAction(null)
    if (!hasBetaDisclaimerBeenSeen('ignite_deploy')) {
      setPendingAction('deploy')
      setShowDisclaimer(true)
      return
    }
    await _doDeploy()
  }, [_doDeploy])

  const onDisclaimerContinue = useCallback(() => {
    if (pendingAction === 'ignite') {
      _doIgnite()
    } else if (pendingAction === 'deploy') {
      _doDeploy()
    }
  }, [pendingAction, _doIgnite, _doDeploy])

  // Deploy label for menu items
  let deployLabel = 'Deploy to Vercel'
  let deployMenuIcon: ReactNode = <Upload className="h-4 w-4 mr-2" />
  if (isDeploying || isActive) {
    deployMenuIcon = <Loader2 className="h-4 w-4 mr-2 animate-spin" />
    deployLabel = deployment?.status === 'deploying' ? 'Deploying...' : 'Starting...'
  } else if (isDeployed) {
    deployMenuIcon = <ExternalLink className="h-4 w-4 mr-2 text-emerald-500" />
    deployLabel = 'View deployed app'
  } else if (isFailed) {
    deployMenuIcon = <AlertTriangle className="h-4 w-4 mr-2 text-red-400" />
    deployLabel = 'Retry deploy'
  }

  return {
    isReactSpark,
    canDeploy,
    confirmAction,
    requestIgnite,
    requestDeploy,
    cancelConfirm,
    executeIgnite,
    executeDeploy,
    isDeploying,
    isActive,
    isDeployed,
    isFailed,
    previewUrl,
    deployLabel,
    deployMenuIcon,
    showDisclaimer,
    setShowDisclaimer,
    pendingAction,
    onDisclaimerContinue,
  }
}

export type IgniteDeployHandle = ReturnType<typeof useIgniteDeploy>

// ---------------------------------------------------------------------------
// Dropdown Menu Items
// ---------------------------------------------------------------------------

export function IgniteMenuItems({ ignite }: { ignite: IgniteDeployHandle }) {
  const isMobile = useUIStore((state) => state.isMobile)
  const { loaded, getStage } = useFeatureFlags()
  const sparkDeployStage = getStage('spark_deploy')
  const showBetaBadge = loaded && (sparkDeployStage === 'beta' || sparkDeployStage === 'experimental')

  if (!ignite.isReactSpark) return null

  const deployDisabled = !ignite.canDeploy || ignite.isDeploying || ignite.isActive

  return (
    <>
      <DropdownMenuSeparator />
      {isMobile ? (
        <DropdownMenuItem onClick={ignite.requestIgnite} className="flex-col items-start gap-0.5 py-2">
          <span className="flex items-center">
            <Flame className="h-4 w-4 mr-2" />
            Ignite
            {showBetaBadge && (
              <BetaBadge variant={sparkDeployStage as 'beta' | 'experimental'} className="ml-1.5" />
            )}
          </span>
          <span className="text-[11px] text-muted-foreground ml-6">Create a project from this spark</span>
        </DropdownMenuItem>
      ) : (
        <TooltipProvider delayDuration={300}>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuItem onClick={ignite.requestIgnite}>
                <Flame className="h-4 w-4 mr-2" />
                Ignite
                {showBetaBadge && (
                  <BetaBadge variant={sparkDeployStage as 'beta' | 'experimental'} className="ml-auto" />
                )}
              </DropdownMenuItem>
            </TooltipTrigger>
            <TooltipContent side="left"><p>Create a project from this spark</p></TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
      <TooltipProvider delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuItem
              onClick={ignite.requestDeploy}
              disabled={deployDisabled}
            >
              {ignite.deployMenuIcon}
              {ignite.deployLabel}
              {showBetaBadge && !ignite.isDeploying && !ignite.isActive && !ignite.isDeployed && (
                <BetaBadge variant={sparkDeployStage as 'beta' | 'experimental'} className="ml-auto" />
              )}
            </DropdownMenuItem>
          </TooltipTrigger>
          {!ignite.canDeploy && (
            <TooltipContent side="left"><p>Run Ignite to scaffold the project before deploying</p></TooltipContent>
          )}
        </Tooltip>
      </TooltipProvider>
    </>
  )
}

// ---------------------------------------------------------------------------
// Confirmation Dialogs
// ---------------------------------------------------------------------------

export function IgniteDialogs({ ignite }: { ignite: IgniteDeployHandle }) {
  return (
    <>
      <AlertDialog open={ignite.confirmAction === 'ignite'} onOpenChange={(open) => { if (!open) ignite.cancelConfirm() }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Create project from this spark?</AlertDialogTitle>
            <AlertDialogDescription>
              This will send a message to the coding agent to scaffold a full Next.js project based on this spark's code.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={ignite.executeIgnite}>Create Project</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={ignite.confirmAction === 'deploy'} onOpenChange={(open) => { if (!open) ignite.cancelConfirm() }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Deploy to Vercel?</AlertDialogTitle>
            <AlertDialogDescription>
              This will package and deploy the project to Vercel. Deployment typically takes 15-30 seconds.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={ignite.executeDeploy}>Deploy</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <BetaDisclaimerModal
        featureName="Ignite"
        featureKey="ignite_deploy"
        limitations={[
          'Deployment to Vercel may take up to 2 minutes',
          'Deployments can fail if the generated code has build errors',
          'Each project gets a new Vercel URL on every deploy',
        ]}
        open={ignite.showDisclaimer}
        onContinue={ignite.onDisclaimerContinue}
        onCancel={() => ignite.setShowDisclaimer(false)}
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// Legacy Button (SparksPage gallery cards)
// ---------------------------------------------------------------------------

interface IgniteButtonProps {
  sparkId: string
  sparkTitle?: string
  framework?: string
  conversationId?: string | null
  latestDeployment?: { id: string; status: string; preview_url: string; claim_url: string } | null
  isIgnited?: boolean
  variant?: 'icon' | 'full'
  onIgnite?: (sparkId: string, sparkTitle: string) => void
}

export function IgniteButton({
  sparkId,
  sparkTitle,
  framework,
  conversationId,
  latestDeployment,
  isIgnited,
  variant = 'icon',
  onIgnite,
}: IgniteButtonProps) {
  const ignite = useIgniteDeploy({ sparkId, sparkTitle, framework, conversationId, latestDeployment, isIgnited, onIgnite })
  const isMobile = useUIStore((state) => state.isMobile)
  const { loaded, getStage } = useFeatureFlags()
  const sparkDeployStage = getStage('spark_deploy')
  const showBetaBadge = loaded && (sparkDeployStage === 'beta' || sparkDeployStage === 'experimental')

  if (!ignite.isReactSpark) return null

  const deployButtonDisabled = !ignite.canDeploy || ignite.isDeploying || ignite.isActive

  // Button-level deploy icon (smaller)
  let deployIcon = <Upload className="h-3.5 w-3.5" />
  let deployTooltip = !ignite.canDeploy ? 'Run Ignite to scaffold the project before deploying' : 'Deploy to Vercel'
  if (ignite.isDeploying || ignite.isActive) {
    deployIcon = <Loader2 className="h-3.5 w-3.5 animate-spin" />
    deployTooltip = 'Deploying...'
  } else if (ignite.isDeployed) {
    deployIcon = <ExternalLink className="h-3.5 w-3.5 text-emerald-500" />
    deployTooltip = 'View deployed app'
  } else if (ignite.isFailed) {
    deployIcon = <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
    deployTooltip = 'Retry deploy'
  }

  if (variant === 'full') {
    return (
      <>
        <div className="flex items-center gap-1.5">
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="default" size="sm" className="h-8 gap-1.5" onClick={ignite.requestIgnite}>
                  <Flame className="h-3.5 w-3.5" />
                  {isMobile ? 'Create Project' : 'Ignite'}
                  {showBetaBadge && (
                    <BetaBadge variant={sparkDeployStage as 'beta' | 'experimental'} className="ml-0.5" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">Create a project from this spark</TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant={ignite.isDeployed ? 'outline' : 'secondary'}
                  size="sm"
                  className="h-8 gap-1.5"
                  onClick={ignite.requestDeploy}
                  disabled={deployButtonDisabled}
                >
                  {deployIcon}
                  {ignite.isDeployed ? 'View App' : ignite.isDeploying || ignite.isActive ? 'Deploying...' : 'Deploy'}
                  {showBetaBadge && !ignite.isDeployed && !ignite.isDeploying && !ignite.isActive && (
                    <BetaBadge variant={sparkDeployStage as 'beta' | 'experimental'} className="ml-0.5" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">{deployTooltip}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <IgniteDialogs ignite={ignite} />
      </>
    )
  }

  return (
    <>
      <div className="flex items-center gap-0.5">
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={ignite.requestIgnite}
                className="inline-flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all"
              >
                <Flame className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Create a project from this spark</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={ignite.requestDeploy}
                disabled={deployButtonDisabled}
                className="inline-flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all disabled:opacity-50"
              >
                {deployIcon}
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{deployTooltip}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
      <IgniteDialogs ignite={ignite} />
    </>
  )
}
