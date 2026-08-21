/**
 * FileTreePanel - Complete file tree sidebar with drag & drop
 */

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'
import {
  Loader2,
  FilePlus,
  FolderPlus,
  PanelLeftClose,
  PanelLeft,
  GripVertical,
  Download,
  MoreVertical,
  Upload,
  Eye,
  EyeOff,
} from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { FileTreeNode } from './FileTreeNode'
import type { FileNode } from './types'

interface FileTreePanelProps {
  fileTree: FileNode[]
  isLoadingTree: boolean
  selectedPath: string | null
  isSidebarCollapsed: boolean
  sidebarWidth: number
  isResizing: boolean
  showHiddenFiles: boolean
  /** When true, hides header and uses simplified layout for mobile sheet */
  isMobileSheet?: boolean
  /** List of file paths that have been modified (for git status coloring) */
  modifiedFilePaths?: string[]
  /** List of file paths that have been staged/added (for git status coloring) */
  stagedFilePaths?: string[]
  /** List of file paths that are new/untracked (for git status coloring) */
  newFilePaths?: string[]
  onSelectPath: (path: string) => void
  onToggleDirectory: (path: string) => void
  onOpenFile: (path: string, name: string) => void
  onNewFile: (parentPath: string) => void
  onNewFolder: (parentPath: string) => void
  onRename: (path: string, oldName: string) => void
  onDelete: (path: string) => void
  onShowDetails?: (path: string, name: string) => void
  onDownload?: (path: string, name: string) => void
  onDownloadWorkspace?: () => void
  onImport?: () => void
  onMove: (draggedNode: FileNode, targetNode: FileNode) => void
  onToggleSidebar: (collapsed: boolean) => void
  onToggleShowHiddenFiles: () => void
  onStartResize: () => void
  getParentPathForNewItem: () => string
}

