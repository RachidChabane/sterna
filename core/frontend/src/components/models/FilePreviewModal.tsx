/**
 * FilePreviewModal Component
 *
 * Premium modal for displaying text file content with:
 * - Syntax highlighting for code files
 * - Rendered markdown/HTML/SVG preview with code toggle
 * - CSV table display
 * - Copy to clipboard functionality
 */

import { useState, useEffect, useCallback, Suspense, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { X, Copy, Check, FileCode, FileText, Table2, Download, Eye, Code2, Globe, Image, Loader2, FileX2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { TypeBadge, getTypeIconColor } from '@/lib/type-badges'
import { useToast } from '@/hooks/use-toast'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { Markdown } from '@/components/ui/markdown'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'
import { getFileExtension, formatFileSize, getLanguageFromFilename } from '@/utils/fileUtils'
import { parseCSV } from '@/utils/csv'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

// Known binary file extensions that cannot be previewed as text
// NOTE: Do NOT add file types that have dedicated preview handlers (xlsx, csv, md, html, svg)
const BINARY_EXTENSIONS = new Set([
  'docx', 'doc', 'pptx', 'ppt',
  'odt', 'ods', 'odp', 'rtf',
  'zip', 'rar', '7z', 'tar', 'gz', 'bz2',
  'exe', 'dll', 'so', 'dylib',
  'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico', 'tiff',
  'mp3', 'mp4', 'wav', 'avi', 'mov', 'mkv', 'flac',
  'woff', 'woff2', 'ttf', 'otf', 'eot',
])

/**
 * Detect if content appears to be binary/garbled
 * Checks for high ratio of non-printable characters
 */
function isBinaryContent(content: string): boolean {
  if (!content || content.length === 0) return false

  // Sample first 1000 chars for performance
  const sample = content.slice(0, 1000)

  // Count non-printable characters (excluding common whitespace)
  let nonPrintable = 0
  for (let i = 0; i < sample.length; i++) {
    const code = sample.charCodeAt(i)
    // Allow: tab (9), newline (10), carriage return (13), and printable ASCII (32-126)
    // Also allow common extended characters (160-255)
    if (
      (code < 32 && code !== 9 && code !== 10 && code !== 13) ||
      (code > 126 && code < 160) ||
      code === 0xFFFD // Replacement character (common in binary-as-text)
    ) {
      nonPrintable++
    }
  }

  // If more than 10% non-printable, likely binary
  return nonPrintable / sample.length > 0.1
}

interface FilePreviewModalProps {
  isOpen: boolean
  onClose: () => void
  fileName: string
  fileSize: number
  textContent: string
}

type ViewMode = 'code' | 'preview'

export function FilePreviewModal({
  isOpen,
  onClose,
  fileName,
  fileSize,
  textContent
}: FilePreviewModalProps) {
  const { toast } = useToast()
  const [copied, setCopied] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('preview')
  const [isTransitioning, setIsTransitioning] = useState(false)

  // Handle view mode change with loading state
  const handleViewModeChange = useCallback((mode: ViewMode) => {
    if (mode === viewMode) return
    setIsTransitioning(true)
    // Brief delay to show loading state
    setTimeout(() => {
      setViewMode(mode)
      setIsTransitioning(false)
    }, 150)
  }, [viewMode])

  // File type detection
  const extension = getFileExtension(fileName).toLowerCase()
  const isMarkdown = extension === 'md' || extension === 'markdown'
  const isHTML = extension === 'html' || extension === 'htm'
  const isSVG = extension === 'svg'
  const isCSV = extension === 'csv'
  const isExcel = ['xlsx', 'xls', 'xlsm', 'xlsb'].includes(extension)
  const hasPreviewMode = isMarkdown || isHTML || isSVG
  const language = getLanguageFromFilename(fileName)

  // Check if this is a binary file that can't be previewed
  const isBinaryFile = useMemo(() => {
    // Known binary extension
    if (BINARY_EXTENSIONS.has(extension)) return true
    // Content appears binary/garbled
    if (isBinaryContent(textContent)) return true
    return false
  }, [extension, textContent])

  // Reset to preview mode when file changes
  useEffect(() => {
    if (hasPreviewMode) {
      setViewMode('preview')
    }
  }, [fileName, hasPreviewMode])

  // Get file type icon and label
  const getFileTypeInfo = () => {
    if (isMarkdown) return { icon: FileText, label: 'Markdown', color: getTypeIconColor('markdown') }
    if (isHTML) return { icon: Globe, label: 'HTML', color: getTypeIconColor('html') }
    if (isSVG) return { icon: Image, label: 'SVG', color: getTypeIconColor('svg') }
    if (isCSV) return { icon: Table2, label: 'CSV', color: getTypeIconColor('csv') }
    if (isExcel) return { icon: Table2, label: 'Excel', color: getTypeIconColor('excel') }
    return { icon: FileCode, label: language.toUpperCase() || 'Text', color: getTypeIconColor(language || 'text') }
  }
  const fileTypeInfo = getFileTypeInfo()
  const FileIcon = fileTypeInfo.icon

  // Copy handler
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(textContent)
      setCopied(true)
      toast({ title: 'Copied to clipboard' })
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast({ title: 'Failed to copy', variant: 'destructive' })
    }
  }, [textContent, toast])

  // Download handler
  const handleDownload = useCallback(() => {
    const blob = new Blob([textContent], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }, [textContent, fileName])

  // Close on escape
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  // Line count for code files
  const lineCount = textContent.split('\n').length

  const modalContent = (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm animate-in fade-in-0 duration-200"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 pointer-events-none">
        <div
          className="relative bg-background rounded-2xl overflow-hidden shadow-2xl border border-border pointer-events-auto animate-in zoom-in-95 fade-in-0 duration-200 w-full max-w-4xl max-h-[95vh] sm:max-h-[85vh] flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between px-3 py-3 sm:px-5 sm:py-4 border-b border-border flex-shrink-0 gap-2 sm:gap-0">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <div className={cn("p-2 rounded-lg bg-muted shrink-0", fileTypeInfo.color)}>
                <FileIcon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-sm sm:text-base font-semibold text-foreground truncate">
                  {fileName}
                </h2>
                <div className="flex items-center gap-2 mt-0.5">
                  <TypeBadge type={extension} />
                  <span className="text-xs text-muted-foreground">
                    {formatFileSize(fileSize)}
                  </span>
                  {!isMarkdown && !isCSV && !isSVG && (
                    <span className="text-xs text-muted-foreground hidden sm:inline">
                      • {lineCount} line{lineCount !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              </div>

              {/* Close button - visible on mobile at top-right */}
              <button
                onClick={onClose}
                className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors sm:hidden shrink-0 touch-manipulation"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1 shrink-0 sm:ml-4">
              {/* View mode toggle for previewable files */}
              {hasPreviewMode && (
                <div className="flex items-center bg-muted rounded-lg p-0.5 mr-2">
                  <button
                    onClick={() => handleViewModeChange('preview')}
                    disabled={isTransitioning}
                    className={cn(
                      "flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 sm:py-2 rounded-md text-xs font-medium transition-colors touch-manipulation",
                      viewMode === 'preview'
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground active:text-foreground active:bg-background/50",
                      isTransitioning && "opacity-50 cursor-wait"
                    )}
                  >
                    <Eye className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">Preview</span>
                  </button>
                  <button
                    onClick={() => handleViewModeChange('code')}
                    disabled={isTransitioning}
                    className={cn(
                      "flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 sm:py-2 rounded-md text-xs font-medium transition-colors touch-manipulation",
                      viewMode === 'code'
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground active:text-foreground active:bg-background/50",
                      isTransitioning && "opacity-50 cursor-wait"
                    )}
                  >
                    <Code2 className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">Code</span>
                  </button>
                </div>
              )}

              <TooltipProvider delayDuration={300}>
                {/* Copy button - only show for previewable files */}
                {!isBinaryFile && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={handleCopy}
                        className={cn(
                          "p-2 sm:p-2.5 rounded-lg transition-colors touch-manipulation",
                          copied
                            ? "bg-green-500/10 text-green-500"
                            : "text-muted-foreground hover:text-foreground hover:bg-muted active:bg-muted active:text-foreground active:scale-95"
                        )}
                      >
                        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">
                      <p>{copied ? 'Copied!' : 'Copy to clipboard'}</p>
                    </TooltipContent>
                  </Tooltip>
                )}

                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={handleDownload}
                      className="p-2 sm:p-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted active:bg-muted active:text-foreground active:scale-95 transition-colors touch-manipulation"
                    >
                      <Download className="h-4 w-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">
                    <p>Download</p>
                  </TooltipContent>
                </Tooltip>

                {/* Close button - desktop only (mobile close is in the file info row) */}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={onClose}
                      className="hidden sm:block p-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted active:bg-muted active:text-foreground active:scale-95 transition-colors ml-1 touch-manipulation"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">
                    <p>Close</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>

          {/* Content - use flex for components with their own scroll containers */}
          <div className={cn(
            "flex-1 min-h-0",
            // CSV, Excel, and Code handle their own scrolling - make this a flex container
            (isCSV || isExcel || (!isMarkdown && !isHTML && !isSVG) || (hasPreviewMode && viewMode === 'code'))
              ? "flex flex-col"
              : "overflow-auto"
          )}>
            {isTransitioning ? (
              <LoadingPreview message={viewMode === 'preview' ? 'Loading code...' : 'Loading preview...'} />
            ) : isBinaryFile ? (
              <UnsupportedPreview onDownload={handleDownload} />
            ) : (
              <Suspense fallback={<LoadingPreview />}>
                {isMarkdown ? (
                  viewMode === 'preview' ? (
                    <MarkdownPreview textContent={textContent} />
                  ) : (
                    <CodePreview textContent={textContent} language="markdown" />
                  )
                ) : isHTML ? (
                  viewMode === 'preview' ? (
                    <HTMLPreview textContent={textContent} />
                  ) : (
                    <CodePreview textContent={textContent} language="html" />
                  )
                ) : isSVG ? (
                  viewMode === 'preview' ? (
                    <SVGPreview textContent={textContent} fileName={fileName} />
                  ) : (
                    <CodePreview textContent={textContent} language="xml" />
                  )
                ) : isCSV ? (
                  <CSVPreview textContent={textContent} />
                ) : isExcel ? (
                  <ExcelPreview textContent={textContent} fileName={fileName} />
                ) : (
                  <CodePreview textContent={textContent} language={language} />
                )}
              </Suspense>
            )}
          </div>
        </div>
      </div>
    </>
  )

  return createPortal(modalContent, document.body)
}

// Loading Preview Component
function LoadingPreview({ message = 'Loading preview...' }: { message?: string }) {
  return (
    <div className="p-6 flex items-center justify-center min-h-[300px]">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="text-sm">{message}</span>
      </div>
    </div>
  )
}

// Unsupported File Preview Component - Clean fallback for binary files
function UnsupportedPreview({ onDownload }: { onDownload: () => void }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="text-center">
        <div className="mx-auto w-16 h-16 rounded-2xl bg-muted/50 flex items-center justify-center mb-4">
          <FileX2 className="w-8 h-8 text-muted-foreground" />
        </div>
        <h3 className="text-base font-medium text-foreground mb-1">
          Preview Not Available
        </h3>
        <p className="text-sm text-muted-foreground mb-5">
          This file type cannot be previewed in the browser
        </p>
        <button
          onClick={onDownload}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium text-sm bg-accent-brand text-white hover:bg-accent-brand/90 transition-colors"
        >
          <Download className="w-4 h-4" />
          Download
        </button>
      </div>
    </div>
  )
}

// Markdown Preview Component
function MarkdownPreview({ textContent }: { textContent: string }) {
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Small delay to show loading state, then render
    const timer = setTimeout(() => setIsLoading(false), 50)
    return () => clearTimeout(timer)
  }, [textContent])

  if (isLoading) {
    return <LoadingPreview />
  }

  return (
    <div className="p-3 sm:p-6 flex items-center justify-center min-h-[200px] sm:min-h-[300px]">
      <div className="w-full max-w-3xl rounded-lg overflow-hidden ring-1 ring-border shadow-lg bg-background">
        <div className="p-3 sm:p-6 prose prose-sm dark:prose-invert max-w-none overflow-auto">
          <Markdown>{textContent}</Markdown>
        </div>
      </div>
    </div>
  )
}

