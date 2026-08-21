/**
 * EditorTabs - Sortable tabs for open files with action buttons
 */

import { useState } from 'react'
import { X, Code, Eye, Columns } from 'lucide-react'
import { FileIcon } from './FileIcon'
import { cn } from '@/lib/utils'
import { supportsPreview, isBinaryPreviewable, type OpenFile } from './types'
import type { ViewMode } from './SplitView'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  DndContext,
  DragOverlay,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  horizontalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

interface EditorTabsProps {
  openFiles: OpenFile[]
  activeFilePath: string | null
  activeFile?: OpenFile | undefined
  isExecuting?: boolean
  viewMode?: ViewMode
  onReorder: (files: OpenFile[]) => void
  onSelectFile: (path: string) => void
  onCloseFile: (path: string) => void
  onSaveFile?: (path: string) => void
  onRunFile?: () => void
  onAbortExecution?: () => void
  onViewModeChange?: (mode: ViewMode) => void
}

interface SortableTabProps {
  file: OpenFile
  isActive: boolean
  onSelect: () => void
  onClose: (e: React.MouseEvent) => void
}

function SortableTab({ file, isActive, onSelect, onClose }: SortableTabProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: file.path })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  // Get display path (remove /workspace prefix)
  const displayPath = file.path.replace(/^\/workspace\/?/, '')

  return (
    <TooltipProvider>
      <Tooltip delayDuration={500}>
        <TooltipTrigger asChild>
          <div
            ref={setNodeRef}
            style={style}
            {...attributes}
            {...listeners}
            className={cn(
              'group flex items-center gap-2 px-3 py-1.5 text-sm rounded-t cursor-pointer transition-colors duration-200',
              isActive
                ? 'bg-background border border-b-0 border-accent-brand/20'
                : 'hover:bg-secondary',
              isDragging && 'z-50 shadow-lg'
            )}
            onClick={onSelect}
          >
            <FileIcon filename={file.name} className="h-3.5 w-3.5 shrink-0" />
            <span className="max-w-[120px] truncate text-foreground">
              {file.name}
              {file.isDirty && <span className="text-accent-brand ml-0.5">●</span>}
            </span>
            <button
              onClick={onClose}
              className={cn(
                "rounded p-0.5 transition-all duration-200 shrink-0",
                isActive
                  ? "opacity-60 hover:opacity-100 hover:bg-destructive/20 hover:text-destructive"
                  : "opacity-0 group-hover:opacity-60 hover:!opacity-100 hover:bg-destructive/20 hover:text-destructive"
              )}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs">
          <div className="text-xs">
            <div className="font-medium">{file.name}</div>
            <div className="text-muted-foreground mt-0.5">{displayPath}</div>
            {file.isDirty && (
              <div className="text-accent-brand mt-1">Unsaved changes</div>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}


export function EditorTabs({
  openFiles,
  activeFilePath,
  activeFile,
  isExecuting = false,
  viewMode = 'code',
  onReorder,
  onSelectFile,
  onCloseFile,
  onSaveFile,
  onRunFile,
  onAbortExecution,
  onViewModeChange,
}: EditorTabsProps) {
  const [activeTabId, setActiveTabId] = useState<string | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  const handleDragStart = (event: DragStartEvent) => {
    setActiveTabId(event.active.id as string)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      const oldIndex = openFiles.findIndex((item) => item.path === active.id)
      const newIndex = openFiles.findIndex((item) => item.path === over.id)
      onReorder(arrayMove(openFiles, oldIndex, newIndex))
    }

    setActiveTabId(null)
  }

  if (openFiles.length === 0) return null

  const showPreviewControls = activeFile && supportsPreview(activeFile.name) && onViewModeChange
  const isPreviewOnly = activeFile && isBinaryPreviewable(activeFile.name)

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex items-center border-b bg-muted/30 min-w-0">
        <div className="flex items-center gap-0.5 px-2 py-1 overflow-x-auto flex-1 min-w-0">
          <SortableContext
            items={openFiles.map(f => f.path)}
            strategy={horizontalListSortingStrategy}
          >
            {openFiles.map(file => (
              <SortableTab
                key={file.path}
                file={file}
                isActive={activeFilePath === file.path}
                onSelect={() => onSelectFile(file.path)}
                onClose={(e) => {
                  e.stopPropagation()
                  onCloseFile(file.path)
                }}
              />
            ))}
          </SortableContext>
        </div>

        {/* View Mode Toggle Buttons */}
        {showPreviewControls && (
          <div className="flex items-center gap-1 px-2 border-l border-border flex-shrink-0">
            <TooltipProvider>
              {/* Code button - hidden for preview-only files (XLSX, images, PDF) */}
              {!isPreviewOnly && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant={viewMode === 'code' ? 'secondary' : 'ghost'}
                      size="sm"
                      onClick={() => onViewModeChange('code')}
                      className="h-7 w-7 p-0"
                    >
                      <Code className="h-3.5 w-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Code only</TooltipContent>
                </Tooltip>
              )}

              {/* Split button - hidden for preview-only files */}
              {!isPreviewOnly && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant={viewMode === 'split' ? 'secondary' : 'ghost'}
                      size="sm"
                      onClick={() => onViewModeChange('split')}
                      className="h-7 w-7 p-0"
                    >
                      <Columns className="h-3.5 w-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Split view</TooltipContent>
                </Tooltip>
              )}

              {/* Preview button - always shown for files that support preview */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant={viewMode === 'preview' ? 'secondary' : 'ghost'}
                    size="sm"
                    onClick={() => onViewModeChange('preview')}
                    className="h-7 w-7 p-0"
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Preview{isPreviewOnly ? '' : ' only'}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        )}
      </div>
      <DragOverlay>
        {activeTabId ? (
          <div className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-t bg-background border border-accent-brand/20 shadow-lg">
            <FileIcon
              filename={openFiles.find(f => f.path === activeTabId)?.name || ''}
              className="h-3.5 w-3.5"
            />
            <span className="text-foreground">
              {openFiles.find(f => f.path === activeTabId)?.name}
            </span>
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  )
}
