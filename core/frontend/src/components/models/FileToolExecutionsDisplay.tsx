/**
 * FileToolExecutionsDisplay Component
 *
 * Displays file tool executions with visual feedback like Claude.ai:
 * - Shows each tool call with an icon
 * - Displays success/error state
 * - Shows arguments and results
 * - Special handling for execute_code with collapsible output
 */

import React, { useState, useMemo } from 'react'
import { Check, X, FileText, FolderOpen, Pencil, Trash2, FolderPlus, FileEdit, Loader2, Terminal, ChevronDown, ChevronRight, Image, Video, MapPin, Newspaper, Navigation, Store, Wind, Camera, Search, Code2, Copy, Building2, Palette, Wand2, Layers, ListTodo, Github, Maximize2, User, Play, Zap, BookOpen, ExternalLink, Film, Mic2, Server, Cpu, FolderGit2, Globe, Square, Activity, BrainCircuit } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { cn } from '@/lib/utils'
import { TypeBadge } from '@/lib/type-badges'
import { formatModelId } from '@/utils/modelNames'
import { FileIcon } from '@/components/sandbox/FileIcon'
import { FileListDisplay } from './FileListDisplay'
import { BraveSearchMediaCarousel } from './BraveSearchMediaCarousel'
import { SearchPlusIcon } from './icons/SearchPlusIcon'
import { useTheme } from '@/hooks/useTheme'
import { AssetImage } from './AssetImage'
import { VideoPlayer } from '@/components/videos/VideoPlayer'
import { CodingAgentDisplay } from './CodingAgentDisplay'
import { ListToolResultsDisplay, isListToolName, extractListToolData } from './ListToolResultsDisplay'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { CodingAgentStep, CodingAgentResult, CodingAgentQuestion } from '@/api/llm'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'

interface FileToolExecution {
  tool_call: {
    id: string
    type: 'function'
    function: {
      name: string
      arguments: string
    }
    display_name?: string  // User-friendly display name (from backend)
    server_icon_url?: string  // MCP server icon URL (from backend)
    server_icon_invert?: boolean  // Whether to invert icon in dark mode
  }
  result: any
  success: boolean | null
  isExecuting?: boolean  // True while tool is executing
  // Coding Agent specific fields
  coding_agent_steps?: CodingAgentStep[]  // Streamed execution steps
  coding_agent_result?: CodingAgentResult  // Final execution result
}

interface FileToolExecutionsDisplayProps {
  executions: FileToolExecution[]
  showBraveSearchMedia?: boolean  // Whether to show Brave Search media carousel (default: true for legacy, false when called from MessageSteps)
  variant?: 'chat' | 'code'  // 'code' uses dots instead of check/x, 'chat' is default
  onOpenIDE?: () => void  // Callback to open IDE for Coding Agent
  chatId?: string  // Chat ID for real-time progress tracking
  pendingCodingAgentQuestion?: CodingAgentQuestion | null
  onAnswerCodingAgentQuestion?: (chatId: string, answer: string) => void
}

// Map tool names to icons and display names
// If backendDisplayName is provided (from backend), use it instead of deriving from toolName
const getToolInfo = (toolName: string, backendDisplayName?: string) => {
  switch (toolName) {
    case 'read_file':
      return { icon: FileText, displayName: 'Read' }
    case 'write_file':
      return { icon: Pencil, displayName: 'Write' }
    case 'edit_file':
      return { icon: FileEdit, displayName: 'Edit' }
    case 'list_files':
      return { icon: FolderOpen, displayName: 'List' }
    case 'delete_file':
      return { icon: Trash2, displayName: 'Delete' }
    case 'create_directory':
      return { icon: FolderPlus, displayName: 'Create' }
    case 'rename_file':
      return { icon: FileEdit, displayName: 'Rename' }
    case 'execute_code':
      return { icon: Terminal, displayName: 'Execute code' }
    case 'run_bash':
      return { icon: Terminal, displayName: 'Run bash' }
    case 'brave_web_search':
      return { icon: SearchPlusIcon, displayName: 'Web search' }
    case 'brave_image_search':
      return { icon: Image, displayName: 'Image search' }
    case 'brave_video_search':
      return { icon: Video, displayName: 'Video search' }
    case 'brave_local_search':
      return { icon: MapPin, displayName: 'Local search' }
    case 'brave_news_search':
      return { icon: Newspaper, displayName: 'News search' }
    case 'fetch_web_page':
      return { icon: Globe, displayName: 'Fetch page' }
    case 'geocode_address':
      return { icon: MapPin, displayName: 'Geocode' }
    case 'get_directions':
      return { icon: Navigation, displayName: 'Directions' }
    case 'search_nearby_places':
      return { icon: Store, displayName: 'Places Search' }
    case 'get_air_quality':
      return { icon: Wind, displayName: 'Air Quality' }
    case 'get_street_view':
      return { icon: Camera, displayName: 'Street View' }
    case 'get_place_details':
      return { icon: Building2, displayName: 'Place Details' }
    case 'search_available_tools':
      return { icon: Search, displayName: 'Tool Discovery' }
    case 'get_tool_details':
      return { icon: FileText, displayName: 'Tool Details' }
    case 'search_code':
      return { icon: Search, displayName: 'Search' }
    case 'execute_programming_task':
      return { icon: Code2, displayName: 'Programming task' }
    case 'generate_image':
      return { icon: Palette, displayName: 'Generate Image' }
    case 'edit_image':
      return { icon: Wand2, displayName: 'Edit Image' }
    case 'create_image_variations':
      return { icon: Layers, displayName: 'Image Variations' }
    case 'generate_video':
      return { icon: Video, displayName: 'Generate Video' }
    case 'animate_image':
      return { icon: Play, displayName: 'Animate Image' }
    case 'upscale_video':
      return { icon: Maximize2, displayName: 'Upscale Video' }
    case 'animate_character':
      return { icon: User, displayName: 'Animate Character' }
    case 'update_todos':
      return { icon: ListTodo, displayName: 'Update tasks' }
    // GitHub tools
    case 'github_list_issues':
      return { icon: Github, displayName: 'List issues' }
    case 'github_get_issue':
      return { icon: Github, displayName: 'Get issue' }
    case 'github_create_issue':
      return { icon: Github, displayName: 'Create issue' }
    case 'github_update_issue':
      return { icon: Github, displayName: 'Update issue' }
    case 'github_list_pull_requests':
      return { icon: Github, displayName: 'List PRs' }
    case 'github_get_pull_request':
      return { icon: Github, displayName: 'Get PR' }
    case 'github_create_pull_request':
      return { icon: Github, displayName: 'Create PR' }
    case 'github_list_repos':
      return { icon: Github, displayName: 'List repos' }
    case 'github_get_repo':
      return { icon: Github, displayName: 'Get repo' }
    case 'github_search_code':
      return { icon: Github, displayName: 'Search code' }
    case 'github_get_file_contents':
      return { icon: Github, displayName: 'Get file' }
    case 'github_list_commits':
      return { icon: Github, displayName: 'List commits' }
    case 'github_list_branches':
      return { icon: Github, displayName: 'List branches' }
    case 'prepare_pull_request':
      return { icon: Github, displayName: 'Prepare PR' }
    case 'clone_repo':
      return { icon: FolderGit2, displayName: 'Clone Repo' }
    case 'list_processes':
      return { icon: Server, displayName: 'List Processes' }
    case 'check_process_health':
      return { icon: Activity, displayName: 'Check Health' }
    case 'start_preview':
      return { icon: Globe, displayName: 'Starting Preview' }
    case 'stop_preview':
      return { icon: Square, displayName: 'Stopping Preview' }
    case 'coding_agent':
    case 'plan_implementation':
    case 'implement_plan':
    case 'edit_plan':
      return { icon: Terminal, displayName: 'Coding Agent' }
    case 'create_spark':
      return { icon: Zap, displayName: 'Create Spark' }
    case 'update_spark':
      return { icon: Zap, displayName: 'Update Spark' }
    case 'query_knowledge_base':
      return { icon: BookOpen, displayName: 'Knowledge Base' }
    case 'list_knowledge_base_documents':
      return { icon: BookOpen, displayName: 'List Documents' }
    // List tools
    case 'list_sparks':
      return { icon: Zap, displayName: 'List Sparks' }
    case 'list_generated_images':
      return { icon: Image, displayName: 'List Images' }
    case 'list_generated_videos':
      return { icon: Film, displayName: 'List Videos' }
    case 'list_voice_rooms':
      return { icon: Mic2, displayName: 'List Voice Rooms' }
    case 'list_mcp_servers':
      return { icon: Server, displayName: 'List MCP Servers' }
    case 'list_available_models':
      return { icon: Cpu, displayName: 'List Models' }
    case 'compare_models':
      return { icon: Cpu, displayName: 'Compare Models' }
    // Coding agents (sub-agents) tools
    case 'list_coding_agents':
      return { icon: BrainCircuit, displayName: 'List Coding Agents' }
    case 'update_coding_agent':
      return { icon: BrainCircuit, displayName: 'Update Coding Agent' }
    // Asset access tools
    case 'get_image':
      return { icon: Image, displayName: 'Get Image' }
    case 'get_video':
      return { icon: Film, displayName: 'Get Video' }
    case 'get_spark':
      return { icon: Zap, displayName: 'Get Spark' }
    case 'get_document':
      return { icon: FileText, displayName: 'Get Document' }
    case 'export_asset':
      return { icon: ExternalLink, displayName: 'Export Asset' }
    case 'save_asset_to_workspace':
      return { icon: FolderPlus, displayName: 'Save to Workspace' }
    default:
      // Handle any other github_ prefixed tools
      if (toolName.startsWith('github_')) {
        return { icon: Github, displayName: backendDisplayName || formatToolName(toolName.replace('github_', '')) }
      }
      // Use backend display name if provided, otherwise format the tool name nicely
      return { icon: FileText, displayName: backendDisplayName || formatToolName(toolName) }
  }
}

