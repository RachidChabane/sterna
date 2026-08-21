/**
 * MentionAutocomplete Component
 *
 * Floating dropdown for @mention autocomplete of MCP servers and tools.
 * Appears when user types @ in the message input.
 *
 * Supports secondary pickers for coding agent tools:
 * - Issues picker (for @plan_implementation)
 * - Plans picker (for @implement_plan, @edit_plan)
 */

import { memo, useEffect, useRef, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/utils'
import { Globe, BookOpen, Terminal, CircleDot, ListTodo, Loader2, Github, Lock, ImageIcon, Video, Clapperboard, UserRound, BrainCircuit } from 'lucide-react'
import { CODING_AGENT_DISPLAY_NAMES, MEDIA_TOOL_DISPLAY_NAMES, type MentionItem, type MediaToolConfig } from '@/hooks/useMentionAutocomplete'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { MCPServer } from '@/api/mcp'

interface MentionAutocompleteProps {
  isOpen: boolean
  mode: 'servers' | 'tools' | 'issues' | 'plans' | 'repos' | 'image_params' | 'video_params'
  items: MentionItem[]
  activeIndex: number
  selectedServer: MCPServer | null
  inputRef: React.RefObject<HTMLTextAreaElement | null>
  triggerStart: number
  isLoadingSecondary?: boolean
  secondaryPickerTool?: string | null
  isCloningRepo?: boolean
  cloningRepoName?: string | null
  mediaConfig?: MediaToolConfig | null
  onMediaConfigChange?: (config: MediaToolConfig) => void
  onMediaConfigConfirm?: () => void
  onSelect: (item: MentionItem) => void
  onClose: () => void
}

/**
 * Get cursor pixel coordinates in a textarea
 * Uses a hidden mirror div to calculate position
 */
function getCursorCoordinates(
  textarea: HTMLTextAreaElement,
  position: number
): { x: number; y: number } {
  // Create mirror div
  const mirror = document.createElement('div')
  const style = getComputedStyle(textarea)

  // Copy relevant styles
  const properties = [
    'fontFamily', 'fontSize', 'fontWeight', 'fontStyle',
    'letterSpacing', 'textTransform', 'wordSpacing',
    'lineHeight', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
    'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
    'boxSizing', 'whiteSpace', 'wordWrap', 'overflowWrap'
  ]

  mirror.style.cssText = properties.map(p => `${p}:${style.getPropertyValue(p.replace(/([A-Z])/g, '-$1').toLowerCase())}`).join(';')
  mirror.style.position = 'absolute'
  mirror.style.top = '-9999px'
  mirror.style.left = '-9999px'
  mirror.style.width = `${textarea.clientWidth}px`
  mirror.style.height = 'auto'
  mirror.style.whiteSpace = 'pre-wrap'
  mirror.style.wordWrap = 'break-word'
  mirror.style.visibility = 'hidden'

  // Insert text and span at position
  const text = textarea.value.substring(0, position)
  const textNode = document.createTextNode(text)
  const span = document.createElement('span')
  span.textContent = '|'

  mirror.appendChild(textNode)
  mirror.appendChild(span)
  document.body.appendChild(mirror)

  // Get position relative to textarea
  const rect = textarea.getBoundingClientRect()
  const spanRect = span.getBoundingClientRect()
  const mirrorRect = mirror.getBoundingClientRect()

  // Calculate position
  const x = spanRect.left - mirrorRect.left + rect.left
  const y = spanRect.top - mirrorRect.top + rect.top - textarea.scrollTop

  // Cleanup
  document.body.removeChild(mirror)

  return { x, y }
}

function MentionAutocompleteComponent({
  isOpen,
  mode,
  items,
  activeIndex,
  selectedServer,
  inputRef,
  triggerStart,
  isLoadingSecondary,
  secondaryPickerTool,
  isCloningRepo,
  cloningRepoName,
  mediaConfig,
  onMediaConfigChange,
  onMediaConfigConfirm,
  onSelect,
  onClose
}: MentionAutocompleteProps) {
  const dropdownRef = useRef<HTMLDivElement>(null)
  const activeItemRef = useRef<HTMLDivElement>(null)

  // Calculate dropdown position
  const position = useMemo(() => {
    if (!isOpen || !inputRef.current) return { x: 0, y: 0 }
    return getCursorCoordinates(inputRef.current, triggerStart)
  }, [isOpen, inputRef, triggerStart])

  // Scroll active item into view
  useEffect(() => {
    if (activeItemRef.current && dropdownRef.current) {
      activeItemRef.current.scrollIntoView({
        block: 'nearest',
        behavior: 'smooth'
      })
    }
  }, [activeIndex])

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(target) &&
        inputRef.current &&
        !inputRef.current.contains(target)
      ) {
        // Don't close if clicking inside a Radix Select portal (model dropdown)
        const radixContent = (target as Element).closest?.('[data-radix-popper-content-wrapper]')
        if (radixContent) return

        onClose()
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen, onClose, inputRef])

  if (!isOpen) return null

  // Show loading or empty states for secondary pickers
  const isMediaParamMode = mode === 'image_params' || mode === 'video_params'
  const isSecondaryMode = mode === 'issues' || mode === 'plans' || mode === 'repos'
  const showItems = !isLoadingSecondary && items.length > 0
  const showEmpty = !isLoadingSecondary && items.length === 0 && isSecondaryMode
  const showLoading = isLoadingSecondary && (isSecondaryMode || isMediaParamMode)

  // Non-secondary modes with no items: hide (but keep open for media param modes)
  if (!isSecondaryMode && !isMediaParamMode && items.length === 0) return null

  const heading = (() => {
    switch (mode) {
      case 'image_params': return 'Image Settings'
      case 'video_params': return 'Video Settings'
      case 'issues': return 'Select Issue'
      case 'plans': return 'Select Plan'
      case 'repos': return 'Select Repository'
      case 'tools': return `${selectedServer?.name || 'Server'} Tools`
      default: return 'Connectors'
    }
  })()

  // Position dropdown above the cursor (bottom-up)
  const viewportHeight = typeof window !== 'undefined' ? window.innerHeight : 800
  const bottomOffset = viewportHeight - position.y + 8

  const renderItemIcon = (item: MentionItem) => {
    if (item.type === 'repo') {
      return item.repoIsPrivate
        ? <Lock className="h-3.5 w-3.5 text-muted-foreground" />
        : <Github className="h-3.5 w-3.5 text-muted-foreground" />
    }
    if (item.type === 'issue') {
      return <CircleDot className="h-3.5 w-3.5 text-green-500" />
    }
    if (item.type === 'plan') {
      return <ListTodo className="h-3.5 w-3.5 text-accent-brand" />
    }
    if (item.type === 'knowledge_base') {
      return <BookOpen className="h-3.5 w-3.5 text-emerald-500" />
    }
    if (item.type === 'coding_agent') {
      return <Terminal className="h-3.5 w-3.5 text-accent-brand" />
    }
    if (item.type === 'sub_agent') {
      return <BrainCircuit className="h-3.5 w-3.5 text-accent-brand" />
    }
    if (item.type === 'media_tool') {
      const iconMap: Record<string, React.ReactNode> = {
        generate_image: <ImageIcon className="h-3.5 w-3.5 text-purple-500" />,
        generate_video: <Video className="h-3.5 w-3.5 text-purple-500" />,
        animate_image: <Clapperboard className="h-3.5 w-3.5 text-purple-500" />,
        animate_character: <UserRound className="h-3.5 w-3.5 text-purple-500" />,
      }
      return iconMap[item.name] || <Video className="h-3.5 w-3.5 text-purple-500" />
    }
    if (item.icon) {
      return <img src={item.icon} alt="" className="w-4 h-4 object-contain" />
    }
    return <Globe className="h-3.5 w-3.5 text-blue-500" />
  }

  const renderItemContent = (item: MentionItem) => {
    if (item.type === 'repo') {
      return (
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{item.name}</div>
          {item.description && (
            <div className="text-xs text-muted-foreground truncate">{item.description}</div>
          )}
        </div>
      )
    }

    if (item.type === 'issue') {
      return (
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-muted-foreground">#{item.issueNumber}</span>
            <span className="text-sm font-medium truncate">{item.name}</span>
          </div>
          {item.issueLabels && item.issueLabels.length > 0 && (
            <div className="flex items-center gap-1 mt-0.5">
              {item.issueLabels.slice(0, 3).map((label) => (
                <span
                  key={label.name}
                  className="inline-flex items-center px-1.5 py-0 text-[10px] rounded-full border"
                  style={{
                    backgroundColor: `#${label.color}20`,
                    borderColor: `#${label.color}40`,
                    color: `#${label.color}`,
                  }}
                >
                  {label.name}
                </span>
              ))}
            </div>
          )}
        </div>
      )
    }

    if (item.type === 'plan') {
      return (
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium truncate">{item.name}</span>
            {item.planStatus && (
              <span className={cn(
                "inline-flex items-center px-1.5 py-0 text-[10px] rounded-full",
                item.planStatus === 'ready' && "bg-blue-500/10 text-blue-500",
                item.planStatus === 'completed' && "bg-green-500/10 text-green-500",
              )}>
                {item.planStatus}
              </span>
            )}
          </div>
          {item.planProgress && item.planProgress.total > 0 && (
            <div className="text-xs text-muted-foreground mt-0.5">
              {item.planProgress.completed}/{item.planProgress.total} steps
            </div>
          )}
        </div>
      )
    }

    // Default rendering for servers, tools, etc.
    return (
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">
          {item.displayName || item.name}
        </div>
        {item.description && (
          <div className="text-xs text-muted-foreground truncate">
            {item.description}
          </div>
        )}
      </div>
    )
  }

  const dropdown = (
    <div
      ref={dropdownRef}
      className="fixed z-[100] bg-popover border border-border rounded-lg shadow-lg overflow-hidden animate-in fade-in-0 zoom-in-95 duration-100"
      style={{
        left: position.x,
        bottom: bottomOffset,
        minWidth: isMediaParamMode ? 280 : 240,
        maxWidth: 400,
        maxHeight: isMediaParamMode ? 420 : 280
      }}
    >
      {/* Header */}
      <div className="px-3 py-2 border-b border-border bg-muted/50">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          {isMediaParamMode && secondaryPickerTool && (
            <span className="inline-flex items-center gap-1 text-purple-500">
              {secondaryPickerTool === 'generate_image' && <ImageIcon className="h-3 w-3" />}
              {secondaryPickerTool === 'generate_video' && <Video className="h-3 w-3" />}
              {secondaryPickerTool === 'animate_image' && <Clapperboard className="h-3 w-3" />}
              {secondaryPickerTool === 'animate_character' && <UserRound className="h-3 w-3" />}
              {MEDIA_TOOL_DISPLAY_NAMES[secondaryPickerTool] || secondaryPickerTool}
            </span>
          )}
          {isMediaParamMode && secondaryPickerTool && (
            <span className="text-border">/</span>
          )}
          {isSecondaryMode && secondaryPickerTool && (
            <span className="inline-flex items-center gap-1 text-accent-brand">
              <Terminal className="h-3 w-3" />
              {CODING_AGENT_DISPLAY_NAMES[secondaryPickerTool] || secondaryPickerTool}
            </span>
          )}
          {isSecondaryMode && secondaryPickerTool && (
            <span className="text-border">/</span>
          )}
          <span>{heading}</span>
        </div>
      </div>

      {/* Cloning overlay */}
      {isCloningRepo && (
        <div className="flex flex-col items-center justify-center py-8 gap-2">
          <Loader2 className="h-6 w-6 animate-spin text-accent-brand" />
          <span className="text-sm text-muted-foreground">
            Cloning {cloningRepoName || 'repository'}...
          </span>
        </div>
      )}

      {/* Media parameter picker form */}
      {isMediaParamMode && mediaConfig && !isLoadingSecondary && (
        <div className="px-3 py-2 space-y-3">
          {/* Model selector with input type badges */}
          <div>
            <label className="text-[11px] font-medium text-muted-foreground mb-1 block">Model</label>
            {mediaConfig.availableModels.length === 0 ? (
              <div className="text-xs text-muted-foreground py-2 text-center">
                No compatible models available
              </div>
            ) : (
              <Select
                value={mediaConfig.selectedModel}
                onValueChange={(value) => onMediaConfigChange?.({ ...mediaConfig, selectedModel: value })}
              >
                <SelectTrigger className="w-full h-8 text-xs">
                  <SelectValue>
                    {mediaConfig.availableModels.find(m => m.id === mediaConfig.selectedModel)?.name || mediaConfig.selectedModel}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="z-[110] max-h-60">
                  {mediaConfig.availableModels.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      <div className="flex flex-col">
                        <div className="flex items-center gap-1.5">
                          <span>{m.name}</span>
                          {m.inputType && (
                            <span className="text-[9px] px-1 py-0 rounded bg-muted text-muted-foreground leading-tight">
                              {({
                                text: 'Text→Video',
                                image: 'Image→Video',
                                video: 'Video→Video',
                                image_video: 'Image/Video→Video',
                                image_audio: 'Image+Video→Video',
                              } as Record<string, string>)[m.inputType] || m.inputType}
                            </span>
                          )}
                        </div>
                        <span className="text-[10px] text-muted-foreground">{m.provider}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          {/* Aspect Ratio - only for generate_video and generate_image */}
          {mediaConfig.availableAspectRatios && mediaConfig.availableAspectRatios.length > 0 && (
            <div>
              <label className="text-[11px] font-medium text-muted-foreground mb-1 block">Aspect Ratio</label>
              <div className="flex gap-1 flex-wrap">
                {mediaConfig.availableAspectRatios.map((ratio) => (
                  <button
                    key={ratio}
                    type="button"
                    className={cn(
                      "px-2 py-1 text-xs rounded-md border transition-colors",
                      mediaConfig.selectedAspectRatio === ratio
                        ? "bg-purple-500/15 border-purple-500/40 text-purple-500 font-medium"
                        : "bg-background border-border text-muted-foreground hover:bg-accent"
                    )}
                    onClick={() => onMediaConfigChange?.({ ...mediaConfig, selectedAspectRatio: ratio })}
                  >
                    {ratio}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Image: Resolution */}
          {mediaConfig.category === 'image' && mediaConfig.availableResolutions && (
            <div>
              <label className="text-[11px] font-medium text-muted-foreground mb-1 block">Resolution</label>
              <div className="flex gap-1">
                {mediaConfig.availableResolutions.map((res) => (
                  <button
                    key={res}
                    type="button"
                    className={cn(
                      "px-2 py-1 text-xs rounded-md border transition-colors",
                      mediaConfig.selectedResolution === res
                        ? "bg-purple-500/15 border-purple-500/40 text-purple-500 font-medium"
                        : "bg-background border-border text-muted-foreground hover:bg-accent"
                    )}
                    onClick={() => onMediaConfigChange?.({ ...mediaConfig, selectedResolution: res })}
                  >
                    {res}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Video: Duration - for generate_video and animate_image */}
          {mediaConfig.category === 'video' && mediaConfig.availableDurations && mediaConfig.availableDurations.length > 0 && (
            <div>
              <label className="text-[11px] font-medium text-muted-foreground mb-1 block">Duration</label>
              <div className="flex gap-1 flex-wrap">
                {mediaConfig.availableDurations.map((dur) => (
                  <button
                    key={dur}
                    type="button"
                    className={cn(
                      "px-2 py-1 text-xs rounded-md border transition-colors",
                      mediaConfig.selectedDuration === dur
                        ? "bg-purple-500/15 border-purple-500/40 text-purple-500 font-medium"
                        : "bg-background border-border text-muted-foreground hover:bg-accent"
                    )}
                    onClick={() => onMediaConfigChange?.({ ...mediaConfig, selectedDuration: dur })}
                  >
                    {dur}s
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Video: Quality - only for generate_video */}
          {mediaConfig.category === 'video' && mediaConfig.availableQualities && mediaConfig.availableQualities.length > 0 && (
            <div>
              <label className="text-[11px] font-medium text-muted-foreground mb-1 block">Quality</label>
              <div className="flex gap-1">
                {mediaConfig.availableQualities.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className={cn(
                      "px-2 py-1 text-xs rounded-md border transition-colors capitalize",
                      mediaConfig.selectedQuality === q
                        ? "bg-purple-500/15 border-purple-500/40 text-purple-500 font-medium"
                        : "bg-background border-border text-muted-foreground hover:bg-accent"
                    )}
                    onClick={() => onMediaConfigChange?.({ ...mediaConfig, selectedQuality: q })}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Apply button */}
          <button
            type="button"
            className={cn(
              "w-full py-1.5 text-xs font-medium rounded-md border transition-colors",
              mediaConfig.availableModels.length > 0
                ? "bg-purple-500/15 border-purple-500/30 text-purple-500 hover:bg-purple-500/25"
                : "bg-muted border-border text-muted-foreground cursor-not-allowed"
            )}
            onClick={() => onMediaConfigConfirm?.()}
            disabled={mediaConfig.availableModels.length === 0}
          >
            Apply Settings
          </button>
        </div>
      )}

      {/* Loading state */}
      {!isCloningRepo && showLoading && (
        <div className="flex items-center justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty state */}
      {!isCloningRepo && showEmpty && (
        <div className="px-4 py-6 text-center text-sm text-muted-foreground">
          {mode === 'repos'
            ? 'No repositories found. Connect GitHub first.'
            : mode === 'issues'
              ? 'No open issues found. Clone a repo with issues first.'
              : 'No plans available yet.'}
        </div>
      )}

      {/* Items */}
      {!isCloningRepo && showItems && (
        <div className="overflow-y-auto max-h-[220px] py-1">
          {items.map((item, index) => (
            <div
              key={item.id}
              ref={index === activeIndex ? activeItemRef : null}
              className={cn(
                "flex items-center gap-3 px-3 py-2 cursor-pointer transition-colors",
                index === activeIndex
                  ? "bg-accent text-accent-foreground"
                  : "hover:bg-accent/50"
              )}
              onClick={() => onSelect(item)}
            >
              {/* Icon */}
              {(mode === 'servers' || isSecondaryMode) && (
                <div className="flex-shrink-0 w-6 h-6 rounded-md bg-muted flex items-center justify-center">
                  {renderItemIcon(item)}
                </div>
              )}

              {/* Content */}
              {renderItemContent(item)}
            </div>
          ))}
        </div>
      )}

      {/* Footer hint */}
      <div className="px-3 py-1.5 border-t border-border bg-muted/30">
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          {!isMediaParamMode && (
            <>
              <span>
                <kbd className="px-1 py-0.5 bg-background border border-border rounded text-[9px]">↑↓</kbd>
                {' '}navigate
              </span>
              <span>
                <kbd className="px-1 py-0.5 bg-background border border-border rounded text-[9px]">↵</kbd>
                {' '}select
              </span>
            </>
          )}
          {isMediaParamMode && (
            <span>
              <kbd className="px-1 py-0.5 bg-background border border-border rounded text-[9px]">↵</kbd>
              {' '}apply
            </span>
          )}
          {mode === 'servers' && (
            <span>
              <kbd className="px-1 py-0.5 bg-background border border-border rounded text-[9px]">:</kbd>
              {' '}tools
            </span>
          )}
          {(isSecondaryMode || isMediaParamMode) && (
            <span>
              <kbd className="px-1 py-0.5 bg-background border border-border rounded text-[9px]">Esc</kbd>
              {' '}skip
            </span>
          )}
        </div>
      </div>
    </div>
  )

  // Portal to body to escape any stacking contexts
  return createPortal(dropdown, document.body)
}

export const MentionAutocomplete = memo(MentionAutocompleteComponent)
