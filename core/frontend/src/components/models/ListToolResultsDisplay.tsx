/**
 * ListToolResultsDisplay Component
 *
 * Displays results from list tools using a registry pattern.
 * Adding a new list tool = adding one entry to TOOL_REGISTRY.
 */

import React, { useState, useMemo, useEffect } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Zap,
  Image,
  Film,
  Mic2,
  Server,
  Cpu,
  FileText,
  Globe,
  Shapes,
  Square,
  RectangleHorizontal,
  Smartphone,
  FileCode2,
  ExternalLink,
  Database,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Terminal,
  BrainCircuit,
  Shield,
  Wrench,
  Settings2,
  BookOpen,
} from 'lucide-react'
import { Link } from '@tanstack/react-router'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { TypeBadge, getTypeIconColor } from '@/lib/type-badges'
import { useTheme } from '@/hooks/useTheme'
import useModelStore from '@/store/modelStore'
import { ModelIcon } from './ModelIcon'
import { ModelDetailsModal } from './ModelDetailsModal'
import { removeProviderPrefix } from '@/lib/model-utils'
import type { ModelCatalogEntry } from '@/types/models'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

// =============================================================================
// COMMON DISPLAY SCHEMA
// All tool data gets transformed to this format for rendering
// =============================================================================

interface DisplayItem {
  id: string
  title: string
  subtitle?: string
  icon?: LucideIcon | string  // LucideIcon component or URL string
  iconColor?: string
  framework?: 'react' | 'html' | 'svg' | 'markdown' | 'mermaid' | 'pdf' | 'docx' | 'ics' | 'csv' | 'xlsx'  // For sparks - renders framework-specific icon
  badges?: Array<{ label: string; color?: string }>
  metadata?: Array<{ label: string; value: string }>
}

interface DisplayData {
  items: DisplayItem[]
  count: number
  stats?: Array<{ label: string; value: string | number }>
}

// =============================================================================
// TOOL REGISTRY
// Each tool defines: icon, label, items key, and adapter function
// =============================================================================

interface ToolConfig {
  icon: LucideIcon
  label: string
  labelPlural: string
  itemsKey: string
  countKey: string
  pageUrl: string  // Link to the full page for this resource type
  adapter: (item: any) => DisplayItem
  stats?: (data: any) => Array<{ label: string; value: string | number }>
  // Custom renderer component for special displays (e.g., models with icons and modals)
  CustomRenderer?: React.ComponentType<{ rawData: any; isDark: boolean }>
}

// =============================================================================
// FRAMEWORK ICON COMPONENT (matches ArtifactsSidePanel)
// =============================================================================

const ReactAtomIcon = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.5">
    <ellipse cx="12" cy="12" rx="10" ry="4" className="opacity-60" />
    <ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)" className="opacity-60" />
    <ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(120 12 12)" className="opacity-60" />
    <circle cx="12" cy="12" r="2" fill="currentColor" />
  </svg>
)

// Framework config: icon component (color now from type-badges)
const FRAMEWORK_ICON_MAP: Record<string, 'react' | LucideIcon> = {
  react: 'react',
  html: Globe,
  svg: Shapes,
}

const getFrameworkIcon = (framework: string): 'react' | LucideIcon => {
  return FRAMEWORK_ICON_MAP[framework] || FileCode2
}

const getOrientationIcon = (orientation: string): LucideIcon | undefined => {
  switch (orientation) {
    case 'square': return Square
    case 'landscape': return RectangleHorizontal
    case 'portrait': return Smartphone
    default: return undefined
  }
}

// =============================================================================
// MODELS LIST RENDERER
// Custom renderer for list_available_models - uses ModelIcon and ModelDetailsModal
// =============================================================================

interface ModelsRawData {
  total_models: number
  capability_counts: { vision: number; tools: number; reasoning: number }
  models: Array<{
    id: string
    name: string
    provider: string
    context_length: number
    context_str: string
    supports_vision: boolean
    supports_tools: boolean
    supports_reasoning: boolean
  }>
}

