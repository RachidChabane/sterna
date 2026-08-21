/**
 * AddServerDialog Component
 *
 * Wizard-based dialog for adding/editing MCP servers.
 * Two-step flow:
 *   Step 1: "Server" — type selection, name, package/URL
 *   Step 2: "Connect" — credentials, setup guide, advanced settings
 *
 * Smart flows:
 *   - Prefilled servers skip to Step 2 (no step indicator)
 *   - Edit mode opens at Step 1 with all fields populated
 *   - Custom flow: Step 1 → Step 2
 */

import { useState, useEffect } from 'react'
import { Loader2, Plus, Trash2, Info, Package, Key, Globe, Link2, Server, Sparkles, ExternalLink, ChevronDown, ChevronRight, ChevronLeft, Settings2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { useMediaQuery } from '@/hooks/use-media-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { mcpApi, type MCPServerCreateRequest, type MCPConfigHelpResponse } from '@/api/mcp'

interface EnvVar {
  key: string
  value: string
}

type ServerType = 'local' | 'remote'
type AuthType = 'none' | 'api_key' | 'bearer' | 'oauth'

interface PrefillData {
  name?: string
  description?: string
  npm_package?: string
  remote_url?: string
  transport_type?: string
  auth_type?: string
  icon_url?: string
  icon_invert_in_dark_mode?: boolean
}

interface EditServerData {
  id: string
  name: string
  description?: string
  npm_package?: string
  remote_url?: string
  transport_type?: string
  auth_type?: string
  env_var_keys?: string[]
  allowed_domains?: string[]
}

interface AddServerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onServerCreated?: () => void
  prefillData?: PrefillData
  editServer?: EditServerData
  autoFetchConfigHelp?: boolean  // Auto-fetch config help on open (for AI discovery)
}

const STEPS = [
  { id: 1, label: 'Server', icon: Server },
  { id: 2, label: 'Connect', icon: Key },
]