// HTML Preview Component
function HTMLPreview({ textContent }: { textContent: string }) {
  const [isLoading, setIsLoading] = useState(true)

  return (
    <div className="p-3 sm:p-6 flex items-center justify-center min-h-[200px] sm:min-h-[300px]">
      <div className="w-full max-w-3xl rounded-lg overflow-hidden ring-1 ring-border shadow-lg bg-white relative">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
            <div className="flex flex-col items-center gap-3 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span className="text-sm">Rendering HTML...</span>
            </div>
          </div>
        )}
        <iframe
          srcDoc={textContent}
          title="HTML Preview"
          sandbox="allow-scripts"
          className="w-full h-[60vh] sm:h-[500px] border-0"
          onLoad={() => setIsLoading(false)}
        />
      </div>
    </div>
  )
}

// SVG Preview Component
function SVGPreview({ textContent, fileName }: { textContent: string; fileName: string }) {
  const [isLoading, setIsLoading] = useState(true)
  const [hasError, setHasError] = useState(false)

  // Convert SVG content to data URL
  const svgSrc = textContent.startsWith('data:')
    ? textContent
    : `data:image/svg+xml;utf8,${encodeURIComponent(textContent)}`

  return (
    <div className="p-3 sm:p-6 flex items-center justify-center min-h-[200px] sm:min-h-[300px]">
      <div className="rounded-lg overflow-hidden ring-1 ring-border shadow-lg bg-muted/30 p-4 sm:p-8 relative min-w-[150px] sm:min-w-[200px] min-h-[150px]">
        {isLoading && !hasError && (
          <div className="absolute inset-0 flex items-center justify-center bg-muted/30 z-10">
            <div className="flex flex-col items-center gap-3 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span className="text-sm">Loading SVG...</span>
            </div>
          </div>
        )}
        {hasError ? (
          <p className="text-muted-foreground text-sm">Unable to render SVG</p>
        ) : (
          <img
            src={svgSrc}
            alt={fileName}
            className="max-w-full max-h-[50vh] sm:max-h-[400px] object-contain"
            onLoad={() => setIsLoading(false)}
            onError={() => {
              setIsLoading(false)
              setHasError(true)
            }}
          />
        )}
      </div>
    </div>
  )
}

