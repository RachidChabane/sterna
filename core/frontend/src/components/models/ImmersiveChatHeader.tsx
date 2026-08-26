import type { ReactNode } from 'react'
import {
  Minimize2,
  Plus,
  MoreVertical,
  Copy,
  Download,
  MessageSquarePlus,
  RefreshCw,
  Loader2,
  GalleryVerticalEnd,
  ScrollText,
  BookOpen,
  FileText,
  Braces,
  X,
  FolderGit2,
  Globe,
  PanelRight,
  Code2,
} from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from '@/components/ui/dropdown-menu'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'
import { cn } from '@/lib/utils'
import { removeProviderPrefix } from '@/lib/model-utils'
import { useNavigationStore } from '@/store/navigationStore'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import { useProjectPanelStore } from '@/store/projectPanelStore'
import { usePreviewPanelStore } from '@/store/previewPanelStore'
import { ModelComboBox } from './ModelComboBox'
import { ModelIcon } from './ModelIcon'
import type { Filters, Model } from './types'
import type { ModelCatalogEntry } from '@/types/models'

interface ImmersiveChatHeaderProps {
  model: Model | null
  models: ModelCatalogEntry[]
  onModelSelect: (model: Model) => void
  showFilters?: boolean
  onToggleFilters?: () => void
  hasActiveFilters?: boolean
  filters?: Filters
  onFiltersChange?: (filters: Filters) => void
  providers?: string[]
  recentModelIds?: string[]
  headerCenterContent?: ReactNode
  onAddChat?: () => void
  hasWorkspace: boolean
  onOpenCodeEditor: () => void
  sparksCount: number
  onRemoveChat?: () => void
  canRemoveChat?: boolean
  onOpenMobileModelSheet: () => void
  onOpenInstructions: () => void
  hasMessages: boolean
  onSaveToKnowledgeBase: () => void
  isSavingToKnowledgeBase: boolean
  onCopyResponses?: () => void
  onCopyMetadata?: () => void
  onExportResponses?: () => void
  onExportMetadata?: () => void
  onExitImmersive?: () => void
}

