/**
 * FilePreview Component
 *
 * Displays preview for different file types:
 * - HTML: Rendered in sandboxed iframe with automatic CSS/JS resolution
 * - Markdown: Rendered markdown
 * - Images: Image display
 * - PDF: PDF viewer in iframe
 * - CSV: Table view
 * - Other code files: Syntax highlighted code
 */

import { Markdown } from '@/components/ui/markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { getLanguageFromFilename } from '@/utils/fileUtils'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'
import { parseCSV } from '@/utils/csv'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { FileWarning } from 'lucide-react'
import { HTMLPreview } from './HTMLPreview'
import { ExcelPreview } from './ExcelPreview'

interface FilePreviewProps {
  fileName: string
  filePath: string
  content: string
  language?: string
  userId?: string
  projectId?: string
}

export function FilePreview({ fileName, filePath, content, language, userId, projectId }: FilePreviewProps) {
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)
  const ext = fileName.toLowerCase().split('.').pop() || ''
  const detectedLanguage = language || getLanguageFromFilename(fileName)

  // HTML Preview with automatic CSS/JS resolution
  if (ext === 'html' || ext === 'htm') {
    return (
      <HTMLPreview
        htmlContent={content}
        currentFilePath={filePath}
        userId={userId}
        projectId={projectId}
      />
    )
  }

  // Markdown Preview
  if (ext === 'md' || ext === 'markdown') {
    return (
      <div className="h-full w-full overflow-auto bg-background p-6">
        <div className="max-w-4xl mx-auto prose prose-invert prose-slate">
          <Markdown>{content}</Markdown>
        </div>
      </div>
    )
  }

  // SVG Preview (text-based XML, special handling)
  if (ext === 'svg') {
    try {
      // SVG files are returned as plain text XML
      // Create data URL with proper SVG MIME type
      let svgContent: string

      if (content.startsWith('data:')) {
        svgContent = content
      } else if (content.startsWith('<')) {
        // Plain SVG XML - encode it properly
        svgContent = `data:image/svg+xml;utf8,${encodeURIComponent(content)}`
      } else {
        // Base64-encoded SVG
        svgContent = `data:image/svg+xml;base64,${content}`
      }

      return (
        <div className="h-full w-full flex items-center justify-center bg-slate-900 p-4">
          <img
            src={svgContent}
            alt={fileName}
            className="max-w-full max-h-full object-contain"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
              const errorDiv = document.createElement('div');
              errorDiv.className = 'text-muted-foreground text-center';
              errorDiv.innerHTML = '<p>Unable to display SVG</p>';
              e.currentTarget.parentElement?.appendChild(errorDiv);
            }}
          />
        </div>
      )
    } catch (error) {
      return (
        <div className="h-full w-full flex items-center justify-center bg-slate-900 text-muted-foreground">
          <div className="text-center space-y-2">
            <FileWarning className="h-12 w-12 mx-auto text-muted-foreground/50" />
            <p>Unable to preview SVG</p>
          </div>
        </div>
      )
    }
  }

  // Binary Image Preview (PNG, JPG, etc.)
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico'].includes(ext)) {
    try {
      // Binary images are returned as base64
      const base64Content = content.startsWith('data:')
        ? content
        : `data:image/${ext};base64,${content}`

      return (
        <div className="h-full w-full flex items-center justify-center bg-slate-900 p-4">
          <img
            src={base64Content}
            alt={fileName}
            className="max-w-full max-h-full object-contain"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
              const errorDiv = document.createElement('div');
              errorDiv.className = 'text-muted-foreground text-center';
              errorDiv.innerHTML = '<p>Unable to display image</p>';
              e.currentTarget.parentElement?.appendChild(errorDiv);
            }}
          />
        </div>
      )
    } catch (error) {
      return (
        <div className="h-full w-full flex items-center justify-center bg-slate-900 text-muted-foreground">
          <div className="text-center space-y-2">
            <FileWarning className="h-12 w-12 mx-auto text-muted-foreground/50" />
            <p>Unable to preview image</p>
          </div>
        </div>
      )
    }
  }

  // XLSX/Excel Preview with Editing
  if (['xlsx', 'xls', 'xlsm'].includes(ext)) {
    return <ExcelPreview fileName={fileName} filePath={filePath} content={content} userId={userId} projectId={projectId} />
  }

  // PDF Preview
  if (ext === 'pdf') {
    try {
      // If content is base64, create data URL
      const pdfSrc = content.startsWith('data:')
        ? content
        : `data:application/pdf;base64,${content}`

      return (
        <div className="h-full w-full bg-slate-800">
          <iframe
            src={pdfSrc.includes('#') ? pdfSrc : `${pdfSrc}#page=1&view=FitH`}
            title="PDF Preview"
            className="w-full h-full border-0"
          />
        </div>
      )
    } catch (error) {
      return (
        <div className="h-full w-full flex items-center justify-center bg-slate-900 text-muted-foreground">
          <div className="text-center space-y-2">
            <FileWarning className="h-12 w-12 mx-auto text-muted-foreground/50" />
            <p>Unable to preview PDF</p>
          </div>
        </div>
      )
    }
  }

  // CSV Preview
  if (ext === 'csv') {
    try {
      const { rows, truncated } = parseCSV(content, { maxRows: 201 })
      const header = rows[0] || []
      const data = rows.slice(1)
      const colCount = header.length || Math.max(0, ...data.map(r => r.length))
      const safeHeader = header.length === colCount
        ? header
        : Array.from({ length: colCount }, (_, i) => header[i] ?? `Column ${i + 1}`)

      return (
        <div className="h-full w-full overflow-auto bg-background p-4">
          <div className="rounded-lg border border-border bg-background">
            <div className="px-4 py-2 text-xs text-muted-foreground border-b">
              Previewing CSV • showing first {data.length} row{data.length !== 1 ? 's' : ''}{truncated ? ' (truncated)' : ''}
            </div>
            <div className="relative w-full overflow-auto">
              <Table className="min-w-max">
                <TableHeader>
                  <TableRow>
                    {safeHeader.map((h, idx) => (
                      <TableHead key={idx} className="whitespace-nowrap">{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.map((row, rIdx) => (
                    <TableRow key={rIdx}>
                      {Array.from({ length: colCount }).map((_, cIdx) => (
                        <TableCell key={cIdx} className="whitespace-pre-wrap align-top">
                          {row[cIdx] ?? ''}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </div>
      )
    } catch (error) {
      // Fall through to syntax highlighting
    }
  }

  // JSON Preview - formatted
  if (ext === 'json') {
    try {
      const parsed = JSON.parse(content)
      const formatted = JSON.stringify(parsed, null, 2)

      return (
        <div className="h-full w-full overflow-auto bg-[#1e1e1e]">
          <SyntaxHighlighter
            language="json"
            style={codeTheme.style}
            showLineNumbers={true}
            wrapLongLines={true}
            customStyle={{
              margin: 0,
              padding: '1rem',
              background: 'transparent',
              fontSize: '0.875rem',
              lineHeight: '1.7',
              height: '100%',
            }}
          >
            {formatted}
          </SyntaxHighlighter>
        </div>
      )
    } catch (error) {
      // Fall through to regular syntax highlighting
    }
  }

  // Default: Syntax highlighting for code files
  return (
    <div className="h-full w-full overflow-auto bg-[#1e1e1e]">
      <SyntaxHighlighter
        language={detectedLanguage}
        style={codeTheme.style}
        showLineNumbers={true}
        wrapLongLines={true}
        customStyle={{
          margin: 0,
          padding: '1rem',
          background: 'transparent',
          fontSize: '0.875rem',
          lineHeight: '1.7',
          height: '100%',
        }}
      >
        {content}
      </SyntaxHighlighter>
    </div>
  )
}