// CSV Preview Component
function CSVPreview({ textContent }: { textContent: string }) {
  try {
    const { rows, truncated } = parseCSV(textContent, { maxRows: 201 })
    const header = rows[0] || []
    const data = rows.slice(1)
    const colCount = header.length || Math.max(0, ...data.map(r => r.length))
    const safeHeader = header.length === colCount
      ? header
      : Array.from({ length: colCount }, (_, i) => header[i] ?? `Column ${i + 1}`)

    return (
      <div className="flex-1 min-h-0 flex flex-col">
        {/* Table info bar */}
        <div className="px-5 py-2.5 bg-muted/30 border-b border-border flex items-center gap-2 text-xs text-muted-foreground flex-shrink-0">
          <Table2 className="h-3.5 w-3.5" />
          <span>{data.length} row{data.length !== 1 ? 's'  : ''}</span>
          <span>•</span>
          <span>{colCount} column{colCount !== 1 ? 's' : ''}</span>
          {truncated && (
            <>
              <span>•</span>
              <span className="text-amber-500">Truncated</span>
            </>
          )}
        </div>

        {/* Table - horizontal scroll at bottom, vertical scroll inside */}
        <div className="flex-1 min-h-0 flex flex-col overflow-x-auto">
          <div className="flex-1 overflow-y-auto min-w-max">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted/50 backdrop-blur-sm">
                <tr>
                  {safeHeader.map((h, idx) => (
                    <th
                      key={idx}
                      className="px-4 py-2.5 text-left font-medium text-foreground border-b border-border whitespace-nowrap min-w-[100px]"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((row, rIdx) => (
                  <tr
                    key={rIdx}
                    className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                  >
                    {Array.from({ length: colCount }).map((_, cIdx) => (
                      <td
                        key={cIdx}
                        className="px-4 py-2 text-foreground/90 whitespace-pre-wrap align-top min-w-[100px]"
                      >
                        {row[cIdx] ?? ''}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    )
  } catch {
    return (
      <div className="p-6">
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-4 text-sm text-destructive">
          Failed to parse CSV. Showing raw content:
        </div>
        <pre className="mt-4 p-4 rounded-lg bg-muted text-xs font-mono overflow-auto">
          {textContent}
        </pre>
      </div>
    )
  }
}

// Excel Preview Component
// Parses pandas df.to_string() output format which uses fixed-width columns
function ExcelPreview({ textContent, fileName }: { textContent: string; fileName: string }) {
  const [isLoading, setIsLoading] = useState(true)
  const [activeSheet, setActiveSheet] = useState(0)

  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 100)
    return () => clearTimeout(timer)
  }, [textContent])

  if (isLoading) {
    return <LoadingPreview message="Loading spreadsheet..." />
  }

  // Parse multi-sheet Excel content from pandas output
  interface SheetData {
    name: string
    headers: string[]
    rows: string[][]
  }

  const parseExcelContent = (text: string): SheetData[] => {
    const sheets: SheetData[] = []

    // Split by sheet markers: "--- Sheet: SheetName ---"
    const sheetPattern = /---\s*Sheet:\s*(.+?)\s*---/g
    const sheetSections: { name: string; content: string }[] = []

    let lastIndex = 0
    let match

    while ((match = sheetPattern.exec(text)) !== null) {
      if (sheetSections.length > 0) {
        sheetSections[sheetSections.length - 1].content = text.slice(lastIndex, match.index).trim()
      }
      sheetSections.push({ name: match[1], content: '' })
      lastIndex = match.index + match[0].length
    }

    if (sheetSections.length > 0) {
      sheetSections[sheetSections.length - 1].content = text.slice(lastIndex).trim()
    } else {
      sheetSections.push({ name: 'Sheet1', content: text.trim() })
    }

    // Parse each sheet's pandas output
    for (const section of sheetSections) {
      const lines = section.content.split('\n').filter(line => line.trim().length > 0)
      if (lines.length === 0) continue

      // Pandas to_string() separates columns with 2+ spaces
      // Split each line on 2+ consecutive spaces
      const splitLine = (line: string): string[] => {
        // First try: split on 2+ spaces
        const parts = line.split(/\s{2,}/).map(s => s.trim()).filter(s => s.length > 0)
        if (parts.length > 1) return parts

        // Fallback: try tab-separated
        const tabParts = line.split('\t').map(s => s.trim())
        if (tabParts.length > 1) return tabParts

        // Fallback: try pipe-separated (common in text tables)
        if (line.includes('|')) {
          const pipeParts = line.split('|').map(s => s.trim()).filter(s => s.length > 0)
          if (pipeParts.length > 1) return pipeParts
        }

        // Last resort: return as single cell
        return [line.trim()]
      }

      const headers = splitLine(lines[0])
      const rows: string[][] = []

      for (let i = 1; i < lines.length; i++) {
        const row = splitLine(lines[i])
        if (row.length > 0 && row.some(cell => cell.length > 0)) {
          rows.push(row)
        }
      }

      if (headers.length > 0) {
        sheets.push({ name: section.name, headers, rows })
      }
    }

    return sheets
  }

  try {
    const sheets = parseExcelContent(textContent)

    if (sheets.length === 0) {
      return (
        <div className="p-6 flex items-center justify-center min-h-[300px]">
          <div className="text-center text-muted-foreground">
            <Table2 className="h-12 w-12 mx-auto mb-3 opacity-50" />
            <p className="text-sm">No data found in spreadsheet</p>
          </div>
        </div>
      )
    }

    const currentSheet = sheets[activeSheet] || sheets[0]
    const { headers, rows } = currentSheet
    const colCount = Math.max(headers.length, ...rows.map(r => r.length))

    // Limit rows for preview
    const maxRows = 200
    const truncated = rows.length > maxRows
    const displayRows = truncated ? rows.slice(0, maxRows) : rows

    // Helper to get Excel column letter
    const getColumnLetter = (index: number): string => {
      let letter = ''
      let num = index
      while (num >= 0) {
        letter = String.fromCharCode(65 + (num % 26)) + letter
        num = Math.floor(num / 26) - 1
      }
      return letter
    }

    return (
      <div className="flex-1 min-h-0 flex flex-col">
        {/* Sheet tabs (if multiple sheets) */}
        {sheets.length > 1 && (
          <div className="px-4 py-2 bg-muted/30 border-b border-border flex items-center gap-1 overflow-x-auto flex-shrink-0">
            {sheets.map((sheet, idx) => (
              <button
                key={idx}
                onClick={() => setActiveSheet(idx)}
                className={cn(
                  "px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap",
                  idx === activeSheet
                    ? "bg-emerald-500 text-white shadow-sm"
                    : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                )}
              >
                {sheet.name}
              </button>
            ))}
          </div>
        )}

        {/* Spreadsheet info bar */}
        <div className="px-5 py-2.5 bg-emerald-500/10 border-b border-border flex items-center gap-2 text-xs text-muted-foreground flex-shrink-0">
          <Table2 className="h-3.5 w-3.5 text-emerald-500" />
          <span className="font-medium text-emerald-600 dark:text-emerald-400">{currentSheet.name}</span>
          <span>•</span>
          <span>{rows.length} row{rows.length !== 1 ? 's' : ''}</span>
          <span>•</span>
          <span>{colCount} column{colCount !== 1 ? 's' : ''}</span>
          {truncated && (
            <>
              <span>•</span>
              <span className="text-amber-500">Showing first {maxRows} rows</span>
            </>
          )}
        </div>

        {/* Spreadsheet table - horizontal scroll at bottom, vertical scroll inside */}
        <div className="flex-1 min-h-0 flex flex-col overflow-x-auto">
          <div className="flex-1 overflow-y-auto min-w-max">
            <table className="text-sm border-collapse w-max">
              <thead className="sticky top-0 z-10">
                <tr>
                  {/* Row number header */}
                  <th className="px-2 py-2 text-center font-medium text-muted-foreground bg-muted/70 backdrop-blur-sm border-b border-r border-border w-12 min-w-[48px] sticky left-0 z-20">
                    #
                  </th>
                  {headers.map((h, idx) => (
                    <th
                      key={idx}
                      className="px-3 py-2 text-left font-semibold text-foreground bg-emerald-500/10 backdrop-blur-sm border-b border-r border-border/50 last:border-r-0 whitespace-nowrap min-w-[100px]"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono bg-emerald-500/20 px-1 rounded">
                          {getColumnLetter(idx)}
                        </span>
                        <span className="truncate">{h}</span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayRows.map((row, rIdx) => (
                  <tr
                    key={rIdx}
                    className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                  >
                    {/* Row number */}
                    <td className="px-2 py-1.5 text-center text-xs text-muted-foreground bg-muted/30 border-r border-border font-mono sticky left-0">
                      {rIdx + 1}
                    </td>
                    {Array.from({ length: colCount }).map((_, cIdx) => {
                      const cellValue = row[cIdx] ?? ''
                      // Detect numeric values for right-alignment
                      const isNumeric = cellValue && !isNaN(Number(cellValue.replace(/[,$%]/g, '')))
                      return (
                        <td
                          key={cIdx}
                          className={cn(
                            "px-3 py-1.5 text-foreground/90 align-top border-r border-border/30 last:border-r-0 min-w-[100px]",
                            isNumeric ? "text-right font-mono text-emerald-600 dark:text-emerald-400" : "whitespace-pre-wrap"
                          )}
                        >
                          {cellValue}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    )
  } catch {
    return (
      <div className="p-6">
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-4 text-sm text-destructive">
          Failed to parse Excel content. Showing raw text:
        </div>
        <pre className="mt-4 p-4 rounded-lg bg-muted text-xs font-mono overflow-auto max-h-[400px]">
          {textContent}
        </pre>
      </div>
    )
  }
}

// Code Preview Component
function CodePreview({ textContent, language }: { textContent: string; language: string }) {
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  return (
    <div className="flex-1 min-h-0 flex flex-col code-preview-wrapper">
      <style>{`
        .code-preview-wrapper pre {
          margin: 0 !important;
          background: transparent !important;
        }
        .code-preview-wrapper code {
          font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', ui-monospace, monospace !important;
        }
        .code-preview-wrapper .linenumber {
          min-width: 3em !important;
          padding-right: 1em !important;
          text-align: right !important;
          user-select: none !important;
          opacity: 0.4 !important;
        }
      `}</style>
      <SyntaxHighlighter
        language={language}
        style={codeTheme.style}
        showLineNumbers
        wrapLongLines
        customStyle={{
          margin: 0,
          padding: '1.25rem',
          background: 'transparent',
          fontSize: '0.8125rem',
          lineHeight: '1.6',
        }}
      >
        {textContent}
      </SyntaxHighlighter>
    </div>
  )
}