// Helper to format tool names: snake_case -> Title Case
const formatToolName = (name: string): string => {
  return name
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

// Extract file path from arguments (for icon display)
const getFilePath = (toolName: string, argumentsStr: string): string | null => {
  try {
    const args = JSON.parse(argumentsStr)
    switch (toolName) {
      case 'read_file':
      case 'write_file':
      case 'edit_file':
      case 'delete_file':
      case 'list_files':
      case 'create_directory':
        return args.path || null
      case 'rename_file':
        return args.new_path || args.old_path || null
      default:
        return null
    }
  } catch {
    return null
  }
}

// Parse nested JSON/object structures
const deepParse = (val: any): any => {
  if (typeof val === 'string') {
    try { return deepParse(JSON.parse(val)) } catch { return val }
  }
  return val
}

// Extract line count from read_file result
const getReadLineCount = (result: any): number | null => {
  if (!result) return null
  try {
    let data = deepParse(result)

    // Navigate nested structures: result.result.data or result.data
    if (data?.result) data = deepParse(data.result)
    if (data?.data) data = deepParse(data.data)

    // Check for lines field from backend
    if (typeof data?.lines === 'number') return data.lines

    // Count lines in content as fallback
    const content = data?.content
    if (typeof content === 'string') {
      return content.split('\n').length
    }
    return null
  } catch {
    return null
  }
}

// Extract key info from arguments
const getArgumentsDisplay = (toolName: string, argumentsStr: string) => {
  try {
    const args = JSON.parse(argumentsStr)
    switch (toolName) {
      case 'read_file':
        return args.path || 'unknown file'
      case 'write_file':
        return args.path || 'unknown file'
      case 'edit_file':
        return args.path || 'unknown file'
      case 'list_files':
        return args.path || '/workspace'
      case 'delete_file':
        return args.path || 'unknown file'
      case 'create_directory':
        return args.path || 'unknown directory'
      case 'rename_file':
        return `${args.old_path} → ${args.new_path}`
      case 'execute_code':
        return args.language || 'python'
      case 'run_bash':
        // Show command, truncated if too long
        const cmd = args.command || ''
        return cmd.length > 60 ? cmd.slice(0, 60) + '...' : cmd
      case 'brave_image_search':
      case 'brave_video_search':
        return args.query || 'unknown query'
      case 'search_available_tools':
        // Display query and optional category in a user-friendly format
        const query = args.query || ''
        const category = args.category ? ` (${args.category})` : ''
        return `"${query}"${category}`
      case 'execute_programming_task':
        // Display the task description
        return args.task_description || 'Programming task'
      case 'update_todos':
        // Count tasks by status
        const todos = args.todos || []
        const pending = todos.filter((t: any) => t.status === 'pending').length
        const inProgress = todos.filter((t: any) => t.status === 'in_progress').length
        const completed = todos.filter((t: any) => t.status === 'completed').length
        return `${completed}/${todos.length} done`
      default:
        return JSON.stringify(args, null, 2)
    }
  } catch {
    return argumentsStr
  }
}

// Extract media items from Brave Search results
const extractBraveSearchMedia = (toolName: string, executionResult: any) => {
  

  // The executionResult is {tool_call, result, success}
  // We need to access result.result or result directly
  let braveResult = executionResult

  // If executionResult has a nested result property, use that
  if (executionResult && typeof executionResult === 'object' && 'result' in executionResult) {
    braveResult = executionResult.result
    
  }

  // Parse result if it's a JSON string
  if (typeof braveResult === 'string') {
    try {
      braveResult = JSON.parse(braveResult)
    } catch (e) {
      console.error('[BraveSearchMedia] Failed to parse result:', e)
      return null
    }
  }

  

  // Check if this is a Brave Search result with media
  if (!braveResult || !braveResult.results || !Array.isArray(braveResult.results)) {
    
    return null
  }

  const items: any[] = []

  // Extract images
  if (toolName === 'brave_image_search') {
    
    braveResult.results.forEach((item: any, index: number) => {
      
      if (item.thumbnail && item.thumbnail.src) {
        const mediaItem = {
          type: 'image',
          thumbnail: item.thumbnail.src,
          url: item.url || item.properties?.url || '',
          title: item.title || item.properties?.title,
          source: item.source || item.properties?.domain,
          width: item.properties?.width,
          height: item.properties?.height
        }
        
        items.push(mediaItem)
      }
    })
  }

  // Extract videos
  if (toolName === 'brave_video_search') {
    
    braveResult.results.forEach((item: any, index: number) => {
      
      if (item.thumbnail && item.thumbnail.src) {
        const mediaItem = {
          type: 'video',
          thumbnail: item.thumbnail.src,
          url: item.url || item.page_url || '',
          title: item.title,
          source: item.creator || item.author,
          duration: item.duration,
          views: item.view_count ? `${item.view_count} views` : undefined
        }
        
        items.push(mediaItem)
      }
    })
  }


  return items.length > 0 ? items : null
}

// Knowledge Base result type
interface KnowledgeBaseResult {
  chunk_id: string
  document_id: string
  document_filename: string
  document_type: string
  content: string
  full_content: string
  chunk_index: number
  page_number: number | null
  similarity_score: number
  token_count: number
}

interface KnowledgeBaseSearchData {
  query: string
  total_results: number
  results: KnowledgeBaseResult[]
  formatted_text: string
}

// Extract knowledge base results from tool result
const extractKnowledgeBaseResults = (executionResult: any): KnowledgeBaseSearchData | null => {
  let result = executionResult

  // If executionResult has a nested result property, use that
  if (executionResult && typeof executionResult === 'object' && 'result' in executionResult) {
    result = executionResult.result
  }

  // Parse result if it's a JSON string
  if (typeof result === 'string') {
    try {
      result = JSON.parse(result)
    } catch {
      // Result might be a simple string message (e.g., "No relevant documents found")
      return null
    }
  }

  // Check if this is a valid knowledge base result
  if (!result || typeof result !== 'object' || !result.results || !Array.isArray(result.results)) {
    return null
  }

  return {
    query: result.query || '',
    total_results: result.total_results || result.results.length,
    results: result.results,
    formatted_text: result.formatted_text || '',
  }
}


// Knowledge Base Results Display Component
const KnowledgeBaseResultsDisplay = React.memo(({ data }: { data: KnowledgeBaseSearchData }) => {
  const [expandedChunks, setExpandedChunks] = useState<Set<string>>(new Set())
  const { isDark } = useTheme()

  if (!data.results || data.results.length === 0) return null

  const toggleChunk = (chunkId: string) => {
    setExpandedChunks(prev => {
      const next = new Set(prev)
      if (next.has(chunkId)) {
        next.delete(chunkId)
      } else {
        next.add(chunkId)
      }
      return next
    })
  }

  return (
    <div className={cn(
      "mt-2 ml-5 border rounded-lg overflow-hidden",
      isDark ? "border-border/60 bg-card/30" : "border-border bg-white"
    )}>
      {/* Header */}
      <div className={cn(
        "px-3 py-2 border-b flex items-center justify-between",
        isDark ? "bg-emerald-500/10 border-border/50" : "bg-emerald-50 border-emerald-200"
      )}>
        <span className={cn("text-sm font-medium", isDark ? "text-emerald-400" : "text-emerald-700")}>
          {data.total_results} result{data.total_results !== 1 ? 's' : ''} found
        </span>
        <span className={cn("text-xs", isDark ? "text-muted-foreground/60" : "text-slate-500")}>
          "{data.query}"
        </span>
      </div>

      {/* Results list */}
      <div className="divide-y divide-border/50">
        {data.results.map((result, index) => {
          const isExpanded = expandedChunks.has(result.chunk_id)
          const similarityPercent = Math.round(result.similarity_score * 100)

          return (
            <Collapsible
              key={result.chunk_id || index}
              open={isExpanded}
              onOpenChange={() => toggleChunk(result.chunk_id)}
              className={cn(
                "transition-colors",
                isDark ? "hover:bg-muted/20" : "hover:bg-slate-50"
              )}
            >
              {/* Result header */}
              <CollapsibleTrigger className="w-full px-3 py-2 cursor-pointer text-left">
                <div className="flex items-start gap-2">
                  {/* Expand/collapse icon */}
                  <div className="flex-shrink-0 mt-0.5">
                    <ChevronRight className={cn(
                      "w-3.5 h-3.5 transition-transform duration-200",
                      isExpanded && "rotate-90",
                      isDark ? "text-muted-foreground" : "text-slate-400"
                    )} />
                  </div>

                  {/* Document info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {/* File type badge */}
                      <TypeBadge type={result.document_type} />

                      {/* Filename */}
                      <span className={cn(
                        "text-sm font-medium truncate",
                        isDark ? "text-foreground" : "text-slate-800"
                      )}>
                        {result.document_filename}
                      </span>

                      {/* Page number */}
                      {result.page_number && (
                        <span className={cn(
                          "text-xs",
                          isDark ? "text-muted-foreground/60" : "text-slate-500"
                        )}>
                          Page {result.page_number}
                        </span>
                      )}

                      {/* Similarity score */}
                      <span className={cn(
                        "ml-auto text-xs font-mono",
                        similarityPercent >= 80
                          ? isDark ? "text-emerald-400" : "text-emerald-600"
                          : similarityPercent >= 60
                            ? isDark ? "text-amber-400" : "text-amber-600"
                            : isDark ? "text-muted-foreground" : "text-slate-500"
                      )}>
                        {similarityPercent}% match
                      </span>
                    </div>

                    {/* Content preview (always shown) */}
                    {!isExpanded && (
                      <p className={cn(
                        "mt-1 text-xs line-clamp-2",
                        isDark ? "text-muted-foreground" : "text-slate-600"
                      )}>
                        {result.content}
                      </p>
                    )}
                  </div>
                </div>
              </CollapsibleTrigger>

              {/* Expanded content */}
              <CollapsibleContent>
                <div className={cn(
                  "px-3 pb-3 ml-6",
                  isDark ? "border-l border-border/30" : "border-l border-slate-200"
                )}>
                  {/* Full content */}
                  <div className={cn(
                    "p-3 rounded-md text-xs font-mono whitespace-pre-wrap",
                    isDark ? "bg-muted/30 text-muted-foreground" : "bg-slate-50 text-slate-700"
                  )}>
                    {result.full_content || result.content}
                  </div>

                  {/* Metadata footer */}
                  <div className={cn(
                    "mt-2 flex items-center gap-4 text-[10px]",
                    isDark ? "text-muted-foreground/50" : "text-slate-400"
                  )}>
                    <span>Chunk #{result.chunk_index + 1}</span>
                    <span>{result.token_count} tokens</span>
                    <a
                      href={`/knowledge?doc=${result.document_id}`}
                      className={cn(
                        "flex items-center gap-1 transition-colors",
                        isDark
                          ? "text-emerald-400/70 hover:text-emerald-400"
                          : "text-emerald-600/70 hover:text-emerald-600"
                      )}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <ExternalLink className="w-3 h-3" />
                      View document
                    </a>
                  </div>
                </div>
              </CollapsibleContent>
            </Collapsible>
          )
        })}
      </div>
    </div>
  )
})

// Component for displaying write_file content (expandable)
const WriteFileContentResult = React.memo(({ result, filePath, args }: {
  result: any
  filePath?: string
  args?: { path?: string; content?: string }
}) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const { isDark } = useTheme()
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  // Get content from args (what was written) or try to extract from result
  let content = args?.content || ''

  // If no content in args, try to extract from result
  if (!content && result) {
    try {
      const parsed = typeof result === 'string' ? JSON.parse(result) : result
      content = parsed?.data?.content || parsed?.content || ''
    } catch {
      // ignore
    }
  }

  if (!content) return null

  const filename = filePath || args?.path || 'file'
  const lineCount = content.split('\n').length

  // Detect language from filename extension
  const getLanguage = (fname: string): string => {
    const ext = fname.split('.').pop()?.toLowerCase() || ''
    const langMap: Record<string, string> = {
      'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'tsx': 'tsx',
      'jsx': 'jsx', 'json': 'json', 'md': 'markdown', 'yml': 'yaml',
      'yaml': 'yaml', 'sh': 'bash', 'bash': 'bash', 'css': 'css',
      'html': 'html', 'sql': 'sql', 'go': 'go', 'rs': 'rust',
      'rb': 'ruby', 'java': 'java', 'cpp': 'cpp', 'c': 'c', 'h': 'c',
    }
    return langMap[ext] || 'text'
  }

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="ml-5">
      {/* Header - clickable to expand */}
      <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
        <ChevronRight className={cn(
          "h-3 w-3 transition-transform duration-200",
          isExpanded && "rotate-90"
        )} />
        <span className="text-emerald-500">+ {lineCount} lines written</span>
        <span className="text-muted-foreground/40">·</span>
        <span>{isExpanded ? 'Hide' : 'View content'}</span>
      </CollapsibleTrigger>

      {/* Content - animated */}
      <CollapsibleContent>
        <div className={cn(
          "mt-1.5 pl-3 border-l border-border/40 max-h-[300px] overflow-y-auto rounded-r",
          isDark ? "bg-card/30" : "bg-slate-50/50"
        )}>
          <SyntaxHighlighter
            language={getLanguage(filename)}
            style={codeTheme.style}
            showLineNumbers={true}
            wrapLongLines={true}
            customStyle={{
              margin: 0,
              padding: '0.5rem',
              background: 'transparent',
              fontSize: '0.65rem',
              lineHeight: '1.4',
            }}
            lineNumberStyle={{
              minWidth: '2em',
              paddingRight: '0.5em',
              color: isDark ? '#4a5568' : '#a0aec0',
              userSelect: 'none',
            }}
          >
            {content}
          </SyntaxHighlighter>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})

