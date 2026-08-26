/**
 * Hook for @mention autocomplete in message input
 *
 * Detects @server_name and @server_name:tool_name patterns
 * and provides autocomplete functionality for MCP servers and tools.
 * Also supports @knowledge for Knowledge Base queries.
 *
 * Coding agent tools with secondary pickers:
 * - @plan_implementation → shows issue picker
 * - @implement_plan → shows plan picker
 * - @edit_plan → shows plan picker
 * - @coding_agent → no secondary picker
 */

import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { useSubAgentStore } from '@/store/subAgentStore'
import { useMCPStore } from '@/store/mcpStore'
import { useProjectPanelStore } from '@/store/projectPanelStore'
import { codeSessionApi } from '@/api/codeSession'
import type { GitHubIssue, GitHubRepo } from '@/api/codeSession'
import type { AgentPlan } from '@/store/projectPanelStore'
import type { MCPServer } from '@/api/mcp'
import { conversationsAPI } from '@/api/conversations'
import apiClient from '@/api/client'
import { getDefaultModelParameters } from '@/config/modelParameters'

export interface MentionItem {
  id: string
  name: string
  displayName?: string
  description?: string
  icon?: string
  type?: 'server' | 'tool' | 'knowledge_base' | 'coding_agent' | 'media_tool' | 'sub_agent' | 'issue' | 'plan' | 'repo'
  agentSlug?: string
  issueNumber?: number
  issueLabels?: { name: string; color: string }[]
  planStatus?: string
  planProgress?: { completed: number; total: number }
  repoFullName?: string
  repoDefaultBranch?: string
  repoIsPrivate?: boolean
}

export interface MediaToolConfig {
  toolName: string
  category: 'image' | 'video'
  inputType?: string // video model input_type for filtering (text, image, video, image_audio)
  availableModels: { id: string; name: string; provider: string; inputType?: string }[]
  availableAspectRatios: string[]
  availableResolutions?: string[]
  availableDurations?: number[]
  availableQualities?: string[]
  selectedModel: string
  selectedAspectRatio: string
  selectedResolution?: string
  selectedDuration?: number
  selectedQuality?: string
}

/** A single entry in the `/settings/images/` endpoint's `available_models` list. */
interface ImageModelOption { id: string; name: string; provider?: string }
interface ImageModelsResponse { available_models?: ImageModelOption[]; preferred_image_model?: string }
/** A single entry in the `/settings/videos/` endpoint's `available_models` list. */
interface VideoModelOption { id?: string; canonical_id?: string; model_id?: string; name?: string; display_name?: string; provider?: string; input_type?: string }
interface VideoModelsResponse { available_models?: VideoModelOption[]; preferred_video_model?: string }

// User-friendly display names for coding agent tools
export const CODING_AGENT_DISPLAY_NAMES: Record<string, string> = {
  coding_agent: 'Coding Agent',
  plan_implementation: 'Plan Implementation',
  implement_plan: 'Implement Plan',
  edit_plan: 'Edit Plan',
}

// User-friendly display names for media tools
export const MEDIA_TOOL_DISPLAY_NAMES: Record<string, string> = {
  generate_image: 'Generate Image',
  generate_video: 'Generate Video',
  animate_image: 'Animate Image',
  animate_character: 'Animate Character',
}

// Map video tool names to their compatible input_types for model filtering
// Some models support multiple input types (e.g. image_video accepts both image and video)
const VIDEO_TOOL_COMPATIBLE_TYPES: Record<string, string[]> = {
  generate_video: ['text'],
  animate_image: ['image', 'image_video'],      // image_video models also accept image input
  animate_character: ['image_audio'],
}

// Knowledge Base mention item
const KNOWLEDGE_BASE_ITEMS: MentionItem[] = [
  {
    id: 'knowledge',
    name: 'knowledge',
    description: 'Search your knowledge base',
    icon: 'knowledge', // Special marker for knowledge base icon
    type: 'knowledge_base',
  },
]

// Coding Agent tool mention items
const CODING_AGENT_ITEMS: MentionItem[] = [
  {
    id: 'coding_agent',
    name: 'coding_agent',
    displayName: 'Coding Agent',
    description: 'Delegate complex coding tasks to an autonomous agent',
    type: 'coding_agent',
  },
  {
    id: 'plan_implementation',
    name: 'plan_implementation',
    displayName: 'Plan Implementation',
    description: 'Create an implementation plan for a GitHub issue',
    type: 'coding_agent',
  },
  {
    id: 'implement_plan',
    name: 'implement_plan',
    displayName: 'Implement Plan',
    description: 'Execute an approved implementation plan',
    type: 'coding_agent',
  },
  {
    id: 'edit_plan',
    name: 'edit_plan',
    displayName: 'Edit Plan',
    description: 'Edit an existing implementation plan',
    type: 'coding_agent',
  },
]

