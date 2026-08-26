/**
 * Body for the "list" tool family (sparks, generated images/videos, voice
 * rooms, MCP servers, models, knowledge-base documents, coding agents,
 * update_coding_agent): delegates entirely to ListToolResultsDisplay,
 * whose own registry already owns the set of tool ids it covers.
 */
import { ListToolResultsDisplay, extractListToolData } from '../ListToolResultsDisplay'
import type { ToolRenderContext } from './types'

export function ListToolsBody({ execution, toolName }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting || execution.success === false) return null

  const data = extractListToolData(toolName, execution.result)
  if (!data) return null

  return <ListToolResultsDisplay data={data} />
}