export function FileTreePanel({
  fileTree,
  isLoadingTree,
  selectedPath,
  isSidebarCollapsed,
  sidebarWidth,
  isResizing,
  showHiddenFiles,
  isMobileSheet = false,
  modifiedFilePaths = [],
  stagedFilePaths = [],
  newFilePaths = [],
  onSelectPath,
  onToggleDirectory,
  onOpenFile,
  onNewFile,
  onNewFolder,
  onRename,
  onDelete,
  onShowDetails,
  onDownload,
  onDownloadWorkspace,
  onImport,
  onMove,
  onToggleSidebar,
  onToggleShowHiddenFiles,
  onStartResize,
  getParentPathForNewItem,
}: FileTreePanelProps) {
  const [draggedNode, setDraggedNode] = useState<FileNode | null>(null)

  const handleTreeDragStart = (node: FileNode) => {
    setDraggedNode(node)
  }

  const handleTreeDragOver = (e: React.DragEvent, targetNode: FileNode) => {
    e.preventDefault()
    e.stopPropagation()

    if (targetNode.type === 'directory') {
      e.currentTarget.classList.add('bg-accent-brand/20')
    }
  }

  const handleTreeDragLeave = (e: React.DragEvent) => {
    e.currentTarget.classList.remove('bg-accent-brand/20')
  }

  const handleTreeDrop = (e: React.DragEvent, targetNode: FileNode) => {
    e.preventDefault()
    e.stopPropagation()
    e.currentTarget.classList.remove('bg-accent-brand/20')

    if (draggedNode && targetNode.type === 'directory') {
      onMove(draggedNode, targetNode)
    }

    setDraggedNode(null)
  }

  const handleNodeClick = (node: FileNode) => {
    if (node.type === 'directory') {
      onToggleDirectory(node.path)
    } else {
      onOpenFile(node.path, node.name)
    }
  }

  // Normalize path for comparison (removes trailing slashes, handles edge cases)
  const normalizePath = (p: string) => p.replace(/\/+$/, '').replace(/\/+/g, '/')

  // Convert file paths to Sets for O(1) lookup, with normalized paths
  const modifiedSet = new Set(modifiedFilePaths.map(normalizePath))
  const stagedSet = new Set(stagedFilePaths.map(normalizePath))
  const newSet = new Set(newFilePaths.map(normalizePath))

  // Debug: log paths for git status coloring
  if (modifiedFilePaths.length > 0) {
    
    
  }

  const renderFileTree = (nodes: FileNode[], depth: number = 0): React.ReactNode => {
    return nodes.map(node => (
      <FileTreeNode
        key={node.path}
        node={node}
        depth={depth}
        selectedPath={selectedPath}
        draggedNode={draggedNode}
        isNew={newSet.has(normalizePath(node.path))}
        isModified={modifiedSet.has(normalizePath(node.path))}
        isStaged={stagedSet.has(normalizePath(node.path))}
        onSelect={onSelectPath}
        onClick={handleNodeClick}
        onDragStart={handleTreeDragStart}
        onDragOver={handleTreeDragOver}
        onDragLeave={handleTreeDragLeave}
        onDrop={handleTreeDrop}
        onNewFile={onNewFile}
        onNewFolder={onNewFolder}
        onRename={onRename}
        onDelete={onDelete}
        onShowDetails={onShowDetails}
        onDownload={onDownload}
        modifiedFilePaths={modifiedFilePaths}
        stagedFilePaths={stagedFilePaths}
        newFilePaths={newFilePaths}
        renderChildren={renderFileTree}
      />
    ))
  }

  // Desktop collapsed state - not used in mobile sheet
  if (isSidebarCollapsed && !isMobileSheet) {
    return (
      <div className="border-r flex flex-col bg-muted/30 w-12">
        <div className="flex flex-col items-center gap-2 pt-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-accent-brand hover:text-accent-brand hover:bg-accent-brand/10"
            onClick={() => onToggleSidebar(false)}
            title="Show Explorer"
          >
            <PanelLeft className="h-4 w-4" />
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        "flex flex-col relative",
        !isMobileSheet && "border-r bg-muted/30",
        !isMobileSheet && isResizing && "shadow-glow border-accent-brand/20"
      )}
      style={!isMobileSheet ? {
        width: `${sidebarWidth}px`,
        minWidth: '180px',
        maxWidth: `min(50vw, 800px)`,
        flexShrink: 0
      } : undefined}
    >
      {/* Header - simplified for mobile sheet */}
      {isMobileSheet ? (
        <div className="flex items-center justify-between px-3 py-2 border-b">
          {/* Quick actions for mobile */}
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onNewFile(getParentPathForNewItem())}
              className="h-8 px-2 text-xs"
            >
              <FilePlus className="h-3.5 w-3.5 mr-1" />
              New
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onNewFolder(getParentPathForNewItem())}
              className="h-8 px-2 text-xs"
            >
              <FolderPlus className="h-3.5 w-3.5 mr-1" />
              Folder
            </Button>
          </div>

          {/* More actions */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
              >
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              {onImport && (
                <DropdownMenuItem onClick={onImport} className="cursor-pointer">
                  <Upload className="h-4 w-4 mr-2" />
                  Import
                </DropdownMenuItem>
              )}
              {onDownloadWorkspace && (
                <DropdownMenuItem onClick={onDownloadWorkspace} className="cursor-pointer">
                  <Download className="h-4 w-4 mr-2" />
                  Export All
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onToggleShowHiddenFiles} className="cursor-pointer">
                {showHiddenFiles ? <EyeOff className="h-4 w-4 mr-2" /> : <Eye className="h-4 w-4 mr-2" />}
                {showHiddenFiles ? 'Hide System Files' : 'Show Hidden Files'}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ) : (
        <div className="flex items-center justify-between px-2 py-2 border-b bg-background gap-1 overflow-hidden">
          <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden">
            <span className="text-sm font-semibold text-foreground shrink-0">Explorer</span>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {/* Actions Menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 hover:bg-accent-brand/10 hover:text-accent-brand transition-colors duration-200"
                >
                  <MoreVertical className="h-3.5 w-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuItem
                  onClick={() => onNewFile(getParentPathForNewItem())}
                  className="cursor-pointer"
                >
                  <FilePlus className="h-4 w-4 mr-2" />
                  New File
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => onNewFolder(getParentPathForNewItem())}
                  className="cursor-pointer"
                >
                  <FolderPlus className="h-4 w-4 mr-2" />
                  New Folder
                </DropdownMenuItem>
                {onImport && (
                  <DropdownMenuItem
                    onClick={onImport}
                    className="cursor-pointer"
                  >
                    <Upload className="h-4 w-4 mr-2" />
                    Import
                  </DropdownMenuItem>
                )}
                {onDownloadWorkspace && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={onDownloadWorkspace}
                      className="cursor-pointer"
                    >
                      <Download className="h-4 w-4 mr-2" />
                      Export All
                    </DropdownMenuItem>
                  </>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={onToggleShowHiddenFiles}
                  className="cursor-pointer"
                >
                  {showHiddenFiles ? (
                    <EyeOff className="h-4 w-4 mr-2" />
                  ) : (
                    <Eye className="h-4 w-4 mr-2" />
                  )}
                  {showHiddenFiles ? 'Hide System Files' : 'Show Hidden Files'}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 hover:bg-secondary transition-colors duration-200"
              onClick={() => onToggleSidebar(true)}
              title="Hide Explorer"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* File Tree */}
      <ScrollArea
        className="flex-1"
        onClick={(e) => {
          const target = e.target as HTMLElement
          const isFileTreeNode = target.closest('[data-path]')

          if (!isFileTreeNode) {
            onSelectPath('/workspace')
          }
        }}
      >
        <div className="py-1 min-w-max">
          {isLoadingTree ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            renderFileTree(fileTree)
          )}
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>

      {/* Resize Handle - hidden in mobile sheet */}
      {!isMobileSheet && (
        <div
          className="absolute top-0 right-0 w-2 h-full cursor-col-resize hover:bg-accent-brand/20 active:bg-accent-brand/40 transition-colors duration-200 group z-10"
          onMouseDown={onStartResize}
          title="Drag to resize"
        >
          <div className="absolute top-1/2 right-0 transform -translate-y-1/2 translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-background rounded-full p-0.5 border border-accent-brand/30 shadow-sm">
            <GripVertical className="h-3 w-3 text-accent-brand" />
          </div>
        </div>
      )}
    </div>
  )
}