// Component for displaying edit_file diff inline like Coding Agent
const EditFileDiffResult = React.memo(({ result, filePath, args }: {
  result: any
  filePath?: string
  args?: { path?: string; old_content?: string; new_content?: string }
}) => {
  const [showFullDiff, setShowFullDiff] = useState(false)
  const { isDark } = useTheme()
  const MAX_VISIBLE_LINES = 15

  // Parse result - handles nested JSON strings
  const parseResult = (r: any): any => {
    if (typeof r === 'string') {
      try { return parseResult(JSON.parse(r)) } catch { return r }
    }
    return r
  }

  const parsedResult = parseResult(result)
  const actualResult = parsedResult?.result || parsedResult

  // Extract diff - could be in various places
  let diff = actualResult?.diff || actualResult?.data?.diff || parsedResult?.data?.diff || parsedResult?.diff

  // If no diff from result, generate one from args
  if (!diff && args?.old_content && args?.new_content) {
    // Generate a simple diff representation
    const oldLines = args.old_content.split('\n')
    const newLines = args.new_content.split('\n')
    const diffParts: string[] = []
    diffParts.push(`--- a/${args.path || filePath || 'file'}`)
    diffParts.push(`+++ b/${args.path || filePath || 'file'}`)
    diffParts.push(`@@ -1,${oldLines.length} +1,${newLines.length} @@`)
    oldLines.forEach(line => diffParts.push(`-${line}`))
    newLines.forEach(line => diffParts.push(`+${line}`))
    diff = diffParts.join('\n')
  }

  if (!diff) return null

  // Parse diff into structured lines with line numbers
  const parseDiff = (diffText: string) => {
    const lines = diffText.split('\n')
    const parsedLines: Array<{
      type: 'header' | 'hunk' | 'context' | 'added' | 'removed'
      content: string
      oldLineNum?: number
      newLineNum?: number
    }> = []

    let oldLine = 0
    let newLine = 0

    for (const line of lines) {
      if (line.startsWith('---') || line.startsWith('+++')) {
        parsedLines.push({ type: 'header', content: line })
      } else if (line.startsWith('@@')) {
        // Parse hunk header like @@ -113,19 +113,4 @@
        const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/)
        if (match) {
          oldLine = parseInt(match[1], 10)
          newLine = parseInt(match[2], 10)
        }
        parsedLines.push({ type: 'hunk', content: line })
      } else if (line.startsWith('-')) {
        parsedLines.push({ type: 'removed', content: line, oldLineNum: oldLine })
        oldLine++
      } else if (line.startsWith('+')) {
        parsedLines.push({ type: 'added', content: line, newLineNum: newLine })
        newLine++
      } else {
        // Context line (starts with space or empty)
        parsedLines.push({ type: 'context', content: line, oldLineNum: oldLine, newLineNum: newLine })
        oldLine++
        newLine++
      }
    }

    return parsedLines
  }

  const diffLines = parseDiff(diff)
  const addedCount = diffLines.filter(l => l.type === 'added').length
  const removedCount = diffLines.filter(l => l.type === 'removed').length
  const visibleLines = showFullDiff ? diffLines : diffLines.slice(0, MAX_VISIBLE_LINES)
  const hasMoreLines = diffLines.length > MAX_VISIBLE_LINES

  return (
    <Collapsible open={showFullDiff} onOpenChange={setShowFullDiff} className="ml-5">
      {/* Header - matches WriteFileContentResult style */}
      <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
        <ChevronRight className={cn(
          "h-3 w-3 transition-transform duration-200",
          showFullDiff && "rotate-90"
        )} />
        <span className="text-amber-500">
          {addedCount > 0 && `+${addedCount}`}
          {addedCount > 0 && removedCount > 0 && ' / '}
          {removedCount > 0 && <span className="text-red-400">-{removedCount}</span>}
          {addedCount === 0 && removedCount === 0 && 'No changes'}
        </span>
        <span className="text-muted-foreground/40">·</span>
        <span>{showFullDiff ? 'Hide diff' : 'View diff'}</span>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className={cn(
          "mt-1.5 pl-3 border-l border-border/40 overflow-hidden rounded-r",
          isDark ? "bg-card/30" : "bg-slate-50/50"
        )}>
          {/* Diff lines */}
          <div className="text-[10px] font-mono leading-[1.5] max-h-[250px] overflow-y-auto">
        {visibleLines.map((line, index) => {
          // Theme-aware styles based on line type - high contrast for light mode
          let bgClass = ''
          let textClass = isDark ? 'text-muted-foreground' : 'text-foreground/80'

          switch (line.type) {
            case 'header':
              bgClass = isDark ? 'bg-muted/30' : 'bg-slate-100'
              textClass = isDark ? 'text-muted-foreground/70' : 'text-slate-500'
              break
            case 'hunk':
              bgClass = isDark ? 'bg-blue-500/10' : 'bg-blue-50'
              textClass = isDark ? 'text-blue-400' : 'text-blue-700 font-medium'
              break
            case 'removed':
              bgClass = isDark ? 'bg-red-500/15' : 'bg-red-50'
              textClass = isDark ? 'text-red-400' : 'text-red-700'
              break
            case 'added':
              bgClass = isDark ? 'bg-emerald-500/15' : 'bg-emerald-50'
              textClass = isDark ? 'text-emerald-400' : 'text-emerald-700'
              break
            case 'context':
              textClass = isDark ? 'text-muted-foreground/80' : 'text-slate-600'
              break
          }

          const showLineNums = line.type !== 'header' && line.type !== 'hunk'

          return (
            <div
              key={index}
              className={cn("flex", bgClass)}
            >
              {/* Line numbers */}
              {showLineNums && (
                <div className={cn(
                  "flex-shrink-0 w-16 flex select-none border-r",
                  isDark ? "text-muted-foreground/40 border-border/30" : "text-slate-400 border-slate-200"
                )}>
                  <span className="w-8 text-right pr-1">
                    {line.type === 'added' ? '' : line.oldLineNum || ''}
                  </span>
                  <span className="w-8 text-right pr-1">
                    {line.type === 'removed' ? '' : line.newLineNum || ''}
                  </span>
                </div>
              )}
              {!showLineNums && (
                <div className={cn(
                  "flex-shrink-0 w-16 border-r",
                  isDark ? "border-border/30" : "border-slate-200"
                )} />
              )}

              {/* Content */}
              <pre className={cn("flex-1 px-2 whitespace-pre-wrap break-all", textClass)}>
                {line.type === 'header' || line.type === 'hunk'
                  ? line.content
                  : line.content.slice(1) || ' '}
              </pre>
            </div>
          )
        })}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})

// Component for displaying spark update diff
const SparkUpdateDiff = React.memo(({ result }: { result: any }) => {
  const [showFullDiff, setShowFullDiff] = useState(false)
  const { isDark } = useTheme()
  const MAX_VISIBLE_LINES = 15

  // Parse result - handles nested JSON strings
  const parseResult = (r: any): any => {
    if (typeof r === 'string') {
      try { return parseResult(JSON.parse(r)) } catch { return r }
    }
    return r
  }

  const parsedResult = parseResult(result)

  // Extract old and new code from spark result
  // Handle both direct spark and nested result.spark structures
  const spark = parsedResult?.spark || parsedResult?.result?.spark
  const oldCode = spark?.old_code
  const newCode = spark?.code
  const title = spark?.title || 'Spark'
  const version = spark?.version

  if (!oldCode || !newCode) return null

  // Generate diff from old and new code
  const oldLines = oldCode.split('\n')
  const newLines = newCode.split('\n')
  const diffParts: string[] = []
  diffParts.push(`--- a/${title} v${(version || 1) - 1}`)
  diffParts.push(`+++ b/${title} v${version || 1}`)
  diffParts.push(`@@ -1,${oldLines.length} +1,${newLines.length} @@`)
  oldLines.forEach((line: string) => diffParts.push(`-${line}`))
  newLines.forEach((line: string) => diffParts.push(`+${line}`))
  const diff = diffParts.join('\n')

  // Parse diff into structured lines
  const parseDiff = (diffText: string) => {
    const lines = diffText.split('\n')
    const parsedLines: Array<{
      type: 'header' | 'hunk' | 'context' | 'added' | 'removed'
      content: string
      oldLineNum?: number
      newLineNum?: number
    }> = []

    let oldLine = 0
    let newLine = 0

    for (const line of lines) {
      if (line.startsWith('---') || line.startsWith('+++')) {
        parsedLines.push({ type: 'header', content: line })
      } else if (line.startsWith('@@')) {
        const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/)
        if (match) {
          oldLine = parseInt(match[1], 10)
          newLine = parseInt(match[2], 10)
        }
        parsedLines.push({ type: 'hunk', content: line })
      } else if (line.startsWith('-')) {
        parsedLines.push({ type: 'removed', content: line, oldLineNum: oldLine })
        oldLine++
      } else if (line.startsWith('+')) {
        parsedLines.push({ type: 'added', content: line, newLineNum: newLine })
        newLine++
      } else {
        parsedLines.push({ type: 'context', content: line, oldLineNum: oldLine, newLineNum: newLine })
        oldLine++
        newLine++
      }
    }

    return parsedLines
  }

  const diffLines = parseDiff(diff)
  const visibleLines = showFullDiff ? diffLines : diffLines.slice(0, MAX_VISIBLE_LINES)
  const hasMoreLines = diffLines.length > MAX_VISIBLE_LINES

  return (
    <div className={cn(
      "mt-1.5 ml-5 border rounded-md overflow-hidden",
      isDark ? "border-border/60 bg-card/50" : "border-border bg-white"
    )}>
      {/* Header */}
      <div className={cn(
        "px-2 py-1 text-xs flex items-center gap-2 border-b",
        isDark ? "bg-amber-500/10 border-border/30" : "bg-amber-50 border-amber-200"
      )}>
        <Zap className={cn("w-3 h-3", isDark ? "text-amber-400" : "text-amber-600")} />
        <span className={isDark ? "text-amber-400" : "text-amber-700"}>
          Code changes in {title}
        </span>
      </div>

      {/* Diff lines */}
      <div className="text-[11px] font-mono leading-[1.6] max-h-[300px] overflow-y-auto">
        {visibleLines.map((line, index) => {
          let bgClass = ''
          let textClass = isDark ? 'text-muted-foreground' : 'text-foreground/80'

          switch (line.type) {
            case 'header':
              bgClass = isDark ? 'bg-muted/30' : 'bg-slate-100'
              textClass = isDark ? 'text-muted-foreground/70' : 'text-slate-500'
              break
            case 'hunk':
              bgClass = isDark ? 'bg-blue-500/10' : 'bg-blue-50'
              textClass = isDark ? 'text-blue-400' : 'text-blue-700 font-medium'
              break
            case 'removed':
              bgClass = isDark ? 'bg-red-500/15' : 'bg-red-50'
              textClass = isDark ? 'text-red-400' : 'text-red-700'
              break
            case 'added':
              bgClass = isDark ? 'bg-emerald-500/15' : 'bg-emerald-50'
              textClass = isDark ? 'text-emerald-400' : 'text-emerald-700'
              break
            case 'context':
              textClass = isDark ? 'text-muted-foreground/80' : 'text-slate-600'
              break
          }

          const showLineNums = line.type !== 'header' && line.type !== 'hunk'

          return (
            <div key={index} className={cn("flex", bgClass)}>
              {showLineNums && (
                <div className={cn(
                  "flex-shrink-0 w-16 flex select-none border-r",
                  isDark ? "text-muted-foreground/40 border-border/30" : "text-slate-400 border-slate-200"
                )}>
                  <span className="w-8 text-right pr-1">
                    {line.type === 'added' ? '' : line.oldLineNum || ''}
                  </span>
                  <span className="w-8 text-right pr-1">
                    {line.type === 'removed' ? '' : line.newLineNum || ''}
                  </span>
                </div>
              )}
              {!showLineNums && (
                <div className={cn(
                  "flex-shrink-0 w-16 border-r",
                  isDark ? "border-border/30" : "border-slate-200"
                )} />
              )}
              <pre className={cn("flex-1 px-2 whitespace-pre-wrap break-all", textClass)}>
                {line.type === 'header' || line.type === 'hunk'
                  ? line.content
                  : line.content.slice(1) || ' '}
              </pre>
            </div>
          )
        })}
      </div>

      {/* Show more link */}
      {hasMoreLines && !showFullDiff && (
        <button
          onClick={() => setShowFullDiff(true)}
          className={cn(
            "w-full py-1.5 text-center text-xs transition-colors border-t",
            isDark
              ? "text-muted-foreground hover:text-foreground hover:bg-muted/30 border-border/30"
              : "text-slate-500 hover:text-slate-700 hover:bg-slate-50 border-slate-200"
          )}
        >
          Show full diff ({diffLines.length - MAX_VISIBLE_LINES} more lines)
        </button>
      )}
    </div>
  )
})

