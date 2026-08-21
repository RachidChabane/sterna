/**
 * MonacoDiffViewer Component
 *
 * Enhanced diff viewer using Monaco Editor's diff functionality.
 * Supports side-by-side and inline diff modes with syntax highlighting.
 */

import { useRef, useEffect, useState } from 'react'
import { DiffEditor, type DiffOnMount, type Monaco } from '@monaco-editor/react'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Button } from '@/components/ui/button'
import { SplitSquareHorizontal, AlignLeft, Copy, Check, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getLanguageFromPath } from '@/components/sandbox/types'

interface MonacoDiffViewerProps {
  originalContent: string
  modifiedContent: string
  filePath: string
  originalLabel?: string
  modifiedLabel?: string
  className?: string
}

export function MonacoDiffViewer({
  originalContent,
  modifiedContent,
  filePath,
  originalLabel = 'Original',
  modifiedLabel = 'Modified',
  className,
}: MonacoDiffViewerProps) {
  const editorRef = useRef<any>(null)
  const monacoRef = useRef<Monaco | null>(null)
  const [viewMode, setViewMode] = useState<'side-by-side' | 'inline'>('side-by-side')
  const [copied, setCopied] = useState(false)
  const [isReady, setIsReady] = useState(false)

  const language = getLanguageFromPath(filePath)

  const handleEditorDidMount: DiffOnMount = (editor, monaco) => {
    editorRef.current = editor
    monacoRef.current = monaco
    setIsReady(true)

    // Configure editor options
    editor.updateOptions({
      readOnly: true,
      renderSideBySide: viewMode === 'side-by-side',
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      renderOverviewRuler: false,
      fontSize: 12,
      lineNumbers: 'on',
      glyphMargin: false,
      folding: true,
      lineDecorationsWidth: 0,
      lineNumbersMinChars: 3,
    })

    // Apply custom theme
    monaco.editor.defineTheme('diff-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [],
      colors: {
        'editor.background': '#0d1117',
        'diffEditor.insertedTextBackground': '#2ea04326',
        'diffEditor.removedTextBackground': '#f8514926',
        'diffEditor.insertedLineBackground': '#2ea04315',
        'diffEditor.removedLineBackground': '#f8514915',
      },
    })
    monaco.editor.setTheme('diff-dark')
  }

  // Update render mode when viewMode changes
  useEffect(() => {
    if (editorRef.current) {
      editorRef.current.updateOptions({
        renderSideBySide: viewMode === 'side-by-side',
      })
    }
  }, [viewMode])

  const handleCopyDiff = async () => {
    try {
      // Get diff as unified format (simplified)
      const lines = modifiedContent.split('\n')
      const origLines = originalContent.split('\n')
      let diffText = `--- ${originalLabel}\n+++ ${modifiedLabel}\n`

      // Simple line-by-line comparison
      const maxLines = Math.max(lines.length, origLines.length)
      for (let i = 0; i < maxLines; i++) {
        const orig = origLines[i]
        const mod = lines[i]
        if (orig !== mod) {
          if (orig !== undefined) diffText += `-${orig}\n`
          if (mod !== undefined) diffText += `+${mod}\n`
        } else if (orig !== undefined) {
          diffText += ` ${orig}\n`
        }
      }

      await navigator.clipboard.writeText(diffText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      console.error('Failed to copy diff:', error)
    }
  }

  // Calculate stats
  const origLines = originalContent.split('\n')
  const modLines = modifiedContent.split('\n')
  const addedLines = modLines.filter((line, i) => !origLines.includes(line)).length
  const removedLines = origLines.filter((line, i) => !modLines.includes(line)).length

  return (
    <div className={cn("flex flex-col h-full bg-[#0d1117] rounded-lg overflow-hidden", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/50 bg-muted/30">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-muted-foreground truncate max-w-[300px]">
            {filePath}
          </span>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-emerald-400">+{addedLines}</span>
            <span className="text-red-400">-{removedLines}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* View mode toggle */}
          <ToggleGroup
            type="single"
            value={viewMode}
            onValueChange={(value) => value && setViewMode(value as typeof viewMode)}
            className="h-7"
          >
            <ToggleGroupItem value="side-by-side" aria-label="Side by side" className="h-7 px-2">
              <SplitSquareHorizontal className="h-3.5 w-3.5" />
            </ToggleGroupItem>
            <ToggleGroupItem value="inline" aria-label="Inline" className="h-7 px-2">
              <AlignLeft className="h-3.5 w-3.5" />
            </ToggleGroupItem>
          </ToggleGroup>

          {/* Copy button */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={handleCopyDiff}
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-green-500" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
      </div>

      {/* Diff Editor */}
      <div className="flex-1 relative">
        {!isReady && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        )}
        <DiffEditor
          original={originalContent}
          modified={modifiedContent}
          language={language}
          theme="vs-dark"
          onMount={handleEditorDidMount}
          options={{
            readOnly: true,
            renderSideBySide: viewMode === 'side-by-side',
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            renderOverviewRuler: false,
            fontSize: 12,
            lineNumbers: 'on',
            glyphMargin: false,
            folding: true,
            lineDecorationsWidth: 0,
            lineNumbersMinChars: 3,
            automaticLayout: true,
          }}
        />
      </div>

      {/* Footer with labels */}
      {viewMode === 'side-by-side' && (
        <div className="flex border-t border-border/50">
          <div className="flex-1 px-3 py-1 text-xs text-muted-foreground border-r border-border/50">
            {originalLabel}
          </div>
          <div className="flex-1 px-3 py-1 text-xs text-muted-foreground">
            {modifiedLabel}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * SimpleDiffViewer - Lightweight diff viewer without Monaco
 * For use when Monaco is not needed or for simple diffs
 */
export function SimpleDiffViewer({
  diff,
  className,
}: {
  diff: string
  className?: string
}) {
  const lines = diff.split('\n')

  return (
    <div className={cn("rounded-lg border border-border overflow-hidden", className)}>
      <pre className="text-xs font-mono overflow-x-auto">
        {lines.map((line, index) => {
          let bgColor = 'bg-transparent'
          let textColor = 'text-muted-foreground'

          if (line.startsWith('+++') || line.startsWith('---')) {
            bgColor = 'bg-muted/50'
            textColor = 'text-foreground font-semibold'
          } else if (line.startsWith('@@')) {
            bgColor = 'bg-blue-500/10'
            textColor = 'text-blue-400'
          } else if (line.startsWith('+')) {
            bgColor = 'bg-emerald-500/10'
            textColor = 'text-emerald-400'
          } else if (line.startsWith('-')) {
            bgColor = 'bg-red-500/10'
            textColor = 'text-red-400'
          }

          return (
            <div
              key={index}
              className={cn(bgColor, textColor, "px-3 py-0.5 whitespace-pre-wrap break-all")}
            >
              {line || ' '}
            </div>
          )
        })}
      </pre>
    </div>
  )
}
