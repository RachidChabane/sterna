/**
 * GlobalSearch - Ctrl+Shift+F style search across all files
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { Search, Loader2, ChevronRight, ChevronDown } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { FileIcon } from './FileIcon'
import { fsAPI } from '@/api/fs'
import type { FileNode } from './types'

interface SearchResult {
  path: string
  name: string
  matches: {
    line: number
    content: string
    matchStart: number
    matchEnd: number
  }[]
}

interface GlobalSearchProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  fileTree: FileNode[]
  userId?: string
  projectId: string
  onSelectFile: (path: string, name: string, line?: number) => void
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

// Check if file is searchable (not binary)
function isSearchableFile(filename: string): boolean {
  const binaryExtensions = new Set([
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico', 'svg',
    'pdf', 'zip', 'tar', 'gz', 'rar', '7z',
    'mp3', 'mp4', 'wav', 'avi', 'mov', 'webm',
    'exe', 'dll', 'so', 'dylib',
    'woff', 'woff2', 'ttf', 'eot', 'otf',
    'xlsx', 'xls', 'doc', 'docx', 'ppt', 'pptx',
    'pyc', 'class', 'o', 'obj',
  ])
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return !binaryExtensions.has(ext)
}

export function GlobalSearch({
  open,
  onOpenChange,
  fileTree,
  userId,
  projectId,
  onSelectFile,
}: GlobalSearchProps) {
  const [query, setQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [isLoadingFiles, setIsLoadingFiles] = useState(false)
  const [results, setResults] = useState<SearchResult[]>([])
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set())
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [caseSensitive, setCaseSensitive] = useState(false)
  const [useRegex, setUseRegex] = useState(false)
  const [allFiles, setAllFiles] = useState<{ path: string; name: string }[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const filesLoadedRef = useRef(false)

  // Recursively fetch all files from the filesystem
  const loadAllFiles = useCallback(async () => {
    if (!userId || filesLoadedRef.current) return

    setIsLoadingFiles(true)
    const files: { path: string; name: string }[] = []

    const loadDirectory = async (path: string) => {
      try {
        const result = await fsAPI.listFiles({
          user_id: userId,
          conversation_id: projectId,
          chat_id: projectId,
          project_id: projectId,
          sync_mode: true,
          path,
        })

        if (result.success && result.files) {
          for (const file of result.files) {
            if (file.type === 'file' && isSearchableFile(file.name)) {
              files.push({ path: file.path, name: file.name })
            } else if (file.type === 'directory' && !file.name.startsWith('.') && file.name !== 'node_modules') {
              await loadDirectory(file.path)
            }
          }
        }
      } catch (error) {
        console.error('Failed to load directory:', path, error)
      }
    }

    await loadDirectory('/workspace')
    setAllFiles(files)
    filesLoadedRef.current = true
    setIsLoadingFiles(false)
  }, [userId, projectId])

  // Load files when dialog opens
  useEffect(() => {
    if (open && !filesLoadedRef.current) {
      loadAllFiles()
    }
  }, [open, loadAllFiles])

  // Reset when dialog closes
  useEffect(() => {
    if (!open) {
      filesLoadedRef.current = false
      setAllFiles([])
    }
  }, [open])

  // Search files
  const performSearch = useCallback(async (searchQuery: string) => {
    if (!searchQuery.trim() || !userId) {
      setResults([])
      return
    }

    setIsSearching(true)
    const searchResults: SearchResult[] = []

    try {
      // Search in batches for better performance
      const batchSize = 10
      for (let i = 0; i < allFiles.length; i += batchSize) {
        const batch = allFiles.slice(i, i + batchSize)

        await Promise.all(
          batch.map(async (file) => {
            try {
              const result = await fsAPI.readFile({
                user_id: userId,
                conversation_id: projectId,
                chat_id: projectId,
                project_id: projectId,
                sync_mode: true,
                path: file.path,
              })

              if (result.success && result.content) {
                const matches = findMatches(result.content, searchQuery, caseSensitive, useRegex)
                if (matches.length > 0) {
                  searchResults.push({
                    path: file.path,
                    name: file.name,
                    matches,
                  })
                }
              }
            } catch (error) {
              // Skip files that can't be read
            }
          })
        )
      }

      setResults(searchResults)
      // Auto-expand first few results
      const toExpand = new Set(searchResults.slice(0, 3).map(r => r.path))
      setExpandedFiles(toExpand)
    } finally {
      setIsSearching(false)
    }
  }, [allFiles, userId, projectId, caseSensitive, useRegex])

  // Find matches in content
  function findMatches(
    content: string,
    query: string,
    caseSensitive: boolean,
    useRegex: boolean
  ): SearchResult['matches'] {
    const matches: SearchResult['matches'] = []
    const lines = content.split('\n')

    let searchPattern: RegExp
    try {
      if (useRegex) {
        searchPattern = new RegExp(query, caseSensitive ? 'g' : 'gi')
      } else {
        const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        searchPattern = new RegExp(escaped, caseSensitive ? 'g' : 'gi')
      }
    } catch {
      // Invalid regex
      return []
    }

    lines.forEach((line, index) => {
      const lineMatches = [...line.matchAll(searchPattern)]
      if (lineMatches.length > 0) {
        // Only take first match per line for display
        const firstMatch = lineMatches[0]
        matches.push({
          line: index + 1,
          content: line.trim(),
          matchStart: firstMatch.index || 0,
          matchEnd: (firstMatch.index || 0) + firstMatch[0].length,
        })
      }
    })

    // Limit to 10 matches per file
    return matches.slice(0, 10)
  }

  // Store performSearch in a ref to avoid useEffect dependency issues
  const performSearchRef = useRef(performSearch)
  performSearchRef.current = performSearch

  // Debounced search - only when modal is open
  useEffect(() => {
    if (!open) return

    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }

    if (query.trim().length >= 2) {
      searchTimeoutRef.current = setTimeout(() => {
        performSearchRef.current(query)
      }, 300)
    } else {
      setResults([])
    }

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [query, open])

  // Focus input when dialog opens
  useEffect(() => {
    if (open) {
      setQuery('')
      setResults([])
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  const toggleExpanded = (path: string) => {
    setExpandedFiles(prev => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  const handleSelectMatch = (path: string, name: string, line: number) => {
    onSelectFile(path, name, line)
    onOpenChange(false)
  }

  const totalMatches = results.reduce((sum, r) => sum + r.matches.length, 0)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl p-0 gap-0 overflow-hidden" hideCloseButton>
        <DialogTitle className="sr-only">Search in Files</DialogTitle>

        {/* Search input */}
        <div className="flex items-center gap-2 px-3 border-b">
          <Search className="h-4 w-4 text-muted-foreground shrink-0" />
          <Input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search in files..."
            className="h-12 border-0 focus-visible:ring-0 focus-visible:ring-offset-0 text-base"
          />
          {isSearching && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}

          {/* Search options */}
          <div className="flex items-center gap-1">
            <Button
              variant={caseSensitive ? "secondary" : "ghost"}
              size="sm"
              className="h-6 px-2 text-xs font-mono"
              onClick={() => setCaseSensitive(!caseSensitive)}
              title="Match Case"
            >
              Aa
            </Button>
            <Button
              variant={useRegex ? "secondary" : "ghost"}
              size="sm"
              className="h-6 px-2 text-xs font-mono"
              onClick={() => setUseRegex(!useRegex)}
              title="Use Regular Expression"
            >
              .*
            </Button>
          </div>

          <kbd className="hidden sm:inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
            ESC
          </kbd>
        </div>

        {/* Results summary */}
        {(query.length >= 2 || isLoadingFiles) && (
          <div className="px-3 py-1.5 text-xs text-muted-foreground border-b bg-muted/30">
            {isLoadingFiles ? (
              `Loading files... (${allFiles.length} found)`
            ) : isSearching ? (
              'Searching...'
            ) : results.length > 0 ? (
              `${totalMatches} results in ${results.length} files`
            ) : query.length >= 2 ? (
              'No results found'
            ) : null}
          </div>
        )}

        {/* Results */}
        <div className="overflow-y-auto max-h-[500px]">
          <div className="py-1">
            {results.map((result) => (
              <div key={result.path} className="border-b border-border/50 last:border-b-0">
                {/* File header */}
                <button
                  onClick={() => toggleExpanded(result.path)}
                  className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/50 transition-colors text-left"
                >
                  {expandedFiles.has(result.path) ? (
                    <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
                  ) : (
                    <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                  )}
                  <FileIcon filename={result.name} className="h-4 w-4 shrink-0" />
                  <span className="text-sm font-medium truncate">{result.name}</span>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {result.matches.length} {result.matches.length === 1 ? 'match' : 'matches'}
                  </span>
                </button>

                {/* Matches */}
                {expandedFiles.has(result.path) && (
                  <div className="bg-muted/20">
                    {result.matches.map((match, index) => (
                      <button
                        key={`${result.path}-${match.line}-${index}`}
                        onClick={() => handleSelectMatch(result.path, result.name, match.line)}
                        className="w-full flex items-start gap-2 px-3 py-1.5 pl-10 hover:bg-muted/50 transition-colors text-left"
                      >
                        <span className="text-xs text-muted-foreground font-mono w-8 shrink-0 text-right">
                          {match.line}
                        </span>
                        <span className="text-xs font-mono truncate text-muted-foreground">
                          <HighlightedText
                            text={match.content}
                            query={query}
                            caseSensitive={caseSensitive}
                            useRegex={useRegex}
                          />
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {/* No results */}
            {!isSearching && !isLoadingFiles && query.length >= 2 && results.length === 0 && (
              <div className="px-3 py-12 text-center text-sm text-muted-foreground">
                <Search className="h-8 w-8 mx-auto mb-2 opacity-50" />
                No results found for "{query}"
              </div>
            )}

            {/* Initial state */}
            {query.length < 2 && !isLoadingFiles && (
              <div className="px-3 py-12 text-center text-sm text-muted-foreground">
                <Search className="h-8 w-8 mx-auto mb-2 opacity-50" />
                Type at least 2 characters to search
              </div>
            )}

            {/* Loading files state */}
            {isLoadingFiles && (
              <div className="px-3 py-12 text-center text-sm text-muted-foreground">
                <Loader2 className="h-8 w-8 mx-auto mb-2 opacity-50 animate-spin" />
                Indexing files...
              </div>
            )}
          </div>
        </div>

        {/* Footer hint */}
        <div className="px-3 py-2 border-t bg-muted/30 text-xs text-muted-foreground flex items-center gap-4">
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-muted border text-[10px]">Enter</kbd>
            Open file
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

// Component to highlight matched text
function HighlightedText({
  text,
  query,
  caseSensitive,
  useRegex,
}: {
  text: string
  query: string
  caseSensitive: boolean
  useRegex: boolean
}) {
  if (!query) return <>{text}</>

  try {
    let pattern: RegExp
    if (useRegex) {
      pattern = new RegExp(`(${query})`, caseSensitive ? 'g' : 'gi')
    } else {
      const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      pattern = new RegExp(`(${escaped})`, caseSensitive ? 'g' : 'gi')
    }

    const parts = text.split(pattern)

    return (
      <>
        {parts.map((part, index) => {
          const isMatch = pattern.test(part)
          // Reset lastIndex for next test
          pattern.lastIndex = 0
          return isMatch ? (
            <span key={index} className="bg-yellow-500/30 text-yellow-200 font-medium">
              {part}
            </span>
          ) : (
            <span key={index}>{part}</span>
          )
        })}
      </>
    )
  } catch {
    return <>{text}</>
  }
}
