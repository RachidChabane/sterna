/**
 * Tool id -> icon/display-name/file-path metadata, looked up once by the
 * dispatcher before it hands off to a renderer.
 */
import { FileText, FolderOpen, Pencil, Trash2, FolderPlus, FileEdit, Terminal, Image, Video, MapPin, Newspaper, Navigation, Store, Wind, Camera, Search, Code2, Building2, Palette, Wand2, Layers, ListTodo, Github, Maximize2, User, Play, Zap, BookOpen, ExternalLink, Film, Mic2, Server, Cpu, FolderGit2, Globe, Square, Activity, BrainCircuit } from 'lucide-react'
import { SearchPlusIcon } from '../icons/SearchPlusIcon'

// Map tool names to icons and display names
// If backendDisplayName is provided (from backend), use it instead of deriving from toolName
export const getToolInfo = (toolName: string, backendDisplayName?: string) => {
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
export const getFilePath = (toolName: string, argumentsStr: string): string | null => {
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
