/** list_files body: the tree view of the returned listing. */
import { FileListDisplay } from '../FileListDisplay'
import type { ToolRenderContext } from './types'

export function ListFilesBody({ execution }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting) return null
  return <FileListDisplay result={execution.result} />
}
