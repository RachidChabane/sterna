import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical } from 'lucide-react'

export function SortableItem({ id, children }: { id: string; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  }

  return (
    <div ref={setNodeRef} style={style} className="bg-background rounded-md border p-2">
      <div className="flex items-start gap-2">
        <button className="cursor-grab text-muted-foreground" {...attributes} {...listeners}>
          <GripVertical className="h-4 w-4" />
        </button>
        <div className="flex-1">
          {children}
        </div>
      </div>
    </div>
  )
}