export function ImmersiveChatHeader({
  model,
  models,
  onModelSelect,
  showFilters,
  onToggleFilters,
  hasActiveFilters,
  filters,
  onFiltersChange,
  providers,
  recentModelIds,
  headerCenterContent,
  onAddChat,
  hasWorkspace,
  onOpenCodeEditor,
  sparksCount,
  onRemoveChat,
  canRemoveChat,
  onOpenMobileModelSheet,
  onOpenInstructions,
  hasMessages,
  onSaveToKnowledgeBase,
  isSavingToKnowledgeBase,
  onCopyResponses,
  onCopyMetadata,
  onExportResponses,
  onExportMetadata,
  onExitImmersive,
}: ImmersiveChatHeaderProps) {
  const { openMobileSidebar } = useNavigationStore()
  const { isPanelOpen: isArtifactsPanelOpen, imageCount, videoCount } = useArtifactsPanelStore()
  const { isPanelOpen: isProjectPanelOpen, openPanel: openProjectPanel, closePanel: closeProjectPanel } = useProjectPanelStore()
  const { isPanelOpen: isPreviewPanelOpen, openPanel: openPreviewPanel, closePanel: closePreviewPanel } = usePreviewPanelStore()
  const navigate = useNavigate()

  return (
    <header className="flex-shrink-0 sticky top-0 flex items-center justify-between px-3 md:px-4 py-2 border-b border-border/50 bg-background/95 backdrop-blur-sm z-10">
      {/* Left: Menu button (mobile) + Model selector */}
      <div className="flex items-center gap-1">
        {/* Mobile sidebar menu button */}
        <Button
          variant="ghost"
          size="sm"
          className="md:hidden h-8 w-8 p-0 shrink-0"
          onClick={openMobileSidebar}
        >
          <PremiumMenuIcon size={18} />
        </Button>
        <div className="hidden md:block min-w-[180px] max-w-[280px]">
          <ModelComboBox
            models={models}
            value={model?.model_id}
            onValueChange={(modelId) => {
              const found = models.find(m => m.model_id === modelId)
              if (found) onModelSelect(found as Model)
            }}
            showFilters={showFilters}
            onToggleFilters={onToggleFilters}
            hasActiveFilters={hasActiveFilters}
            filters={filters}
            onFiltersChange={onFiltersChange}
            providers={providers}
            recentModelIds={recentModelIds}
            variant="ghost"
          />
        </div>
        {/* Mobile: Tap to open model selection sheet (hidden in multi-chat mode - tabs show models) */}
        {!headerCenterContent && (
          <button
            onClick={onOpenMobileModelSheet}
            className="md:hidden flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-muted transition-colors max-w-[160px]"
          >
            {model ? (
              <>
                <ModelIcon
                  modelName={model.name}
                  modelId={model.model_id}
                  provider={model.provider}
                  modelIconSlug={model.model_icon_slug}
                  modelIconUrl={model.model_icon_url}
                  providerIconSlug={model.provider_icon_slug}
                  providerIconUrl={model.provider_icon_url}
                  size={20}
                  showTooltip={false}
                />
                <span className="text-sm font-medium truncate">
                  {removeProviderPrefix(model.name, model.provider)}
                </span>
              </>
            ) : (
              <span className="text-sm text-muted-foreground">Select model</span>
            )}
          </button>
        )}
      </div>

      {/* Center: Optional content (e.g., multi-chat tab bar) */}
      {headerCenterContent && (
        <div className="absolute left-1/2 -translate-x-1/2 max-w-[calc(100vw-200px)] md:max-w-[calc(100vw-400px)]">
          {headerCenterContent}
        </div>
      )}

      {/* Right: Actions */}
      <div className="flex items-center gap-1">
        {/* Add comparison chat - hidden on mobile, shown in menu instead */}
        {onAddChat && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onAddChat}
                  className="hidden md:flex h-8 px-2 text-muted-foreground hover:text-foreground"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  <span className="text-xs">Compare</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                Add another model to compare responses
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {/* Open IDE button - desktop only */}
        {hasWorkspace && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onOpenCodeEditor}
                  className="hidden md:flex h-8 px-2 text-muted-foreground hover:text-foreground"
                >
                  <Code2 className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Open IDE</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {/* Unified Panels popover */}
        {(() => {
          const totalArtifacts = sparksCount + imageCount + videoCount
          const openPanelCount = [isArtifactsPanelOpen, isProjectPanelOpen, isPreviewPanelOpen].filter(Boolean).length
          return (
            <Popover>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <PopoverTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className={cn(
                          "h-8 px-2 gap-1.5 relative",
                          openPanelCount > 0
                            ? "text-primary hover:text-primary/80"
                            : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        <PanelRight className="h-4 w-4" />
                        {openPanelCount > 0 && (
                          <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-primary" />
                        )}
                      </Button>
                    </PopoverTrigger>
                  </TooltipTrigger>
                  <TooltipContent>Panels</TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <PopoverContent align="end" className="w-52 p-1.5">
                <button
                  onClick={() => useArtifactsPanelStore.getState().setPanelOpen(!isArtifactsPanelOpen)}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
                    isArtifactsPanelOpen ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                  )}
                >
                  <GalleryVerticalEnd className={cn("h-4 w-4 shrink-0", isArtifactsPanelOpen ? "text-brand-500" : "text-muted-foreground")} />
                  <span className="flex-1 text-left">Creations</span>
                  {totalArtifacts > 0 && (
                    <span className="text-xs tabular-nums text-muted-foreground">{totalArtifacts}</span>
                  )}
                </button>
                <button
                  onClick={() => isProjectPanelOpen ? closeProjectPanel() : openProjectPanel()}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
                    isProjectPanelOpen ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                  )}
                >
                  <FolderGit2 className={cn("h-4 w-4 shrink-0", isProjectPanelOpen ? "text-blue-500" : "text-muted-foreground")} />
                  <span className="flex-1 text-left">Project</span>
                </button>
                <TooltipProvider delayDuration={300}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => isPreviewPanelOpen ? closePreviewPanel() : openPreviewPanel()}
                        className={cn(
                          "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
                          isPreviewPanelOpen ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                        )}
                      >
                        <Globe className={cn("h-4 w-4 shrink-0", isPreviewPanelOpen ? "text-green-500" : "text-muted-foreground")} />
                        <span className="flex-1 text-left">Dev Server</span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="left"><p>Live preview of running processes</p></TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </PopoverContent>
            </Popover>
          )
        })()}

        {/* More Options Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {/* Change model - mobile only since selector opens sheet */}
            <DropdownMenuItem
              onClick={onOpenMobileModelSheet}
              className="md:hidden"
            >
              <RefreshCw className="h-4 w-4 mr-2" /> Change model
            </DropdownMenuItem>
            {/* Compare models - mobile only, desktop has button */}
            {onAddChat && (
              <DropdownMenuItem
                onClick={onAddChat}
                className="md:hidden"
              >
                <Plus className="h-4 w-4 mr-2" /> Compare models
              </DropdownMenuItem>
            )}
            {/* Remove chat - mobile only, for multi-chat mode */}
            {onRemoveChat && canRemoveChat && (
              <DropdownMenuItem
                onClick={onRemoveChat}
                className="md:hidden text-destructive focus:text-destructive"
              >
                <X className="h-4 w-4 mr-2" /> Remove chat
              </DropdownMenuItem>
            )}
            {/* New conversation - mobile only */}
            <DropdownMenuItem
              onClick={() => navigate({ to: '/chats', search: { new: true } })}
              className="md:hidden"
            >
              <MessageSquarePlus className="h-4 w-4 mr-2" /> New conversation
            </DropdownMenuItem>
            <DropdownMenuSeparator className="md:hidden" />

            <DropdownMenuItem onClick={onOpenInstructions}>
              <ScrollText className="h-4 w-4 mr-2" /> Chat instructions
            </DropdownMenuItem>
            {hasWorkspace && (
              <DropdownMenuItem onClick={onOpenCodeEditor} className="md:hidden">
                <Code2 className="h-4 w-4 mr-2" /> Open IDE
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />

            {(onCopyResponses || onExportResponses) && (
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  <FileText className="h-4 w-4 mr-2" /> Responses
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent>
                  {onCopyResponses && (
                    <DropdownMenuItem onClick={onCopyResponses}>
                      <Copy className="h-4 w-4 mr-2" /> Copy
                    </DropdownMenuItem>
                  )}
                  {onExportResponses && (
                    <DropdownMenuItem onClick={onExportResponses}>
                      <Download className="h-4 w-4 mr-2" /> Export (.txt)
                    </DropdownMenuItem>
                  )}
                </DropdownMenuSubContent>
              </DropdownMenuSub>
            )}
            {(onCopyMetadata || onExportMetadata) && (
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  <Braces className="h-4 w-4 mr-2" /> Metadata
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent>
                  {onCopyMetadata && (
                    <DropdownMenuItem onClick={onCopyMetadata}>
                      <Copy className="h-4 w-4 mr-2" /> Copy (JSON)
                    </DropdownMenuItem>
                  )}
                  {onExportMetadata && (
                    <DropdownMenuItem onClick={onExportMetadata}>
                      <Download className="h-4 w-4 mr-2" /> Export (.json)
                    </DropdownMenuItem>
                  )}
                </DropdownMenuSubContent>
              </DropdownMenuSub>
            )}

            {/* Save to Knowledge Base */}
            {hasMessages && (
              <DropdownMenuItem
                onClick={onSaveToKnowledgeBase}
                disabled={isSavingToKnowledgeBase}
              >
                {isSavingToKnowledgeBase ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <BookOpen className="h-4 w-4 mr-2" />
                )}
                Save to knowledge base
              </DropdownMenuItem>
            )}

          </DropdownMenuContent>
        </DropdownMenu>

        {/* Exit immersive - hidden on mobile (mobile is always immersive) */}
        {onExitImmersive && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onExitImmersive}
                  className="hidden md:flex h-8 px-2 text-muted-foreground hover:text-foreground"
                >
                  <Minimize2 className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                Exit focus mode
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>
    </header>
  )
}
