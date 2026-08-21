import { useEffect, useState, useMemo } from 'react'
import { Plus, Upload, Terminal, ChevronRight, Settings2 } from 'lucide-react'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { useSubAgentStore } from '@/store/subAgentStore'
import { subAgentApi, modelPreferencesApi, type SubAgentSummary } from '@/api/subAgents'
import AgentCard from '@/components/agents/AgentCard'
import AgentFormDialog from '@/components/agents/AgentFormDialog'
import AgentPreviewDialog from '@/components/agents/AgentPreviewDialog'
import ImportAgentDialog from '@/components/agents/ImportAgentDialog'
import { ModelComboBox } from '@/components/models/ModelComboBox'
import type { Model } from '@/components/models/types'
import useModelStore from '@/store/modelStore'
import type { SubAgent } from '@/api/subAgents'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { useNavigationStore } from '@/store/navigationStore'
import { toast } from 'sonner'

/** Find the latest Anthropic model matching a keyword (haiku/sonnet/opus) from the catalog */
function findLatestAnthropicModel(allModels: { model_id: string }[], keyword: string): string {
  const matches = allModels.filter(m =>
    m.model_id.startsWith('anthropic/') && m.model_id.includes(keyword)
  )
  if (matches.length === 0) return ''
  // Sort descending so newest version comes first (e.g. claude-sonnet-4.5 > claude-sonnet-4)
  matches.sort((a, b) => b.model_id.localeCompare(a.model_id))
  return matches[0].model_id
}