export function AddServerDialog({
  open,
  onOpenChange,
  onServerCreated,
  prefillData,
  editServer,
  autoFetchConfigHelp = false,
}: AddServerDialogProps) {
  const isEditMode = !!editServer
  const isPrefilled = !!prefillData
  const [isCreating, setIsCreating] = useState(false)
  const [serverType, setServerType] = useState<ServerType>('local')

  // Wizard state
  const [step, setStep] = useState(isPrefilled ? 2 : 1)
  const [animationDirection, setAnimationDirection] = useState<'forward' | 'backward'>('forward')

  // Common fields
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [showDescription, setShowDescription] = useState(false)

  // Local server fields
  const [npmPackage, setNpmPackage] = useState('')
  const [envVars, setEnvVars] = useState<EnvVar[]>([{ key: '', value: '' }])
  const [allowedDomains, setAllowedDomains] = useState('')

  // Remote server fields
  const [remoteUrl, setRemoteUrl] = useState('')
  const [authType, setAuthType] = useState<AuthType>('none')
  const [authToken, setAuthToken] = useState('')
  const [authHeaderName, setAuthHeaderName] = useState('Authorization')

  const [errors, setErrors] = useState<Record<string, string>>({})

  // Config help state
  const [isLoadingConfigHelp, setIsLoadingConfigHelp] = useState(false)
  const [configHelp, setConfigHelp] = useState<MCPConfigHelpResponse | null>(null)

  // Advanced section state
  const [showAdvanced, setShowAdvanced] = useState(false)

  // Pre-fill form when prefillData or editServer changes
  useEffect(() => {
    if (open && editServer) {
      // Edit mode - populate from existing server
      setName(editServer.name)
      if (editServer.description) {
        setDescription(editServer.description)
        setShowDescription(true)
      }
      setStep(1)

      if (editServer.npm_package) {
        setServerType('local')
        setNpmPackage(editServer.npm_package)
        if (editServer.env_var_keys && editServer.env_var_keys.length > 0) {
          setEnvVars(editServer.env_var_keys.map(key => ({ key, value: '' })))
        }
        if (editServer.allowed_domains && editServer.allowed_domains.length > 0) {
          setAllowedDomains(editServer.allowed_domains.join('\n'))
          setShowAdvanced(true)
        }
      } else if (editServer.remote_url) {
        setServerType('remote')
        setRemoteUrl(editServer.remote_url)
        if (editServer.auth_type && ['none', 'api_key', 'bearer', 'oauth'].includes(editServer.auth_type)) {
          setAuthType(editServer.auth_type as AuthType)
        }
      }
    } else if (open && prefillData) {
      if (prefillData.name) setName(prefillData.name)
      if (prefillData.description) setDescription(prefillData.description)

      if (prefillData.npm_package) {
        setServerType('local')
        setNpmPackage(prefillData.npm_package)
      } else if (prefillData.remote_url) {
        setServerType('remote')
        setRemoteUrl(prefillData.remote_url)
        if (prefillData.auth_type && ['none', 'api_key', 'bearer', 'oauth'].includes(prefillData.auth_type)) {
          setAuthType(prefillData.auth_type as AuthType)
        }
      }
      setStep(2)
    }
  }, [open, prefillData, editServer])

  // Auto-fetch config help when opening from AI discovery
  useEffect(() => {
    if (open && autoFetchConfigHelp && prefillData?.npm_package && !configHelp && !isLoadingConfigHelp) {
      const timer = setTimeout(() => {
        fetchConfigHelp()
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [open, autoFetchConfigHelp, prefillData?.npm_package])

  // Debounced auto-fetch config help when package/URL changes (min 5 chars, 800ms)
  useEffect(() => {
    const input = serverType === 'local' ? npmPackage.trim() : remoteUrl.trim()
    if (!input || input.length < 5) return
    // Don't auto-fetch if we already have config help for this input
    if (configHelp) return

    const timer = setTimeout(() => {
      fetchConfigHelp()
    }, 800)
    return () => clearTimeout(timer)
  }, [npmPackage, remoteUrl, serverType])

  const resetForm = () => {
    setServerType('local')
    setName('')
    setDescription('')
    setShowDescription(false)
    setNpmPackage('')
    setEnvVars([{ key: '', value: '' }])
    setAllowedDomains('')
    setRemoteUrl('')
    setAuthType('none')
    setAuthToken('')
    setAuthHeaderName('Authorization')
    setErrors({})
    setConfigHelp(null)
    setShowAdvanced(false)
    setStep(isPrefilled ? 2 : 1)
    setAnimationDirection('forward')
  }

  const fetchConfigHelp = async () => {
    const hasLocalInput = serverType === 'local' && npmPackage.trim()
    const hasRemoteInput = serverType === 'remote' && remoteUrl.trim()

    if (!hasLocalInput && !hasRemoteInput) {
      return
    }

    setIsLoadingConfigHelp(true)

    try {
      const response = await mcpApi.getConfigHelp({
        npm_package: serverType === 'local' ? npmPackage.trim() : undefined,
        remote_url: serverType === 'remote' ? remoteUrl.trim() : undefined,
        server_name: name.trim() || npmPackage.trim() || 'MCP Server',
      })
      setConfigHelp(response.data)

      // Auto-fill env var keys from the response
      if (response.data.env_vars && response.data.env_vars.length > 0) {
        const existingKeys = new Set(envVars.filter(ev => ev.key.trim()).map(ev => ev.key.trim()))
        const newEnvVars = [...envVars.filter(ev => ev.key.trim() || ev.value.trim())]

        for (const configVar of response.data.env_vars) {
          if (!existingKeys.has(configVar.name)) {
            newEnvVars.push({ key: configVar.name, value: '' })
          }
        }

        if (newEnvVars.length === 0) {
          newEnvVars.push({ key: '', value: '' })
        }

        setEnvVars(newEnvVars)
      }

      // Auto-fill allowed domains from the response
      if (response.data.allowed_domains && response.data.allowed_domains.length > 0) {
        const existingDomains = new Set(
          allowedDomains.split(/[,\n]/).map(d => d.trim().toLowerCase()).filter(d => d)
        )
        const newDomains = response.data.allowed_domains.filter(
          d => !existingDomains.has(d.toLowerCase())
        )
        if (newDomains.length > 0) {
          const currentDomains = allowedDomains.trim()
          const separator = currentDomains ? '\n' : ''
          setAllowedDomains(currentDomains + separator + newDomains.join('\n'))
        }
      }

      // Auto-select auth type for remote servers
      if (serverType === 'remote' && response.data.auth_type) {
        const detectedAuthType = response.data.auth_type as AuthType
        if (['none', 'api_key', 'bearer', 'oauth'].includes(detectedAuthType)) {
          setAuthType(detectedAuthType)
        }
      }
    } catch (error: any) {
      console.error('Failed to get config help:', error)
      setConfigHelp(null)
    } finally {
      setIsLoadingConfigHelp(false)
    }
  }

  const handleClose = () => {
    resetForm()
    onOpenChange(false)
  }

  const addEnvVar = () => {
    setEnvVars([...envVars, { key: '', value: '' }])
  }

  const removeEnvVar = (index: number) => {
    setEnvVars(envVars.filter((_, i) => i !== index))
  }

  const updateEnvVar = (index: number, field: 'key' | 'value', value: string) => {
    const newEnvVars = [...envVars]
    newEnvVars[index][field] = value
    setEnvVars(newEnvVars)
  }

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {}

    if (!name.trim()) {
      newErrors.name = 'Name is required'
    }

    if (serverType === 'local') {
      if (!npmPackage.trim()) {
        newErrors.npmPackage = 'NPM package is required'
      } else {
        const npmPattern = /^(@[a-z0-9-~][a-z0-9-._~]*\/)?[a-z0-9-~][a-z0-9-._~]*$/i
        if (!npmPattern.test(npmPackage.trim())) {
          newErrors.npmPackage = 'Invalid NPM package name format'
        }
      }

      const filledEnvVars = envVars.filter(ev => ev.key.trim() || ev.value.trim())
      for (const ev of filledEnvVars) {
        if (!isEditMode && ev.key.trim() && !ev.value.trim()) {
          newErrors.envVars = 'All environment variable keys must have values'
          break
        }
        if (!ev.key.trim() && ev.value.trim()) {
          newErrors.envVars = 'All environment variable values must have keys'
          break
        }
      }
    } else {
      if (!remoteUrl.trim()) {
        newErrors.remoteUrl = 'URL is required'
      } else if (!remoteUrl.startsWith('http://') && !remoteUrl.startsWith('https://')) {
        newErrors.remoteUrl = 'URL must start with http:// or https://'
      }

      if (authType !== 'none' && authType !== 'oauth' && !authToken.trim()) {
        newErrors.authToken = 'Token is required when authentication is enabled'
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return

    setIsCreating(true)
    try {
      let data: MCPServerCreateRequest

      if (serverType === 'local') {
        const envVarsObj: Record<string, string> = {}
        for (const ev of envVars) {
          if (ev.key.trim() && ev.value.trim()) {
            envVarsObj[ev.key.trim()] = ev.value.trim()
          }
        }

        const domainsArray = allowedDomains
          .split(/[,\n]/)
          .map(d => d.trim())
          .filter(d => d.length > 0)

        data = {
          name: name.trim(),
          description: description.trim() || undefined,
          npm_package: npmPackage.trim(),
          env_vars: Object.keys(envVarsObj).length > 0 ? envVarsObj : undefined,
          allowed_domains: domainsArray.length > 0 ? domainsArray : undefined,
          is_active: true,
          icon_url: prefillData?.icon_url,
          icon_invert_in_dark_mode: prefillData?.icon_invert_in_dark_mode,
        }
      } else {
        data = {
          name: name.trim(),
          description: description.trim() || undefined,
          remote_url: remoteUrl.trim(),
          auth_type: authType,
          auth_header_name: authHeaderName.trim() || 'Authorization',
          auth_config: authType !== 'none' && authToken.trim()
            ? { token: authToken.trim() }
            : undefined,
          is_active: true,
          icon_url: prefillData?.icon_url,
          icon_invert_in_dark_mode: prefillData?.icon_invert_in_dark_mode,
        }
      }

      if (isEditMode && editServer) {
        await mcpApi.updateServer(editServer.id, data)
        toast.success(`Server "${name}" updated successfully`)
      } else {
        await mcpApi.createServer(data)
        toast.success(`Server "${name}" created successfully`)
      }
      handleClose()
      onServerCreated?.()
    } catch (error: any) {
      console.error('Failed to create server:', error)

      let errorMessage = 'Failed to create server'
      const responseData = error.response?.data

      if (responseData) {
        if (typeof responseData === 'string') {
          errorMessage = responseData
        } else if (responseData.detail) {
          errorMessage = responseData.detail
        } else if (responseData.message) {
          errorMessage = responseData.message
        } else {
          const fieldErrors = Object.entries(responseData)
            .filter(([_, value]) => Array.isArray(value) || typeof value === 'string')
            .map(([_, messages]) => Array.isArray(messages) ? (messages as string[]).join(', ') : messages as string)
          if (fieldErrors.length > 0) {
            errorMessage = fieldErrors.join('. ')
          }
        }
      } else if (error.message) {
        errorMessage = error.message
      }

      toast.error(errorMessage)
    } finally {
      setIsCreating(false)
    }
  }

  const canProceedFromStep = (s: number) => {
    if (s === 1) {
      if (!name.trim()) return false
      if (serverType === 'local' && !npmPackage.trim()) return false
      if (serverType === 'remote' && !remoteUrl.trim()) return false
      return true
    }
    return true
  }

  const goToStep = (target: number) => {
    setAnimationDirection(target > step ? 'forward' : 'backward')
    setStep(target)
  }

  const isMobile = useMediaQuery('(max-width: 640px)')
  const showStepIndicator = !isPrefilled || isEditMode

  const titleText = isEditMode
    ? `Edit ${editServer?.name}`
    : isPrefilled
      ? `Connect to ${prefillData?.name}`
      : 'Add Integration'

  const descriptionText = isEditMode
    ? 'Update server configuration. Leave secret values empty to keep existing.'
    : isPrefilled
      ? 'Enter your credentials to connect.'
      : 'Connect a local package or remote service.'

  // ── Step 1: Server ────────────────────────────────────────────────

  const renderStep1Content = () => (
    <div className="space-y-5">
      {/* Type selection cards */}
      <div className="grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={() => setServerType('local')}
          className={cn(
            "relative flex flex-col items-start gap-2 rounded-xl border-2 p-4 text-left transition-all",
            serverType === 'local'
              ? "border-accent-brand bg-accent-brand/5"
              : "border-border hover:border-border/80 hover:bg-muted/30"
          )}
        >
          <Package className={cn("h-5 w-5", serverType === 'local' ? "text-accent-brand" : "text-muted-foreground")} />
          <div>
            <p className="text-sm font-medium">Local Package</p>
            <p className="text-xs text-muted-foreground">Runs in a sandbox on our infrastructure</p>
          </div>
        </button>

        <button
          type="button"
          onClick={() => setServerType('remote')}
          className={cn(
            "relative flex flex-col items-start gap-2 rounded-xl border-2 p-4 text-left transition-all",
            serverType === 'remote'
              ? "border-accent-brand bg-accent-brand/5"
              : "border-border hover:border-border/80 hover:bg-muted/30"
          )}
        >
          <Globe className={cn("h-5 w-5", serverType === 'remote' ? "text-accent-brand" : "text-muted-foreground")} />
          <div>
            <p className="text-sm font-medium">Remote Service</p>
            <p className="text-xs text-muted-foreground">Connect to an external endpoint</p>
          </div>
        </button>
      </div>

      {/* Server name */}
      <div className="space-y-1.5">
        <Label htmlFor="name" className="text-xs text-muted-foreground">Server Name *</Label>
        <Input
          id="name"
          placeholder={serverType === 'local' ? 'My GitHub Server' : 'Zapier MCP'}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={errors.name ? 'border-red-500' : ''}
        />
        {errors.name && <p className="text-xs text-red-500">{errors.name}</p>}
      </div>

      {/* Package name or URL */}
      {serverType === 'local' ? (
        <div className="space-y-1.5">
          <Label htmlFor="npmPackage" className="text-xs text-muted-foreground flex items-center gap-1">
            <Package className="h-3.5 w-3.5" />
            NPM Package *
          </Label>
          <div className="flex gap-2">
            <Input
              id="npmPackage"
              placeholder="@modelcontextprotocol/server-github"
              value={npmPackage}
              onChange={(e) => {
                setNpmPackage(e.target.value)
                setConfigHelp(null) // Reset to re-trigger auto-fetch
              }}
              className={cn("flex-1", errors.npmPackage && 'border-red-500')}
            />
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={fetchConfigHelp}
                    disabled={isLoadingConfigHelp || !npmPackage.trim()}
                    className="shrink-0"
                  >
                    {isLoadingConfigHelp ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="h-4 w-4" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Auto-detect configuration</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          {errors.npmPackage && <p className="text-xs text-red-500">{errors.npmPackage}</p>}
          <p className="text-xs text-muted-foreground">
            e.g. <code className="text-xs">@modelcontextprotocol/server-github</code>
          </p>
        </div>
      ) : (
        <div className="space-y-1.5">
          <Label htmlFor="remoteUrl" className="text-xs text-muted-foreground flex items-center gap-1">
            <Link2 className="h-3.5 w-3.5" />
            Server URL *
          </Label>
          <div className="flex gap-2">
            <Input
              id="remoteUrl"
              placeholder="https://mcp.example.com/api/mcp"
              value={remoteUrl}
              onChange={(e) => {
                setRemoteUrl(e.target.value)
                setConfigHelp(null)
              }}
              className={cn("flex-1", errors.remoteUrl && 'border-red-500')}
            />
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={fetchConfigHelp}
                    disabled={isLoadingConfigHelp || !remoteUrl.trim()}
                    className="shrink-0"
                  >
                    {isLoadingConfigHelp ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="h-4 w-4" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Auto-detect configuration</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          {errors.remoteUrl && <p className="text-xs text-red-500">{errors.remoteUrl}</p>}
          <p className="text-xs text-muted-foreground">
            The HTTP endpoint of the remote MCP server
          </p>
        </div>
      )}

      {/* Description — collapsed by default, auto-expand in edit mode */}
      {showDescription ? (
        <div className="space-y-1.5">
          <Label htmlFor="description" className="text-xs text-muted-foreground">Description</Label>
          <Textarea
            id="description"
            placeholder="What does this server do?"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowDescription(true)}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          + Add description
        </button>
      )}
    </div>
  )

  // ── Step 2: Connect ───────────────────────────────────────────────

  const renderStep2Content = () => {
    // Find config help env var info for a given key
    const getConfigVarInfo = (key: string) =>
      configHelp?.env_vars?.find(cv => cv.name === key)

    return (
      <div className="space-y-5">
        {/* Context banner for prefilled servers */}
        {isPrefilled && prefillData?.name && (
          <div className="flex items-center gap-3 rounded-lg bg-muted/40 px-3 py-2.5">
            {prefillData.icon_url ? (
              <img
                src={prefillData.icon_url}
                alt=""
                className="h-5 w-5 rounded object-contain"
              />
            ) : (
              <Server className="h-5 w-5 text-muted-foreground" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{prefillData.name}</p>
              {prefillData.npm_package && (
                <p className="text-xs text-muted-foreground font-mono truncate">{prefillData.npm_package}</p>
              )}
            </div>
          </div>
        )}

        {/* Compatibility warning */}
        {configHelp?.compatibility_warning && (
          <Alert variant="destructive" className="py-2">
            <Info className="h-4 w-4" />
            <AlertDescription className="text-xs">{configHelp.compatibility_warning}</AlertDescription>
          </Alert>
        )}

        {/* Setup guide — inline numbered steps with docs link */}
        {configHelp && (configHelp.setup_steps?.length > 0 || configHelp.docs_url) && (
          <div className="rounded-lg border border-border bg-muted/20 px-3 py-3 space-y-2">
            {configHelp.setup_steps && configHelp.setup_steps.length > 0 && (
              <ol className="text-sm space-y-1.5 list-decimal list-inside text-muted-foreground">
                {configHelp.setup_steps.map((s, idx) => (
                  <li key={idx}>{s}</li>
                ))}
              </ol>
            )}
            {configHelp.docs_url && (
              <a
                href={configHelp.docs_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-accent-brand hover:underline"
              >
                <ExternalLink className="h-3 w-3" />
                View documentation
              </a>
            )}
          </div>
        )}

        {/* Loading state for config help */}
        {isLoadingConfigHelp && (
          <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Analyzing configuration...
          </div>
        )}

        {/* Credentials section */}
        {serverType === 'local' ? (
          <div className="space-y-3">
            <Label className="text-xs text-muted-foreground flex items-center gap-1">
              <Key className="h-3.5 w-3.5" />
              API Keys & Secrets
            </Label>
            <p className="text-xs text-muted-foreground -mt-1">
              {isEditMode ? 'Leave values empty to keep existing secrets.' : 'Credentials are encrypted at rest.'}
            </p>

            {envVars.map((envVar, index) => {
              const configVar = getConfigVarInfo(envVar.key)
              const hasConfigInfo = !!configVar

              return (
                <div key={index} className="space-y-1">
                  {/* Label: friendly description or raw key */}
                  {hasConfigInfo ? (
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{configVar!.description || configVar!.label}</p>
                        <p className="text-xs text-muted-foreground font-mono">{envVar.key}</p>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {configVar!.docs_url && (
                          <a
                            href={configVar!.docs_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-accent-brand hover:underline"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        )}
                        {envVars.length > 1 && (
                          <Button type="button" variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeEnvVar(index)}>
                            <Trash2 className="h-3.5 w-3.5 text-red-500" />
                          </Button>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-2 items-center">
                      <Input
                        placeholder="KEY_NAME"
                        value={envVar.key}
                        onChange={(e) => updateEnvVar(index, 'key', e.target.value)}
                        className="flex-1 font-mono text-sm h-8"
                      />
                      {envVars.length > 1 && (
                        <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => removeEnvVar(index)}>
                          <Trash2 className="h-3.5 w-3.5 text-red-500" />
                        </Button>
                      )}
                    </div>
                  )}

                  {/* Value input */}
                  <Input
                    type="password"
                    placeholder={hasConfigInfo ? (configVar!.example || 'Paste your secret here') : 'Value'}
                    value={envVar.value}
                    onChange={(e) => updateEnvVar(index, 'value', e.target.value)}
                    className={cn(hasConfigInfo && "font-mono text-sm")}
                  />
                </div>
              )
            })}
            {errors.envVars && <p className="text-xs text-red-500">{errors.envVars}</p>}

            <Button type="button" variant="outline" size="sm" onClick={addEnvVar} className="w-full">
              <Plus className="h-4 w-4 mr-1" />
              Add secret
            </Button>
          </div>
        ) : (
          /* Remote server auth */
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="authType" className="text-xs text-muted-foreground flex items-center gap-1">
                <Key className="h-3.5 w-3.5" />
                Authentication
              </Label>
              <Select value={authType} onValueChange={(v) => setAuthType(v as AuthType)}>
                <SelectTrigger>
                  <SelectValue placeholder="Select authentication type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No Authentication</SelectItem>
                  <SelectItem value="api_key">API Key</SelectItem>
                  <SelectItem value="bearer">Bearer Token</SelectItem>
                  <SelectItem value="oauth">OAuth 2.0 (Dynamic)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {(authType === 'api_key' || authType === 'bearer') && (
              <div className="space-y-1.5">
                <Label htmlFor="authToken" className="text-xs text-muted-foreground">
                  {authType === 'api_key' ? 'API Key' : 'Bearer Token'} *
                </Label>
                <Input
                  id="authToken"
                  type="password"
                  placeholder={authType === 'api_key' ? 'Your API key' : 'Your bearer token'}
                  value={authToken}
                  onChange={(e) => setAuthToken(e.target.value)}
                  className={errors.authToken ? 'border-red-500' : ''}
                />
                {errors.authToken && <p className="text-xs text-red-500">{errors.authToken}</p>}
              </div>
            )}

            {authType === 'oauth' && (
              <Alert>
                <Info className="h-4 w-4" />
                <AlertDescription className="text-xs">
                  OAuth will be configured after creating the server.
                  You'll be redirected to authorize with the provider.
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}

        {/* Advanced section */}
        <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <Settings2 className="h-3.5 w-3.5" />
              Advanced
              <ChevronDown className={cn("h-3 w-3 transition-transform duration-200", showAdvanced && "rotate-180")} />
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="space-y-3 pt-3">
              {serverType === 'local' ? (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="allowedDomains" className="text-xs text-muted-foreground flex items-center gap-1">
                      <Globe className="h-3.5 w-3.5" />
                      Allowed Domains
                    </Label>
                    <Textarea
                      id="allowedDomains"
                      placeholder={"api.github.com\napi.example.com"}
                      value={allowedDomains}
                      onChange={(e) => setAllowedDomains(e.target.value)}
                      rows={2}
                      className="font-mono text-sm"
                    />
                    <p className="text-xs text-muted-foreground">
                      Domains the server can access. NPM registry allowed by default.
                    </p>
                  </div>
                  <Alert>
                    <Info className="h-4 w-4" />
                    <AlertDescription className="text-xs">
                      Runs in an isolated Docker container with limited resources and network access.
                    </AlertDescription>
                  </Alert>
                </>
              ) : (
                <>
                  {(authType === 'api_key' || authType === 'bearer') && (
                    <div className="space-y-1.5">
                      <Label htmlFor="authHeaderName" className="text-xs text-muted-foreground">Auth Header Name</Label>
                      <Input
                        id="authHeaderName"
                        placeholder="Authorization"
                        value={authHeaderName}
                        onChange={(e) => setAuthHeaderName(e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">
                        HTTP header name for authentication (default: Authorization)
                      </p>
                    </div>
                  )}
                  <Alert>
                    <Info className="h-4 w-4" />
                    <AlertDescription className="text-xs">
                      Remote servers run externally. Connect to enterprise MCP servers,
                      third-party integrations, or any MCP-compatible HTTP endpoint.
                    </AlertDescription>
                  </Alert>
                </>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </div>
    )
  }

  // ── Step Indicator ────────────────────────────────────────────────

  const renderStepIndicator = () => {
    if (!showStepIndicator) return null

    return (
      <div className="flex items-center justify-center gap-2 py-3 border-b border-border/30 shrink-0 bg-muted/30">
        {STEPS.map((s) => {
          const StepIcon = s.icon
          const isActive = step === s.id
          const isCompleted = step > s.id

          return (
            <button
              key={s.id}
              onClick={() => {
                if (s.id < step || canProceedFromStep(step)) {
                  goToStep(s.id)
                }
              }}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                isActive
                  ? "bg-accent-brand/15 text-accent-brand"
                  : isCompleted
                    ? "bg-muted/50 text-foreground hover:bg-muted/70"
                    : "text-muted-foreground"
              )}
            >
              <StepIcon className="h-3.5 w-3.5" />
              {s.label}
            </button>
          )
        })}
      </div>
    )
  }

  // ── Footer ────────────────────────────────────────────────────────

  const renderFooter = () => {
    const submitLabel = isEditMode ? 'Save Changes' : isPrefilled ? 'Connect Server' : 'Connect Server'

    if (step === 1) {
      return (
        <>
          <Button variant="ghost" onClick={handleClose} disabled={isCreating}>Cancel</Button>
          <Button
            onClick={() => goToStep(2)}
            disabled={!canProceedFromStep(1)}
          >
            Continue
            <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </>
      )
    }

    return (
      <>
        <Button variant="ghost" onClick={handleClose} disabled={isCreating}>Cancel</Button>
        <div className="flex items-center gap-2">
          {showStepIndicator && (
            <Button variant="outline" onClick={() => goToStep(1)} disabled={isCreating}>
              <ChevronLeft className="h-4 w-4 mr-1" />
              Back
            </Button>
          )}
          <Button
            onClick={handleSubmit}
            disabled={isCreating}
            variant="outline"
            className="rounded-full text-brand-700 dark:text-brand-400 border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-800 dark:hover:text-brand-300"
          >
            {isCreating && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {submitLabel}
          </Button>
        </div>
      </>
    )
  }

  // ── Animation class ───────────────────────────────────────────────

  const stepAnimationClass = animationDirection === 'forward'
    ? "animate-in fade-in-0 slide-in-from-right-4 duration-200"
    : "animate-in fade-in-0 slide-in-from-left-4 duration-200"

  // ── Render ────────────────────────────────────────────────────────

  const stepContent = step === 1 ? renderStep1Content() : renderStep2Content()

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={handleClose}>
        <SheetContent side="bottom" className="h-[85vh] rounded-t-2xl p-0 flex flex-col [&>button]:hidden">
          <SheetHeader className="shrink-0 px-4 pt-4 pb-3 border-b border-border/30">
            <SheetTitle className="flex items-center gap-2 text-base">
              <Server className="h-5 w-5" />
              {titleText}
            </SheetTitle>
            <SheetDescription className="text-xs">{descriptionText}</SheetDescription>
          </SheetHeader>

          {renderStepIndicator()}

          <div className="flex-1 overflow-y-auto px-4 py-4">
            <div key={step} className={stepAnimationClass}>
              {stepContent}
            </div>
          </div>

          <div className="shrink-0 border-t border-border/30 px-4 py-3 flex justify-between items-center bg-background">
            {renderFooter()}
          </div>
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg max-h-[85vh] p-0 gap-0 overflow-hidden flex flex-col">
        <DialogHeader className="shrink-0 px-6 pt-5 pb-3 border-b border-border/30">
          <DialogTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            {titleText}
          </DialogTitle>
          <DialogDescription className="text-xs">{descriptionText}</DialogDescription>
        </DialogHeader>

        {renderStepIndicator()}

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div key={step} className={stepAnimationClass}>
            {stepContent}
          </div>
        </div>

        <div className="shrink-0 border-t border-border/30 px-6 py-4 flex justify-between items-center bg-background">
          {renderFooter()}
        </div>
      </DialogContent>
    </Dialog>
  )
}