// Media tool mention items
const MEDIA_TOOL_ITEMS: MentionItem[] = [
  {
    id: 'generate_image',
    name: 'generate_image',
    displayName: 'Generate Image',
    description: 'Create an image with custom model & settings',
    type: 'media_tool',
  },
  {
    id: 'generate_video',
    name: 'generate_video',
    displayName: 'Generate Video',
    description: 'Text-to-video with custom model & settings',
    type: 'media_tool',
  },
  {
    id: 'animate_image',
    name: 'animate_image',
    displayName: 'Animate Image',
    description: 'Bring a static image to life as video',
    type: 'media_tool',
  },
  {
    id: 'animate_character',
    name: 'animate_character',
    displayName: 'Animate Character',
    description: 'Animate a character with a reference performance video',
    type: 'media_tool',
  },
]

// Mapping of coding agent tools to their secondary picker type
const TOOL_SECONDARY_PICKER: Record<string, 'issues' | 'plans'> = {
  plan_implementation: 'issues',
  implement_plan: 'plans',
  edit_plan: 'plans',
}

interface MentionState {
  start: number      // Position of @ in input
  serverQuery: string
  hasColon: boolean
  toolQuery: string
  matchedServer: MCPServer | null
}

export interface UseMentionAutocompleteReturn {
  isOpen: boolean
  mode: 'servers' | 'tools' | 'issues' | 'plans' | 'repos' | 'image_params' | 'video_params'
  query: string
  selectedServer: MCPServer | null
  items: MentionItem[]
  activeIndex: number
  triggerStart: number
  isLoadingSecondary: boolean
  secondaryPickerTool: string | null
  isCloningRepo: boolean
  cloningRepoName: string | null
  mediaConfig: MediaToolConfig | null
  handleKeyDown: (e: React.KeyboardEvent) => boolean
  selectItem: (item: MentionItem) => void
  updateMediaConfig: (config: MediaToolConfig) => void
  confirmMediaConfig: () => void
  close: () => void
}

/**
 * Detect @mention pattern at cursor position
 */