export default function SubAgentsPage() {
  const { openMobileSidebar } = useNavigationStore()
  const {
    agents,
    agentsLoading,
    lastFetchTime,
    fetchAgents,
    getAgent,
    deleteAgent,
    toggleAgent,
  } = useSubAgentStore()

  const [formOpen, setFormOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewMarkdown, setPreviewMarkdown] = useState('')
  const [previewFilename, setPreviewFilename] = useState('')
  const [editAgent, setEditAgent] = useState<SubAgent | null>(null)
  const [tierOpen, setTierOpen] = useState(false)
  const [tierPrefs, setTierPrefs] = useState({ fast_model_id: '', balanced_model_id: '', powerful_model_id: '' })
  const [tierSaving, setTierSaving] = useState(false)

  const { allModels, allModelsLoaded, fetchAllModels } = useModelStore()
  const models = allModels as unknown as Model[]

  // Resolve dynamic defaults from the model catalog
  const dynamicDefaults = useMemo(() => ({
    fast_model_id: findLatestAnthropicModel(allModels, 'haiku'),
    balanced_model_id: findLatestAnthropicModel(allModels, 'sonnet'),
    powerful_model_id: findLatestAnthropicModel(allModels, 'opus'),
  }), [allModels])

  const hasData = lastFetchTime > 0
  const isLoading = agentsLoading || !hasData

  useEffect(() => {
    fetchAgents()
    fetchAllModels()
    modelPreferencesApi.get()
      .then(res => {
        setTierPrefs({
          fast_model_id: res.data.fast_model_id,
          balanced_model_id: res.data.balanced_model_id,
          powerful_model_id: res.data.powerful_model_id,
        })
      })
      .catch(() => {})
  }, [fetchAgents, fetchAllModels])

  // Use dynamic defaults when stored prefs are empty
  const resolvedPrefs = useMemo(() => ({
    fast_model_id: tierPrefs.fast_model_id || dynamicDefaults.fast_model_id,
    balanced_model_id: tierPrefs.balanced_model_id || dynamicDefaults.balanced_model_id,
    powerful_model_id: tierPrefs.powerful_model_id || dynamicDefaults.powerful_model_id,
  }), [tierPrefs, dynamicDefaults])

  const handleTierChange = async (tier: 'fast_model_id' | 'balanced_model_id' | 'powerful_model_id', modelId: string) => {
    const prev = tierPrefs[tier]
    setTierPrefs(p => ({ ...p, [tier]: modelId }))
    setTierSaving(true)
    try {
      await modelPreferencesApi.update({ [tier]: modelId })
    } catch {
      setTierPrefs(p => ({ ...p, [tier]: prev }))
    } finally {
      setTierSaving(false)
    }
  }

  const handleEdit = async (agent: SubAgentSummary) => {
    const full = await getAgent(agent.id)
    if (full) {
      setEditAgent(full)
      setFormOpen(true)
    }
  }

  const handleExport = async (agent: SubAgentSummary) => {
    try {
      const response = await subAgentApi.exportMd(agent.id)
      setPreviewMarkdown(response.data.markdown)
      setPreviewFilename(response.data.filename)
      setPreviewOpen(true)
    } catch {
      toast.error('Failed to export agent')
    }
  }

  const handleDelete = async (agent: SubAgentSummary) => {
    const success = await deleteAgent(agent.id)
    if (success) {
      toast.success(`Agent "${agent.name}" deleted`)
    }
  }

  const handleCreate = () => {
    setEditAgent(null)
    setFormOpen(true)
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Mobile header */}
      <div className="md:hidden flex items-center justify-between px-4 py-3 border-b">
        <button onClick={openMobileSidebar} className="p-2 -ml-2 text-foreground transition-colors">
          <PremiumMenuIcon size={18} />
        </button>
        <h1 className="text-base font-semibold">Coding Agents</h1>
        <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={handleCreate}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      {/* Desktop hero */}
      <div className="relative overflow-hidden border-b hidden md:block">
        <div className="absolute inset-0 bg-gradient-to-br from-accent-brand/[0.03] via-transparent to-purple-500/[0.02]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_120%,rgba(120,119,198,0.05),transparent)]" />

        <div className="relative max-w-6xl mx-auto px-6 py-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Coding Agents</h1>
              <p className="text-sm text-muted-foreground mt-0.5">
                Create custom sub-agents for your coding workflows
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                <Upload className="mr-1.5 h-3.5 w-3.5" />
                Import
              </Button>
              <Button variant="outline" size="sm" onClick={handleCreate} className="rounded-full text-brand-700 dark:text-brand-400 border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-800 dark:hover:text-brand-300">
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                Create Agent
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 pb-24 md:pb-8">
          {/* Model Tier Configuration */}
          <Collapsible open={tierOpen} onOpenChange={setTierOpen} className="mb-6 rounded-lg border bg-card">
            <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/50 transition-colors rounded-lg">
              <div className="flex items-center gap-2">
                <Settings2 className="h-4 w-4 text-muted-foreground" />
                <span>Model Tier Mapping</span>
              </div>
              <ChevronRight className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${tierOpen ? 'rotate-90' : ''}`} />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="border-t px-4 py-4 space-y-4">
                <p className="text-xs text-muted-foreground">
                  Configure which model each sub-agent tier resolves to.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-sm font-medium">Fast</Label>
                    <ModelComboBox
                      models={allModelsLoaded ? models : []}
                      value={resolvedPrefs.fast_model_id}
                      onValueChange={(id) => handleTierChange('fast_model_id', id)}
                      disabled={tierSaving}
                      variant="outline"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-sm font-medium">Balanced</Label>
                    <ModelComboBox
                      models={allModelsLoaded ? models : []}
                      value={resolvedPrefs.balanced_model_id}
                      onValueChange={(id) => handleTierChange('balanced_model_id', id)}
                      disabled={tierSaving}
                      variant="outline"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-sm font-medium">Powerful</Label>
                    <ModelComboBox
                      models={allModelsLoaded ? models : []}
                      value={resolvedPrefs.powerful_model_id}
                      onValueChange={(id) => handleTierChange('powerful_model_id', id)}
                      disabled={tierSaving}
                      variant="outline"
                    />
                  </div>
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent-brand border-t-transparent" />
            </div>
          ) : agents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-muted/50 mb-4">
                <Terminal className="h-8 w-8 text-muted-foreground/50" />
              </div>
              <h2 className="text-lg font-semibold">No agents yet</h2>
              <p className="mt-1 text-sm text-muted-foreground max-w-sm">
                Create custom sub-agents that get automatically deployed into your coding agent sandboxes.
              </p>
              <div className="flex gap-2 mt-4">
                <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                  <Upload className="mr-1.5 h-3.5 w-3.5" />
                  Import
                </Button>
                <Button size="sm" onClick={handleCreate}>
                  <Plus className="mr-1.5 h-3.5 w-3.5" />
                  Create your first agent
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {agents.map(agent => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  onEdit={handleEdit}
                  onExport={handleExport}
                  onDelete={handleDelete}
                  onToggle={() => toggleAgent(agent.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Mobile FAB */}
      <button
        className="md:hidden fixed bottom-20 right-4 z-20 flex h-14 w-14 items-center justify-center rounded-full bg-accent-brand text-white shadow-lg active:scale-95 transition-transform"
        onClick={handleCreate}
      >
        <Plus className="h-6 w-6" />
      </button>

      {/* Dialogs */}
      <AgentFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        editAgent={editAgent}
      />
      <AgentPreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        markdown={previewMarkdown}
        filename={previewFilename}
      />
      <ImportAgentDialog
        open={importOpen}
        onOpenChange={setImportOpen}
      />
    </div>
  )
}
