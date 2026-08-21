/**
 * FileListDisplay Component
 *
 * Displays file listing results in a tree structure with file type icons.
 * Supports nested directories when depth > 1.
 */

import React, { useState, useMemo } from 'react'
import { ChevronRight, ChevronDown, Folder } from 'lucide-react'
import { cn } from '@/lib/utils'
import { FileIcon } from '@/components/sandbox/FileIcon'

interface FileEntry {
  name: string
  type: 'file' | 'directory'
  path?: string
}

interface TreeNode {
  name: string
  type: 'file' | 'directory'
  children: Map<string, TreeNode>
}

interface FileListDisplayProps {
  result: any
  className?: string
}

// Parse the result to extract file entries
const parseFileList = (result: any): { path: string, files: FileEntry[], depth: number } | null => {
  let data = result

  // Parse if string
  if (typeof data === 'string') {
    try { data = JSON.parse(data) } catch { return null }
  }

  // Extract nested structures
  if (data?.result) data = data.result
  if (typeof data === 'string') {
    try { data = JSON.parse(data) } catch { return null }
  }
  if (data?.data) data = data.data

  const path = data?.path || '/workspace'
  const depth = data?.depth || 1

  // Handle files array
  if (data?.files && Array.isArray(data.files)) {
    return {
      path,
      depth,
      files: data.files.map((f: any) => ({
        name: typeof f === 'string' ? f : f.name,
        type: (typeof f === 'object' && f.type === 'directory') ? 'directory' : 'file',
        path: typeof f === 'object' ? f.path : undefined
      }))
    }
  }

  return null
}

// Build a tree structure from flat file list
const buildTree = (files: FileEntry[]): TreeNode => {
  const root: TreeNode = { name: '', type: 'directory', children: new Map() }

  for (const file of files) {
    const parts = file.name.split('/').filter(Boolean)
    let current = root

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      const isLast = i === parts.length - 1

      if (!current.children.has(part)) {
        current.children.set(part, {
          name: part,
          type: isLast ? file.type : 'directory',
          children: new Map()
        })
      }
      current = current.children.get(part)!
    }
  }

  return root
}

// Render a tree node
const TreeNodeComponent = React.memo(({ node, level = 0 }: { node: TreeNode, level?: number }) => {
  const [isExpanded, setIsExpanded] = useState(level < 2) // Auto-expand first 2 levels
  const isDir = node.type === 'directory'
  const hasChildren = node.children.size > 0

  // Sort children: directories first, then alphabetically
  const sortedChildren = useMemo(() => {
    return Array.from(node.children.values()).sort((a, b) => {
      if (a.type !== b.type) return a.type === 'directory' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
  }, [node.children])

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-1.5 py-0.5 text-xs",
          hasChildren && "cursor-pointer hover:bg-muted/30 rounded px-1 -mx-1"
        )}
        onClick={() => hasChildren && setIsExpanded(!isExpanded)}
      >
        {hasChildren ? (
          isExpanded ? <ChevronDown className="w-3 h-3 text-muted-foreground/50" /> : <ChevronRight className="w-3 h-3 text-muted-foreground/50" />
        ) : (
          <span className="w-3" />
        )}
        {isDir ? (
          <Folder className="w-4 h-4 text-amber-400/80 shrink-0" />
        ) : (
          <FileIcon filename={node.name} className="w-4 h-4 shrink-0" />
        )}
        <span className={cn("truncate", isDir ? "text-foreground" : "text-muted-foreground")}>
          {node.name}
        </span>
      </div>
      {hasChildren && isExpanded && (
        <div className="ml-4 pl-2 border-l border-border/30">
          {sortedChildren.map((child) => (
            <TreeNodeComponent key={child.name} node={child} level={level + 1} />
          ))}
        </div>
      )}
    </div>
  )
})

export const FileListDisplay = React.memo(({ result, className }: FileListDisplayProps) => {
  const [isExpanded, setIsExpanded] = useState(false)

  const parsed = parseFileList(result)

  // Show "(no content)" when no files or parsing failed
  if (!parsed || parsed.files.length === 0) {
    return (
      <div className={cn("ml-5 text-xs text-muted-foreground/60 flex items-center", className)}>
        <span className="mr-1">⎿</span><span className="italic">(no content)</span>
      </div>
    )
  }

  // Build tree if we have nested paths (depth > 1)
  const hasNestedPaths = parsed.files.some(f => f.name.includes('/'))
  const tree = useMemo(() => hasNestedPaths ? buildTree(parsed.files) : null, [parsed.files, hasNestedPaths])

  // Count stats
  const dirCount = parsed.files.filter(f => f.type === 'directory').length
  const fileCount = parsed.files.filter(f => f.type === 'file').length

  return (
    <div className={cn("ml-5", className)}>
      <div className="flex items-center text-xs text-muted-foreground/60">
        <span className="mr-1">⎿</span>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-1 text-muted-foreground/70 hover:text-muted-foreground transition-colors"
        >
          <span>
            {dirCount > 0 && `${dirCount} folder${dirCount !== 1 ? 's' : ''}`}
            {dirCount > 0 && fileCount > 0 && ', '}
            {fileCount > 0 && `${fileCount} file${fileCount !== 1 ? 's' : ''}`}
          </span>
          {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        </button>
      </div>

      {isExpanded && (
        <div className="mt-1 ml-1 pl-2 border-l border-border/50">
          {tree ? (
            // Render as tree for nested paths
            Array.from(tree.children.values())
              .sort((a, b) => {
                if (a.type !== b.type) return a.type === 'directory' ? -1 : 1
                return a.name.localeCompare(b.name)
              })
              .map((child) => (
                <TreeNodeComponent key={child.name} node={child} />
              ))
          ) : (
            // Render flat list for single level
            [...parsed.files]
              .sort((a, b) => {
                if (a.type !== b.type) return a.type === 'directory' ? -1 : 1
                return a.name.localeCompare(b.name)
              })
              .map((file, idx) => (
                <div key={`${file.name}-${idx}`} className="flex items-center gap-1.5 py-0.5 text-xs">
                  <span className="w-3" />
                  {file.type === 'directory' ? (
                    <Folder className="w-4 h-4 text-amber-400/80 shrink-0" />
                  ) : (
                    <FileIcon filename={file.name} className="w-4 h-4 shrink-0" />
                  )}
                  <span className={cn("truncate", file.type === 'directory' ? "text-foreground" : "text-muted-foreground")}>
                    {file.name}
                  </span>
                </div>
              ))
          )}
        </div>
      )}
    </div>
  )
})
