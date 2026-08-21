/**
 * FileTreeNode - A single node in the file tree
 */

import { useState } from 'react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import {
  Folder,
  FolderOpen,
  FilePlus,
  FolderPlus,
  Trash2,
  Edit2,
  ChevronRight,
  ChevronDown,
  MoreVertical,
  Info,
  Download,
} from 'lucide-react'
import { FileIcon } from './FileIcon'
import { cn } from '@/lib/utils'
import type { FileNode } from './types'

interface FileTreeNodeProps {
  node: FileNode
  depth: number
  selectedPath: string | null
  draggedNode: FileNode | null
  /** File is newly created (untracked) - shown in blue */
  isNew?: boolean
  /** File has been modified but not staged - shown in orange/red */
  isModified?: boolean
  /** File has been staged (git add) - shown in green */
  isStaged?: boolean
  /** Pass through for recursive rendering */
  modifiedFilePaths?: string[]
  stagedFilePaths?: string[]
  newFilePaths?: string[]
  onSelect: (path: string) => void
  onClick: (node: FileNode) => void
  onDragStart: (node: FileNode) => void
  onDragOver: (e: React.DragEvent, node: FileNode) => void
  onDragLeave: (e: React.DragEvent) => void
  onDrop: (e: React.DragEvent, node: FileNode) => void
  onNewFile: (parentPath: string) => void
  onNewFolder: (parentPath: string) => void
  onRename: (path: string, name: string) => void
  onDelete: (path: string) => void
  onShowDetails?: (path: string, name: string) => void
  onDownload?: (path: string, name: string) => void
  renderChildren?: (children: FileNode[], depth: number) => React.ReactNode
}

export function FileTreeNode({
  node,
  depth,
  selectedPath,
  draggedNode,
  isNew = false,
  isModified = false,
  isStaged = false,
  modifiedFilePaths = [],
  stagedFilePaths = [],
  newFilePaths = [],
  onSelect,
  onClick,
  onDragStart,
  onDragOver,
  onDragLeave,
  onDrop,
  onNewFile,
  onNewFolder,
  onRename,
  onDelete,
  onShowDetails,
  onDownload,
  renderChildren,
}: FileTreeNodeProps) {
  const [isHovered, setIsHovered] = useState(false)
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)

  return (
    <div>
      <div
        data-path={node.path}
        draggable
        onDragStart={(e) => {
          e.stopPropagation()
          onDragStart(node)
          if (e.dataTransfer) {
            e.dataTransfer.effectAllowed = 'move'
            e.dataTransfer.setData('text/plain', node.path)
          }
        }}
        onDragOver={(e) => onDragOver(e, node)}
        onDragLeave={onDragLeave}
        onDrop={(e) => onDrop(e, node)}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={cn(
          'group flex items-center gap-1 px-2 py-1 text-sm cursor-pointer hover:bg-secondary rounded-sm transition-colors duration-200 whitespace-nowrap relative',
          selectedPath === node.path && 'bg-accent-brand/10 border-l-2 border-accent-brand',
          draggedNode?.path === node.path && 'opacity-50'
        )}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={(e) => {
          e.stopPropagation()
          onSelect(node.path)
          onClick(node)
        }}
      >
        {node.type === 'directory' ? (
          <>
            {node.isOpen ? (
              <ChevronDown className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
            )}
            {node.isOpen ? (
              <FolderOpen className="h-4 w-4 text-accent-brand flex-shrink-0" />
            ) : (
              <Folder className="h-4 w-4 text-accent-brand flex-shrink-0" />
            )}
          </>
        ) : (
          <FileIcon filename={node.name} className="ml-3 h-4 w-4 flex-shrink-0" />
        )}
        <span className={cn(
          "flex-1 truncate",
          // Git status colors (priority: new > staged > modified)
          isNew && "text-blue-400",
          !isNew && isStaged && "text-emerald-400",
          !isNew && !isStaged && isModified && "text-amber-400"
        )}>{node.name}</span>

        {/* Actions button - appears on hover */}
        <DropdownMenu open={isDropdownOpen} onOpenChange={setIsDropdownOpen}>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                'h-5 w-5 p-0 hover:bg-accent-brand/20 transition-opacity duration-200',
                // Mobile: always visible, Desktop: show on hover
                'opacity-100 md:opacity-0 md:pointer-events-none',
                (isHovered || isDropdownOpen) && 'md:opacity-100 md:pointer-events-auto'
              )}
              onClick={(e) => {
                e.stopPropagation()
              }}
            >
              <MoreVertical className="h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            {node.type === 'directory' && (
              <>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    onNewFile(node.path)
                    setIsDropdownOpen(false)
                  }}
                >
                  <FilePlus className="h-4 w-4 mr-2" />
                  New File
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    onNewFolder(node.path)
                    setIsDropdownOpen(false)
                  }}
                >
                  <FolderPlus className="h-4 w-4 mr-2" />
                  New Folder
                </DropdownMenuItem>
              </>
            )}
            {node.type === 'file' && onShowDetails && (
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onShowDetails(node.path, node.name)
                  setIsDropdownOpen(false)
                }}
              >
                <Info className="h-4 w-4 mr-2" />
                Details
              </DropdownMenuItem>
            )}
            {node.type === 'file' && onDownload && (
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onDownload(node.path, node.name)
                  setIsDropdownOpen(false)
                }}
              >
                <Download className="h-4 w-4 mr-2" />
                Download
              </DropdownMenuItem>
            )}
            <DropdownMenuItem
              onClick={(e) => {
                e.stopPropagation()
                onRename(node.path, node.name)
                setIsDropdownOpen(false)
              }}
            >
              <Edit2 className="h-4 w-4 mr-2" />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={(e) => {
                e.stopPropagation()
                onDelete(node.path)
                setIsDropdownOpen(false)
              }}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {node.type === 'directory' && node.isOpen && node.children && renderChildren && (
        renderChildren(node.children, depth + 1)
      )}
    </div>
  )
}