const ModelsListRenderer = ({ rawData, isDark }: { rawData: ModelsRawData; isDark: boolean }) => {
  const { allModels, allModelsLoaded, fetchAllModels } = useModelStore()
  const [selectedModel, setSelectedModel] = useState<ModelCatalogEntry | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)

  // Ensure models are loaded for icon lookup
  useEffect(() => {
    if (!allModelsLoaded) {
      fetchAllModels()
    }
  }, [allModelsLoaded, fetchAllModels])

  // Create lookup map for model data (including icons)
  const modelLookup = useMemo(() => {
    const map = new Map<string, ModelCatalogEntry>()
    allModels.forEach(m => map.set(m.model_id, m))
    return map
  }, [allModels])

  const handleModelClick = (modelId: string) => {
    const fullModel = modelLookup.get(modelId)
    if (fullModel) {
      setSelectedModel(fullModel)
      setIsModalOpen(true)
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {rawData.models.map((model) => {
          const fullModel = modelLookup.get(model.id)

          return (
            <button
              key={model.id}
              onClick={() => handleModelClick(model.id)}
              className={cn(
                "flex items-center gap-2.5 p-2 rounded-lg text-left transition-colors",
                isDark
                  ? "bg-muted/20 hover:bg-muted/40"
                  : "bg-slate-50 hover:bg-slate-100"
              )}
            >
              {/* Model Icon - use full model data if available, fallback to generic */}
              {fullModel ? (
                <ModelIcon
                  modelName={fullModel.name}
                  modelId={fullModel.model_id}
                  provider={fullModel.provider}
                  modelIconSlug={fullModel.model_icon_slug}
                  modelIconUrl={fullModel.model_icon_url}
                  providerIconSlug={fullModel.provider_icon_slug}
                  providerIconUrl={fullModel.provider_icon_url}
                  size={24}
                  showTooltip={false}
                />
              ) : (
                <div className={cn(
                  "w-6 h-6 rounded flex items-center justify-center flex-shrink-0",
                  isDark ? "bg-muted/30" : "bg-slate-200"
                )}>
                  <Cpu className="w-3.5 h-3.5 text-muted-foreground" />
                </div>
              )}

              {/* Model Info */}
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate">{model.name}</div>
                <div className="text-[10px] text-muted-foreground truncate">
                  {model.provider} · {model.context_str}
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {/* Model Details Modal */}
      <ModelDetailsModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        model={selectedModel}
      />
    </>
  )
}

// =============================================================================
// COMPARE MODELS RENDERER
// Custom renderer for compare_models - shows ranked models with scores
// =============================================================================

interface CompareModelsRawData {
  total_compared: number
  preset: string
  weights: Record<string, number>
  models: Array<{
    id: string
    name: string
    provider: string
    score: number
    score_pct: number
    breakdown: {
      cost: number
      context: number
      capabilities: number
      multimodality: number
      availability: number
    }
    cost_per_1k: number
    context_str: string
    capabilities: string[]
    is_best?: boolean
  }>
  best_model: {
    id: string
    name: string
    provider: string
    score_pct: number
    cost_per_1k: number
    context_str: string
  } | null
}

const PRESET_LABELS: Record<string, string> = {
  balanced: 'Balanced',
  budget: 'Budget',
  long_context: 'Long Context',
  tool_use: 'Tool Use',
  multimodal: 'Multimodal',
  coding: 'Coding',
}

const CompareModelsRenderer = ({ rawData, isDark }: { rawData: CompareModelsRawData; isDark: boolean }) => {
  const { allModels, allModelsLoaded, fetchAllModels } = useModelStore()
  const [selectedModel, setSelectedModel] = useState<ModelCatalogEntry | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)

  // Ensure models are loaded for icon lookup
  useEffect(() => {
    if (!allModelsLoaded) {
      fetchAllModels()
    }
  }, [allModelsLoaded, fetchAllModels])

  // Create lookup map for model data (including icons)
  const modelLookup = useMemo(() => {
    const map = new Map<string, ModelCatalogEntry>()
    allModels.forEach(m => map.set(m.model_id, m))
    return map
  }, [allModels])

  const handleModelClick = (modelId: string) => {
    const fullModel = modelLookup.get(modelId)
    if (fullModel) {
      setSelectedModel(fullModel)
      setIsModalOpen(true)
    }
  }

  // Get max score for relative bar widths
  const maxScore = Math.max(...rawData.models.map(m => m.score_pct), 1)

  return (
    <>
      {/* Preset badge */}
      <div className="flex items-center gap-2 mb-3">
        <span className={cn(
          "text-[10px] px-2 py-0.5 rounded-full",
          isDark ? "bg-accent-brand/20 text-accent-brand" : "bg-brand-100 text-brand-700"
        )}>
          {PRESET_LABELS[rawData.preset] || rawData.preset} preset
        </span>
        <span className="text-[10px] text-muted-foreground">
          {rawData.total_compared} models compared
        </span>
      </div>

      {/* Model cards */}
      <div className="space-y-2">
        {rawData.models.map((model, index) => {
          const fullModel = modelLookup.get(model.id)
          const rank = index + 1

          return (
            <button
              key={model.id}
              onClick={() => handleModelClick(model.id)}
              className={cn(
                "w-full text-left rounded-lg p-3 transition-all",
                model.is_best
                  ? isDark
                    ? "bg-accent-brand/10 border border-accent-brand/30 hover:bg-accent-brand/20"
                    : "bg-brand-50 border border-brand-200 hover:bg-brand-100"
                  : isDark
                    ? "bg-muted/20 hover:bg-muted/40"
                    : "bg-slate-50 hover:bg-slate-100"
              )}
            >
              <div className="flex items-start gap-3">
                {/* Rank badge */}
                <div className={cn(
                  "flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold",
                  rank === 1
                    ? "bg-yellow-500/20 text-yellow-600"
                    : rank === 2
                      ? "bg-slate-300/30 text-slate-500"
                      : rank === 3
                        ? "bg-orange-500/20 text-orange-600"
                        : isDark
                          ? "bg-muted/30 text-muted-foreground"
                          : "bg-slate-200 text-slate-500"
                )}>
                  {rank}
                </div>

                {/* Model Icon */}
                <div className="flex-shrink-0">
                  {fullModel ? (
                    <ModelIcon
                      modelName={fullModel.name}
                      modelId={fullModel.model_id}
                      provider={fullModel.provider}
                      modelIconSlug={fullModel.model_icon_slug}
                      modelIconUrl={fullModel.model_icon_url}
                      providerIconSlug={fullModel.provider_icon_slug}
                      providerIconUrl={fullModel.provider_icon_url}
                      size={28}
                      showTooltip={false}
                    />
                  ) : (
                    <div className={cn(
                      "w-7 h-7 rounded flex items-center justify-center",
                      isDark ? "bg-muted/30" : "bg-slate-200"
                    )}>
                      <Cpu className="w-4 h-4 text-muted-foreground" />
                    </div>
                  )}
                </div>

                {/* Model Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{removeProviderPrefix(model.name, model.provider)}</span>
                    {model.is_best && (
                      <span className={cn(
                        "text-[9px] px-1.5 py-0.5 rounded-full font-medium",
                        isDark ? "bg-accent-brand/30 text-accent-brand" : "bg-brand-200 text-brand-800"
                      )}>
                        BEST MATCH
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">
                    {model.provider} · {model.context_str} · ${model.cost_per_1k.toFixed(2)}/1M
                  </div>

                  {/* Score bar */}
                  <div className="mt-2 flex items-center gap-2">
                    <div className={cn(
                      "flex-1 h-1.5 rounded-full overflow-hidden",
                      isDark ? "bg-muted/30" : "bg-slate-200"
                    )}>
                      <div
                        className={cn(
                          "h-full rounded-full transition-all",
                          model.is_best
                            ? "bg-accent-brand"
                            : isDark ? "bg-muted-foreground/50" : "bg-slate-400"
                        )}
                        style={{ width: `${(model.score_pct / maxScore) * 100}%` }}
                      />
                    </div>
                    <span className={cn(
                      "text-[10px] font-medium tabular-nums w-10 text-right",
                      model.is_best
                        ? "text-accent-brand"
                        : "text-muted-foreground"
                    )}>
                      {model.score_pct.toFixed(1)}%
                    </span>
                  </div>
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {/* Model Details Modal */}
      <ModelDetailsModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        model={selectedModel}
      />
    </>
  )
}


const getStatusIcon = (status: string) => {
  switch (status?.toLowerCase()) {
    case 'ready':
    case 'processed':
      return { Icon: CheckCircle2, color: 'text-emerald-500' }
    case 'processing':
      return { Icon: Loader2, color: 'text-amber-500' }
    case 'error':
    case 'failed':
      return { Icon: AlertCircle, color: 'text-red-500' }
    default:
      return { Icon: Clock, color: 'text-muted-foreground' }
  }
}

// =============================================================================
// KNOWLEDGE BASE DOCUMENTS RENDERER
// Custom renderer for list_knowledge_base_documents - matches KnowledgeBaseResultsDisplay style
// =============================================================================

interface KnowledgeBaseDocument {
  id: string
  filename: string
  type: string
  status?: string
  size_kb?: number
  size_bytes?: number
  chunk_count?: number
  created_at?: string
  updated_at?: string
}

interface KnowledgeBaseDocumentsRawData {
  total_documents: number
  total_size_bytes?: number
  documents: KnowledgeBaseDocument[]
}

const KnowledgeBaseDocumentsRenderer = ({ rawData, isDark }: { rawData: KnowledgeBaseDocumentsRawData; isDark: boolean }) => {
  const formatSize = (sizeKb?: number, sizeBytes?: number): string => {
    if (sizeKb) return `${sizeKb.toFixed(0)} KB`
    if (sizeBytes) {
      if (sizeBytes < 1024) return `${sizeBytes} B`
      if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`
      return `${(sizeBytes / (1024 * 1024)).toFixed(2)} MB`
    }
    return ''
  }

  const formatDate = (dateStr?: string): string => {
    if (!dateStr) return ''
    try {
      const date = new Date(dateStr)
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    } catch {
      return ''
    }
  }

  const totalSizeMb = rawData.total_size_bytes
    ? (rawData.total_size_bytes / (1024 * 1024)).toFixed(2)
    : null

  return (
    <div className={cn(
      "border rounded-lg overflow-hidden",
      isDark ? "border-border/60 bg-card/30" : "border-border bg-white"
    )}>
      {/* Header */}
      <div className={cn(
        "px-3 py-2 border-b flex items-center justify-between",
        isDark ? "bg-blue-500/10 border-border/50" : "bg-blue-50 border-blue-200"
      )}>
        <div className="flex items-center gap-2">
          <Database className={cn("w-4 h-4", isDark ? "text-blue-400" : "text-blue-600")} />
          <span className={cn("text-sm font-medium", isDark ? "text-blue-400" : "text-blue-700")}>
            {rawData.total_documents} document{rawData.total_documents !== 1 ? 's' : ''}
          </span>
        </div>
        {totalSizeMb && (
          <span className={cn("text-xs", isDark ? "text-muted-foreground/60" : "text-slate-500")}>
            {totalSizeMb} MB total
          </span>
        )}
      </div>

      {/* Documents list */}
      <div className="divide-y divide-border/50 max-h-[350px] overflow-y-auto">
        {rawData.documents.map((doc, index) => {
          const { Icon: StatusIcon, color: statusColor } = getStatusIcon(doc.status || '')
          const size = formatSize(doc.size_kb, doc.size_bytes)
          const date = formatDate(doc.created_at)

          return (
            <div
              key={doc.id || index}
              className={cn(
                "px-3 py-2.5 transition-colors",
                isDark ? "hover:bg-muted/20" : "hover:bg-slate-50"
              )}
            >
              <div className="flex items-start gap-2.5">
                {/* File type badge */}
                <TypeBadge type={doc.type || '?'} className="flex-shrink-0 mt-0.5" />

                {/* Document info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      "text-sm font-medium truncate",
                      isDark ? "text-foreground" : "text-slate-800"
                    )}>
                      {doc.filename}
                    </span>

                    {/* Status icon */}
                    {doc.status && (
                      <StatusIcon className={cn("w-3.5 h-3.5 flex-shrink-0", statusColor)} />
                    )}
                  </div>

                  {/* Metadata row */}
                  <div className={cn(
                    "mt-1 flex items-center gap-3 text-[10px]",
                    isDark ? "text-muted-foreground/60" : "text-slate-500"
                  )}>
                    {size && (
                      <span>{size}</span>
                    )}
                    {doc.chunk_count !== undefined && doc.chunk_count > 0 && (
                      <span>{doc.chunk_count} chunk{doc.chunk_count !== 1 ? 's' : ''}</span>
                    )}
                    {date && (
                      <span>{date}</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// =============================================================================
// CODING AGENTS LIST RENDERER
// Custom renderer for list_coding_agents - shows agents with tier, tools, status
// =============================================================================

const TIER_CONFIG: Record<string, { label: string; color: string; darkColor: string }> = {
  fast: { label: 'Fast', color: 'bg-amber-100 text-amber-700', darkColor: 'bg-amber-500/20 text-amber-400' },
  balanced: { label: 'Balanced', color: 'bg-blue-100 text-blue-700', darkColor: 'bg-blue-500/20 text-blue-400' },
  powerful: { label: 'Powerful', color: 'bg-purple-100 text-purple-700', darkColor: 'bg-purple-500/20 text-purple-400' },
  inherit: { label: 'Inherit', color: 'bg-slate-100 text-slate-600', darkColor: 'bg-slate-500/20 text-slate-400' },
}

const PERMISSION_LABELS: Record<string, string> = {
  default: 'Default',
  plan: 'Plan Only',
  autoEdit: 'Auto Edit',
  fullAuto: 'Full Auto',
}

interface CodingAgentsRawData {
  total_agents: number
  active_count: number
  agents: Array<{
    id: string
    name: string
    description: string
    model_tier: string
    tools: string[]
    disallowed_tools: string[]
    max_turns: number
    permission_mode: string
    is_active: boolean
    updated_at: string | null
  }>
}

const CodingAgentsListRenderer = ({ rawData, isDark }: { rawData: CodingAgentsRawData; isDark: boolean }) => {
  return (
    <div className="space-y-2">
      {rawData.agents.map((agent) => {
        const tier = TIER_CONFIG[agent.model_tier] || TIER_CONFIG.balanced

        return (
          <div
            key={agent.id}
            className={cn(
              "rounded-lg p-3 transition-colors",
              agent.is_active
                ? isDark
                  ? "bg-muted/20 hover:bg-muted/40"
                  : "bg-slate-50 hover:bg-slate-100"
                : isDark
                  ? "bg-muted/10 opacity-60"
                  : "bg-slate-50/60 opacity-60"
            )}
          >
            {/* Header: name + status + tier */}
            <div className="flex items-center gap-2">
              <BrainCircuit className={cn("w-4 h-4 flex-shrink-0", isDark ? "text-accent-brand" : "text-brand-600")} />
              <span className="text-sm font-medium truncate flex-1">{agent.name}</span>
              <span className={cn(
                "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                isDark ? tier.darkColor : tier.color
              )}>
                {tier.label}
              </span>
              {!agent.is_active && (
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded-full",
                  isDark ? "bg-red-500/20 text-red-400" : "bg-red-100 text-red-600"
                )}>
                  Inactive
                </span>
              )}
            </div>

            {/* Description */}
            {agent.description && (
              <p className={cn(
                "text-[11px] mt-1 ml-6 truncate",
                isDark ? "text-muted-foreground/60" : "text-slate-500"
              )}>
                {agent.description}
              </p>
            )}

            {/* Metadata row: tools, permissions, max_turns */}
            <div className={cn(
              "flex items-center gap-3 mt-2 ml-6 text-[10px] flex-wrap",
              isDark ? "text-muted-foreground/50" : "text-slate-400"
            )}>
              {agent.tools.length > 0 && (
                <span className="flex items-center gap-1">
                  <Wrench className="w-3 h-3" />
                  {agent.tools.length} tool{agent.tools.length !== 1 ? 's' : ''}
                </span>
              )}
              <span className="flex items-center gap-1">
                <Shield className="w-3 h-3" />
                {PERMISSION_LABELS[agent.permission_mode] || agent.permission_mode}
              </span>
              <span>
                {agent.max_turns} turns
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// =============================================================================
// UPDATE CODING AGENT RENDERER
// Custom renderer for update_coding_agent - shows what changed
// =============================================================================

interface UpdateCodingAgentRawData {
  success: boolean
  agent: {
    id: string
    name: string
    description: string
    model_tier: string
    tools: string[]
    disallowed_tools: string[]
    max_turns: number
    permission_mode: string
    is_active: boolean
  }
  changes: string[]
  error?: string
}

const UpdateCodingAgentRenderer = ({ rawData, isDark }: { rawData: UpdateCodingAgentRawData; isDark: boolean }) => {
  if (!rawData.success) {
    return (
      <div className={cn(
        "rounded-lg p-3",
        isDark ? "bg-red-500/10 border border-red-500/30" : "bg-red-50 border border-red-200"
      )}>
        <span className={cn("text-xs", isDark ? "text-red-400" : "text-red-600")}>
          {rawData.error || 'Update failed'}
        </span>
      </div>
    )
  }

  const agent = rawData.agent
  const tier = TIER_CONFIG[agent.model_tier] || TIER_CONFIG.balanced

  return (
    <div className={cn(
      "rounded-lg p-3 border",
      isDark
        ? "bg-accent-brand/5 border-accent-brand/20"
        : "bg-brand-50/50 border-brand-200"
    )}>
      {/* Agent header */}
      <div className="flex items-center gap-2">
        <Terminal className={cn("w-4 h-4 flex-shrink-0", isDark ? "text-accent-brand" : "text-brand-600")} />
        <span className="text-sm font-medium">{agent.name}</span>
        <span className={cn(
          "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
          isDark ? tier.darkColor : tier.color
        )}>
          {tier.label}
        </span>
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 ml-auto flex-shrink-0" />
      </div>

      {/* Changes list */}
      {rawData.changes.length > 0 && (
        <div className={cn("mt-2 ml-6 space-y-0.5", isDark ? "text-muted-foreground/70" : "text-slate-600")}>
          {rawData.changes.map((change, i) => (
            <div key={i} className="text-[11px] flex items-start gap-1.5">
              <Settings2 className="w-3 h-3 mt-0.5 flex-shrink-0 text-muted-foreground/40" />
              <span>{change}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const TOOL_REGISTRY: Record<string, ToolConfig> = {
  list_sparks: {
    icon: Zap,
    label: 'spark',
    labelPlural: 'sparks',
    itemsKey: 'sparks',
    countKey: 'total_sparks',
    pageUrl: '/creations?tab=sparks',
    adapter: (item) => ({
      id: item.id,
      title: item.title,
      framework: item.framework,  // Renderer will show framework-specific icon
      badges: [
        ...(item.version > 1 ? [{ label: `v${item.version}` }] : []),
        ...(item.notable_deps?.includes('recharts') ? [{ label: 'Charts', color: 'text-emerald-500' }] : []),
      ],
      metadata: item.created_at ? [{ label: 'Created', value: item.created_at }] : undefined,
    }),
    stats: (data) => {
      const fb = data.framework_breakdown
      if (!fb) return []
      const stats: Array<{ label: string; value: string | number }> = []
      if (fb.react) stats.push({ label: 'React', value: fb.react })
      if (fb.html) stats.push({ label: 'HTML', value: fb.html })
      if (fb.svg) stats.push({ label: 'SVG', value: fb.svg })
      return stats
    },
  },

  list_generated_images: {
    icon: Image,
    label: 'image',
    labelPlural: 'images',
    itemsKey: 'images',
    countKey: 'total_images',
    pageUrl: '/creations?tab=images',
    adapter: (item) => ({
      id: item.id,
      title: item.filename,
      subtitle: item.prompt ? `"${item.prompt}"` : undefined,
      icon: item.orientation ? getOrientationIcon(item.orientation) : undefined,
      badges: item.dimensions ? [{ label: item.dimensions }] : [],
      metadata: [
        ...(item.size_kb ? [{ label: 'Size', value: `${item.size_kb.toFixed(0)} KB` }] : []),
      ],
    }),
    stats: (data) => data.total_size_mb ? [{ label: 'Total', value: `${data.total_size_mb.toFixed(1)} MB` }] : [],
  },

  list_generated_videos: {
    icon: Film,
    label: 'video',
    labelPlural: 'videos',
    itemsKey: 'videos',
    countKey: 'total_videos',
    pageUrl: '/creations?tab=videos',
    adapter: (item) => ({
      id: item.id,
      title: item.filename,
      subtitle: item.prompt ? `"${item.prompt}"` : undefined,
      icon: Film,
      badges: [
        ...(item.duration_str ? [{ label: item.duration_str }] : []),
        ...(item.dimensions ? [{ label: item.dimensions }] : []),
      ],
      metadata: item.size_mb ? [{ label: 'Size', value: `${item.size_mb.toFixed(1)} MB` }] : undefined,
    }),
    stats: (data) => {
      const stats: Array<{ label: string; value: string | number }> = []
      if (data.total_size_mb) stats.push({ label: 'Total', value: `${data.total_size_mb.toFixed(1)} MB` })
      if (data.total_duration_seconds) {
        const secs = data.total_duration_seconds
        stats.push({ label: 'Runtime', value: secs < 60 ? `${secs.toFixed(0)}s` : `${(secs / 60).toFixed(1)}min` })
      }
      return stats
    },
  },

  list_voice_rooms: {
    icon: Mic2,
    label: 'voice room',
    labelPlural: 'voice rooms',
    itemsKey: 'rooms',
    countKey: 'total_rooms',
    pageUrl: '/voice-rooms',
    adapter: (item) => ({
      id: item.id,
      title: item.name,
      subtitle: item.description,
      icon: Mic2,
      iconColor: 'text-cyan-500',
      badges: [{ label: `${item.agent_count} agent${item.agent_count !== 1 ? 's' : ''}` }],
    }),
    stats: (data) => data.total_agents ? [{ label: 'Total agents', value: data.total_agents }] : [],
  },

  list_mcp_servers: {
    icon: Server,
    label: 'server',
    labelPlural: 'servers',
    itemsKey: 'servers',
    countKey: 'total_servers',
    pageUrl: '/connectors',
    adapter: (item) => ({
      id: item.id || item.name,
      title: item.name,
      subtitle: item.description,
      icon: item.icon_url || Server,
      badges: [
        ...(item.is_connected ? [{ label: 'Connected', color: 'text-emerald-500' }] : []),
        ...(item.is_official ? [{ label: 'Official', color: 'text-blue-500' }] : []),
      ],
    }),
    stats: (data) => data.connected_count !== undefined ? [{ label: 'Connected', value: data.connected_count }] : [],
  },

  list_available_models: {
    icon: Cpu,
    label: 'model',
    labelPlural: 'models',
    itemsKey: 'models',
    countKey: 'total_models',
    pageUrl: '/models',
    CustomRenderer: ModelsListRenderer,
    adapter: (item) => ({
      id: item.id || item.name,
      title: item.name,
      subtitle: item.provider,
      icon: Cpu,
    }),
    stats: (data) => {
      const stats: Array<{ label: string; value: string | number }> = []
      const caps = data.capability_counts
      if (caps) {
        if (caps.vision) stats.push({ label: 'vision', value: caps.vision })
        if (caps.tools) stats.push({ label: 'tools', value: caps.tools })
        if (caps.reasoning) stats.push({ label: 'reasoning', value: caps.reasoning })
      }
      return stats
    },
  },

  compare_models: {
    icon: Cpu,
    label: 'model',
    labelPlural: 'models',
    itemsKey: 'models',
    countKey: 'total_compared',
    pageUrl: '/models',
    CustomRenderer: CompareModelsRenderer,
    adapter: (item) => ({
      id: item.id || item.name,
      title: item.name,
      subtitle: `${item.provider} - ${item.score_pct?.toFixed(1) || 0}%`,
      icon: Cpu,
    }),
    stats: (data) => {
      const stats: Array<{ label: string; value: string | number }> = []
      if (data.preset_label) {
        stats.push({ label: 'preset', value: data.preset_label })
      }
      if (data.best_model?.name) {
        stats.push({ label: 'best', value: data.best_model.name })
      }
      return stats
    },
  },

  list_knowledge_base_documents: {
    icon: FileText,
    label: 'document',
    labelPlural: 'documents',
    itemsKey: 'documents',
    countKey: 'total_documents',
    pageUrl: '/knowledge',
    CustomRenderer: KnowledgeBaseDocumentsRenderer,
    adapter: (item) => ({
      id: item.id || item.filename,
      title: item.filename,
      icon: FileText,
      badges: item.type ? [{ label: item.type.toUpperCase() }] : [],
      metadata: item.size_kb ? [{ label: 'Size', value: `${item.size_kb.toFixed(0)} KB` }] : undefined,
    }),
    stats: (data) => {
      if (!data.total_size_bytes) return []
      const mb = data.total_size_bytes / (1024 * 1024)
      return [{ label: 'Total', value: `${mb.toFixed(2)} MB` }]
    },
  },

  list_coding_agents: {
    icon: BrainCircuit,
    label: 'agent',
    labelPlural: 'agents',
    itemsKey: 'agents',
    countKey: 'total_agents',
    pageUrl: '/agents',
    CustomRenderer: CodingAgentsListRenderer,
    adapter: (item) => ({
      id: item.id,
      title: item.name,
      subtitle: item.description,
      icon: BrainCircuit,
      badges: [
        { label: (TIER_CONFIG[item.model_tier] || TIER_CONFIG.balanced).label },
        ...(!item.is_active ? [{ label: 'Inactive', color: 'text-red-500' }] : []),
      ],
      metadata: item.tools?.length > 0
        ? [{ label: 'Tools', value: `${item.tools.length}` }]
        : undefined,
    }),
    stats: (data) => {
      const stats: Array<{ label: string; value: string | number }> = []
      if (data.active_count !== undefined) {
        stats.push({ label: 'active', value: data.active_count })
      }
      return stats
    },
  },

  update_coding_agent: {
    icon: BrainCircuit,
    label: 'change',
    labelPlural: 'changes',
    itemsKey: 'changes',
    countKey: 'total_changes',
    pageUrl: '/agents',
    CustomRenderer: UpdateCodingAgentRenderer,
    adapter: (item) => ({
      id: String(Math.random()),
      title: typeof item === 'string' ? item : 'Change applied',
    }),
    stats: (data) => {
      if (data.agent?.name) {
        return [{ label: 'agent', value: data.agent.name }]
      }
      return []
    },
  },

}

// =============================================================================
// PUBLIC API
// =============================================================================

export const LIST_TOOL_NAMES = Object.keys(TOOL_REGISTRY)

export const isListToolName = (toolName: string): boolean => {
  return toolName in TOOL_REGISTRY
}

export interface ListToolData {
  toolName: string
  displayData: DisplayData
  config: ToolConfig
  rawData?: any  // Raw data for custom renderers
}

export const extractListToolData = (toolName: string, executionResult: any): ListToolData | null => {
  const config = TOOL_REGISTRY[toolName]
  if (!config) return null

  // Unwrap nested result
  let result = executionResult
  if (result && typeof result === 'object' && 'result' in result) {
    result = result.result
  }
  if (typeof result === 'string') {
    try { result = JSON.parse(result) } catch { return null }
  }
  if (!result || typeof result !== 'object') return null

  // Extract items using config
  const items = result[config.itemsKey] || []
  const count = result[config.countKey] || items.length

  if (items.length === 0 && count === 0) return null

  // Transform items using adapter
  const displayItems: DisplayItem[] = items.map((item: any) => {
    try {
      return config.adapter(item)
    } catch {
      return { id: String(Math.random()), title: 'Unknown item' }
    }
  })

  // Extract stats if defined
  const stats = config.stats?.(result) || []

  return {
    toolName,
    config,
    rawData: config.CustomRenderer ? result : undefined,  // Pass raw data only if custom renderer exists
    displayData: {
      items: displayItems,
      count,
      stats,
    },
  }
}

// =============================================================================
// GENERIC ITEM RENDERER
// =============================================================================

interface DisplayItemRowProps {
  item: DisplayItem
  isDark: boolean
}

const DisplayItemRow = React.memo(({ item, isDark }: DisplayItemRowProps) => {
  // Render icon - could be framework, LucideIcon, or URL string
  const renderIcon = () => {
    // Framework-specific icons (for sparks)
    if (item.framework) {
      const icon = getFrameworkIcon(item.framework)
      const color = getTypeIconColor(item.framework)
      if (icon === 'react') {
        return <ReactAtomIcon className={cn("w-3.5 h-3.5", color)} />
      }
      const Icon = icon
      return <Icon className={cn("w-3.5 h-3.5", color)} />
    }

    if (!item.icon) return null

    if (typeof item.icon === 'string') {
      // URL string - render as img
      return (
        <img
          src={item.icon}
          alt=""
          className="w-4 h-4 object-contain"
          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
      )
    }

    // LucideIcon component
    const Icon = item.icon
    return <Icon className={cn("w-3.5 h-3.5", item.iconColor || "text-muted-foreground")} />
  }

  return (
    <div className="py-1.5">
      <div className="flex items-center gap-2">
        {renderIcon()}
        <span className="text-xs font-medium truncate flex-1">{item.title}</span>
        {item.badges?.map((badge, i) => (
          <span
            key={i}
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded",
              badge.color || (isDark ? "bg-muted/50 text-muted-foreground" : "bg-slate-100 text-slate-500")
            )}
          >
            {badge.label}
          </span>
        ))}
      </div>
      {item.subtitle && (
        <p className={cn(
          "text-[10px] mt-0.5 truncate",
          item.icon ? "pl-5" : "",
          isDark ? "text-muted-foreground/50" : "text-slate-400"
        )}>
          {item.subtitle}
        </p>
      )}
    </div>
  )
})

DisplayItemRow.displayName = 'DisplayItemRow'

// =============================================================================
// MAIN COMPONENT
// =============================================================================

interface ListToolResultsDisplayProps {
  data: ListToolData
  className?: string
}

export const ListToolResultsDisplay = React.memo(({
  data,
  className,
}: ListToolResultsDisplayProps) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const { isDark } = useTheme()

  const { config, displayData, rawData } = data
  const CustomRenderer = config.CustomRenderer

  if (!displayData.items || displayData.items.length === 0) return null

  const label = displayData.count === 1 ? config.label : config.labelPlural

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className={cn("ml-5 mt-1", className)}>
      {/* Header - clickable to expand */}
      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground/40">|</span>
        <CollapsibleTrigger
          className={cn(
            "flex items-center gap-1.5 text-xs transition-colors",
            isDark ? "text-muted-foreground hover:text-foreground" : "text-slate-500 hover:text-slate-700"
          )}
        >
          <ChevronRight className={cn(
            "w-3 h-3 transition-transform duration-200",
            isExpanded && "rotate-90"
          )} />
          <span>{displayData.count} {label}</span>
          {displayData.stats && displayData.stats.length > 0 && (
            <span className={cn("text-[10px]", isDark ? "text-muted-foreground/50" : "text-slate-400")}>
              ({displayData.stats.map(s => `${s.value} ${s.label}`).join(', ')})
            </span>
          )}
        </CollapsibleTrigger>
        <Link
          to={config.pageUrl}
          className={cn(
            "flex items-center gap-1 text-[10px] transition-colors ml-1",
            isDark ? "text-muted-foreground/50 hover:text-accent-brand" : "text-slate-400 hover:text-accent-brand"
          )}
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink className="w-3 h-3" />
          <span>View all</span>
        </Link>
      </div>

      {/* Expanded content with animation */}
      <CollapsibleContent>
        <div className={cn(
          "mt-2 ml-2 pl-3 border-l max-h-[400px] overflow-y-auto",
          isDark ? "border-border/30" : "border-slate-200"
        )}>
          {CustomRenderer && rawData ? (
            <CustomRenderer rawData={rawData} isDark={isDark} />
          ) : (
            displayData.items.map((item) => (
              <DisplayItemRow key={item.id} item={item} isDark={isDark} />
            ))
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})

ListToolResultsDisplay.displayName = 'ListToolResultsDisplay'
