/** update_todos body: the task checklist. */
import { memo } from 'react'
import { cn } from '@/lib/utils'
import { Check } from 'lucide-react'
import { deepParse } from './shared'
import type { ToolRenderContext } from './types'

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

export function TodosBody({ execution }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting) return null
  return <TodosDisplay result={execution.result} />
}

// Component for displaying todos inline
const TodosDisplay = memo(({ result }: { result: any }) => {
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
