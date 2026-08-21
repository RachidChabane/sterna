import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useMediaQuery } from '@/hooks/use-media-query'
import { useSubAgentStore } from '@/store/subAgentStore'
import type { SubAgent, SubAgentCreateData, ModelTier } from '@/api/subAgents'
import { toast } from 'sonner'
import { Sparkles, ChevronDown, ChevronLeft, Loader2, X } from 'lucide-react'

// ==================== Constants ====================

const TOOL_CATEGORIES = [
  {
    label: 'File Access',
    tools: [
      { name: 'Read', desc: 'Read file contents' },
      { name: 'Write', desc: 'Create or overwrite files' },
      { name: 'Edit', desc: 'Make targeted edits to files' },
    ],
  },
  {
    label: 'Search',
    tools: [
      { name: 'Glob', desc: 'Find files by pattern' },
      { name: 'Grep', desc: 'Search file contents' },
    ],
  },
  {
    label: 'Execution',
    tools: [
      { name: 'Bash', desc: 'Run shell commands' },
    ],
  },
  {
    label: 'Web',
    tools: [
      { name: 'WebSearch', desc: 'Search the internet' },
      { name: 'WebFetch', desc: 'Fetch URL contents' },
    ],
  },
  {
    label: 'Delegation',
    tools: [
      { name: 'Task', desc: 'Spawn sub-agents' },
    ],
  },
  {
    label: 'Notebooks',
    tools: [
      { name: 'NotebookEdit', desc: 'Edit Jupyter notebooks' },
    ],
  },
]

const ALL_TOOLS = TOOL_CATEGORIES.flatMap(c => c.tools.map(t => t.name))

const EXAMPLE_PROMPTS = [
  {
    title: 'Security Reviewer',
    prompt: `You are a security-focused code reviewer. When given code to review:

1. Check for OWASP Top 10 vulnerabilities (injection, XSS, CSRF, etc.)
2. Look for hardcoded secrets, credentials, or API keys
3. Identify insecure dependencies or outdated patterns
4. Flag missing input validation and sanitization
5. Check authentication and authorization logic

Format findings as: [SEVERITY] File:Line - Description. Group by severity (Critical, High, Medium, Low).`,
  },
  {
    title: 'Test Writer',
    prompt: `You are a test-writing specialist. When asked to write tests:

1. Read the source code to understand the function/module under test
2. Write comprehensive unit tests covering happy paths, edge cases, and error conditions
3. Follow the project's existing test patterns and frameworks
4. Use descriptive test names that explain what is being tested
5. Include setup/teardown when needed, prefer minimal mocking

Aim for high coverage without redundant tests. Each test should verify one behavior.`,
  },
  {
    title: 'Documentation Writer',
    prompt: `You are a documentation specialist. When asked to document code:

1. Read the source code thoroughly before writing
2. Write clear, concise docstrings/comments for public APIs
3. Include parameter types, return types, and usage examples
4. Document non-obvious behavior, gotchas, and edge cases
5. Keep documentation close to the code it describes

Use the project's existing documentation style. Avoid over-documenting obvious code.`,
  },
]

const MODEL_TIERS: Array<{ value: ModelTier; label: string; description: string }> = [
  { value: 'fast', label: 'Fast', description: 'Quick, low-cost tasks' },
  { value: 'balanced', label: 'Balanced', description: 'Best for most coding tasks' },
  { value: 'powerful', label: 'Powerful', description: 'Complex analysis and reasoning' },
  { value: 'inherit', label: 'Inherit from Chat', description: "Uses the chat's selected model" },
]

const PERMISSION_MODES = [
  { value: 'default', label: 'Default', description: 'Asks before writing files' },
  { value: 'plan', label: 'Plan Only', description: 'Read-only, no code changes' },
  { value: 'autoEdit', label: 'Auto Edit', description: 'Auto-approves file edits' },
  { value: 'fullAuto', label: 'Full Auto', description: 'No confirmations needed' },
]

const NAME_RE = /^[a-zA-Z][a-zA-Z0-9_-]*$/

type ToolState = 'default' | 'allowed' | 'disallowed'

const MOBILE_TABS = [
  { id: 'identity', label: 'Identity' },
  { id: 'instructions', label: 'Instructions' },
  { id: 'permissions', label: 'Permissions' },
] as const

interface AgentFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editAgent?: SubAgent | null
}

