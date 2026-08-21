/**
 * QuickFileSearch - Ctrl+P style file search dialog
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Search, File, Clock } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { FileIcon } from './FileIcon'
import type { FileNode } from './types'

interface QuickFileSearchProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  fileTree: FileNode[]
  recentFiles?: string[]
  onSelectFile: (path: string, name: string) => void
}

// Flatten file tree into a list of files
function flattenFileTree(nodes: FileNode[], result: { path: string; name: string }[] = []): { path: string; name: string }[] {
  for (const node of nodes) {
    if (node.type === 'file') {
      result.push({ path: node.path, name: node.name })
    } else if (node.children) {
      flattenFileTree(node.children, result)
    }
  }
  return result
}

// Fuzzy match score
function fuzzyMatch(query: string, text: string): { match: boolean; score: number } {
  const queryLower = query.toLowerCase()
  const textLower = text.toLowerCase()

  // Exact match gets highest score
  if (textLower === queryLower) return { match: true, score: 100 }

  // Contains gets high score
  if (textLower.includes(queryLower)) {
    const index = textLower.indexOf(queryLower)
    // Prefer matches at start of filename
    return { match: true, score: 80 - index }
  }

  // Fuzzy match - all chars must appear in order
  let queryIndex = 0
  let score = 0
  let consecutiveBonus = 0

  for (let i = 0; i < textLower.length && queryIndex < queryLower.length; i++) {
    if (textLower[i] === queryLower[queryIndex]) {
      queryIndex++
      score += 10 + consecutiveBonus
      consecutiveBonus += 5
    } else {
      consecutiveBonus = 0
    }
  }

  if (queryIndex === queryLower.length) {
    return { match: true, score }
  }

  return { match: false, score: 0 }
}

export function QuickFileSearch({
  open,
  onOpenChange,
  fileTree,
  recentFiles = [],
  onSelectFile,
}: QuickFileSearchProps) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // Flatten file tree
  const allFiles = useMemo(() => flattenFileTree(fileTree), [fileTree])

  // Filter and sort files
  const filteredFiles = useMemo(() => {
    if (!query.trim()) {
      // Show recent files first, then all files
      const recentSet = new Set(recentFiles)
      const recent = recentFiles
        .map(path => allFiles.find(f => f.path === path))
        .filter((f): f is { path: string; name: string } => f !== undefined)

      const others = allFiles.filter(f => !recentSet.has(f.path))

      return {
        recent,
        files: others.slice(0, 50), // Limit to 50 for performance
      }
    }

    // Fuzzy search
    const scored = allFiles
      .map(file => {
        const nameMatch = fuzzyMatch(query, file.name)
        const pathMatch = fuzzyMatch(query, file.path)
        const bestScore = Math.max(nameMatch.score, pathMatch.score * 0.5)
        return {
          ...file,
          match: nameMatch.match || pathMatch.match,
          score: bestScore,
        }
      })
      .filter(f => f.match)
      .sort((a, b) => b.score - a.score)
      .slice(0, 50)

    return {
      recent: [],
      files: scored,
    }
  }, [query, allFiles, recentFiles])

  const totalResults = filteredFiles.recent.length + filteredFiles.files.length

  // Reset selection when results change
  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  // Focus input when dialog opens
  useEffect(() => {
    if (open) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  // Keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(i => Math.min(i + 1, totalResults - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(i => Math.max(i - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        const allResults = [...filteredFiles.recent, ...filteredFiles.files]
        const selected = allResults[selectedIndex]
        if (selected) {
          onSelectFile(selected.path, selected.name)
          onOpenChange(false)
        }
        break
      case 'Escape':
        e.preventDefault()
        onOpenChange(false)
        break
    }
  }, [selectedIndex, totalResults, filteredFiles, onSelectFile, onOpenChange])

  const handleSelectFile = (path: string, name: string) => {
    onSelectFile(path, name)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] p-0 gap-0 flex flex-col overflow-hidden" hideCloseButton>
        <DialogTitle className="sr-only">Quick File Search</DialogTitle>

        {/* Search input */}
        <div className="flex items-center gap-2 px-3 border-b shrink-0">
          <Search className="h-4 w-4 text-muted-foreground shrink-0" />
          <Input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search files by name..."
            className="h-12 border-0 focus-visible:ring-0 focus-visible:ring-offset-0 text-base"
          />
          <kbd className="hidden sm:inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="overflow-y-auto max-h-[400px]">
          <div className="py-2">
            {/* Recent files section */}
            {filteredFiles.recent.length > 0 && (
              <div>
                <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                  <Clock className="h-3 w-3" />
                  Recent Files
                </div>
                {filteredFiles.recent.map((file, index) => (
                  <FileResultItem
                    key={file.path}
                    file={file}
                    isSelected={selectedIndex === index}
                    onClick={() => handleSelectFile(file.path, file.name)}
                  />
                ))}
              </div>
            )}

            {/* All files / Search results */}
            {filteredFiles.files.length > 0 && (
              <div>
                {!query && filteredFiles.recent.length > 0 && (
                  <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground flex items-center gap-1.5 mt-2">
                    <File className="h-3 w-3" />
                    All Files
                  </div>
                )}
                {filteredFiles.files.map((file, index) => (
                  <FileResultItem
                    key={file.path}
                    file={file}
                    isSelected={selectedIndex === filteredFiles.recent.length + index}
                    onClick={() => handleSelectFile(file.path, file.name)}
                  />
                ))}
              </div>
            )}

            {/* No results */}
            {totalResults === 0 && (
              <div className="px-3 py-8 text-center text-sm text-muted-foreground">
                No files found
              </div>
            )}
          </div>
        </div>

        {/* Footer hint */}
        <div className="px-3 py-2 border-t bg-muted/30 text-xs text-muted-foreground flex items-center gap-4 shrink-0">
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-muted border text-[10px]">↑↓</kbd>
            Navigate
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-muted border text-[10px]">Enter</kbd>
            Open
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-muted border text-[10px]">Esc</kbd>
            Close
          </span>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// Individual file result item
function FileResultItem({
  file,
  isSelected,
  onClick,
}: {
  file: { path: string; name: string }
  isSelected: boolean
  onClick: () => void
}) {
  // Get relative path (remove /workspace prefix)
  const displayPath = file.path.replace(/^\/workspace\/?/, '')
  const directory = displayPath.substring(0, displayPath.lastIndexOf('/'))

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-muted/50 transition-colors",
        isSelected && "bg-accent-brand/10 hover:bg-accent-brand/15"
      )}
    >
      <FileIcon filename={file.name} className="h-4 w-4 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className={cn("text-sm truncate", isSelected && "text-accent-brand font-medium")}>
          {file.name}
        </div>
        {directory && (
          <div className="text-xs text-muted-foreground truncate">
            {directory}
          </div>
        )}
      </div>
    </button>
  )
}
