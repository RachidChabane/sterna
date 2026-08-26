/**
 * Tool id -> renderer registry, mirroring the backend's per-tool plugin
 * pattern (`llm.agent_core.tools`, discovered by `discover_tools()`): the
 * dispatcher never branches on a tool name itself, it looks the id up
 * here and hands off.
 *
 * Most ids are framed (rendered inside `ToolFrame`); Coding Agent's
 * variants are standalone and replace the row entirely. An id absent
 * from `RENDERERS` and not matched by `isListToolName` falls back to
 * `DEFAULT_ENTRY` — the icon + name + one-line summary treatment that
 * covers every tool this registry has no bespoke opinion about,
 * including one the backend adds tomorrow.
 */
import { isListToolName } from '../ListToolResultsDisplay'
import { GenericHeader } from './generic'
import { FilePathHeader } from './file-path'
import { WriteFileBody } from './write-file'
import { EditFileBody } from './edit-file'
import { ListFilesBody } from './list-files'
import { RunBashHeader, deriveRunBashEffectiveSuccess } from './run-bash'
import { ToolDiscoveryHeader, ToolDiscoveryBody } from './tool-discovery'
import { ExecuteCodeBody } from './execute-code'
import { ProgrammingTaskBody } from './programming-task'
import { TodosBody } from './todos'
import { SearchCodeBody } from './search-code'
import { KnowledgeBaseBody } from './knowledge-base'
import { ProcessListBody } from './process-list'
import { BraveMediaBody } from './brave-media'
import { SparkUpdateBody } from './spark'
import { ListToolsBody } from './list-tools'
import { CodingAgentStandalone } from './coding-agent'
import type { RendererEntry, FramedRendererEntry } from './types'

export const DEFAULT_ENTRY: FramedRendererEntry = { kind: 'framed', Header: GenericHeader }

const framed = (entry: Omit<FramedRendererEntry, 'kind'>): FramedRendererEntry => ({ kind: 'framed', ...entry })

const FILE_PATH_ENTRY = framed({ Header: FilePathHeader })
const CODING_AGENT_ENTRY: RendererEntry = { kind: 'standalone', Component: CodingAgentStandalone }

const RENDERERS: Record<string, RendererEntry> = {
  // File operations — path-prefixed header, some with a result body.
  read_file: FILE_PATH_ENTRY,
  write_file: framed({ Header: FilePathHeader, Body: WriteFileBody }),
  edit_file: framed({ Header: FilePathHeader, Body: EditFileBody }),
  delete_file: FILE_PATH_ENTRY,
  list_files: framed({ Header: FilePathHeader, Body: ListFilesBody }),
  create_directory: FILE_PATH_ENTRY,
  rename_file: FILE_PATH_ENTRY,

  // Shell: its own header carries the command + collapsible output; the
  // frame's error row is suppressed since run_bash renders its own.
  run_bash: framed({
    Header: RunBashHeader,
    suppressErrorRow: true,
    deriveEffectiveSuccess: deriveRunBashEffectiveSuccess,
  }),

  search_available_tools: framed({ Header: ToolDiscoveryHeader, Body: ToolDiscoveryBody }),
  execute_code: framed({ Header: GenericHeader, Body: ExecuteCodeBody }),
  execute_programming_task: framed({ Header: GenericHeader, Body: ProgrammingTaskBody }),
  update_todos: framed({ Header: GenericHeader, Body: TodosBody }),
  search_code: framed({ Header: GenericHeader, Body: SearchCodeBody }),
  query_knowledge_base: framed({ Header: GenericHeader, Body: KnowledgeBaseBody }),
  list_processes: framed({ Header: GenericHeader, Body: ProcessListBody }),
  brave_image_search: framed({ Header: GenericHeader, Body: BraveMediaBody }),
  brave_video_search: framed({ Header: GenericHeader, Body: BraveMediaBody }),

  create_spark: framed({ Header: GenericHeader }),
  update_spark: framed({ Header: GenericHeader, Body: SparkUpdateBody }),

  coding_agent: CODING_AGENT_ENTRY,
  plan_implementation: CODING_AGENT_ENTRY,
  implement_plan: CODING_AGENT_ENTRY,
  edit_plan: CODING_AGENT_ENTRY,
}

const LIST_TOOL_ENTRY = framed({ Header: GenericHeader, Body: ListToolsBody })

/**
 * Resolve a tool id to its renderer entry. Explicit ids in `RENDERERS`
 * win; the dynamic "list" tool family (owned by ListToolResultsDisplay's
 * own registry) is checked next; anything else gets `DEFAULT_ENTRY`.
 */
export function getRendererEntry(toolName: string): RendererEntry {
  const explicit = RENDERERS[toolName]
  if (explicit) return explicit
  if (isListToolName(toolName)) return LIST_TOOL_ENTRY
  return DEFAULT_ENTRY
}