// Helper to parse tool discovery result
const parseToolDiscoveryResult = (result: any) => {
  // Recursively parse JSON strings
  const parseJson = (val: any): any => {
    if (typeof val === 'string') {
      try { return parseJson(JSON.parse(val)) } catch { return val }
    }
    return val
  }

  // Unwrap nested result structures
  const unwrap = (obj: any): any => {
    if (!obj || typeof obj !== 'object') return obj
    // Try common wrapper patterns
    if (obj.result) return unwrap(obj.result)
    if (obj.data) return unwrap(obj.data)
    return obj
  }

  const parsed = parseJson(result)
  const toolsData = unwrap(parsed)

  // Extract found count - check multiple possible field names
  const foundCount = toolsData?.found || toolsData?.total || (toolsData?.tools?.length ?? 0)
  const availableCount = toolsData?.available ?? foundCount
  const tools = toolsData?.tools || []
  const disabledCount = foundCount - availableCount

  return { foundCount, availableCount, tools, disabledCount }
}

// Component for displaying discovered tools list (expandable)
const ToolDiscoveryResult = React.memo(({ result }: { result: any }) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const { tools } = parseToolDiscoveryResult(result)

  if (tools.length === 0) return null

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="ml-5">
      <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
        <ChevronRight className={cn(
          "h-3 w-3 transition-transform duration-200",
          isExpanded && "rotate-90"
        )} />
        <span>{isExpanded ? 'Hide' : 'Show'} tools</span>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="mt-1.5 space-y-1.5 pl-3 border-l border-border/40 max-h-[300px] overflow-y-auto">
          {tools.map((tool: any, index: number) => {
            const isDisabled = tool.status === 'disabled'
            const isNotConnected = tool.status === 'not_connected'
            const isUnavailable = isDisabled || isNotConnected
            return (
              <div key={index} className="text-xs">
                <div className="flex items-center gap-1.5 flex-wrap">
                  {tool.server_icon && (
                    <img
                      src={tool.server_icon}
                      alt=""
                      className={`w-3.5 h-3.5 object-contain flex-shrink-0 ${tool.server_icon_invert ? 'dark:invert' : ''}`}
                    />
                  )}
                  <span className={`font-mono ${isUnavailable ? 'text-muted-foreground/50' : 'text-accent-brand'}`}>
                    {tool.display_name || tool.name}
                  </span>
                  {isDisabled && tool.requires && (
                    <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 text-[10px]">
                      Requires: {tool.requires}
                    </span>
                  )}
                  {isNotConnected && tool.requires_connection && (
                    <a
                      href={`/connectors?server=${encodeURIComponent(tool.requires_connection)}`}
                      className="px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 text-[10px] hover:bg-blue-500/30 transition-colors cursor-pointer"
                      onClick={(e) => {
                        e.preventDefault()
                        window.location.href = `/connectors?server=${encodeURIComponent(tool.requires_connection)}`
                      }}
                    >
                      Connect: {tool.requires_connection}
                    </a>
                  )}
                </div>
                {tool.description && (
                  <div className={`ml-0 mt-0.5 ${isUnavailable ? 'text-muted-foreground/40' : 'text-muted-foreground/60'}`}>
                    {tool.description.slice(0, 80)}{tool.description.length > 80 ? '...' : ''}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})

// Component for displaying execute_code results with collapsible output
// Modern inline style matching RunBashDisplay
const ExecuteCodeResult = React.memo(({ result }: { result: any }) => {
  const [isExpanded, setIsExpanded] = useState(false)

  // Parse result if it's a JSON string
  let parsedResult = result
  if (typeof result === 'string') {
    try {
      parsedResult = JSON.parse(result)
    } catch {
      parsedResult = { output: result, error: null, exit_code: 1, execution_time: 0 }
    }
  }

  // Extract the actual execution result (it's nested in result.result)
  const executionResult = parsedResult?.result || parsedResult
  const { output, error, exit_code, execution_time, artifacts } = executionResult

  // Get orchestrator URL from environment (routes through API Gateway)
  const orchestratorUrl = import.meta.env.VITE_ORCHESTRATOR_URL || 'http://localhost:8080/api/v1/sandbox'

  const displayOutput = output || error
  const hasOutput = !!displayOutput || (artifacts && artifacts.length > 0)
  const isError = exit_code !== 0

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="flex-1 min-w-0 mt-1">
      {/* Inline header - execution time and artifacts only (parent shows success/error status) */}
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="text-sm flex items-center gap-1.5">
          {execution_time !== undefined && (
            <span className={cn(
              "text-xs font-mono",
              isError ? "text-red-400" : "text-muted-foreground"
            )}>
              {execution_time.toFixed(2)}s
            </span>
          )}
          {artifacts && artifacts.length > 0 && (
            <span className="text-muted-foreground text-xs">
              • {artifacts.length} file{artifacts.length > 1 ? 's' : ''}
            </span>
          )}
        </span>
        {hasOutput && (
          <CollapsibleTrigger
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors shrink-0"
          >
            <ChevronRight className={cn(
              "h-3 w-3 transition-transform duration-200",
              isExpanded && "rotate-90"
            )} />
          </CollapsibleTrigger>
        )}
      </div>

      {/* Expandable output - matches RunBashDisplay style */}
      {hasOutput && (
        <CollapsibleContent>
          <div className="mt-1 max-h-[400px] overflow-y-auto">
            {/* Artifacts (images, plots) */}
            {artifacts && artifacts.length > 0 && (
              <div className="space-y-2 mb-2">
                {artifacts.map((artifact: any, index: number) => {
                  const fullUrl = `${orchestratorUrl}${artifact.url}`
                  const filename = artifact.filename
                  return (
                    <div key={index} className="rounded border border-border/50 overflow-hidden bg-muted/30">
                      <div className="px-2 py-1 bg-muted/50 flex items-center justify-between">
                        <span className="text-xs font-mono text-muted-foreground">{filename}</span>
                        <a
                          href={fullUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-accent-brand hover:text-accent-brand/80"
                        >
                          Open
                        </a>
                      </div>
                      <div className="p-2">
                        <img
                          src={fullUrl}
                          alt={filename}
                          className="max-w-full h-auto rounded"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none'
                          }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Text/Error output */}
            {displayOutput && (
              <div className="flex">
                <span className="text-muted-foreground/60 mr-1 text-xs">⎿</span>
                <pre className={cn(
                  "text-xs font-mono whitespace-pre-wrap max-h-[300px] overflow-y-auto",
                  isError ? "text-red-400" : "text-muted-foreground"
                )}>
                  {sanitizeOutput(displayOutput)}
                </pre>
              </div>
            )}
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  )
})

// Helper to try parsing a value as JSON if it's a string
const tryParseJSON = (value: any): any => {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

// Helper to extract output from a string that looks like JSON but may be malformed
// Tries to find "output": "..." pattern and extract the value
const extractOutputFromString = (str: string): string | null => {
  // Try to find "output": "..." pattern
  const outputMatch = str.match(/"output"\s*:\s*"/)
  if (!outputMatch) return null

  const startIdx = outputMatch.index! + outputMatch[0].length
  let result = ''
  let i = startIdx
  let escaped = false

  // Parse the string value, handling escapes
  while (i < str.length) {
    const char = str[i]
    if (escaped) {
      // Handle escape sequences
      if (char === 'n') result += '\n'
      else if (char === 't') result += '\t'
      else if (char === 'r') result += '\r'
      else if (char === '\\') result += '\\'
      else if (char === '"') result += '"'
      else result += char
      escaped = false
    } else if (char === '\\') {
      escaped = true
    } else if (char === '"') {
      // End of string
      break
    } else {
      result += char
    }
    i++
  }

  return result
}

// Helper to extract bash output from various result formats
const extractBashOutput = (result: any): { output: string, error: string, exitCode?: number } => {
  // Handle null/undefined
  if (!result) return { output: '', error: '' }

  // If result is a string, first try to extract output directly using regex
  // This handles cases where JSON.parse fails due to malformed data
  if (typeof result === 'string' && result.includes('"output"')) {
    const extractedOutput = extractOutputFromString(result)
    if (extractedOutput) {
      return { output: extractedOutput, error: '' }
    }
  }

  // Parse if string
  let data = tryParseJSON(result)

  // Handle double-encoded JSON
  data = tryParseJSON(data)

  // Navigate through possible nested structures
  // Structure might be: { result: { data: { output } } } or { data: { output } } or { output }
  if (data?.result) {
    data = tryParseJSON(data.result)
  }
  if (data?.data) {
    data = tryParseJSON(data.data)
  }

  // Now data should be { output, error, exit_code } or just a string
  if (typeof data === 'string') {
    // If it still looks like JSON with output field, try to extract
    if (data.includes('"output"')) {
      const extractedOutput = extractOutputFromString(data)
      if (extractedOutput) {
        return { output: extractedOutput, error: '' }
      }
    }
    return { output: data, error: '' }
  }

  if (typeof data === 'object' && data !== null) {
    const output = typeof data.output === 'string' ? data.output : ''
    const error = typeof data.error === 'string' ? data.error : ''
    const exitCode = typeof data.exit_code === 'number' ? data.exit_code : undefined
    return { output, error, exitCode }
  }

  return { output: '', error: '' }
}

// Common error patterns in bash output that indicate failure even if exit_code is 0 or success is true
const BASH_ERROR_PATTERNS = [
  /command not found/i,
  /no such file or directory/i,
  /permission denied/i,
  /cannot find/i,
  /error:/i,
  /fatal:/i,
  /failed:/i,
  /exception/i,
  /traceback/i,
]

// Check if output contains error patterns
const hasErrorPatterns = (text: string): boolean => {
  return BASH_ERROR_PATTERNS.some(pattern => pattern.test(text))
}

// Component for displaying run_bash with command inline and collapsible output
const RunBashDisplay = React.memo(({
  command,
  result,
  success,
  isExecuting,
  variant = 'chat'
}: {
  command: string
  result: any
  success?: boolean | null
  isExecuting?: boolean
  variant?: 'chat' | 'code'
}) => {
  const isCodeVariant = variant === 'code'
  const [isExpanded, setIsExpanded] = useState(false)

  const { output, error } = extractBashOutput(result)
  const displayContent = output || error
  const hasOutput = !!displayContent && !isExecuting
  const isError = success === false || (displayContent && hasErrorPatterns(displayContent))

  // Truncate command for display
  const displayCommand = command.length > 80 ? command.slice(0, 80) + '...' : command

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="flex-1 min-w-0">
      <div className="flex items-center gap-1.5 min-w-0">
        <span className={cn(
          isCodeVariant ? "text-xs" : "text-sm"
        )}>
          <span className="font-medium text-foreground/70">Bash</span>
          {' '}
          <code className="font-mono text-muted-foreground bg-muted/50 px-1 py-0.5 rounded">{displayCommand}</code>
        </span>
        {hasOutput && (
          <CollapsibleTrigger
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors shrink-0"
          >
            <ChevronRight className={cn(
              "h-3 w-3 transition-transform duration-200",
              isExpanded && "rotate-90"
            )} />
          </CollapsibleTrigger>
        )}
      </div>
      {displayContent && (
        <CollapsibleContent>
          <div className="mt-1 flex">
            <span className="text-muted-foreground/60 mr-1 text-xs">⎿</span>
            <pre className={cn(
              "text-xs font-mono whitespace-pre-wrap max-h-[300px] overflow-y-auto",
              isError ? "text-red-400" : "text-muted-foreground"
            )}>
              {sanitizeOutput(displayContent)}
            </pre>
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  )
})

// Interface for todo items
interface TodoItem {
  id?: string
  text?: string
  content?: string
  status: 'pending' | 'in_progress' | 'completed'
}

// Parse todos from update_todos result
const parseTodosFromResult = (result: any): TodoItem[] => {
  const data = deepParse(result)
  const inner = data?.result ? deepParse(data.result) : data
  const todos = inner?.data?.todos || inner?.todos
  if (Array.isArray(todos)) {
    return todos.filter((t: TodoItem) => t.text || t.content)
  }
  return []
}

// Component for displaying todos inline
const TodosDisplay = React.memo(({ result }: { result: any }) => {
  const todos = parseTodosFromResult(result)
  if (todos.length === 0) return null

  return (
    <div className="space-y-0.5">
      <div className="text-xs text-muted-foreground/60 flex items-center mb-1">
        <span className="mr-1">⎿</span>
        <span>{todos.length} task{todos.length !== 1 ? 's' : ''}</span>
      </div>
      {todos.map((todo, idx) => (
        <div key={todo.id || idx} className="flex items-start gap-2 text-xs py-0.5 ml-3">
          <div className={cn(
            "mt-0.5 h-3.5 w-3.5 rounded-sm border flex items-center justify-center shrink-0",
            todo.status === 'completed'
              ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-400"
              : todo.status === 'in_progress'
              ? "bg-amber-500/20 border-amber-500/50"
              : "border-border text-muted-foreground"
          )}>
            {todo.status === 'completed' && <Check className="h-2.5 w-2.5" />}
          </div>
          <span className={cn(
            "text-muted-foreground",
            todo.status === 'completed' && "line-through text-muted-foreground/60"
          )}>
            {todo.text || todo.content}
          </span>
        </div>
      ))}
    </div>
  )
})

// Component for displaying list_processes results
const ProcessListDisplay = React.memo(({ result }: { result: any }) => {
  const data = (() => {
    try {
      if (typeof result === 'string') return JSON.parse(result)
      return result
    } catch { return null }
  })()

  const processes = data?.processes || []
  if (processes.length === 0) return null

  return (
    <div className="space-y-0.5">
      <div className="text-xs text-muted-foreground/60 flex items-center mb-1">
        <span className="mr-1">⎿</span>
        <span>{processes.length} running process{processes.length !== 1 ? 'es' : ''}</span>
      </div>
      {processes.map((proc: any, idx: number) => (
        <div key={proc.pid || idx} className="flex items-center gap-3 text-xs py-0.5 ml-3 text-muted-foreground">
          <span className="font-mono text-muted-foreground/50 w-12 text-right shrink-0">
            {proc.pid || '—'}
          </span>
          <span className="font-mono truncate flex-1">
            {proc.command || proc.name || 'unknown'}
          </span>
          {proc.port && (
            <span className="text-muted-foreground/60 shrink-0">
              :{proc.port}
            </span>
          )}
          {proc.status && (
            <span className={cn(
              "text-xs shrink-0",
              proc.status === 'running' ? "text-emerald-500" : "text-muted-foreground/50"
            )}>
              {proc.status}
            </span>
          )}
        </div>
      ))}
    </div>
  )
})

// Component for displaying search_code results
const SearchCodeResult = React.memo(({ result, pattern }: { result: any, pattern?: string }) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const { isDark } = useTheme()

  // Parse result
  const parsed = useMemo(() => {
    let data = result
    if (typeof data === 'string') {
      try { data = JSON.parse(data) } catch { return { matches: [], total: 0, error: null } }
    }
    // Unwrap nested result
    data = data?.result || data
    data = data?.data || data

    const matches = data?.matches || []
    const total = data?.total_matches || data?.total || matches.length
    const error = data?.error || null

    return { matches, total, error }
  }, [result])

  const { matches, total, error } = parsed

  if (error) {
    return (
      <div className="ml-5 mt-1 text-xs text-red-400">
        <span className="text-muted-foreground/60 mr-1">⎿</span>
        {error}
      </div>
    )
  }

  if (matches.length === 0) {
    return (
      <div className="ml-5 mt-1 text-xs text-muted-foreground/60">
        <span className="mr-1">⎿</span>
        No matches found
      </div>
    )
  }

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="ml-5 mt-1">
      <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
        <ChevronRight className={cn(
          "h-3 w-3 transition-transform duration-200",
          isExpanded && "rotate-90"
        )} />
        <span>{total} match{total !== 1 ? 'es' : ''}</span>
        {pattern && <code className="text-muted-foreground bg-muted/50 px-1 rounded">{pattern}</code>}
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className={cn(
          "mt-1.5 border rounded-md overflow-hidden max-h-[400px] overflow-y-auto",
          isDark ? "border-border/60 bg-card/50" : "border-border bg-white"
        )}>
          <div className="text-[11px] font-mono leading-[1.6]">
            {matches.map((match: any, idx: number) => {
              const file = match.file || match.path || ''
              const lineNum = match.line || match.line_number
              const content = match.content || match.text || ''
              const isMatch = match.is_match !== false

              return (
                <div
                  key={idx}
                  className={cn(
                    "flex border-b last:border-b-0",
                    isDark ? "border-border/30" : "border-slate-200",
                    isMatch
                      ? isDark ? "bg-amber-500/10" : "bg-amber-50"
                      : ""
                  )}
                >
                  {/* File:line number */}
                  <div className={cn(
                    "flex-shrink-0 w-48 px-2 py-0.5 border-r truncate",
                    isDark ? "border-border/30 text-blue-400" : "border-slate-200 text-blue-600"
                  )}>
                    {file}:{lineNum}
                  </div>
                  {/* Content */}
                  <pre className={cn(
                    "flex-1 px-2 py-0.5 whitespace-pre-wrap break-all",
                    isDark ? "text-muted-foreground" : "text-slate-700"
                  )}>
                    {content}
                  </pre>
                </div>
              )
            })}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})

// Image generation result display component
const ImageGenerationResult = React.memo(({ result }: { result: any }) => {
  const { isDark } = useTheme()

  // Parse the result
  const parsed = useMemo(() => {
    let data = result
    if (typeof data === 'string') {
      try { data = JSON.parse(data) } catch { return null }
    }
    // Unwrap nested result
    data = data?.result || data
    return data
  }, [result])

  if (!parsed) return null

  // Check for error status
  if (parsed.status === 'error') {
    return (
      <div className="ml-5 mt-1.5 text-xs text-red-400">
        <span className="text-muted-foreground/60 mr-1">⎿</span>
        {parsed.message || 'Image generation failed'}
      </div>
    )
  }

  // Extract image data
  const imageData = parsed.image
  if (!imageData?.asset_id && !imageData?.url) return null

  return (
    <div className="ml-5 mt-2 max-w-[calc(100%-1.25rem)]">
      {/* Image container */}
      <div className={cn(
        "relative rounded-lg overflow-hidden border transition-all w-fit max-w-full",
        isDark ? "border-border/60 bg-card/30" : "border-border bg-slate-50"
      )}>
        {/* Use AssetImage component which handles authentication */}
        <AssetImage
          assetId={imageData.asset_id}
          alt="Generated image"
          className="max-w-[250px] sm:max-w-sm max-h-60 sm:max-h-80 object-contain rounded-lg"
        />
      </div>

      {/* Image metadata */}
      <div className="flex items-center flex-wrap gap-2 sm:gap-3 mt-1.5 text-xs text-muted-foreground/70">
        {imageData.width && imageData.height && (
          <span>{imageData.width}×{imageData.height}</span>
        )}
        {parsed.model && (
          <span className={cn(
            "px-1.5 py-0.5 rounded-full text-[10px] font-medium",
            isDark ? "bg-accent-brand/10 text-accent-brand/80" : "bg-emerald-50 text-emerald-600"
          )}>
            {formatModelId(parsed.model)}
          </span>
        )}
        {parsed.generation_time_ms && (
          <span>{(parsed.generation_time_ms / 1000).toFixed(1)}s</span>
        )}
      </div>
    </div>
  )
})

// Video generation result display component
const VideoGenerationResult = React.memo(({ result }: { result: any }) => {
  const { isDark } = useTheme()

  // Parse the result
  const parsed = useMemo(() => {
    let data = result
    if (typeof data === 'string') {
      try { data = JSON.parse(data) } catch { return null }
    }
    // Unwrap nested result
    data = data?.result || data
    return data
  }, [result])

  if (!parsed) return null

  // Check for error status
  if (parsed.status === 'error') {
    return (
      <div className="ml-5 mt-1.5 text-xs text-red-400">
        <span className="text-muted-foreground/60 mr-1">⎿</span>
        {parsed.message || 'Video generation failed'}
      </div>
    )
  }

  // Extract video data
  const videoData = parsed.video
  if (!videoData?.asset_id) return null

  // Format duration
  const formatDuration = (seconds: number | null) => {
    if (!seconds) return null
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="ml-5 mt-2 max-w-[calc(100%-1.25rem)]">
      {/* Video container */}
      <div className={cn(
        "relative rounded-lg overflow-hidden border transition-all w-fit max-w-full",
        isDark ? "border-border/60 bg-card/30" : "border-border bg-slate-50"
      )}>
        {/* Use VideoPlayer component */}
        <VideoPlayer
          assetId={videoData.asset_id}
          autoPlay={false}
          loop={false}
          controls={true}
          className="max-w-[280px] sm:max-w-md max-h-48 sm:max-h-80"
          alt="Generated video"
        />
      </div>

      {/* Video metadata */}
      <div className="flex items-center flex-wrap gap-2 sm:gap-3 mt-1.5 text-xs text-muted-foreground/70">
        {videoData.width && videoData.height && (
          <span>{videoData.width}×{videoData.height}</span>
        )}
        {videoData.duration_seconds && (
          <span className="font-mono">{formatDuration(videoData.duration_seconds)}</span>
        )}
        {parsed.model && (
          <span className={cn(
            "px-1.5 py-0.5 rounded-full text-[10px] font-medium",
            isDark ? "bg-purple-500/10 text-purple-400/80" : "bg-purple-50 text-purple-600"
          )}>
            {formatModelId(parsed.model)}
          </span>
        )}
        {parsed.generation_time_ms && (
          <span>{(parsed.generation_time_ms / 1000).toFixed(1)}s</span>
        )}
      </div>
    </div>
  )
})

// Sanitize and format output for display
// Handles escaped characters, truncates long output, and ensures proper line breaks
const sanitizeOutput = (output: string | undefined | null, maxLength = 10000): string => {
  if (!output) return ''

  let sanitized = String(output)

  // Unescape common escape sequences that might be double-escaped
  sanitized = sanitized
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\r/g, '\r')
    .replace(/\\"/g, '"')
    .replace(/\\'/g, "'")

  // Truncate if too long
  if (sanitized.length > maxLength) {
    sanitized = sanitized.slice(0, maxLength) + '\n\n... (output truncated)'
  }

  return sanitized
}

// Detect language from code content
const detectCodeLanguage = (code: string): string => {
  const trimmed = code.trim()

  // Check for shebang
  if (trimmed.startsWith('#!/bin/bash') || trimmed.startsWith('#!/bin/sh') || trimmed.startsWith('#!/usr/bin/env bash')) {
    return 'bash'
  }

  // Check for common bash patterns
  const bashPatterns = [
    /^\s*(if|then|else|fi|for|do|done|while|case|esac)\s/m,
    /^\s*(echo|cd|ls|grep|awk|sed|cat|rm|mv|cp|mkdir|chmod|chown)\s/m,
    /\$\{?\w+\}?/,  // $VAR or ${VAR}
    /^\s*export\s+\w+=/m,
    /\|\s*(grep|awk|sed|sort|uniq|head|tail|wc)/,
  ]

  // Check for Python patterns
  const pythonPatterns = [
    /^\s*(import|from)\s+\w+/m,
    /^\s*def\s+\w+\s*\(/m,
    /^\s*class\s+\w+/m,
    /^\s*(print|len|range|open)\s*\(/m,
    /:\s*$/m,  // Colon at end of line (if/for/def/class)
  ]

  const bashScore = bashPatterns.filter(p => p.test(trimmed)).length
  const pythonScore = pythonPatterns.filter(p => p.test(trimmed)).length

  if (bashScore > pythonScore) return 'bash'
  return 'python'  // Default to python
}

// Extract actual bash command from Python subprocess wrapper
const extractBashCommand = (code: string): { command: string | null, fullCode: string } => {
  // Pattern to match subprocess.run/call/check_output with bash -c
  // Handles both ['bash', '-c', 'command'] and ['/bin/bash', '-c', 'command'] formats
  const patterns = [
    // subprocess.run(['bash', '-c', 'command'], ...)
    /subprocess\.(?:run|call|check_output|Popen)\s*\(\s*\[\s*['"](?:\/bin\/)?(?:bash|sh)['"]\s*,\s*['"]-c['"]\s*,\s*['"](.+?)['"]\s*\]/s,
    // subprocess.run('command', shell=True, ...)
    /subprocess\.(?:run|call|check_output|Popen)\s*\(\s*['"](.+?)['"]\s*,\s*shell\s*=\s*True/s,
    // os.system('command')
    /os\.system\s*\(\s*['"](.+?)['"]\s*\)/s,
  ]

  for (const pattern of patterns) {
    const match = code.match(pattern)
    if (match && match[1]) {
      // Unescape the command (handle escaped quotes)
      let command = match[1]
        .replace(/\\'/g, "'")
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, '\\')
      return { command, fullCode: code }
    }
  }

  // Also try to extract from f-strings or string concatenation (common pattern)
  // subprocess.run(['bash', '-c', f'find {path} ...'], ...)
  const fstringPattern = /subprocess\.(?:run|call|check_output|Popen)\s*\(\s*\[\s*['"](?:\/bin\/)?(?:bash|sh)['"]\s*,\s*['"]-c['"]\s*,\s*f?['"](.+?)['"]\s*\]/s
  const fstringMatch = code.match(fstringPattern)
  if (fstringMatch && fstringMatch[1]) {
    let command = fstringMatch[1]
      .replace(/\\'/g, "'")
      .replace(/\\"/g, '"')
    return { command, fullCode: code }
  }

  return { command: null, fullCode: code }
}

// Component for displaying file content in a collapsible section with syntax highlighting
const FileContentDisplay = React.memo(({ filename, content, isDark }: {
  filename: string
  content: string
  isDark: boolean
}) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  // Detect language from filename extension
  const getLanguage = (fname: string): string => {
    const ext = fname.split('.').pop()?.toLowerCase() || ''
    const langMap: Record<string, string> = {
      'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'tsx': 'tsx',
      'jsx': 'jsx', 'json': 'json', 'md': 'markdown', 'yml': 'yaml',
      'yaml': 'yaml', 'sh': 'bash', 'bash': 'bash', 'css': 'css',
      'html': 'html', 'sql': 'sql', 'go': 'go', 'rs': 'rust',
      'rb': 'ruby', 'java': 'java', 'cpp': 'cpp', 'c': 'c', 'h': 'c',
    }
    return langMap[ext] || 'text'
  }

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const lineCount = content.split('\n').length
  const charCount = content.length

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className={cn(
      "border rounded overflow-hidden",
      isDark ? "border-slate-700" : "border-slate-300"
    )}>
      <CollapsibleTrigger className={cn(
        "w-full flex items-center justify-between px-2 py-1.5 text-xs transition-colors",
        isDark ? "bg-slate-800/50 hover:bg-slate-800" : "bg-slate-100 hover:bg-slate-200"
      )}>
        <div className="flex items-center gap-2">
          <ChevronRight className={cn(
            "h-3 w-3 transition-transform duration-200",
            isExpanded && "rotate-90",
            isDark ? "text-slate-400" : "text-slate-500"
          )} />
          <span className={cn("font-mono font-medium", isDark ? "text-slate-300" : "text-slate-700")}>
            {filename}
          </span>
          <span className={cn("text-xs", isDark ? "text-slate-500" : "text-slate-400")}>
            ({lineCount} lines, {charCount > 1000 ? `${(charCount / 1000).toFixed(1)}K` : charCount} chars)
          </span>
        </div>
        {isExpanded && (
          <button
            onClick={(e) => { e.stopPropagation(); handleCopy() }}
            className={cn(
              "flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors",
              copied
                ? "text-emerald-500"
                : isDark
                  ? "text-slate-400 hover:text-slate-300 hover:bg-slate-700/50"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-200/50"
            )}
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          </button>
        )}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="max-h-[400px] overflow-y-auto">
          <SyntaxHighlighter
            language={getLanguage(filename)}
            style={codeTheme.style}
            showLineNumbers={true}
            wrapLongLines={true}
            customStyle={{
              margin: 0,
              padding: '0.5rem',
              background: isDark ? '#1a1a2e' : '#f8f8f8',
              fontSize: '0.7rem',
              lineHeight: '1.5',
            }}
            lineNumberStyle={{
              minWidth: '2.5em',
              paddingRight: '0.75em',
              color: isDark ? '#4a5568' : '#a0aec0',
              userSelect: 'none',
            }}
          >
            {content}
          </SyntaxHighlighter>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})

// Helper to deeply parse and extract meaningful data from programming task result
const parseProgrammingTaskOutput = (result: any): {
  success: boolean
  error: string | null
  output: string | null
  data: Record<string, any> | null
  isTruncated: boolean
  truncationSummary: string | null
} => {
  // Parse if string
  let parsed = result
  if (typeof parsed === 'string') {
    try {
      parsed = JSON.parse(parsed)
    } catch {
      return { success: false, error: null, output: parsed, data: null, isTruncated: false, truncationSummary: null }
    }
  }

  // Extract nested result
  const taskResult = parsed?.result || parsed

  // Check truncation
  const isTruncated = parsed?._truncated || taskResult?._truncated || false
  const truncationSummary = parsed?._summary || taskResult?._summary || null

  // Get success status
  const success = parsed?.success ?? taskResult?.success ?? isTruncated ?? false
  const error = parsed?.error || taskResult?.error || null

  // Get output - try to parse it if it's JSON
  let output = taskResult?.output || null
  let data: Record<string, any> | null = null

  if (output && typeof output === 'string') {
    try {
      const parsedOutput = JSON.parse(output)
      if (typeof parsedOutput === 'object' && parsedOutput !== null) {
        data = parsedOutput
        output = null // Don't show raw output if we parsed it
      }
    } catch {
      // Keep as string output
    }
  }

  // Also check taskResult.result for structured data
  if (!data && taskResult?.result) {
    let resultData = taskResult.result
    if (typeof resultData === 'string') {
      try {
        resultData = JSON.parse(resultData)
      } catch {
        // ignore
      }
    }
    if (typeof resultData === 'object' && resultData !== null && !Array.isArray(resultData)) {
      // Filter internal fields
      const { _truncated, _summary, success: _, error: __, output: ___, ...cleanData } = resultData
      if (Object.keys(cleanData).length > 0) {
        data = cleanData
      }
    }
  }

  return { success, error, output, data, isTruncated, truncationSummary }
}

// Component for displaying execute_programming_task results - compact like other tools
const ProgrammingTaskResult = React.memo(({ result, code }: { result: any, code?: string }) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const [showCode, setShowCode] = useState(false)
  const { isDark } = useTheme()
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  // Parse the result - deeply unwrap nested JSON strings
  const parsed = useMemo(() => {
    const WRAPPER_KEYS = new Set(['success', 'error', 'output', 'data', 'result', '_truncated', '_summary', 'status', 'task'])

    // Recursively parse JSON strings until we get an object
    const parse = (val: any): any => {
      if (typeof val !== 'string') return val
      try { return parse(JSON.parse(val)) } catch { return val }
    }

    // Recursively unwrap wrapper objects to get actual data
    const unwrap = (obj: any): any => {
      if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return obj
      // Try to go deeper through common wrappers
      if (obj.data?.result) return unwrap(obj.data.result)
      if (obj.result && typeof obj.result === 'object') return unwrap(obj.result)
      if (obj.data && typeof obj.data === 'object' && !Array.isArray(obj.data)) return unwrap(obj.data)
      return obj
    }

    // Get useful keys from an object (exclude wrapper keys)
    const getDataKeys = (obj: any): string[] => {
      if (!obj || typeof obj !== 'object') return []
      return Object.keys(obj).filter(k => !WRAPPER_KEYS.has(k))
    }

    const r = parse(result)
    if (!r || typeof r !== 'object') {
      return { success: false, error: null, output: typeof result === 'string' ? result : null, data: null }
    }

    const success = r.success ?? true
    const error = r.error || r.data?.error || r.data?.result?.error || null

    // Unwrap to get the actual data
    const unwrapped = unwrap(r)
    const dataKeys = getDataKeys(unwrapped)

    // If we have actual data keys, use as structured data
    if (dataKeys.length > 0) {
      // Filter to only include the actual data, not wrapper fields
      const cleanData: Record<string, any> = {}
      for (const key of dataKeys) {
        cleanData[key] = unwrapped[key]
      }
      return { success, error, output: null, data: cleanData }
    }

    // Otherwise check for output field
    const output = r.output || r.data?.output || r.data?.result?.output || null
    return { success, error, output, data: null }
  }, [result])

  const { success, error, output, data } = parsed

  // Get summary for collapsed view - extract useful info
  const summary = useMemo(() => {
    // Extract useful data from result
    const extract = (obj: any): Record<string, any> | null => {
      if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null
      if (obj.data?.result) return extract(obj.data.result)
      if (obj.result && typeof obj.result === 'object') return extract(obj.result)
      if (obj.data && typeof obj.data === 'object') return extract(obj.data)
      const keys = Object.keys(obj).filter(k =>
        !['success', 'error', 'output', 'data', 'result', 'status', '_truncated', '_summary', 'task'].includes(k)
      )
      if (keys.length > 0) {
        const extracted: Record<string, any> = {}
        keys.forEach(k => extracted[k] = obj[k])
        return extracted
      }
      return null
    }

    // Check for error first
    let raw = result
    if (typeof raw === 'string') {
      try { raw = JSON.parse(raw) } catch { /* keep string */ }
    }
    const err = raw?.error || raw?.data?.error
    if (err) {
      const lines = String(err).split('\n')
      const errorLine = lines.find(l => l.includes('Error:') || l.includes('Exception:')) || lines[lines.length - 1]
      return errorLine?.slice(0, 80) || 'Error'
    }

    // Try to extract data
    const extracted = extract(raw)
    if (extracted) {
      const keys = Object.keys(extracted)
      if (keys.length === 1 && Array.isArray(extracted[keys[0]])) {
        return `${keys[0]}: ${extracted[keys[0]].length} items`
      }
      const preview = keys.slice(0, 3).join(', ')
      return keys.length > 3 ? `${preview}, +${keys.length - 3} more` : preview
    }

    // Check for output
    const output = raw?.output || raw?.data?.output
    if (output && typeof output === 'string' && !output.startsWith('{')) {
      return sanitizeOutput(output).slice(0, 60)
    }

    return success ? 'Completed' : 'Failed'
  }, [result, success])

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="ml-5 mt-1">
      {/* Compact header */}
      <div className="flex items-center gap-2">
        <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
          <ChevronRight className={cn(
            "h-3 w-3 transition-transform duration-200",
            isExpanded && "rotate-90"
          )} />
          <span className="truncate max-w-[350px]">{isExpanded ? 'Hide output' : summary}</span>
        </CollapsibleTrigger>
        {code && (
          <button
            onClick={() => setShowCode(!showCode)}
            className="flex items-center gap-1 text-xs text-muted-foreground/40 hover:text-muted-foreground transition-colors"
          >
            <Code2 className="h-3 w-3" />
            <span>{showCode ? 'Hide' : 'View'} code</span>
          </button>
        )}
      </div>

      {/* Code display */}
      {showCode && code && (
        <div className="mt-1.5 ml-4 max-h-[200px] overflow-y-auto rounded bg-[#1e1e1e]">
          <SyntaxHighlighter
            language="python"
            style={codeTheme.style}
            showLineNumbers={true}
            wrapLongLines={true}
            customStyle={{ margin: 0, padding: '0.5rem', background: 'transparent', fontSize: '0.7rem' }}
          >
            {code}
          </SyntaxHighlighter>
        </div>
      )}

      {/* Expanded output */}
      <CollapsibleContent>
        <div className="mt-1.5 ml-4 max-h-[300px] overflow-y-auto space-y-2">
          {/* Error */}
          {error && (
            <pre className="text-xs font-mono whitespace-pre-wrap break-all text-red-400 bg-red-500/10 rounded p-2">
              {sanitizeOutput(String(error))}
            </pre>
          )}

          {/* Always try to extract and display useful data */}
          {!error && (() => {
            // Extract useful data from result, unwrapping wrappers
            const extract = (obj: any): Record<string, any> | null => {
              if (!obj || typeof obj !== 'object') return null
              if (Array.isArray(obj)) return null
              if (obj.data?.result) return extract(obj.data.result)
              if (obj.result && typeof obj.result === 'object') return extract(obj.result)
              if (obj.data && typeof obj.data === 'object') return extract(obj.data)
              const keys = Object.keys(obj).filter(k =>
                !['success', 'error', 'output', 'data', 'result', 'status', '_truncated', '_summary', 'task'].includes(k)
              )
              if (keys.length > 0) {
                const extracted: Record<string, any> = {}
                keys.forEach(k => extracted[k] = obj[k])
                return extracted
              }
              // Check for output field as fallback
              if (obj.output && typeof obj.output === 'string') {
                return { output: obj.output }
              }
              return null
            }

            let raw = result
            if (typeof raw === 'string') {
              try { raw = JSON.parse(raw) } catch { /* keep as string */ }
            }
            const extracted = extract(raw)

            if (!extracted) {
              // Last resort: show raw output if it's a simple string
              if (typeof result === 'string' && !result.startsWith('{')) {
                return <pre className="text-xs font-mono text-muted-foreground">{sanitizeOutput(result)}</pre>
              }
              return <span className="text-xs text-muted-foreground/60">No data to display</span>
            }

            return (
              <div className="space-y-1.5">
                {Object.entries(extracted).map(([key, value]) => {
                  // File content
                  const isFile = key.includes('/') || (key.includes('.') && typeof value === 'string' && value.length > 100)
                  if (isFile && typeof value === 'string') {
                    return <FileContentDisplay key={key} filename={key} content={value} isDark={isDark} />
                  }
                  // Arrays
                  if (Array.isArray(value)) {
                    const preview = value.slice(0, 5).map(v => typeof v === 'string' ? v : JSON.stringify(v)).join(', ')
                    return (
                      <div key={key} className="text-xs">
                        <span className="text-muted-foreground/60 font-medium">{key}:</span>
                        <span className="ml-2 text-muted-foreground font-mono">
                          {value.length} items{value.length > 0 ? `: ${preview}${value.length > 5 ? '...' : ''}` : ''}
                        </span>
                      </div>
                    )
                  }
                  // Plain output
                  if (key === 'output' && typeof value === 'string') {
                    return (
                      <pre key={key} className="text-xs font-mono whitespace-pre-wrap text-muted-foreground">
                        {sanitizeOutput(value)}
                      </pre>
                    )
                  }
                  // Other values
                  return (
                    <div key={key} className="text-xs">
                      <span className="text-muted-foreground/60 font-medium">{key}:</span>
                      <span className="ml-2 text-muted-foreground font-mono">
                        {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )
          })()}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})

// Extract spark ID from spark tool result
const extractSparkId = (result: any): string | null => {
  if (!result) return null
  try {
    let data = result
    if (typeof data === 'string') {
      try { data = JSON.parse(data) } catch { return null }
    }
    // Result structure: { status: 'success', spark: { id, title, ... } }
    if (data?.status === 'success' && data?.spark?.id) {
      return data.spark.id
    }
    return null
  } catch {
    return null
  }
}

// Extract a brief summary from tool results for display
const getToolResultSummary = (toolName: string, result: any): string | null => {
  if (!result) return null

  try {
    // Parse result if string
    let data = result
    if (typeof data === 'string') {
      try { data = JSON.parse(data) } catch { return null }
    }

    // Unwrap nested result structures
    data = data?.result || data
    data = data?.data || data

    // Tool-specific summaries
    switch (toolName) {
      // Brave Search tools
      case 'brave_web_search':
      case 'brave_news_search':
      case 'brave_local_search': {
        const results = data?.results || data?.web?.results || []
        const count = Array.isArray(results) ? results.length : 0
        return count > 0 ? `${count} result${count !== 1 ? 's' : ''}` : 'No results'
      }

      // GitHub tools
      case 'github_list_issues': {
        const issues = Array.isArray(data) ? data : data?.issues || []
        return `${issues.length} issue${issues.length !== 1 ? 's' : ''}`
      }
      case 'github_get_issue':
      case 'github_create_issue':
      case 'github_update_issue': {
        const num = data?.number || data?.issue?.number
        const title = data?.title || data?.issue?.title
        if (num) return `#${num}${title ? `: ${title.slice(0, 40)}${title.length > 40 ? '...' : ''}` : ''}`
        return null
      }
      case 'github_list_pull_requests': {
        const prs = Array.isArray(data) ? data : data?.pull_requests || []
        return `${prs.length} PR${prs.length !== 1 ? 's' : ''}`
      }
      case 'github_get_pull_request':
      case 'github_create_pull_request': {
        const num = data?.number || data?.pull_request?.number
        const title = data?.title || data?.pull_request?.title
        if (num) return `PR #${num}${title ? `: ${title.slice(0, 35)}${title.length > 35 ? '...' : ''}` : ''}`
        return null
      }
      case 'github_list_repos': {
        const repos = Array.isArray(data) ? data : data?.repositories || []
        return `${repos.length} repo${repos.length !== 1 ? 's' : ''}`
      }
      case 'github_search_code': {
        const count = data?.total_count || (Array.isArray(data?.items) ? data.items.length : 0)
        return `${count} match${count !== 1 ? 'es' : ''}`
      }
      case 'github_list_commits': {
        const commits = Array.isArray(data) ? data : data?.commits || []
        return `${commits.length} commit${commits.length !== 1 ? 's' : ''}`
      }
      case 'github_list_branches': {
        const branches = Array.isArray(data) ? data : data?.branches || []
        return `${branches.length} branch${branches.length !== 1 ? 'es' : ''}`
      }

      // Web fetch
      case 'fetch_web_page': {
        if (!data?.success) return data?.error?.slice(0, 50) || 'Failed'
        const title = data?.title
        if (title) return title.slice(0, 50) + (title.length > 50 ? '...' : '')
        const url = data?.url
        if (url) {
          try { return new URL(url).hostname } catch { return null }
        }
        return null
      }

      // Google Maps tools
      case 'geocode_address': {
        const lat = data?.latitude || data?.lat
        const lng = data?.longitude || data?.lng
        if (lat && lng) return `${lat.toFixed(4)}, ${lng.toFixed(4)}`
        return data?.formatted_address?.slice(0, 50) || null
      }
      case 'get_directions': {
        const duration = data?.duration || data?.routes?.[0]?.duration
        const distance = data?.distance || data?.routes?.[0]?.distance
        if (duration) return `${duration}${distance ? ` (${distance})` : ''}`
        return null
      }
      case 'search_nearby_places': {
        const places = Array.isArray(data) ? data : data?.places || data?.results || []
        return `${places.length} place${places.length !== 1 ? 's' : ''}`
      }

      // Spark tools
      case 'create_spark':
      case 'update_spark': {
        if (data?.status === 'success' && data?.spark?.title) {
          return data.spark.title.slice(0, 40) + (data.spark.title.length > 40 ? '...' : '')
        }
        return null
      }

      // Process tools
      case 'list_processes': {
        const procs = data?.processes || []
        if (procs.length === 0) return 'no running processes'
        return `${procs.length} process${procs.length !== 1 ? 'es' : ''} running`
      }
      case 'check_process_health': {
        if (data?.ready) return `port ${data.port} responding`
        return `port ${data?.port || '?'} not responding`
      }

      // Preview tools
      case 'start_preview': {
        if (data?.success) return `server on port ${data.port}`
        return data?.error || 'failed to start'
      }
      case 'stop_preview': {
        if (data?.success) return `port ${data.port} stopped`
        return data?.error || 'failed to stop'
      }

      // Coding agent management tools
      case 'update_coding_agent': {
        if (data?.success && data?.agent?.name) {
          const changeCount = data.changes?.length || 0
          return `${data.agent.name} (${changeCount} change${changeCount !== 1 ? 's' : ''})`
        }
        if (data?.error) return data.error.slice(0, 50)
        return null
      }

      // List tools - no summary here, shown in ListToolResultsDisplay
      case 'list_sparks':
      case 'list_generated_images':
      case 'list_generated_videos':
      case 'list_voice_rooms':
      case 'list_mcp_servers':
      case 'list_available_models':
      case 'list_knowledge_base_documents':
      case 'list_coding_agents':
        return null

      // Asset access tools
      case 'get_image': {
        if (data?.error) return 'Not found'
        const filename = data?.metadata?.filename
        if (filename) return filename.slice(0, 40) + (filename.length > 40 ? '...' : '')
        if (data?.image_base64) return 'Image data retrieved'
        if (data?.url) return 'Image URL generated'
        return null
      }
      case 'get_video': {
        if (data?.error) return 'Not found'
        const filename = data?.metadata?.filename
        const duration = data?.metadata?.duration_formatted
        if (filename) {
          const shortName = filename.slice(0, 30) + (filename.length > 30 ? '...' : '')
          return duration ? `${shortName} (${duration})` : shortName
        }
        return null
      }
      case 'get_spark': {
        if (data?.error) return 'Not found'
        const title = data?.title
        const framework = data?.framework
        if (title) {
          const shortTitle = title.slice(0, 35) + (title.length > 35 ? '...' : '')
          return framework ? `${shortTitle} (${framework})` : shortTitle
        }
        return null
      }
      case 'get_document': {
        if (data?.error) return 'Not found'
        const filename = data?.filename
        const truncated = data?.truncated
        if (filename) {
          const shortName = filename.slice(0, 35) + (filename.length > 35 ? '...' : '')
          return truncated ? `${shortName} (truncated)` : shortName
        }
        return null
      }

      case 'export_asset': {
        if (data?.error) return 'Failed'
        const assetType = data?.asset_type
        const filename = data?.filename
        if (filename) {
          const shortName = filename.slice(0, 30) + (filename.length > 30 ? '...' : '')
          return assetType ? `${assetType}: ${shortName}` : shortName
        }
        return data?.permanent_url ? 'URL generated' : null
      }

      case 'save_asset_to_workspace': {
        if (data?.error) return 'Failed'
        if (data?.success) {
          const path = data?.path
          return path ? path.slice(0, 40) + (path.length > 40 ? '...' : '') : 'Saved'
        }
        return null
      }

      // Generic array results
      default: {
        if (Array.isArray(data)) {
          return `${data.length} item${data.length !== 1 ? 's' : ''}`
        }
        // Check for common count/total fields
        if (typeof data?.count === 'number') return `${data.count} item${data.count !== 1 ? 's' : ''}`
        if (typeof data?.total === 'number') return `${data.total} item${data.total !== 1 ? 's' : ''}`
        return null
      }
    }
  } catch {
    return null
  }
}

export function FileToolExecutionsDisplay({ executions, showBraveSearchMedia = true, variant = 'chat', onOpenIDE, chatId, pendingCodingAgentQuestion, onAnswerCodingAgentQuestion }: FileToolExecutionsDisplayProps) {
  const isCodeVariant = variant === 'code'
  const { isDark } = useTheme()
  if (!executions || executions.length === 0) {
    return null
  }

  return (
    <div className="space-y-1.5 mt-2">
      {executions.map((execution, index) => {
        const toolName = execution.tool_call.function.name
        const backendDisplayName = execution.tool_call.display_name
        const serverIconUrl = execution.tool_call.server_icon_url
        const serverIconInvert = execution.tool_call.server_icon_invert
        const { icon: Icon, displayName } = getToolInfo(toolName, backendDisplayName)
        const filePath = getFilePath(toolName, execution.tool_call.function.arguments)
        const isExecuteCode = toolName === 'execute_code'
        const isRunBash = toolName === 'run_bash'
        const isListFiles = toolName === 'list_files'
        const isEditFile = toolName === 'edit_file'
        const isWriteFile = toolName === 'write_file'
        const isToolDiscovery = toolName === 'search_available_tools'
        const isProgrammingTask = toolName === 'execute_programming_task'
        const isBraveSearch = toolName === 'brave_image_search' || toolName === 'brave_video_search'
        const isUpdateTodos = toolName === 'update_todos'
        const isSearchCode = toolName === 'search_code'
        const isImageGeneration = toolName === 'generate_image' || toolName === 'edit_image'
        const isVideoGeneration = toolName === 'generate_video'
        const isCodingAgent = toolName === 'coding_agent' || toolName === 'plan_implementation' || toolName === 'implement_plan' || toolName === 'edit_plan'
        const isSparkTool = toolName === 'create_spark' || toolName === 'update_spark'
        const isUpdateSpark = toolName === 'update_spark'
        const isKnowledgeBase = toolName === 'query_knowledge_base'
        const isListTool = isListToolName(toolName)
        const isListProcesses = toolName === 'list_processes'
        const hasSpecialContent = isExecuteCode || isRunBash || isListFiles || isEditFile || isWriteFile || isToolDiscovery || isProgrammingTask || isUpdateTodos || isSearchCode || isImageGeneration || isVideoGeneration || isCodingAgent || isUpdateSpark || isKnowledgeBase || isListTool || isListProcesses

        // Extract Brave Search media if applicable and enabled
        // Only extract media if execution was successful
        const braveSearchMedia = showBraveSearchMedia && isBraveSearch && execution.result && !execution.isExecuting && execution.success !== false
          ? extractBraveSearchMedia(toolName, execution.result)
          : null

        // Extract Knowledge Base results if applicable
        const knowledgeBaseResults = isKnowledgeBase && execution.result && !execution.isExecuting && execution.success !== false
          ? extractKnowledgeBaseResults(execution.result)
          : null

        // Extract List Tool results if applicable
        const listToolData = isListTool && execution.result && !execution.isExecuting && execution.success !== false
          ? extractListToolData(toolName, execution.result)
          : null

        // For run_bash, check if output contains error patterns even if success is true
        let effectiveSuccess = execution.success
        if (isRunBash && execution.result && !execution.isExecuting) {
          const { output, error } = extractBashOutput(execution.result)
          const displayContent = output || error
          if (displayContent && hasErrorPatterns(displayContent)) {
            effectiveSuccess = false
          }
        }

        // For Coding Agent, render ONLY the premium card (skip standard header row)
        if (isCodingAgent) {
          let codingResult: any = undefined
          let codingSteps: any[] = []

          if (execution.coding_agent_result) {
            codingResult = execution.coding_agent_result
          } else if (execution.result) {
            try {
              const parsed = typeof execution.result === 'string'
                ? JSON.parse(execution.result)
                : execution.result

              // Handle potential nested result wrapper from LangChain agent
              // Structure might be: { result: { success, data: { ... } } }
              // Or: { success, data: { ... } }
              const unwrapped = parsed.result || parsed
              const data = unwrapped.data || unwrapped

              codingResult = {
                job_id: data.job_id || unwrapped.job_id || parsed.job_id,
                success: unwrapped.success ?? data.success ?? parsed.success,
                summary: data.summary || unwrapped.summary || parsed.summary,
                files_created: data.files_created || unwrapped.files_created || parsed.files_created || [],
                files_modified: data.files_modified || unwrapped.files_modified || parsed.files_modified || [],
                error: unwrapped.error || data.error || parsed.error,
                duration_ms: data.duration_ms || unwrapped.duration_ms || parsed.duration_ms || 0,
                total_tokens: data.total_tokens || unwrapped.total_tokens || parsed.total_tokens,
              }
              codingSteps = data.steps || unwrapped.steps || parsed.steps || []
            } catch {
              // Parsing failed
            }
          }

          const steps = execution.coding_agent_steps && execution.coding_agent_steps.length > 0
            ? execution.coding_agent_steps
            : codingSteps

          const agentStatus = execution.isExecuting
            ? 'running'
            : codingResult?.success
              ? 'completed'
              : codingResult?.success === false
                ? 'failed'
                : 'pending'

          return (
            <div key={execution.tool_call.id || index} className="min-w-0 overflow-hidden">
              <CodingAgentDisplay
                task={(() => {
                  try {
                    const args = JSON.parse(execution.tool_call.function.arguments)
                    return args.task || 'Coding task'
                  } catch {
                    return 'Coding task'
                  }
                })()}
                jobId={codingResult?.job_id}
                status={agentStatus}
                steps={steps}
                result={codingResult}
                variant={variant}
                chatId={chatId}
                pendingQuestion={agentStatus === 'running' ? pendingCodingAgentQuestion : null}
                onAnswerQuestion={chatId && onAnswerCodingAgentQuestion ? (answer: string) => onAnswerCodingAgentQuestion(chatId, answer) : undefined}
              />
            </div>
          )
        }

        return (
          <div
            key={execution.tool_call.id || index}
            className="space-y-0"
          >
            {/* Header Row - Clean style */}
            <div className={cn(
              "flex items-start gap-2 py-0.5 text-xs",
              isCodeVariant && "text-muted-foreground"
            )}>
              {/* Status Icon - only show spinner while executing */}
              {execution.isExecuting && (
                <div className="flex-shrink-0 flex items-center justify-center mt-0.5">
                  <Loader2 className={cn(
                    "animate-spin",
                    isCodeVariant ? "w-1.5 h-1.5 text-muted-foreground" : "w-3.5 h-3.5 text-accent-brand"
                  )} />
                </div>
              )}

              {/* Content - varies by tool type */}
              <div className="flex-1 min-w-0">
                {/* File operations: show tool name + path inline */}
                {filePath && !isRunBash && (
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className={isCodeVariant ? "text-foreground/70 font-medium" : "text-foreground font-medium"}>{displayName}</span>
                      <code className="font-mono text-muted-foreground bg-muted/50 px-1 py-0.5 rounded truncate">{filePath}</code>
                    </div>
                    {/* Read file: show line count */}
                    {toolName === 'read_file' && execution.result && !execution.isExecuting && (() => {
                      const lineCount = getReadLineCount(execution.result)
                      return lineCount ? (
                        <div className="text-xs text-muted-foreground/60 flex items-center">
                          <span className="mr-1">⎿</span>Read {lineCount} line{lineCount !== 1 ? 's' : ''}
                        </div>
                      ) : null
                    })()}
                  </div>
                )}

                {/* Run bash: show $ command with expandable output */}
                {isRunBash && (
                  <RunBashDisplay
                    command={(() => {
                      try {
                        const args = JSON.parse(execution.tool_call.function.arguments)
                        return args.command || ''
                      } catch {
                        return ''
                      }
                    })()}
                    result={execution.result}
                    success={effectiveSuccess}
                    isExecuting={execution.isExecuting}
                    variant={variant}
                  />
                )}

                {/* Tool discovery: show count inline */}
                {isToolDiscovery && (
                  <div className="flex items-center gap-1.5">
                    <Icon className={cn("w-3.5 h-3.5 shrink-0", isCodeVariant ? "text-foreground/50" : "text-muted-foreground")} />
                    <span className={isCodeVariant ? "text-foreground/70 font-medium" : "text-foreground font-medium"}>{displayName}</span>
                    {execution.result && !execution.isExecuting && (() => {
                      const { foundCount, disabledCount } = parseToolDiscoveryResult(execution.result)
                      return foundCount > 0 ? (
                        <span className="text-muted-foreground/60">
                          {foundCount} tool{foundCount !== 1 ? 's' : ''} found
                          {disabledCount > 0 && <span className="text-amber-400 ml-1">({disabledCount} disabled)</span>}
                        </span>
                      ) : (
                        <span className="text-muted-foreground/60">none found</span>
                      )
                    })()}
                  </div>
                )}

                {/* Other tools: show icon + name + summary */}
                {!filePath && !isRunBash && !isToolDiscovery && !isCodingAgent && (() => {
                  // Determine click handler for spark tools
                  const getClickHandler = (): (() => void) | undefined => {
                    if (execution.isExecuting || effectiveSuccess === false) return undefined
                    if (isSparkTool) {
                      const sparkId = extractSparkId(execution.result)
                      if (sparkId) return () => useArtifactsPanelStore.getState().openSparkInPanel(sparkId)
                    }
                    return undefined
                  }
                  const clickHandler = getClickHandler()
                  const isClickable = !!clickHandler

                  return (
                    <div
                      className={cn(
                        "flex items-center gap-1.5",
                        isClickable && "cursor-pointer hover:text-foreground transition-colors"
                      )}
                      onClick={clickHandler}
                      role={isClickable ? "button" : undefined}
                      tabIndex={isClickable ? 0 : undefined}
                      onKeyDown={isClickable ? (e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          clickHandler!()
                        }
                      } : undefined}
                    >
                      {serverIconUrl ? (
                        <img
                          src={serverIconUrl}
                          alt=""
                          className={cn(
                            "w-3.5 h-3.5 shrink-0 object-contain",
                            isDark && serverIconInvert && "invert"
                          )}
                          onError={(e) => {
                            // Hide broken image, fallback icon will be shown via CSS
                            e.currentTarget.style.display = 'none'
                          }}
                        />
                      ) : (
                        <Icon className={cn("w-3.5 h-3.5 shrink-0", isCodeVariant ? "text-foreground/50" : "text-muted-foreground")} />
                      )}
                      <span className={cn(
                        isCodeVariant ? "text-foreground/70 font-medium" : "text-foreground font-medium",
                        isClickable && "hover:underline"
                      )}>{displayName}</span>
                      {/* Brief summary for completed tools */}
                      {execution.result && !execution.isExecuting && effectiveSuccess !== false && (() => {
                        const summary = getToolResultSummary(toolName, execution.result)
                        return summary ? (
                          <span className="text-muted-foreground/60 text-xs">
                            → {summary}
                          </span>
                        ) : null
                      })()}
                    </div>
                  )
                })()}

                {/* Error indicator */}
                {!execution.isExecuting && effectiveSuccess === false && !isRunBash && (
                  <div className="text-red-400 text-xs flex items-center">
                    <span className="text-muted-foreground/60 mr-1">⎿</span>failed
                  </div>
                )}
              </div>
            </div>


            {/* Execute code result - collapsible section */}
            {isExecuteCode && execution.result && !execution.isExecuting && (
              <ExecuteCodeResult result={execution.result} />
            )}


            {/* List files result - tree view */}
            {isListFiles && execution.result && !execution.isExecuting && (
              <FileListDisplay result={execution.result} />
            )}

            {/* Edit file diff - shows the changes made */}
            {isEditFile && execution.result && !execution.isExecuting && (
              <EditFileDiffResult
                result={execution.result}
                filePath={filePath || undefined}
                args={(() => {
                  try { return JSON.parse(execution.tool_call.function.arguments) } catch { return {} }
                })()}
              />
            )}

            {/* Write file content - expandable view of written content */}
            {isWriteFile && execution.result && !execution.isExecuting && (
              <WriteFileContentResult
                result={execution.result}
                filePath={filePath || undefined}
                args={(() => {
                  try { return JSON.parse(execution.tool_call.function.arguments) } catch { return {} }
                })()}
              />
            )}

            {/* Tool Discovery result - shows discovered tools */}
            {isToolDiscovery && execution.result && !execution.isExecuting && (
              <ToolDiscoveryResult result={execution.result} />
            )}

            {/* Programming Task (PTC) result - shows task execution details */}
            {isProgrammingTask && execution.result && !execution.isExecuting && (
              <ProgrammingTaskResult
                result={execution.result}
                code={(() => {
                  try { return JSON.parse(execution.tool_call.function.arguments)?.code } catch { return undefined }
                })()}
              />
            )}

            {/* Brave Search media carousel */}
            {braveSearchMedia && (
              <BraveSearchMediaCarousel
                items={braveSearchMedia}
                title={toolName === 'brave_image_search' ? 'Images' : 'Videos'}
              />
            )}

            {/* Knowledge Base results */}
            {knowledgeBaseResults && (
              <KnowledgeBaseResultsDisplay data={knowledgeBaseResults} />
            )}

            {/* List Tool results (Sparks, Images, Videos, Voice Rooms, MCP Servers, Models) */}
            {listToolData && (
              <ListToolResultsDisplay data={listToolData} />
            )}

            {/* Todos display */}
            {isUpdateTodos && execution.result && !execution.isExecuting && (
              <TodosDisplay result={execution.result} />
            )}

            {/* Process list results */}
            {isListProcesses && execution.result && !execution.isExecuting && (
              <ProcessListDisplay result={execution.result} />
            )}

            {/* Search code results */}
            {isSearchCode && execution.result && !execution.isExecuting && (
              <SearchCodeResult
                result={execution.result}
                pattern={(() => {
                  try { return JSON.parse(execution.tool_call.function.arguments)?.pattern } catch { return undefined }
                })()}
              />
            )}

            {/* Spark update diff - shows code changes */}
            {isUpdateSpark && execution.result && !execution.isExecuting && effectiveSuccess !== false && (
              <SparkUpdateDiff result={execution.result} />
            )}

            {/* Image generation result - intentionally NOT displayed here */}
            {/* Images are displayed outside the collapsible in MessageSteps */}

            {/* Video generation result - intentionally NOT displayed here */}
            {/* Videos are displayed outside the collapsible in MessageSteps */}
          </div>
        )
      })}
    </div>
  )
}