function detectMention(text: string, cursor: number, servers: MCPServer[]): MentionState | null {
  const beforeCursor = text.slice(0, cursor)

  // Match @ followed by optional server name, optional : and tool name
  // Must be at start or preceded by whitespace/punctuation (not word char)
  const atMatch = beforeCursor.match(/(?:^|[\s.,!?;:'"()\[\]{}])@([a-zA-Z0-9_-]*)(:([a-zA-Z0-9_-]*))?$/)

  if (!atMatch) return null

  const serverQuery = atMatch[1] || ''
  const hasColon = atMatch[2] !== undefined
  const toolQuery = atMatch[3] || ''

  // Find the @ position (accounting for potential preceding char)
  const matchStart = beforeCursor.lastIndexOf('@')
  if (matchStart === -1) return null

  // If we have a colon, try to match server name exactly
  let matchedServer: MCPServer | null = null
  if (hasColon && serverQuery) {
    matchedServer = servers.find(
      s => s.name.toLowerCase() === serverQuery.toLowerCase()
    ) || null
  }

  return {
    start: matchStart,
    serverQuery,
    hasColon,
    toolQuery,
    matchedServer
  }
}

/**
 * Filter servers by query string, including knowledge base mentions
 */
function filterServers(servers: MCPServer[], query: string, includeKnowledgeBase: boolean = true): MentionItem[] {
  const q = query.toLowerCase()

  // Filter knowledge base items first
  const kbItems = includeKnowledgeBase
    ? KNOWLEDGE_BASE_ITEMS.filter(item =>
        item.name.toLowerCase().includes(q) ||
        item.description?.toLowerCase().includes(q)
      )
    : []

  // Filter coding agent items
  const agentItems = CODING_AGENT_ITEMS.filter(item =>
    item.name.toLowerCase().includes(q) ||
    item.description?.toLowerCase().includes(q)
  )

  // Filter user's active sub-agents
  const subAgentItems: MentionItem[] = useSubAgentStore.getState().agents
    .filter(a => a.is_active)
    .filter(a =>
      a.name.toLowerCase().includes(q) ||
      a.description.toLowerCase().includes(q)
    )
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .slice(0, 5)
    .map(a => ({
      id: `sub-agent-${a.id}`,
      name: a.name,
      displayName: a.name,
      description: a.description,
      type: 'sub_agent' as const,
      agentSlug: a.name,
    }))

  // Filter media tool items
  const mediaItems = MEDIA_TOOL_ITEMS.filter(item =>
    item.name.toLowerCase().includes(q) ||
    item.displayName?.toLowerCase().includes(q) ||
    item.description?.toLowerCase().includes(q)
  )

  const builtInCount = kbItems.length + agentItems.length + subAgentItems.length + mediaItems.length

  // Filter MCP servers
  const serverItems = servers
    .filter(s =>
      s.name.toLowerCase().includes(q) ||
      (s.description?.toLowerCase().includes(q))
    )
    .slice(0, 10 - builtInCount) // Leave room for built-in items
    .map(s => ({
      id: s.id,
      name: s.name,
      description: s.description,
      icon: s.icon_url,
      type: 'server' as const,
    }))

  return [...kbItems, ...agentItems, ...subAgentItems, ...mediaItems, ...serverItems]
}

interface ToolLike {
  id: string
  name: string
  description?: string
}

/**
 * Filter tools by query string
 * Works with both MCPTool[] and MCPToolMinimal[]
 */
function filterTools(tools: ToolLike[], query: string): MentionItem[] {
  const q = query.toLowerCase()
  return tools
    .filter(t =>
      t.name.toLowerCase().includes(q) ||
      t.description?.toLowerCase().includes(q)
    )
    .slice(0, 10) // Limit to 10 results
    .map(t => ({
      id: t.id,
      name: t.name,
      description: t.description
    }))
}

export function useMentionAutocomplete(
  inputValue: string,
  cursorPosition: number,
  mcpEnabled: boolean,
  onInsert: (newText: string, newCursorPos: number) => void,
  onCloneComplete?: (conversationId: string) => void
): UseMentionAutocompleteReturn {
  const [activeIndex, setActiveIndex] = useState(0)
  const [isOpen, setIsOpen] = useState(false)

  // Secondary picker state
  const [secondaryMode, setSecondaryMode] = useState<'issues' | 'plans' | 'repos' | 'image_params' | 'video_params' | null>(null)
  const [secondaryPickerTool, setSecondaryPickerTool] = useState<string | null>(null)
  const [secondaryItems, setSecondaryItems] = useState<MentionItem[]>([])
  const [isLoadingSecondary, setIsLoadingSecondary] = useState(false)
  const [secondaryQuery, setSecondaryQuery] = useState('')

  // Media tool parameter picker state
  const [mediaConfig, setMediaConfig] = useState<MediaToolConfig | null>(null)

  // Repo cloning state
  const [isCloningRepo, setIsCloningRepo] = useState(false)
  const [cloningRepoName, setCloningRepoName] = useState<string | null>(null)

  // Track the cursor position after tool name insertion for filtering
  const secondaryInsertEnd = useRef<number>(0)

  // Get MCP data from store
  const servers = useMCPStore(state => state.servers)
  const getActiveServers = useMCPStore(state => state.getActiveServers)

  // Active servers only
  const activeServers = useMemo(() => getActiveServers(), [servers])

  // Lazy-load sub-agents when a mention is first detected
  const subAgentsFetched = useRef(false)
  useEffect(() => {
    if (!subAgentsFetched.current) {
      subAgentsFetched.current = true
      useSubAgentStore.getState().fetchAgents()
    }
  }, [])

  // Detect mention at cursor position
  const mention = useMemo(() => {
    return detectMention(inputValue, cursorPosition, activeServers)
  }, [inputValue, cursorPosition, activeServers])

  // When in secondary mode, track what the user types after the tool name for filtering
  useEffect(() => {
    if (secondaryMode && secondaryInsertEnd.current > 0) {
      const textAfterTool = inputValue.slice(secondaryInsertEnd.current, cursorPosition)
      setSecondaryQuery(textAfterTool.trim())
    }
  }, [inputValue, cursorPosition, secondaryMode])

  // Reset secondary picker when user deletes the @tool_name from the input entirely
  useEffect(() => {
    if (secondaryMode && secondaryPickerTool) {
      const toolPattern = `@${secondaryPickerTool}`
      if (!inputValue.includes(toolPattern)) {
        setSecondaryMode(null)
        setSecondaryPickerTool(null)
        setSecondaryItems([])
        setIsLoadingSecondary(false)
        setSecondaryQuery('')
        setMediaConfig(null)
        secondaryInsertEnd.current = 0
      }
    }
  }, [inputValue, secondaryMode, secondaryPickerTool])

  // Determine mode and filter items
  const { mode, items, selectedServer, query } = useMemo(() => {
    // Secondary mode overrides normal computation
    if (secondaryMode) {
      // Media param modes don't use item lists - they render a form
      if (secondaryMode === 'image_params' || secondaryMode === 'video_params') {
        return {
          mode: secondaryMode,
          items: [],
          selectedServer: null,
          query: '',
        }
      }

      const q = secondaryQuery.toLowerCase()
      let filtered: MentionItem[]
      if (secondaryMode === 'repos') {
        filtered = q
          ? secondaryItems.filter(item =>
              item.name.toLowerCase().includes(q) ||
              (item.description?.toLowerCase().includes(q))
            )
          : secondaryItems
      } else {
        filtered = q
          ? secondaryItems.filter(item =>
              item.name.toLowerCase().includes(q) ||
              (item.issueNumber && `#${item.issueNumber}`.includes(q)) ||
              (item.issueNumber && String(item.issueNumber).includes(q))
            )
          : secondaryItems
      }

      return {
        mode: secondaryMode,
        items: filtered,
        selectedServer: null,
        query: secondaryQuery
      }
    }

    if (!mention) {
      return {
        mode: 'servers' as const,
        items: [],
        selectedServer: null,
        query: ''
      }
    }

    if (mention.hasColon && mention.matchedServer) {
      // Tool mode: show tools for the matched server
      const serverTools = mention.matchedServer.tools || []
      return {
        mode: 'tools' as const,
        items: filterTools(serverTools, mention.toolQuery),
        selectedServer: mention.matchedServer,
        query: mention.toolQuery
      }
    }

    // Server mode: show filtered servers and knowledge base items
    const filteredItems = filterServers(activeServers, mention.serverQuery, true)
    return {
      mode: 'servers' as const,
      items: filteredItems,
      selectedServer: null,
      query: mention.serverQuery
    }
  }, [mention, activeServers, secondaryMode, secondaryItems, secondaryQuery])

  // Update isOpen based on mention detection and secondary mode
  useEffect(() => {
    if (secondaryMode) {
      // Keep open during secondary mode (even if items are loading/empty)
      setIsOpen(true)
    } else {
      setIsOpen(mention !== null && items.length > 0)
    }
  }, [mention, items.length, secondaryMode])

  // Reset active index when items change
  useEffect(() => {
    setActiveIndex(0)
  }, [items])

  // Fetch issues for secondary picker
  const fetchIssues = useCallback(async () => {
    const clonedRepo = useProjectPanelStore.getState().clonedRepo
    if (!clonedRepo?.full_name) {
      setSecondaryItems([])
      setIsLoadingSecondary(false)
      return
    }

    setIsLoadingSecondary(true)
    try {
      const [owner, repo] = clonedRepo.full_name.split('/')
      const response = await codeSessionApi.getIssues(owner, repo, 1, 30, 'open')
      const issueItems: MentionItem[] = response.data.results.map((issue: GitHubIssue) => ({
        id: `issue-${issue.number}`,
        name: issue.title,
        description: `#${issue.number}`,
        type: 'issue' as const,
        issueNumber: issue.number,
        issueLabels: issue.labels,
      }))
      setSecondaryItems(issueItems)
    } catch {
      setSecondaryItems([])
    } finally {
      setIsLoadingSecondary(false)
    }
  }, [])

  // Fetch plans for secondary picker
  const fetchPlans = useCallback(async () => {
    const clonedRepo = useProjectPanelStore.getState().clonedRepo
    setIsLoadingSecondary(true)
    try {
      const response = await codeSessionApi.getPlans({
        repoFullName: clonedRepo?.full_name || undefined,
      })
      const planItems: MentionItem[] = response.data.results
        .filter((plan: AgentPlan) => plan.status === 'ready' || plan.status === 'completed')
        .map((plan: AgentPlan) => ({
          id: plan.id,
          name: plan.title,
          description: plan.task_description,
          type: 'plan' as const,
          planStatus: plan.status,
          planProgress: plan.progress,
        }))
      setSecondaryItems(planItems)
    } catch {
      setSecondaryItems([])
    } finally {
      setIsLoadingSecondary(false)
    }
  }, [])

  // Fetch GitHub repos for secondary picker
  const fetchRepos = useCallback(async () => {
    setIsLoadingSecondary(true)
    try {
      const statusResponse = await codeSessionApi.getGitHubStatus()
      if (!statusResponse.data.connected) {
        // Show a "Connect GitHub" placeholder
        setSecondaryItems([{
          id: 'connect-github',
          name: 'Connect GitHub',
          description: 'Connect your GitHub account to browse repositories',
          type: 'repo' as const,
        }])
        setIsLoadingSecondary(false)
        return
      }
      const response = await codeSessionApi.getRepos(1, 50)
      const repoItems: MentionItem[] = response.data.results.map((repo: GitHubRepo) => ({
        id: `repo-${repo.id}`,
        name: repo.full_name,
        description: repo.description || undefined,
        type: 'repo' as const,
        repoFullName: repo.full_name,
        repoDefaultBranch: repo.default_branch,
        repoIsPrivate: repo.private,
      }))
      setSecondaryItems(repoItems)
    } catch {
      setSecondaryItems([])
    } finally {
      setIsLoadingSecondary(false)
    }
  }, [])

  // Fetch image models for media parameter picker
  const fetchImageModels = useCallback(async () => {
    setIsLoadingSecondary(true)
    try {
      const response = await apiClient.get<ImageModelsResponse>('/settings/images/')
      const data = response.data
      const models = (data.available_models || []).map((m) => ({
        id: m.id,
        name: m.name,
        provider: m.provider || 'Google',
      }))
      const preferredModel = data.preferred_image_model || models[0]?.id || ''
      setMediaConfig({
        toolName: 'generate_image',
        category: 'image',
        availableModels: models,
        availableAspectRatios: ['1:1', '16:9', '9:16', '4:3', '3:4'],
        availableResolutions: ['1K', '2K', '4K'],
        selectedModel: preferredModel,
        selectedAspectRatio: '1:1',
        selectedResolution: '1K',
      })
    } catch (err) {
      console.error('[useMentionAutocomplete] Failed to fetch image models:', err)
      // Fallback config
      setMediaConfig({
        toolName: 'generate_image',
        category: 'image',
        availableModels: [],
        availableAspectRatios: ['1:1', '16:9', '9:16', '4:3', '3:4'],
        availableResolutions: ['1K', '2K', '4K'],
        selectedModel: '',
        selectedAspectRatio: '1:1',
        selectedResolution: '1K',
      })
    } finally {
      setIsLoadingSecondary(false)
    }
  }, [])

  // Fetch video models for media parameter picker, filtered by tool's input_type
  const fetchVideoModels = useCallback(async (toolName: string) => {
    setIsLoadingSecondary(true)
    const compatibleTypes = VIDEO_TOOL_COMPATIBLE_TYPES[toolName] || ['text']
    try {
      const response = await apiClient.get<VideoModelsResponse>('/settings/videos/')
      const data = response.data

      // Map all models with their input_type
      const allModels = (data.available_models || []).map((m) => ({
        id: m.canonical_id || m.id || m.model_id || '',
        name: m.name || m.display_name || '',
        provider: m.provider || '',
        inputType: m.input_type || 'text',
      }))

      // Filter to only models compatible with this tool's input type(s)
      const filteredModels = allModels.filter((m) => compatibleTypes.includes(m.inputType))

      // Pick preferred: user's preferred if compatible, else first filtered model
      const userPreferred = data.preferred_video_model || ''
      const preferredModel = filteredModels.find((m) => m.id === userPreferred)?.id
        || filteredModels[0]?.id || ''

      // Build config based on tool type
      const isTextToVideo = toolName === 'generate_video'
      const isAnimateImage = toolName === 'animate_image'

      setMediaConfig({
        toolName,
        category: 'video',
        inputType: compatibleTypes[0],
        availableModels: filteredModels,
        availableAspectRatios: isTextToVideo ? ['16:9', '9:16', '1:1'] : [],
        availableDurations: isTextToVideo ? [4, 5, 6, 8, 10] : isAnimateImage ? [5, 10] : undefined,
        availableQualities: isTextToVideo ? ['standard', 'pro'] : undefined,
        selectedModel: preferredModel,
        selectedAspectRatio: isTextToVideo ? '16:9' : '',
        selectedDuration: isTextToVideo ? 4 : isAnimateImage ? 5 : undefined,
        selectedQuality: isTextToVideo ? 'standard' : undefined,
      })
    } catch (err) {
      console.error('[useMentionAutocomplete] Failed to fetch video models:', err)
      setMediaConfig({
        toolName,
        category: 'video',
        inputType: compatibleTypes[0],
        availableModels: [],
        availableAspectRatios: toolName === 'generate_video' ? ['16:9', '9:16', '1:1'] : [],
        availableDurations: toolName === 'generate_video' ? [4, 5, 6, 8, 10] : toolName === 'animate_image' ? [5, 10] : undefined,
        availableQualities: toolName === 'generate_video' ? ['standard', 'pro'] : undefined,
        selectedModel: '',
        selectedAspectRatio: toolName === 'generate_video' ? '16:9' : '',
        selectedDuration: toolName === 'generate_video' ? 4 : toolName === 'animate_image' ? 5 : undefined,
        selectedQuality: toolName === 'generate_video' ? 'standard' : undefined,
      })
    } finally {
      setIsLoadingSecondary(false)
    }
  }, [])

  // Handle repo clone: create conversation, clone repo, navigate
  const handleRepoClone = useCallback(async (item: MentionItem) => {
    if (!item.repoFullName || !onCloneComplete) return

    setIsCloningRepo(true)
    setCloningRepoName(item.repoFullName)

    try {
      // 1. Create a new conversation
      const conversation = await conversationsAPI.createConversation({
        name: `Coding: ${item.repoFullName}`,
      })

      // 2. Create a chat in that conversation
      await conversationsAPI.createChat(conversation.id, {
        parameters: getDefaultModelParameters(),
      })

      // 3. Clone the repo
      const cloneResponse = await codeSessionApi.cloneRepo(conversation.id, {
        repo_url: `https://github.com/${item.repoFullName}.git`,
        branch: item.repoDefaultBranch || 'main',
      })

      // 4. Update the project panel store
      if (cloneResponse.data.success) {
        useProjectPanelStore.getState().setClonedRepo({
          id: conversation.id,
          full_name: cloneResponse.data.full_name || item.repoFullName,
          clone_url: `https://github.com/${item.repoFullName}.git`,
          default_branch: item.repoDefaultBranch || 'main',
          current_branch: cloneResponse.data.branch || item.repoDefaultBranch || 'main',
          workspace_path: cloneResponse.data.workspace_path || '',
          head_commit_sha: cloneResponse.data.head_commit_sha || '',
          head_commit_message: cloneResponse.data.head_commit_message || '',
          cloned_at: new Date().toISOString(),
        })
      }

      // 5. Save pending secondary picker info
      const pickerType = secondaryPickerTool ? TOOL_SECONDARY_PICKER[secondaryPickerTool] : null
      if (secondaryPickerTool && pickerType) {
        sessionStorage.setItem('mention_pending_secondary', JSON.stringify({
          toolName: secondaryPickerTool,
          pickerType,
        }))
      }

      // 6. Close dropdown and navigate
      setIsOpen(false)
      setSecondaryMode(null)
      setSecondaryPickerTool(null)
      setSecondaryItems([])
      setSecondaryQuery('')
      secondaryInsertEnd.current = 0
      onCloneComplete(conversation.id)
    } catch (error) {
      console.error('[useMentionAutocomplete] Clone failed:', error)
    } finally {
      setIsCloningRepo(false)
      setCloningRepoName(null)
    }
  }, [onCloneComplete, secondaryPickerTool])

  // Select an item and insert into input
  const selectItem = useCallback((item: MentionItem) => {
    if (!mention && !secondaryMode) return

    // Handle repo selection from secondary picker
    if (item.type === 'repo' && secondaryPickerTool) {
      if (item.id === 'connect-github') {
        // Trigger GitHub OAuth flow
        codeSessionApi.connectGitHub().then((response) => {
          const returnUrl = window.location.href
          sessionStorage.setItem('github_oauth_return_url', returnUrl)
          window.location.href = response.data.authorization_url
        }).catch(console.error)
        return
      }
      // Clone the selected repo
      handleRepoClone(item)
      return
    }

    // Handle secondary picker selections
    if (item.type === 'issue' && secondaryPickerTool) {
      // Insert: @tool_name #number Title
      const before = inputValue.slice(0, mention?.start ?? 0)
      // Remove any text typed for filtering after the tool name
      const afterCursor = inputValue.slice(cursorPosition)
      const insertText = `@${secondaryPickerTool} #${item.issueNumber} ${item.name} `
      const newText = before + insertText + afterCursor
      const newCursorPos = before.length + insertText.length

      onInsert(newText, newCursorPos)
      setIsOpen(false)
      setSecondaryMode(null)
      setSecondaryPickerTool(null)
      setSecondaryItems([])
      setSecondaryQuery('')
      secondaryInsertEnd.current = 0
      return
    }

    if (item.type === 'plan' && secondaryPickerTool) {
      // Insert: @tool_name plan:uuid Title
      const before = inputValue.slice(0, mention?.start ?? 0)
      const afterCursor = inputValue.slice(cursorPosition)
      const insertText = `@${secondaryPickerTool} plan:${item.id} ${item.name} `
      const newText = before + insertText + afterCursor
      const newCursorPos = before.length + insertText.length

      onInsert(newText, newCursorPos)
      setIsOpen(false)
      setSecondaryMode(null)
      setSecondaryPickerTool(null)
      setSecondaryItems([])
      setSecondaryQuery('')
      secondaryInsertEnd.current = 0
      return
    }

    if (!mention) return

    const before = inputValue.slice(0, mention.start)
    const after = inputValue.slice(cursorPosition)

    // Handle sub-agent selection - insert @coding_agent with delegation instruction
    if (item.type === 'sub_agent' && item.agentSlug) {
      const insertText = `@coding_agent Delegate to the "${item.agentSlug}" sub-agent. `
      const newText = before + insertText + after
      const newCursorPos = before.length + insertText.length
      onInsert(newText, newCursorPos)
      setIsOpen(false)
      return
    }

    // Handle media tool selection - open parameter picker
    if (item.type === 'media_tool') {
      const insertText = `@${item.name} `
      const newText = before + insertText + after
      const newCursorPos = before.length + insertText.length

      onInsert(newText, newCursorPos)

      secondaryInsertEnd.current = newCursorPos

      const isImage = item.name === 'generate_image'
      setSecondaryMode(isImage ? 'image_params' : 'video_params')
      setSecondaryPickerTool(item.name)
      setSecondaryQuery('')
      setActiveIndex(0)

      if (isImage) {
        fetchImageModels()
      } else {
        // All video tools (generate_video, animate_image, animate_character)
        fetchVideoModels(item.name)
      }
      return
    }

    // Check if this coding agent tool has a secondary picker
    if (item.type === 'coding_agent' && TOOL_SECONDARY_PICKER[item.name]) {
      // Insert @tool_name with space, then transition to secondary picker
      const insertText = `@${item.name} `
      const newText = before + insertText + after
      const newCursorPos = before.length + insertText.length

      onInsert(newText, newCursorPos)

      // Store the end position for filter tracking
      secondaryInsertEnd.current = newCursorPos

      const clonedRepo = useProjectPanelStore.getState().clonedRepo
      if (clonedRepo) {
        // Repo is already cloned - go straight to issues/plans picker
        const pickerType = TOOL_SECONDARY_PICKER[item.name]
        setSecondaryMode(pickerType)
        setSecondaryPickerTool(item.name)
        setSecondaryQuery('')
        setActiveIndex(0)

        if (pickerType === 'issues') {
          fetchIssues()
        } else {
          fetchPlans()
        }
      } else {
        // No repo cloned - show repo picker first
        setSecondaryMode('repos')
        setSecondaryPickerTool(item.name)
        setSecondaryQuery('')
        setActiveIndex(0)
        fetchRepos()
      }
      return
    }

    let insertText: string
    if (item.type === 'knowledge_base' || item.type === 'coding_agent') {
      // Insert @name with space after (ready for query/context)
      insertText = `@${item.name} `
    } else if (mode === 'servers') {
      // Insert server name, cursor after it for potential :tool
      insertText = `@${item.name}`
    } else {
      // Insert server:tool with space after
      insertText = `@${selectedServer?.name}:${item.name} `
    }

    const newText = before + insertText + after
    const newCursorPos = before.length + insertText.length

    onInsert(newText, newCursorPos)
    setIsOpen(false)
  }, [mention, inputValue, cursorPosition, mode, selectedServer, onInsert, secondaryMode, secondaryPickerTool, fetchIssues, fetchPlans, fetchRepos, handleRepoClone, fetchImageModels, fetchVideoModels])

  // Update media config (from parameter picker UI)
  const updateMediaConfig = useCallback((config: MediaToolConfig) => {
    setMediaConfig(config)
  }, [])

  // Confirm media config - insert bracket params into input
  const confirmMediaConfig = useCallback(() => {
    if (!mediaConfig || !secondaryPickerTool) return

    // Build bracket params based on category and tool type
    const params: string[] = []
    if (mediaConfig.selectedModel) {
      params.push(`model:${mediaConfig.selectedModel}`)
    }
    if (mediaConfig.selectedAspectRatio) {
      params.push(`ratio:${mediaConfig.selectedAspectRatio}`)
    }
    if (mediaConfig.category === 'image' && mediaConfig.selectedResolution) {
      params.push(`res:${mediaConfig.selectedResolution}`)
    }
    if (mediaConfig.category === 'video') {
      if (mediaConfig.selectedDuration != null) {
        params.push(`dur:${mediaConfig.selectedDuration}`)
      }
      if (mediaConfig.selectedQuality) {
        params.push(`quality:${mediaConfig.selectedQuality}`)
      }
    }

    const bracketBlock = `[${params.join(' ')}]`

    // Find the @tool_name in the input and replace "@tool_name " with "@tool_name [params] "
    const toolMention = `@${secondaryPickerTool} `
    const toolIdx = inputValue.indexOf(toolMention)
    if (toolIdx === -1) return

    const before = inputValue.slice(0, toolIdx)
    const afterTool = inputValue.slice(toolIdx + toolMention.length)
    const insertText = `@${secondaryPickerTool} ${bracketBlock} `
    const newText = before + insertText + afterTool
    const newCursorPos = before.length + insertText.length

    onInsert(newText, newCursorPos)

    // Close picker
    setIsOpen(false)
    setSecondaryMode(null)
    setSecondaryPickerTool(null)
    setSecondaryItems([])
    setSecondaryQuery('')
    setMediaConfig(null)
    secondaryInsertEnd.current = 0
  }, [mediaConfig, secondaryPickerTool, inputValue, onInsert])

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent): boolean => {
    if (!isOpen) return false

    // Media param modes: handle Enter to confirm, Escape to skip
    if (secondaryMode === 'image_params' || secondaryMode === 'video_params') {
      if (e.key === 'Enter') {
        e.preventDefault()
        confirmMediaConfig()
        return true
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setSecondaryMode(null)
        setSecondaryPickerTool(null)
        setMediaConfig(null)
        setSecondaryQuery('')
        secondaryInsertEnd.current = 0
        setIsOpen(false)
        return true
      }
      // Let other keys pass through (typing in the textarea)
      return false
    }

    // In secondary mode with no items yet (loading), still handle Escape
    if (secondaryMode && items.length === 0) {
      if (e.key === 'Escape') {
        e.preventDefault()
        setSecondaryMode(null)
        setSecondaryPickerTool(null)
        setSecondaryItems([])
        setSecondaryQuery('')
        secondaryInsertEnd.current = 0
        setIsOpen(false)
        return true
      }
      return false
    }

    if (items.length === 0) return false

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setActiveIndex(prev => (prev + 1) % items.length)
        return true

      case 'ArrowUp':
        e.preventDefault()
        setActiveIndex(prev => (prev - 1 + items.length) % items.length)
        return true

      case 'Enter':
      case 'Tab':
        e.preventDefault()
        selectItem(items[activeIndex])
        return true

      case 'Escape':
        e.preventDefault()
        if (secondaryMode) {
          // Close secondary picker, keep inserted tool text
          setSecondaryMode(null)
          setSecondaryPickerTool(null)
          setSecondaryItems([])
          setSecondaryQuery('')
          secondaryInsertEnd.current = 0
        }
        setIsOpen(false)
        return true

      default:
        return false
    }
  }, [isOpen, items, activeIndex, selectItem, secondaryMode, confirmMediaConfig])

  // Listen for triggerSecondaryPicker events (from ImmersiveChatView after navigation)
  useEffect(() => {
    const handler = (e: Event) => {
      const { toolName, pickerType } = (e as CustomEvent).detail
      setSecondaryMode(pickerType)
      setSecondaryPickerTool(toolName)
      setIsOpen(true)
      secondaryInsertEnd.current = inputValue.indexOf(`@${toolName} `) + `@${toolName} `.length
      if (pickerType === 'issues') fetchIssues()
      else fetchPlans()
    }
    window.addEventListener('triggerSecondaryPicker', handler)
    return () => window.removeEventListener('triggerSecondaryPicker', handler)
  }, [inputValue, fetchIssues, fetchPlans])

  // Close the dropdown
  const close = useCallback(() => {
    setIsOpen(false)
    if (secondaryMode) {
      setSecondaryMode(null)
      setSecondaryPickerTool(null)
      setSecondaryItems([])
      setSecondaryQuery('')
      setMediaConfig(null)
      secondaryInsertEnd.current = 0
    }
  }, [secondaryMode])

  return {
    isOpen,
    mode,
    query,
    selectedServer,
    items,
    activeIndex,
    triggerStart: mention?.start ?? 0,
    isLoadingSecondary,
    secondaryPickerTool,
    isCloningRepo,
    cloningRepoName,
    mediaConfig,
    handleKeyDown,
    selectItem,
    updateMediaConfig,
    confirmMediaConfig,
    close
  }
}