export default function AgentFormDialog({ open, onOpenChange, editAgent }: AgentFormDialogProps) {
  const { createAgent, updateAgent, generateAgent, isGenerating } = useSubAgentStore()
  const isMobile = useMediaQuery('(max-width: 640px)')
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState('identity')
  const [generateOpen, setGenerateOpen] = useState(false)
  const [generateDescription, setGenerateDescription] = useState('')

  // Form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [modelTier, setModelTier] = useState<ModelTier>('inherit')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [toolStates, setToolStates] = useState<Record<string, ToolState>>({})
  const [maxTurns, setMaxTurns] = useState(10)
  const [permissionMode, setPermissionMode] = useState('default')
  const [isActive, setIsActive] = useState(true)

  // Validation
  const [nameError, setNameError] = useState('')

  const buildToolStates = (tools: string[], disallowed: string[]): Record<string, ToolState> => {
    const states: Record<string, ToolState> = {}
    for (const tool of ALL_TOOLS) {
      if (tools.includes(tool)) states[tool] = 'allowed'
      else if (disallowed.includes(tool)) states[tool] = 'disallowed'
      else states[tool] = 'default'
    }
    return states
  }

  // Populate form when editing
  useEffect(() => {
    if (editAgent) {
      setName(editAgent.name)
      setDescription(editAgent.description)
      setModelTier(editAgent.model_tier)
      setSystemPrompt(editAgent.system_prompt)
      setToolStates(buildToolStates(editAgent.tools, editAgent.disallowed_tools))
      setMaxTurns(editAgent.max_turns)
      setPermissionMode(editAgent.permission_mode)
      setIsActive(editAgent.is_active)
    } else {
      setName('')
      setDescription('')
      setModelTier('inherit')
      setSystemPrompt('')
      setToolStates(buildToolStates(['Read', 'Glob', 'Grep'], []))
      setMaxTurns(10)
      setPermissionMode('default')
      setIsActive(true)
    }
    setNameError('')
    setActiveTab('identity')
    setGenerateOpen(false)
    setGenerateDescription('')
  }, [editAgent, open])

  const handleNameChange = (value: string) => {
    setName(value)
    if (value && !NAME_RE.test(value)) {
      setNameError('Must start with a letter, only letters, digits, hyphens, underscores')
    } else {
      setNameError('')
    }
  }

  const cycleToolState = (tool: string) => {
    setToolStates(prev => {
      const current = prev[tool] || 'default'
      const next: ToolState =
        current === 'default' ? 'allowed' :
        current === 'allowed' ? 'disallowed' : 'default'
      return { ...prev, [tool]: next }
    })
  }

  const handleGenerate = async () => {
    if (!generateDescription.trim() || isGenerating) return
    const result = await generateAgent(generateDescription.trim())
    if (result) {
      setName(result.name || '')
      setDescription(result.description || '')
      setModelTier((result.model_tier as ModelTier) || 'balanced')
      setSystemPrompt(result.system_prompt || '')
      setToolStates(buildToolStates(result.tools || [], result.disallowed_tools || []))
      setMaxTurns(result.max_turns || 10)
      setPermissionMode(result.permission_mode || 'default')
      setGenerateOpen(false)
      toast.success('Agent configuration generated')
    }
  }

  const applyExamplePrompt = (prompt: string) => {
    setSystemPrompt(prompt)
    toast.success('Example prompt applied')
  }

  const handleSave = async () => {
    if (!name.trim()) {
      setNameError('Name is required')
      setActiveTab('identity')
      return
    }
    if (!NAME_RE.test(name)) {
      setNameError('Invalid name format')
      setActiveTab('identity')
      return
    }

    const tools: string[] = []
    const disallowedTools: string[] = []
    for (const tool of ALL_TOOLS) {
      const state = toolStates[tool] || 'default'
      if (state === 'allowed') tools.push(tool)
      else if (state === 'disallowed') disallowedTools.push(tool)
    }

    setSaving(true)
    try {
      const data: SubAgentCreateData = {
        name,
        description,
        model_tier: modelTier,
        system_prompt: systemPrompt,
        tools,
        disallowed_tools: disallowedTools,
        max_turns: maxTurns,
        permission_mode: permissionMode,
        is_active: isActive,
      }

      if (editAgent) {
        const result = await updateAgent(editAgent.id, data)
        if (result) {
          toast.success('Agent updated')
          onOpenChange(false)
        }
      } else {
        const result = await createAgent(data)
        if (result) {
          toast.success('Agent created')
          onOpenChange(false)
        }
      }
    } finally {
      setSaving(false)
    }
  }

  // ==================== Shared form content ====================

  const renderGenerateSection = () => {
    if (editAgent) return null
    return (
      <Collapsible open={generateOpen} onOpenChange={setGenerateOpen} className="rounded-lg border bg-card">
        <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2.5 text-sm font-medium hover:bg-muted/50 transition-colors rounded-lg">
          <span className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-accent-brand" />
            Generate from description
          </span>
          <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${generateOpen ? 'rotate-180' : ''}`} />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="border-t px-3 pb-3 pt-3 space-y-2">
            <Textarea
              value={generateDescription}
              onChange={(e) => setGenerateDescription(e.target.value.slice(0, 2000))}
              placeholder="Describe what your agent should do, e.g. 'An agent that reviews Python code for security vulnerabilities and suggests fixes'"
              className="h-20 resize-none text-sm"
            />
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                {generateDescription.length} / 2,000
              </span>
              <Button
                className="w-full sm:w-auto"
                size="sm"
                onClick={handleGenerate}
                disabled={!generateDescription.trim() || isGenerating}
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>Generate</>
                )}
              </Button>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    )
  }

  const renderIdentityTab = () => (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="agent-name">Name</Label>
        <Input
          id="agent-name"
          value={name}
          onChange={(e) => handleNameChange(e.target.value)}
          placeholder="e.g. security-reviewer"
          className={nameError ? 'border-destructive' : ''}
        />
        {nameError && (
          <p className="text-xs text-destructive">{nameError}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="agent-desc">Description</Label>
        <Textarea
          id="agent-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e.g. Reviews code for security vulnerabilities and suggests fixes"
          className="h-16 resize-none"
        />
      </div>

      <div className="space-y-1.5">
        <Label>Model Tier</Label>
        <Select value={modelTier} onValueChange={(v) => setModelTier(v as ModelTier)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MODEL_TIERS.map(tier => (
              <SelectItem key={tier.value} value={tier.value}>
                <span>{tier.label}</span>
                <span className="ml-2 text-xs text-muted-foreground">{tier.description}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Configure which model each tier maps to in Settings &rarr; Coding Agents
        </p>
      </div>

      <div className="flex items-center justify-between">
        <div>
          <Label>Active</Label>
          <p className="text-xs text-muted-foreground">Available for the orchestrator to dispatch</p>
        </div>
        <Switch checked={isActive} onCheckedChange={setIsActive} />
      </div>
    </div>
  )

  const renderInstructionsTab = () => (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Tell the agent what it should do, how to format output, and any domain-specific rules.
      </p>

      <div className="space-y-1.5">
        <Label htmlFor="agent-prompt">
          System Prompt
          <span className="ml-2 text-xs text-muted-foreground">
            {systemPrompt.length.toLocaleString()} / 50,000
          </span>
        </Label>
        <Textarea
          id="agent-prompt"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value.slice(0, 50000))}
          placeholder="Instructions for the sub-agent..."
          className="min-h-[250px] text-sm"
        />
      </div>

      {/* Example Prompts */}
      <div className="space-y-2">
        <Label className="text-xs text-muted-foreground">Example prompts</Label>
        {EXAMPLE_PROMPTS.map((example) => (
          <Collapsible key={example.title}>
            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <CollapsibleTrigger asChild>
                <button type="button" className="flex items-center gap-2 text-sm hover:underline">
                  <ChevronDown className="h-3.5 w-3.5" />
                  {example.title}
                </button>
              </CollapsibleTrigger>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => applyExamplePrompt(example.prompt)}
              >
                Use this prompt
              </Button>
            </div>
            <CollapsibleContent>
              <pre className="mt-1 rounded-md border bg-muted/50 p-3 text-xs whitespace-pre-wrap max-h-40 overflow-y-auto">
                {example.prompt}
              </pre>
            </CollapsibleContent>
          </Collapsible>
        ))}
      </div>
    </div>
  )

  const renderPermissionsTab = () => (
    <div className="space-y-4">
      {/* Tools grouped by category */}
      <div className="space-y-3">
        <div>
          <Label>Tools</Label>
          <p className="text-xs text-muted-foreground mt-0.5">
            Click to cycle: default &rarr; allowed &rarr; disallowed
          </p>
        </div>
        {TOOL_CATEGORIES.map(category => (
          <div key={category.label} className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{category.label}</p>
            <div className="flex flex-wrap gap-1.5">
              {category.tools.map(tool => {
                const state = toolStates[tool.name] || 'default'
                return (
                  <button
                    key={tool.name}
                    type="button"
                    onClick={() => cycleToolState(tool.name)}
                    title={tool.desc}
                    className={`rounded-md border px-2 py-0.5 text-xs transition-colors ${
                      state === 'allowed'
                        ? 'border-accent-brand/50 bg-accent-brand/10 text-accent-brand'
                        : state === 'disallowed'
                        ? 'border-destructive/50 bg-destructive/10 text-destructive line-through'
                        : 'border-border bg-background text-muted-foreground hover:border-border/80'
                    }`}
                  >
                    {tool.name}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Permission Mode */}
      <div className="space-y-1.5">
        <Label>Permission Mode</Label>
        <Select value={permissionMode} onValueChange={setPermissionMode}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PERMISSION_MODES.map(mode => (
              <SelectItem key={mode.value} value={mode.value}>
                <span>{mode.label}</span>
                <span className="ml-2 text-xs text-muted-foreground">{mode.description}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Max Turns */}
      <div className="space-y-1.5">
        <Label htmlFor="max-turns">Max Turns</Label>
        <Input
          id="max-turns"
          type="number"
          min={1}
          max={100}
          value={maxTurns}
          onChange={(e) => setMaxTurns(Math.max(1, Math.min(100, parseInt(e.target.value) || 10)))}
        />
        <p className="text-xs text-muted-foreground">
          Maximum number of back-and-forth iterations before the agent stops
        </p>
      </div>
    </div>
  )

  // ==================== Mobile: Sheet ====================

  if (isMobile) {
    const currentTabIndex = MOBILE_TABS.findIndex(t => t.id === activeTab)
    const isFirstTab = currentTabIndex <= 0
    const isLastTab = currentTabIndex >= MOBILE_TABS.length - 1

    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom" className="h-[90vh] rounded-t-2xl p-0 flex flex-col [&>button]:hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
            <div className="flex items-center gap-3">
              {!isFirstTab && (
                <button
                  onClick={() => setActiveTab(MOBILE_TABS[currentTabIndex - 1].id)}
                  className="p-1 -ml-1 rounded-md text-muted-foreground hover:text-foreground"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
              )}
              <SheetTitle className="text-base">
                {editAgent ? 'Edit Agent' : 'Create Agent'}
              </SheetTitle>
            </div>
            <button
              onClick={() => onOpenChange(false)}
              className="p-1 -mr-1 rounded-md text-muted-foreground hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Tab indicator */}
          <div className="flex items-center justify-center gap-2 py-3 border-b shrink-0">
            {MOBILE_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                  activeTab === tab.id
                    ? 'bg-accent-brand/15 text-accent-brand'
                    : 'text-muted-foreground'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {/* Generate section on identity tab only */}
            {activeTab === 'identity' && renderGenerateSection()}

            {activeTab === 'identity' && renderIdentityTab()}
            {activeTab === 'instructions' && renderInstructionsTab()}
            {activeTab === 'permissions' && renderPermissionsTab()}
          </div>

          {/* Footer */}
          <div className="shrink-0 border-t p-4 bg-background">
            {isLastTab ? (
              <Button
                onClick={handleSave}
                disabled={saving || !name.trim() || !!nameError}
                className="w-full h-11"
              >
                {saving ? 'Saving...' : editAgent ? 'Update' : 'Create'}
              </Button>
            ) : (
              <Button
                onClick={() => setActiveTab(MOBILE_TABS[currentTabIndex + 1].id)}
                className="w-full h-11"
              >
                Continue
              </Button>
            )}
          </div>
        </SheetContent>
      </Sheet>
    )
  }

  // ==================== Desktop: Dialog ====================

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editAgent ? 'Edit Agent' : 'Create Agent'}
          </DialogTitle>
        </DialogHeader>

        {/* AI Generate Section */}
        {renderGenerateSection()}

        {/* Tabbed Form */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="identity">Identity</TabsTrigger>
            <TabsTrigger value="instructions">Instructions</TabsTrigger>
            <TabsTrigger value="permissions">Permissions & Tools</TabsTrigger>
          </TabsList>

          <div className="mt-4">
            <TabsContent value="identity" className="mt-0">
              {renderIdentityTab()}
            </TabsContent>
            <TabsContent value="instructions" className="mt-0">
              {renderInstructionsTab()}
            </TabsContent>
            <TabsContent value="permissions" className="mt-0">
              {renderPermissionsTab()}
            </TabsContent>
          </div>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving || !name.trim() || !!nameError}>
            {saving ? 'Saving...' : editAgent ? 'Update' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
