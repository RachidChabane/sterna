/**
 * MessageSteps Component
 *
 * Displays message content in sequential steps with tool executions in collapsible sections.
 * Similar to Claude.ai's multi-step tool execution display.
 */

import { useState, useEffect, useRef, memo } from 'react'
import { ChevronDown, ChevronRight, Code2, Info, HelpCircle, MapPin, MessageCircle, Newspaper, Video, Image as ImageIcon, Navigation, Globe, Sparkles, Cpu, type LucideIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { Markdown } from '@/components/ui/markdown'
import { FileToolExecutionsDisplay } from './FileToolExecutionsDisplay'
import { ReasoningDisplay, RedactedBadge, ensureTrailingRedaction } from './ReasoningDisplay'
import { BraveSearchMediaCarousel } from './BraveSearchMediaCarousel'
import { LocationsMap } from './LocationsMap'
import { DirectionsMap } from './DirectionsMap'
import { InfoboxDisplay } from './InfoboxDisplay'
import { FAQDisplay } from './FAQDisplay'
import { DiscussionsDisplay } from './DiscussionsDisplay'
import { NewsClusterDisplay } from './NewsClusterDisplay'
import { WebResultsDisplay } from './WebResultsDisplay'
import { ProcessSection } from './ProcessSection'
import { CodeEditorModal } from '@/components/sandbox'
import { AssetImage } from './AssetImage'
import { ImagePreviewModal } from './ImagePreviewModal'
import { VideoPlayer } from '@/components/videos/VideoPlayer'
import { formatModelId } from '@/utils/modelNames'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { useBraveSearchMedia, useEnrichedResults, type EnrichedResults, type BraveMediaGroup } from '@/hooks/useToolEnrichments'
import { cn } from '@/lib/utils'
import { useStreamingText } from '@/hooks/useStreamingText'
import type { Model, Message } from './types'
import type { ToolResult, CodingAgentResult } from '@/api/llm'
import { isRecord, asString, asNumber } from './tool-renderers/shared'

import { WAITING_MESSAGES } from '@/constants/waitingMessages'

// Returns a message based on elapsed time (starts at 30s, rotates every 10s)
const getWaitingMessage = (elapsed: number): string | null => {
  if (elapsed < 30) return null
  const index = Math.floor((elapsed - 30) / 10)
  return WAITING_MESSAGES[index % WAITING_MESSAGES.length]
}


/** One entry in a `tool_executions` step. */
interface StepToolExecution {
  tool_call: {
    id: string
    type: 'function'
    function: {
      name: string
      arguments: string
    }
    display_name?: string  // User-friendly display name from backend
  }
  result: ToolResult
  success: boolean | null  // null when executing
  isExecuting?: boolean  // True while tool is executing
  startTime?: number  // Timestamp when execution started (persisted across reloads)
}

/** A `tool_executions` step, as it appears in `MessageStepsProps['steps']`. */
interface ToolExecutionsStep {
  type: 'tool_executions'
  executions: StepToolExecution[]
  isExecuting?: boolean  // True while any tool is executing
}

/** One row rendered by `ToolExecutionsGroup`/`MasterToolSection`: the executions from one
 * `tool_executions` step, plus the {{ACTION: ...}} description that preceded it (if any). */
interface ToolGroup {
  executions: StepToolExecution[]
  actionDescription: string | null
  isExecuting?: boolean
}

/** One entry of a `master_tool_section` step (see `groupAllToolsBeforeAnswer`). */
type MasterItem =
  | { type: 'tool_group'; groups: ToolGroup[] }
  | { type: 'reasoning'; content: string; isStreaming: boolean }
  | { type: 'text'; content: string }

interface MessageStepsProps {
  steps: Array<
    | { type: 'text'; content: string }
    | { type: 'reasoning'; content: string; isStreaming: boolean }
    | ToolExecutionsStep
  >
  isInterrupted?: boolean
  isStreaming?: boolean
  chatId?: string
  conversationId?: string
  model?: Model | null
  messages?: Message[]
}

export function MessageSteps({ steps, isInterrupted, isStreaming, chatId, conversationId, model, messages }: MessageStepsProps) {
  const [codeEditorOpen, setCodeEditorOpen] = useState(false)
  const [imagePreviewOpen, setImagePreviewOpen] = useState(false)
  const [imagePreviewIndex, setImagePreviewIndex] = useState(0)
  const imageUrlsRef = useRef<Map<string, string>>(new Map())
  const user = useAuthStore(state => state.user)

  // Extract enrichments using custom hooks
  const braveSearchMedia = useBraveSearchMedia(steps)
  const enrichedResults = useEnrichedResults(steps)

  // Group consecutive tool_executions steps together, then consolidate all before answer
  const groupedSteps = groupAllToolsBeforeAnswer(groupConsecutiveToolExecutions(steps))

  // Extract generated images from all tool executions to display at the very end
  const isToolExecutionsStep = (step: MessageStepsProps['steps'][number]): step is ToolExecutionsStep =>
    step.type === 'tool_executions'

  const generatedImages = steps
    .filter(isToolExecutionsStep)
    .flatMap(step => step.executions)
    .filter((e) => {
      const toolName = e.tool_call?.function?.name
      return (toolName === 'generate_image' || toolName === 'edit_image') && e.success !== false && !e.isExecuting
    })
    .map((e) => extractGeneratedImage(e.result))
    .filter((img): img is NonNullable<typeof img> => img !== null)

  // Extract generated videos from all tool executions to display at the very end
  // Include all video generation tools: generate_video, animate_image, animate_character
  const VIDEO_TOOLS = ['generate_video', 'animate_image', 'animate_character']
  const generatedVideos = steps
    .filter(isToolExecutionsStep)
    .flatMap(step => step.executions)
    .filter((e) => {
      const toolName = e.tool_call?.function?.name
      return VIDEO_TOOLS.includes(toolName) && e.success !== false && !e.isExecuting
    })
    .map((e) => extractGeneratedVideo(e.result))
    .filter((vid): vid is NonNullable<typeof vid> => vid !== null)

  // Get image URLs for the preview modal
  const getPreviewImages = () => {
    return generatedImages.map((img) => ({
      src: imageUrlsRef.current.get(img.asset_id) || '',
      alt: img.name || img.description || 'Generated image'
    })).filter(img => img.src)
  }

  // Handle image click to open preview
  const handleImageClick = (assetId: string, src: string) => {
    const idx = generatedImages.findIndex(img => img.asset_id === assetId)
    if (idx >= 0) {
      setImagePreviewIndex(idx)
      setImagePreviewOpen(true)
    }
  }

  // Store loaded image URL
  const handleImageLoad = (assetId: string, blobUrl: string) => {
    imageUrlsRef.current.set(assetId, blobUrl)
  }

  return (
    <>
      <div className="space-y-3">
        {groupedSteps.map((step, index) => {
          if (step.type === 'text') {
            // Only apply streaming animation to the last text step while streaming
            const isLastTextStep = isStreaming && index === groupedSteps.length - 1
            return (
              <StreamingTextStep
                key={index}
                content={step.content}
                isStreaming={!!isLastTextStep}
              />
            )
          } else if (step.type === 'reasoning') {
            return (
              <ReasoningDisplay
                key={index}
                content={step.content}
                isStreaming={step.isStreaming}
                isInterrupted={isInterrupted}
                showStopped={true}
              />
            )
          } else if (step.type === 'master_tool_section') {
            // Master section containing all tool groups and reasoning before the answer
            return (
              <MasterToolSection
                key={index}
                items={step.items}
                onOpenIDE={() => setCodeEditorOpen(true)}
                isInterrupted={isInterrupted}
                chatId={chatId}
              />
            )
          } else if (step.type === 'tool_executions_group') {
            // Merged group of consecutive tool executions
            return (
              <ToolExecutionsGroup
                key={index}
                groups={step.groups}
                onOpenIDE={() => setCodeEditorOpen(true)}
                chatId={chatId}
              />
            )
          } else {
            // Single tool executions step (shouldn't happen after grouping, but fallback)
            return (
              <ToolExecutionsGroup
                key={index}
                groups={[{ executions: step.executions, actionDescription: null }]}
                onOpenIDE={() => setCodeEditorOpen(true)}
                chatId={chatId}
              />
            )
          }
        })}
      </div>

      {/* Enriched Brave Search results (Pro features) - Tabs interface */}
      {(enrichedResults || braveSearchMedia.length > 0) && (
        <EnrichedResultsTabs
          enrichedResults={enrichedResults}
          braveSearchMedia={braveSearchMedia}
        />
      )}

      {/* Generated images - displayed at the very end of the message */}
      {generatedImages.length > 0 && (
        <div className="mt-4 space-y-4">
          {generatedImages.map((img, idx) => (
            <div key={idx}>
              <AssetImage
                assetId={img.asset_id}
                alt={img.name || img.description || 'Generated image'}
                className="max-w-[280px] sm:max-w-sm md:max-w-lg max-h-[300px] sm:max-h-[400px] md:max-h-[500px] object-contain rounded-lg border border-border/40 shadow-sm cursor-pointer hover:shadow-lg transition-shadow"
                onClick={(src) => handleImageClick(img.asset_id, src)}
                onLoad={(blobUrl) => handleImageLoad(img.asset_id, blobUrl)}
              />
              {/* Image metadata */}
              <div className="flex items-center flex-wrap gap-2 sm:gap-3 mt-2 text-xs text-muted-foreground/70">
                {img.width && img.height && (
                  <span>{img.width}×{img.height}</span>
                )}
                {img.model && (
                  <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-accent-brand/10 text-accent-brand/80">
                    {formatModelId(img.model)}
                  </span>
                )}
                {img.generation_time_ms && (
                  <span>{(img.generation_time_ms / 1000).toFixed(1)}s</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Generated videos - displayed at the very end of the message */}
      {generatedVideos.length > 0 && (
        <div className="mt-4 space-y-4">
          {generatedVideos.map((vid, idx) => (
            <div key={idx}>
              <VideoPlayer
                assetId={vid.asset_id}
                className="max-w-[280px] sm:max-w-sm md:max-w-lg rounded-lg border border-border/40 shadow-sm"
                alt={vid.prompt || 'Generated video'}
              />
              {/* Video metadata */}
              <div className="flex items-center flex-wrap gap-2 sm:gap-3 mt-2 text-xs text-muted-foreground/70">
                {vid.width && vid.height && (
                  <span>{vid.width}×{vid.height}</span>
                )}
                {vid.duration_seconds && (
                  <span>{vid.duration_seconds}s</span>
                )}
                {vid.model && (
                  <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-accent-brand/10 text-accent-brand/80">
                    {formatModelId(vid.model)}
                  </span>
                )}
                {vid.generation_time_ms && (
                  <span>{(vid.generation_time_ms / 1000).toFixed(1)}s generation</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Image Preview Modal */}
      <ImagePreviewModal
        isOpen={imagePreviewOpen}
        onClose={() => setImagePreviewOpen(false)}
        images={getPreviewImages()}
        selectedIndex={imagePreviewIndex}
        onIndexChange={setImagePreviewIndex}
      />

      {/* Code Editor Modal */}
      <CodeEditorModal
        open={codeEditorOpen}
        onOpenChange={setCodeEditorOpen}
        userId={user?.id || ''}
        chatId={chatId || ''}
        conversationId={conversationId || ''}
        model={model}
        messages={messages}
      />
    </>
  )
}

// Renders a text step with smooth character-by-character reveal during streaming
const StreamingTextStep = memo(function StreamingTextStep({
  content,
  isStreaming
}: {
  content: string
  isStreaming: boolean
}) {
  const [cleanedContent] = extractActionTag(content)
  const rawContent = stripBase64Images(cleanedContent || '')
  const { displayedText } = useStreamingText(rawContent, isStreaming)
  if (!displayedText) return null
  return (
    <div>
      <Markdown>{displayedText}</Markdown>
    </div>
  )
})

function EnrichedResultsTabs({
  enrichedResults,
  braveSearchMedia
}: {
  enrichedResults: EnrichedResults | null
  braveSearchMedia: BraveMediaGroup[]
}) {
  const [activeTab, setActiveTab] = useState<string | null>(null)
  const [isExpanded, setIsExpanded] = useState(true)

  // Build available sections
  const sections: Array<{ id: string; label: string; icon: LucideIcon; count?: number; priority: number }> = []

  // Media (images/videos) get highest priority - they're visual and should be shown first
  braveSearchMedia.forEach((media, index) => {
    sections.push({
      id: `media-${index}`,
      label: media.title,
      icon: media.title === 'Images' ? ImageIcon : Video,
      count: media.items.length,
      priority: 0
    })
  })

  // Videos from enriched results
  if (enrichedResults?.videos_results && enrichedResults.videos_results.length > 0) {
    sections.push({ id: 'videos', label: 'Videos', icon: Video, count: enrichedResults.videos_results.length, priority: 1 })
  }

  // Knowledge panel is high value
  if (enrichedResults?.infobox) {
    sections.push({ id: 'knowledge', label: 'Overview', icon: Info, priority: 2 })
  }

  // Locations with map
  if (enrichedResults?.locations && enrichedResults.locations.length > 0) {
    sections.push({ id: 'locations', label: 'Places', icon: MapPin, count: enrichedResults.locations.length, priority: 3 })
  }

  // Directions
  if (enrichedResults?.directions) {
    sections.push({ id: 'directions', label: 'Directions', icon: Navigation, priority: 4 })
  }

  // News is time-sensitive
  if (enrichedResults?.news_results && enrichedResults.news_results.length > 0) {
    sections.push({ id: 'news', label: 'News', icon: Newspaper, count: enrichedResults.news_results.length, priority: 5 })
  }

  // Discussions / Forums
  if (enrichedResults?.discussions && enrichedResults.discussions.length > 0) {
    sections.push({ id: 'discussions', label: 'Discussions', icon: MessageCircle, count: enrichedResults.discussions.length, priority: 6 })
  }

  // FAQ
  if (enrichedResults?.faq) {
    sections.push({ id: 'faq', label: 'FAQ', icon: HelpCircle, priority: 7 })
  }

  // Web results are fallback
  if (enrichedResults?.web_results && enrichedResults.web_results.length > 0) {
    sections.push({ id: 'web', label: 'Links', icon: Globe, count: enrichedResults.web_results.length, priority: 8 })
  }

  // Sort by priority
  sections.sort((a, b) => a.priority - b.priority)

  // Set first tab as default
  if (!activeTab && sections.length > 0) {
    setActiveTab(sections[0].id)
  }

  if (sections.length === 0) return null

  // Check if we only have media (images/videos) - show directly without tabs
  const onlyMedia = sections.every(s => s.id.startsWith('media-') || s.id === 'videos')
  const hasMultipleSections = sections.length > 1

  // Direct media display (no tabs needed)
  if (onlyMedia && !hasMultipleSections) {
    return (
      <div className="mt-4">
        {braveSearchMedia.map((media, index) => (
          <BraveSearchMediaCarousel key={index} items={media.items} title={media.title} />
        ))}
        {enrichedResults?.videos_results && enrichedResults.videos_results.length > 0 && (
          <BraveSearchMediaCarousel items={enrichedResults.videos_results} title="Videos" />
        )}
      </div>
    )
  }

  return (
    <div className="mt-4 space-y-3">
      {/* Section header with collapse toggle */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronRight className={cn(
            "w-3.5 h-3.5 transition-transform duration-200",
            isExpanded && "rotate-90"
          )} />
          <span className="font-medium">Search Results</span>
          <span className="px-1.5 py-0.5 rounded-full bg-accent-brand/10 text-accent-brand text-[10px] font-medium">
            {sections.length}
          </span>
        </button>
      </div>

      {isExpanded && (
        <div className="space-y-3">
          {/* Horizontal scrollable tabs */}
          <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-none">
            {sections.map((section) => {
              const Icon = section.icon
              const isActive = activeTab === section.id
              return (
                <button
                  key={section.id}
                  onClick={() => setActiveTab(section.id)}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 whitespace-nowrap flex-shrink-0",
                    "border",
                    isActive
                      ? "bg-accent-brand/15 border-accent-brand/40 text-accent-brand shadow-sm"
                      : "bg-background/50 border-border/40 text-muted-foreground hover:text-foreground hover:border-border hover:bg-muted/30"
                  )}
                >
                  <Icon className="w-3 h-3" />
                  <span>{section.label}</span>
                  {section.count && (
                    <span className={cn(
                      "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                      isActive
                        ? "bg-accent-brand/20 text-accent-brand"
                        : "bg-muted text-muted-foreground"
                    )}>
                      {section.count}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Content area */}
          <div className="rounded-xl border border-border/40 bg-background/30 overflow-hidden">
            <div className="p-3 sm:p-4">
              {activeTab === 'web' && enrichedResults?.web_results && (
                <WebResultsDisplay results={enrichedResults.web_results} />
              )}
              {activeTab === 'knowledge' && enrichedResults?.infobox && (
                <InfoboxDisplay infobox={enrichedResults.infobox} />
              )}
              {activeTab === 'directions' && enrichedResults?.directions && (
                <DirectionsMap directions={enrichedResults.directions} />
              )}
              {activeTab === 'locations' && enrichedResults?.locations && (
                <LocationsMap locations={enrichedResults.locations} />
              )}
              {activeTab === 'faq' && enrichedResults?.faq && (
                <FAQDisplay faq={enrichedResults.faq} />
              )}
              {activeTab === 'discussions' && enrichedResults?.discussions && (
                <DiscussionsDisplay discussions={enrichedResults.discussions} />
              )}
              {activeTab === 'news' && enrichedResults?.news_results && (
                <NewsClusterDisplay news={enrichedResults.news_results} />
              )}
              {activeTab === 'videos' && enrichedResults?.videos_results && (
                <BraveSearchMediaCarousel items={enrichedResults.videos_results} />
              )}
              {braveSearchMedia.map((media, index) => (
                activeTab === `media-${index}` && (
                  <BraveSearchMediaCarousel key={index} items={media.items} />
                )
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Legacy CollapsibleEnrichment - now just wraps ProcessSection
function CollapsibleEnrichment({
  title,
  icon: Icon,
  count,
  defaultExpanded = false,
  children
}: {
  title: string
  icon: LucideIcon
  count?: number
  defaultExpanded?: boolean
  children: React.ReactNode
}) {
  return (
    <ProcessSection
      icon={<Icon className="w-3.5 h-3.5" />}
      title={title}
      badge={count}
      defaultExpanded={defaultExpanded}
    >
      {children}
    </ProcessSection>
  )
}

// Tools that interact with the file system and should show "Open IDE" button
const FILE_SYSTEM_TOOLS = new Set([
  'read_file',
  'write_file',
  'edit_file',
  'delete_file',
  'create_directory',
  'rename_file',
  'list_files',
  'execute_code',
  'execute_programming_task',
  'coding_agent',
  'plan_implementation',
  'implement_plan',
  'edit_plan',
  'start_preview',
  'stop_preview',
])

// Group consecutive tool_executions steps together
type GroupedStep =
  | { type: 'text'; content: string }
  | { type: 'reasoning'; content: string; isStreaming: boolean }
  | ToolExecutionsStep
  | { type: 'tool_executions_group'; groups: ToolGroup[] }
  | { type: 'master_tool_section'; items: MasterItem[] }

function groupConsecutiveToolExecutions(steps: MessageStepsProps['steps']): GroupedStep[] {
  const result: GroupedStep[] = []
  let currentToolGroup: ToolGroup[] = []
  let lastActionDescription: string | null = null

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i]

    if (step.type === 'text') {
      // Check if this text has an action tag (it precedes tool executions)
      const [cleanedContent, action] = extractActionTag(step.content)
      lastActionDescription = action

      // If we have accumulated tool groups and this text has content, flush the group
      if (currentToolGroup.length > 0 && cleanedContent) {
        result.push({ type: 'tool_executions_group', groups: currentToolGroup })
        currentToolGroup = []
      }

      // Only add text step if it has content after removing action tag
      if (cleanedContent) {
        result.push(step)
        lastActionDescription = null // Reset after adding text
      }
    } else if (step.type === 'tool_executions') {
      // Add to current group
      currentToolGroup.push({
        executions: step.executions,
        actionDescription: lastActionDescription,
        isExecuting: step.isExecuting
      })
      lastActionDescription = null // Reset after using
    } else {
      // For reasoning or other types, flush any accumulated tool group first
      if (currentToolGroup.length > 0) {
        result.push({ type: 'tool_executions_group', groups: currentToolGroup })
        currentToolGroup = []
      }
      result.push(step)
      lastActionDescription = null
    }
  }

  // Flush any remaining tool group
  if (currentToolGroup.length > 0) {
    result.push({ type: 'tool_executions_group', groups: currentToolGroup })
  }

  return result
}

// Group all tool execution groups and reasoning into one master section
// Structure: [text before first tool] -> [View Process collapsible] -> [text after last tool]
function groupAllToolsBeforeAnswer(steps: GroupedStep[]): GroupedStep[] {
  // Find the index of the FIRST and LAST tool_executions_group
  let firstToolGroupIndex = -1
  let lastToolGroupIndex = -1

  for (let i = 0; i < steps.length; i++) {
    if (steps[i].type === 'tool_executions_group') {
      if (firstToolGroupIndex === -1) {
        firstToolGroupIndex = i
      }
      lastToolGroupIndex = i
    }
  }

  // If no tool groups found, return as-is
  if (firstToolGroupIndex < 0) {
    return steps
  }

  // Collect tool execution groups, reasoning blocks, AND text steps BETWEEN first and last tool
  const items: MasterItem[] = []

  // Only include items from firstToolGroupIndex to lastToolGroupIndex (inclusive)
  for (let i = firstToolGroupIndex; i <= lastToolGroupIndex; i++) {
    const step = steps[i]
    if (step.type === 'tool_executions_group') {
      items.push({ type: 'tool_group', groups: step.groups })
    } else if (step.type === 'reasoning') {
      items.push({ type: 'reasoning', content: step.content, isStreaming: step.isStreaming })
    } else if (step.type === 'text' && step.content) {
      // Include text steps between tool calls (intermediate AI outputs)
      items.push({ type: 'text', content: step.content })
    }
  }

  // If we have items, consolidate them into one master section
  if (items.length > 0) {
    const result: GroupedStep[] = []

    // Add everything BEFORE the first tool group
    // Reasoning steps go INSIDE the master section; other steps stay outside
    for (let i = 0; i < firstToolGroupIndex; i++) {
      const step = steps[i]
      if (step.type === 'reasoning') {
        // Include reasoning inside the master section (prepend so it appears first)
        items.unshift({ type: 'reasoning', content: step.content, isStreaming: step.isStreaming })
      } else {
        result.push(step)
      }
    }

    // Add the master tool section (collapsible "View Process")
    result.push({ type: 'master_tool_section', items })

    // Add everything AFTER the last tool group (the actual answer)
    for (let i = lastToolGroupIndex + 1; i < steps.length; i++) {
      result.push(steps[i])
    }

    return result
  }

  return steps
}

// Regex to extract {{ACTION: ...}} tags from text
const ACTION_TAG_REGEX = /\{\{ACTION:\s*([^}]+)\}\}/g

// Regex to match base64 data URLs (images) in text - these should be stripped since we display images separately
const BASE64_DATA_URL_REGEX = /data:image\/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+/g

// Strip base64 data URLs from text content (since images are displayed separately via AssetImage)
const stripBase64Images = (text: string): string => {
  return text.replace(BASE64_DATA_URL_REGEX, '').trim()
}

// Extract action tag from text and return [cleanedText, actionDescription]
const extractActionTag = (text: string): [string, string | null] => {
  const match = text.match(ACTION_TAG_REGEX)
  if (match && match.length > 0) {
    // Extract the action description from the first match
    const actionMatch = match[0].match(/\{\{ACTION:\s*([^}]+)\}\}/)
    const action = actionMatch ? actionMatch[1].trim() : null
    // Remove all action tags from text
    const cleanedText = text.replace(ACTION_TAG_REGEX, '').trim()
    return [cleanedText, action]
  }
  return [text, null]
}

// Fallback: Generate action description based on tool names (for models that don't support the format)
const getFallbackActionDescription = (executions: StepToolExecution[]): string => {
  const toolCount = executions.length

  if (toolCount === 0) return 'Running tools'

  // Get display name from execution if available, otherwise use function name
  const getDisplayName = (execution: StepToolExecution): string => {
    // Prefer backend-provided display_name
    if (execution?.tool_call?.display_name) {
      return execution.tool_call.display_name
    }
    return execution?.tool_call?.function?.name || ''
  }

  // Convert tool name to gerund form
  const toGerund = (execution: StepToolExecution): string => {
    // If we have a display_name from backend, use it directly with "Using" prefix
    const displayName = execution?.tool_call?.display_name
    if (displayName) {
      return displayName
    }

    // Fall back to generating from raw tool name
    const toolName = execution?.tool_call?.function?.name || ''
    // Map common tool prefixes/names to gerund descriptions
    if (toolName.startsWith('search_') || toolName.includes('_search')) return `Searching ${toolName.replace(/search_|_search/g, '').replace(/_/g, ' ')}`
    if (toolName.startsWith('get_')) return `Getting ${toolName.replace('get_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('read_')) return `Reading ${toolName.replace('read_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('write_')) return `Writing ${toolName.replace('write_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('edit_')) return `Editing ${toolName.replace('edit_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('delete_')) return `Deleting ${toolName.replace('delete_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('create_')) return `Creating ${toolName.replace('create_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('list_')) return `Listing ${toolName.replace('list_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('execute_')) return `Executing ${toolName.replace('execute_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('generate_')) return `Generating ${toolName.replace('generate_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('animate_')) return `Animating ${toolName.replace('animate_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('upscale_')) return `Upscaling ${toolName.replace('upscale_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('find_')) return `Finding ${toolName.replace('find_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('check_')) return `Checking ${toolName.replace('check_', '').replace(/_/g, ' ')}`
    if (toolName.startsWith('run_')) return `Running ${toolName.replace('run_', '').replace(/_/g, ' ')}`
    // Default: capitalize and add -ing to first word
    const words = toolName.split('_')
    const verb = words[0]
    const rest = words.slice(1).join(' ')
    return `${verb.charAt(0).toUpperCase()}${verb.slice(1)}ing${rest ? ' ' + rest : ''}`
  }

  if (toolCount === 1) return toGerund(executions[0])

  // Multiple tools - check if they all have the same display name (e.g., multiple calls to same tool)
  const displayNames = executions.map(e => getDisplayName(e)).filter(Boolean)
  const uniqueNames = [...new Set(displayNames)]
  if (uniqueNames.length === 1) return toGerund(executions[0])

  return `Running ${toolCount} operations`
}

// Get a short display name for a tool
const getToolDisplayName = (toolName: string): string => {
  const names: Record<string, string> = {
    brave_web_search: 'Web search',
    brave_local_search: 'Local search',
    brave_news_search: 'News search',
    brave_image_search: 'Image search',
    brave_video_search: 'Video search',
    brave_enriched_search: 'Enriched search',
    fetch_web_page: 'Fetch page',
    read_file: 'Read file',
    write_file: 'Write file',
    edit_file: 'Edit file',
    list_files: 'List files',
    execute_code: 'Execute code',
    execute_programming_task: 'Programming task',
    create_directory: 'Create directory',
    delete_file: 'Delete file',
    generate_image: 'Generate image',
    edit_image: 'Edit image',
    generate_video: 'Generate video',
    animate_image: 'Animate image',
    animate_character: 'Animate character',
  }
  // Format unknown tools: snake_case -> Title Case
  return names[toolName] || toolName
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ')
}

function ToolExecutionsGroup({ groups, onOpenIDE, chatId }: { groups: ToolGroup[]; onOpenIDE: () => void; chatId?: string }) {
  const [isExpanded, setIsExpanded] = useState(false) // Collapsed by default
  const [waitingMessage, setWaitingMessage] = useState<string | null>(null)

  // Flatten all executions for counting
  const allExecutions = groups.flatMap(g => g.executions)
  const totalSteps = groups.length
  const isExecuting = allExecutions.some((e) => e.isExecuting === true)
  const failedCount = allExecutions.filter(e => e.success === false).length

  // Check if any tool interacts with the file system
  const hasFileSystemTools = allExecutions.some((e) =>
    FILE_SYSTEM_TOOLS.has(e.tool_call?.function?.name)
  )

  // Get startTime from executions (persisted across reloads)
  const startTime = allExecutions.find((e) => e.startTime)?.startTime

  // Track execution time and update waiting message based on psychology-based phases
  useEffect(() => {
    if (!isExecuting || !startTime) {
      setWaitingMessage(null)
      return
    }

    const updateWaitingMessage = () => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      setWaitingMessage(getWaitingMessage(elapsed))
    }

    updateWaitingMessage()
    const interval = setInterval(updateWaitingMessage, 1000)
    return () => clearInterval(interval)
  }, [isExecuting, startTime])

  // Build header description
  const headerDescription = groups.length === 1
    ? (groups[0].actionDescription || getFallbackActionDescription(groups[0].executions))
    : `Tool calls`

  return (
    <div className="border-l-2 border-accent-brand/40 pl-2 md:pl-3 py-1 w-full max-w-full">
      {/* Header - clickable to expand/collapse */}
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 hover:opacity-80 transition-opacity cursor-pointer min-w-0"
      >
        {isExpanded ? (
          <ChevronDown className="w-3 h-3 md:w-3.5 md:h-3.5 flex-shrink-0 text-accent-brand/70" />
        ) : (
          <ChevronRight className="w-3 h-3 md:w-3.5 md:h-3.5 flex-shrink-0 text-accent-brand/70" />
        )}
        <div className="flex-1 flex items-center gap-2 min-w-0">
          <span className={cn(
            "text-sm truncate",
            isExecuting ? "shimmer-text" : "text-accent-brand/80"
          )}>
            {headerDescription}{isExecuting ? '...' : ''}
          </span>
          <span className="flex-shrink-0 text-xs px-1.5 py-0.5 rounded-full bg-accent-brand/10 text-accent-brand/70">
            {totalSteps} {totalSteps === 1 ? 'step' : 'steps'}
          </span>
          {!isExecuting && failedCount > 0 && (
            <span className="flex-shrink-0 text-xs px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-400">
              {failedCount} failed
            </span>
          )}
          {isExecuting && (
            <div className="w-3 h-3 border-2 border-accent-brand/30 border-t-accent-brand rounded-full animate-spin flex-shrink-0" />
          )}

          {/* Reassuring waiting message - appears after 30s with rotating content */}
          {waitingMessage && isExecuting && (
            <span className="text-xs text-muted-foreground/60 flex-shrink-0 animate-pulse">
              {waitingMessage}...
            </span>
          )}
        </div>

        {/* Open IDE button */}
        {hasFileSystemTools && (
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => { e.stopPropagation(); onOpenIDE() }}
            className="h-6 px-2 text-xs gap-1.5 text-accent-brand/70 hover:text-accent-brand hover:bg-accent-brand/10 transition-colors flex-shrink-0"
          >
            <Code2 className="h-3 w-3" />
            <span>Open IDE</span>
          </Button>
        )}
      </div>

      {/* Collapsible content - each group is a step */}
      {isExpanded && (
        <div className="pt-2 space-y-1.5">
          {groups.map((group, index) => (
            <ToolExecutionStep
              key={index}
              executions={group.executions}
              actionDescription={group.actionDescription}
              isGroupExecuting={group.isExecuting}
              onOpenIDE={onOpenIDE}
              chatId={chatId}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// Individual step within a group - render content directly without collapsible wrapper
function ToolExecutionStep({ executions, actionDescription, isGroupExecuting, onOpenIDE, chatId }: {
  executions: StepToolExecution[]
  actionDescription: string | null
  isGroupExecuting?: boolean
  onOpenIDE?: () => void
  chatId?: string
}) {
  return (
    <div className="text-xs min-w-0 overflow-hidden">
      <FileToolExecutionsDisplay executions={executions} showBraveSearchMedia={false} onOpenIDE={onOpenIDE} chatId={chatId} />
    </div>
  )
}

// Master section that groups ALL tool executions, reasoning, and text before the answer

// Helper to extract image data from tool execution result
const extractGeneratedImage = (result: ToolResult): {
  asset_id: string
  width?: number
  height?: number
  model?: string
  generation_time_ms?: number
  name?: string
  description?: string
} | null => {
  if (!result) return null
  try {
    let data: unknown = result
    if (typeof data === 'string') {
      data = JSON.parse(data)
    }
    // Unwrap nested result
    data = (isRecord(data) ? data.result : undefined) || data
    const dataRecord = isRecord(data) ? data : undefined
    // Check for error status
    if (dataRecord?.status === 'error') return null
    // Extract image data
    const imageData = dataRecord ? dataRecord.image : undefined
    if (isRecord(imageData) && typeof imageData.asset_id === 'string') {
      return {
        asset_id: imageData.asset_id,
        width: asNumber(imageData.width),
        height: asNumber(imageData.height),
        model: asString(dataRecord?.model),
        generation_time_ms: asNumber(dataRecord?.generation_time_ms),
        name: asString(imageData.name),
        description: asString(imageData.description),
      }
    }
    return null
  } catch {
    return null
  }
}

// Helper to extract video data from tool execution result
const extractGeneratedVideo = (result: ToolResult): {
  asset_id: string
  width?: number
  height?: number
  duration_seconds?: number
  model?: string
  generation_time_ms?: number
  prompt?: string
} | null => {
  if (!result) return null
  try {
    let data: unknown = result
    if (typeof data === 'string') {
      data = JSON.parse(data)
    }
    // Unwrap nested result
    data = (isRecord(data) ? data.result : undefined) || data
    const dataRecord = isRecord(data) ? data : undefined
    // Check for error status
    if (dataRecord?.status === 'error') return null
    // Extract video data
    const videoData = dataRecord ? dataRecord.video : undefined
    if (isRecord(videoData) && typeof videoData.asset_id === 'string') {
      return {
        asset_id: videoData.asset_id,
        width: asNumber(videoData.width),
        height: asNumber(videoData.height),
        duration_seconds: asNumber(videoData.duration_seconds),
        model: asString(dataRecord?.model),
        generation_time_ms: asNumber(dataRecord?.generation_time_ms),
        prompt: asString(dataRecord?.prompt),
      }
    }
    return null
  } catch {
    return null
  }
}

function MasterToolSection({ items, onOpenIDE, isInterrupted, chatId }: {
  items: MasterItem[]
  onOpenIDE: () => void
  isInterrupted?: boolean
  chatId?: string
}) {
  const [isExpanded, setIsExpanded] = useState(false) // Collapsed by default
  const [sheetOpen, setSheetOpen] = useState(false)
  const [waitingMessage, setWaitingMessage] = useState<string | null>(null)
  const isMobile = useUIStore((state) => state.isMobile)

  // Extract tool groups for counting and status
  const isToolGroupItem = (item: MasterItem): item is { type: 'tool_group'; groups: ToolGroup[] } => item.type === 'tool_group'
  const toolGroups = items.filter(isToolGroupItem)
  const allExecutions = toolGroups.flatMap(tg => tg.groups.flatMap(g => g.executions))
  const totalSteps = toolGroups.reduce((sum, tg) => sum + tg.groups.length, 0)
  const isExecuting = allExecutions.some((e) => e.isExecuting === true)
  const failedCount = allExecutions.filter(e => e.success === false).length

  // Find the currently executing tool's action description
  const getCurrentActionDescription = (): string | null => {
    for (const toolGroup of toolGroups) {
      for (const group of toolGroup.groups) {
        if (group.isExecuting || group.executions.some((e) => e.isExecuting)) {
          return group.actionDescription || getFallbackActionDescription(group.executions)
        }
      }
    }
    return null
  }
  const currentAction = isExecuting ? getCurrentActionDescription() : null

  // Check if any tool interacts with the file system
  const hasFileSystemTools = allExecutions.some((e) =>
    FILE_SYSTEM_TOOLS.has(e.tool_call?.function?.name)
  )

  // Get startTime from executions (persisted across reloads)
  const startTime = allExecutions.find((e) => e.startTime)?.startTime

  // Track execution time and update waiting message based on psychology-based phases
  useEffect(() => {
    if (!isExecuting || !startTime) {
      setWaitingMessage(null)
      return
    }

    const updateWaitingMessage = () => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      setWaitingMessage(getWaitingMessage(elapsed))
    }

    updateWaitingMessage()
    const interval = setInterval(updateWaitingMessage, 1000)
    return () => clearInterval(interval)
  }, [isExecuting, startTime])

  // Handle toggle - on mobile open sheet, on desktop expand inline
  const handleToggle = () => {
    if (isMobile) {
      setSheetOpen(true)
    } else {
      setIsExpanded(!isExpanded)
    }
  }

  // Shared content for both desktop and mobile
  const ProcessContent = (
    <div className="space-y-2 min-w-0 overflow-hidden">
      {items.map((item, itemIndex) => {
        const isLastItem = itemIndex === items.length - 1

        if (item.type === 'tool_group') {
          return (
            <div key={itemIndex} className="space-y-1">
              {item.groups.map((group, stepIndex) => (
                <ToolExecutionStep
                  key={`${itemIndex}-${stepIndex}`}
                  executions={group.executions}
                  actionDescription={group.actionDescription}
                  isGroupExecuting={group.isExecuting}
                  onOpenIDE={onOpenIDE}
                  chatId={chatId}
                />
              ))}
            </div>
          )
        } else if (item.type === 'reasoning') {
          // Render reasoning as normal text inside the process section
          const rawCleaned = item.content
            .replace(/<\/?thinking>/gi, '')
            .replace(/\{\{ACTION:[^}]*\}\}/g, '')
            .trim()
          if (!rawCleaned) return null
          // Append trailing redaction marker if text ends abruptly after filtering
          const cleaned = ensureTrailingRedaction(rawCleaned)
          // Split on [...] to render redacted badges inline
          const hasRedacted = cleaned.includes('[...]')
          if (hasRedacted) {
            const segments = cleaned.split('[...]')
            return (
              <div key={itemIndex} className="text-xs text-muted-foreground pl-1 border-l border-muted-foreground/20 overflow-hidden [&_p]:text-xs [&_li]:text-xs [&_code]:text-[10px] [&_code]:break-all [&_pre]:overflow-x-auto">
                {segments.map((segment, si) => (
                  <span key={si}>
                    {segment && <Markdown>{segment}</Markdown>}
                    {si < segments.length - 1 && <RedactedBadge />}
                  </span>
                ))}
              </div>
            )
          }
          return (
            <div key={itemIndex} className="text-xs text-muted-foreground pl-1 border-l border-muted-foreground/20 overflow-hidden [&_p]:text-xs [&_li]:text-xs [&_code]:text-[10px] [&_code]:break-all [&_pre]:overflow-x-auto">
              <Markdown>{cleaned}</Markdown>
            </div>
          )
        } else if (item.type === 'text' && item.content) {
          const [cleanedContent] = extractActionTag(item.content)
          if (!cleanedContent) return null
          return (
            <div key={itemIndex} className="text-xs text-muted-foreground pl-1 border-l border-muted-foreground/20 overflow-hidden [&_p]:text-xs [&_li]:text-xs [&_code]:text-[10px] [&_code]:break-all [&_pre]:overflow-x-auto">
              <Markdown>{cleanedContent}</Markdown>
            </div>
          )
        }
        return null
      })}
    </div>
  )

  // Shared trigger header
  const TriggerHeader = (
    <div
      className="w-full flex items-center gap-2 px-2.5 py-2 hover:bg-accent-brand/5 transition-colors cursor-pointer min-w-0 rounded-md group/process"
      onClick={handleToggle}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          handleToggle()
        }
      }}
    >
      <ChevronRight className={cn(
        "w-3.5 h-3.5 flex-shrink-0 text-muted-foreground transition-transform duration-200 group-hover/process:text-accent-brand",
        !isMobile && isExpanded && "rotate-90"
      )} />
      <Cpu className="w-3.5 h-3.5 text-accent-brand/70 flex-shrink-0" />
      <div className="flex-1 flex items-center gap-2 min-w-0">
        <span className={cn(
          "text-xs font-medium truncate transition-all duration-300",
          isExecuting ? "shimmer-text" : "text-foreground/90"
        )}>
          {isExecuting
            ? (currentAction ? `${currentAction}...` : 'Working...')
            : 'View process'}
        </span>
        <span className="flex-shrink-0 text-xs px-1.5 py-0.5 rounded-full bg-accent-brand/10 text-accent-brand font-medium">
          {totalSteps} {totalSteps === 1 ? 'step' : 'steps'}
        </span>
        {!isExecuting && failedCount > 0 && (
          <span className="flex-shrink-0 text-xs px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-400 font-medium">
            {failedCount} failed
          </span>
        )}
        {isExecuting && (
          <div className="w-3 h-3 border-2 border-accent-brand/30 border-t-accent-brand rounded-full animate-spin flex-shrink-0" />
        )}
        {waitingMessage && isExecuting && (
          <span className="text-xs text-muted-foreground/60 flex-shrink-0 animate-pulse hidden md:inline">
            {waitingMessage}...
          </span>
        )}
      </div>

      {/* Open IDE button - desktop only */}
      {hasFileSystemTools && !isMobile && (
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => { e.stopPropagation(); onOpenIDE() }}
          className="h-6 px-2 text-xs gap-1.5 text-accent-brand/70 hover:text-accent-brand hover:bg-accent-brand/10 transition-colors flex-shrink-0"
        >
          <Code2 className="h-3 w-3" />
          <span>Open IDE</span>
        </Button>
      )}
    </div>
  )

  return (
    <>
      <div className="border-l-2 border-accent-brand/40 rounded-r overflow-hidden w-full max-w-full">
        {/* Desktop: Inline collapsible */}
        {!isMobile ? (
          <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
            <CollapsibleTrigger asChild>
              {TriggerHeader}
            </CollapsibleTrigger>
            <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
              <div className="px-2.5 pb-2.5">
                <div className="border border-border/40 rounded-lg bg-background/30 overflow-hidden">
                  <div className="p-3">
                    {ProcessContent}
                  </div>
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>
        ) : (
          /* Mobile: Just the trigger */
          TriggerHeader
        )}
      </div>

      {/* Mobile: Bottom sheet */}
      {isMobile && (
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetContent
            side="bottom"
            className="h-[85vh] rounded-t-2xl border-t-2 border-t-accent-brand p-0 overflow-hidden"
          >
            {/* Drag handle */}
            <div className="flex justify-center pt-3 pb-2">
              <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
            </div>

            <SheetHeader className="px-4 pb-3 border-b border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-accent-brand" />
                  <SheetTitle className="text-base">
                    {isExecuting ? (currentAction || 'Working...') : 'Process Details'}
                  </SheetTitle>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-accent-brand/10 text-accent-brand font-medium">
                    {totalSteps} {totalSteps === 1 ? 'step' : 'steps'}
                  </span>
                </div>
                {hasFileSystemTools && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => { setSheetOpen(false); onOpenIDE() }}
                    className="h-8 px-3 text-xs gap-1.5 text-accent-brand hover:text-accent-brand hover:bg-accent-brand/10"
                  >
                    <Code2 className="h-3.5 w-3.5" />
                    <span>Open IDE</span>
                  </Button>
                )}
              </div>
              {isExecuting && waitingMessage && (
                <SheetDescription className="animate-pulse">
                  {waitingMessage}...
                </SheetDescription>
              )}
            </SheetHeader>

            <div className="flex-1 h-[calc(85vh-90px)] overflow-y-auto overflow-x-hidden">
              <div className="p-4">
                {ProcessContent}
              </div>
            </div>
          </SheetContent>
        </Sheet>
      )}
    </>
  )
}

