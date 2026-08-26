/**
 * DocumentDownloader - Displays downloadable document sparks (csv, ics, pdf, docx)
 *
 * Provides per-type previews:
 * - CSV: Table preview (first 20 rows parsed from code field)
 * - ICS: Event summary card (parsed from code field)
 * - PDF: iframe embed + download button
 * - DOCX: Python source view + download button
 */

import React, { useMemo, useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { TypeBadge } from '@/lib/type-badges'
import { FileText, CalendarDays, Table, Download, Copy, Check, ZoomIn, ZoomOut, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'
import { parseCSV } from '@/utils/csv'
import * as pdfjsLib from 'pdfjs-dist'
import * as XLSX from 'xlsx'
import { fetchStream } from '@/api/transport'

// Configure PDF.js worker
const PDFJS_VERSION = pdfjsLib.version
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${PDFJS_VERSION}/build/pdf.worker.min.mjs`

interface DocumentDownloaderProps {
  framework: 'csv' | 'ics' | 'pdf' | 'docx' | 'xlsx'
  title: string
  code: string
  downloadUrl?: string | null
  className?: string
  /** Hide the header bar (title, icon, copy/download buttons). Used when embedded in fullscreen dialog which provides its own chrome. */
  hideHeader?: boolean
  /** Compact mode for thumbnail cards — hides header and all toolbars */
  compact?: boolean
}

/** Parsed calendar event */
interface ICSEvent {
  summary: string
  start: Date | null
  end: Date | null
  location?: string
  description?: string
}

/** Parse ICS content into multiple events */
function parseICSEvents(content: string): ICSEvent[] {
  const events: ICSEvent[] = []
  const lines = content.split(/\r?\n/)
  let current: Partial<ICSEvent> | null = null

  for (const line of lines) {
    if (line === 'BEGIN:VEVENT') {
      current = {}
      continue
    }
    if (line === 'END:VEVENT' && current) {
      events.push({
        summary: current.summary || 'Untitled Event',
        start: current.start || null,
        end: current.end || null,
        location: current.location,
        description: current.description,
      })
      current = null
      continue
    }
    if (!current) continue

    const colonIndex = line.indexOf(':')
    if (colonIndex === -1) continue
    const key = line.substring(0, colonIndex).split(';')[0].toUpperCase()
    const value = line.substring(colonIndex + 1)

    switch (key) {
      case 'SUMMARY':
        current.summary = value
        break
      case 'DTSTART':
        current.start = parseICSDateToDate(value)
        break
      case 'DTEND':
        current.end = parseICSDateToDate(value)
        break
      case 'LOCATION':
        current.location = value
        break
      case 'DESCRIPTION':
        current.description = value.replace(/\\n/g, '\n').replace(/\\,/g, ',')
        break
    }
  }

  // Fallback: if no VEVENT blocks found, try parsing as flat fields
  if (events.length === 0) {
    const flat: Partial<ICSEvent> = {}
    for (const line of lines) {
      const colonIndex = line.indexOf(':')
      if (colonIndex === -1) continue
      const key = line.substring(0, colonIndex).split(';')[0].toUpperCase()
      const value = line.substring(colonIndex + 1)
      if (key === 'SUMMARY') flat.summary = value
      if (key === 'DTSTART') flat.start = parseICSDateToDate(value)
      if (key === 'DTEND') flat.end = parseICSDateToDate(value)
      if (key === 'LOCATION') flat.location = value
      if (key === 'DESCRIPTION') flat.description = value.replace(/\\n/g, '\n').replace(/\\,/g, ',')
    }
    if (flat.summary || flat.start) {
      events.push({
        summary: flat.summary || 'Untitled Event',
        start: flat.start || null,
        end: flat.end || null,
        location: flat.location,
        description: flat.description,
      })
    }
  }

  return events
}

function parseICSDateToDate(value: string): Date | null {
  const match = value.match(/(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2}))?/)
  if (!match) return null
  const [, year, month, day, hour, minute, second] = match
  if (hour) {
    return new Date(`${year}-${month}-${day}T${hour}:${minute}:${second || '00'}Z`)
  }
  return new Date(`${year}-${month}-${day}T00:00:00`)
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}



/** CSV table preview */
function CSVPreview({ code, compact = false }: { code: string; compact?: boolean }) {
  const parsed = useMemo(() => {
    try {
      return parseCSV(code, { maxRows: 21 })
    } catch {
      return null
    }
  }, [code])

  if (!parsed || parsed.rows.length === 0) {
    return <p className="text-sm text-muted-foreground p-3">No data to preview</p>
  }

  const { rows, truncated } = parsed
  const header = rows[0] || []
  const data = rows.slice(1)
  const colCount = header.length || Math.max(0, ...data.map(r => r.length))
  const safeHeader = header.length === colCount
    ? header
    : Array.from({ length: colCount }, (_, i) => header[i] ?? `Column ${i + 1}`)

  return (
    <div className="flex flex-col">
      {/* Info bar - hidden in compact/thumbnail mode */}
      {!compact && (
        <div className="px-3 py-1.5 bg-muted/30 border-b border-border/40 flex items-center gap-2 text-[10px] text-muted-foreground">
          <Table className="h-3 w-3" />
          <span>{data.length} row{data.length !== 1 ? 's' : ''}</span>
          <span>·</span>
          <span>{colCount} column{colCount !== 1 ? 's' : ''}</span>
          {truncated && (
            <>
              <span>·</span>
              <span className="text-amber-500">Truncated</span>
            </>
          )}
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-muted/80 backdrop-blur-sm">
            <tr>
              {safeHeader.map((h, i) => (
                <th key={i} className="px-3 py-2 text-left font-medium text-foreground/80 border-b border-border/40 whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, rIdx) => (
              <tr key={rIdx} className="border-b border-border/20 hover:bg-muted/30 transition-colors">
                {Array.from({ length: colCount }).map((_, cIdx) => (
                  <td key={cIdx} className="px-3 py-1.5 text-foreground/80 whitespace-nowrap max-w-[200px] truncate">
                    {row[cIdx] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** ICS calendar view */
function ICSPreview({ code, compact = false }: { code: string; compact?: boolean }) {
  const events = useMemo(() => parseICSEvents(code), [code])

  // Determine which month to show based on the earliest event
  const initialDate = useMemo(() => {
    const firstEvent = events.find((e) => e.start)
    return firstEvent?.start || new Date()
  }, [events])

  const [viewMonth, setViewMonth] = useState(initialDate.getMonth())
  const [viewYear, setViewYear] = useState(initialDate.getFullYear())
  const [selectedEvent, setSelectedEvent] = useState<ICSEvent | null>(null)

  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
  const firstDayOfWeek = new Date(viewYear, viewMonth, 1).getDay()
  const monthName = new Date(viewYear, viewMonth).toLocaleString(undefined, { month: 'long', year: 'numeric' })

  // Map events to day numbers
  const eventsByDay = useMemo(() => {
    const map = new Map<number, ICSEvent[]>()
    for (const ev of events) {
      if (!ev.start) continue
      if (ev.start.getFullYear() === viewYear && ev.start.getMonth() === viewMonth) {
        const day = ev.start.getDate()
        if (!map.has(day)) map.set(day, [])
        map.get(day)!.push(ev)
      }
    }
    return map
  }, [events, viewMonth, viewYear])

  const prevMonth = () => {
    if (viewMonth === 0) { setViewMonth(11); setViewYear((y) => y - 1) }
    else setViewMonth((m) => m - 1)
  }
  const nextMonth = () => {
    if (viewMonth === 11) { setViewMonth(0); setViewYear((y) => y + 1) }
    else setViewMonth((m) => m + 1)
  }

  const today = new Date()
  const isToday = (day: number) =>
    today.getDate() === day && today.getMonth() === viewMonth && today.getFullYear() === viewYear

  return (
    <div className="flex flex-col flex-1">
      {/* Month nav - hidden in compact/thumbnail mode */}
      {!compact && (
        <div className="flex items-center justify-between px-3 py-2 border-b border-border/30">
          <button onClick={prevMonth} className="p-1 hover:bg-muted rounded transition-colors">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-sm font-medium">{monthName}</span>
          <button onClick={nextMonth} className="p-1 hover:bg-muted rounded transition-colors">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Day headers */}
      <div className="grid grid-cols-7 border-b border-border/20">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
          <div key={d} className="text-center text-[10px] font-medium text-muted-foreground/60 uppercase py-1.5">
            {d}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 flex-1">
        {/* Empty cells before first day */}
        {Array.from({ length: firstDayOfWeek }).map((_, i) => (
          <div key={`empty-${i}`} className="border-b border-r border-border/10 bg-muted/5 min-h-[52px]" />
        ))}

        {/* Day cells */}
        {Array.from({ length: daysInMonth }).map((_, i) => {
          const day = i + 1
          const dayEvents = eventsByDay.get(day) || []
          const hasEvents = dayEvents.length > 0

          return (
            <div
              key={day}
              className={cn(
                'border-b border-r border-border/10 min-h-[52px] p-1 transition-colors',
                hasEvents && 'cursor-pointer hover:bg-muted/30',
              )}
              onClick={() => hasEvents && setSelectedEvent(dayEvents[0])}
            >
              <span className={cn(
                'inline-flex items-center justify-center w-5 h-5 text-[11px] rounded-full',
                isToday(day) && 'bg-foreground text-background font-bold',
                !isToday(day) && 'text-foreground/70',
              )}>
                {day}
              </span>
              {dayEvents.map((ev, idx) => (
                <div
                  key={idx}
                  className="mt-0.5 px-1 py-0.5 rounded text-[9px] leading-tight truncate bg-violet-500/15 text-violet-600 dark:text-violet-400 font-medium"
                >
                  {ev.start ? formatTime(ev.start) + ' ' : ''}{ev.summary}
                </div>
              ))}
            </div>
          )
        })}
      </div>

      {/* Selected event detail */}
      {selectedEvent && (
        <div className="border-t border-border/30 p-3 bg-muted/10">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-2 h-2 rounded-full bg-violet-500 shrink-0" />
                <span className="text-sm font-medium truncate">{selectedEvent.summary}</span>
              </div>
              <div className="text-xs text-muted-foreground space-y-0.5 pl-4">
                {selectedEvent.start && (
                  <p>
                    {selectedEvent.start.toLocaleString(undefined, {
                      weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                    })}
                    {selectedEvent.end && ` - ${formatTime(selectedEvent.end)}`}
                  </p>
                )}
                {selectedEvent.location && <p>{selectedEvent.location}</p>}
                {selectedEvent.description && (
                  <p className="text-foreground/60 line-clamp-2 whitespace-pre-wrap">{selectedEvent.description}</p>
                )}
              </div>
            </div>
            <button
              onClick={() => setSelectedEvent(null)}
              className="p-0.5 text-muted-foreground hover:text-foreground shrink-0"
            >
              <span className="text-xs">✕</span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/** Custom PDF viewer using pdf.js — renders pages to canvas with zoom/nav controls */
function PDFPreview({ url, compact = false }: { url: string; compact?: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [pdf, setPdf] = useState<any>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageCount, setPageCount] = useState(0)
  const [scale, setScale] = useState<number | null>(null) // null = fit-to-width
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const renderTaskRef = useRef<any>(null)

  // Load the PDF document — fetch bytes ourselves to avoid CORS issues with presigned URLs
  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)

    const loadPdf = async () => {
      try {
        const resp = await fetchStream(url)
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const pdfBytes = await resp.arrayBuffer()

        if (cancelled) return

        const standardFontDataUrl = `https://unpkg.com/pdfjs-dist@${PDFJS_VERSION}/standard_fonts/`
        const loadingTask = pdfjsLib.getDocument({ data: pdfBytes, standardFontDataUrl })
        const pdfDoc = await loadingTask.promise

        if (cancelled) return
        setPdf(pdfDoc)
        setPageCount(pdfDoc.numPages)
        setCurrentPage(1)
      } catch (err: any) {
        if (!cancelled) {
          console.error('[PDFPreview] Load failed:', err)
          setError('Failed to load PDF')
          setIsLoading(false)
        }
      }
    }

    loadPdf()
    return () => { cancelled = true }
  }, [url])

  // Render the current page
  useEffect(() => {
    if (!pdf || !canvasRef.current || !containerRef.current) return

    let cancelled = false

    const renderPage = async () => {
      try {
        const page = await pdf.getPage(currentPage)
        if (cancelled) return

        const canvas = canvasRef.current!
        const ctx = canvas.getContext('2d')!
        const container = containerRef.current!

        // Calculate scale: fit to container width if no explicit scale
        const baseViewport = page.getViewport({ scale: 1 })
        const containerWidth = container.clientWidth - 32 // padding
        const fitScale = containerWidth / baseViewport.width
        const effectiveScale = scale ?? fitScale
        const viewport = page.getViewport({ scale: effectiveScale })

        // HiDPI support
        const dpr = window.devicePixelRatio || 1
        canvas.width = viewport.width * dpr
        canvas.height = viewport.height * dpr
        canvas.style.width = `${viewport.width}px`
        canvas.style.height = `${viewport.height}px`
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

        // Cancel previous render if still running
        if (renderTaskRef.current) {
          renderTaskRef.current.cancel?.()
        }

        const task = page.render({ canvasContext: ctx, viewport })
        renderTaskRef.current = task

        await task.promise
        if (!cancelled) setIsLoading(false)
      } catch (err: any) {
        if (err?.name !== 'RenderingCancelledException' && !cancelled) {
          console.error('[PDFPreview] Render failed:', err)
          setError('Failed to render page')
          setIsLoading(false)
        }
      }
    }

    renderPage()
    return () => { cancelled = true }
  }, [pdf, currentPage, scale])

  // Recalculate fit-to-width on container resize
  useEffect(() => {
    if (!containerRef.current || scale !== null) return
    const observer = new ResizeObserver(() => {
      // Re-trigger render by toggling a dummy state
      setPdf((p: any) => p) // force re-render
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [scale])

  const zoomIn = useCallback(() => {
    setScale(prev => {
      if (prev === null && containerRef.current && pdf) {
        // Estimate current fit scale, bump it
        return 1.5
      }
      return Math.min((prev ?? 1) * 1.25, 5)
    })
  }, [pdf])

  const zoomOut = useCallback(() => {
    setScale(prev => Math.max((prev ?? 1) * 0.8, 0.3))
  }, [])

  const fitToWidth = useCallback(() => setScale(null), [])

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground">
        <FileText className="w-10 h-10 mb-2 opacity-30" />
        <p className="text-sm">{error}</p>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Toolbar - hidden in compact/thumbnail mode */}
      {!compact && (
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/30 bg-muted/20 shrink-0">
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={zoomOut} title="Zoom out">
              <ZoomOut className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={fitToWidth} title="Fit to width">
              {scale === null ? 'Fit' : `${Math.round((scale) * 100)}%`}
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={zoomIn} title="Zoom in">
              <ZoomIn className="h-3.5 w-3.5" />
            </Button>
          </div>
          {pageCount > 1 && (
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage <= 1}>
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <span className="text-xs text-muted-foreground tabular-nums min-w-[4ch] text-center">
                {currentPage}/{pageCount}
              </span>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setCurrentPage(p => Math.min(pageCount, p + 1))} disabled={currentPage >= pageCount}>
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Canvas area */}
      <div ref={containerRef} className="flex-1 overflow-auto bg-muted/10 flex justify-center p-4 min-h-0">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}
        <canvas
          ref={canvasRef}
          className={cn(
            'shadow-md rounded-sm bg-white',
            isLoading && 'opacity-0'
          )}
        />
      </div>
    </div>
  )
}

/** XLSX spreadsheet preview using SheetJS */
function XlsxPreview({ downloadUrl, compact = false }: { downloadUrl: string; compact?: boolean }) {
  const [workbook, setWorkbook] = useState<XLSX.WorkBook | null>(null)
  const [activeSheet, setActiveSheet] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch and parse the xlsx file
  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)

    const loadXlsx = async () => {
      try {
        const resp = await fetchStream(downloadUrl)
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const buffer = await resp.arrayBuffer()
        if (cancelled) return

        const wb = XLSX.read(buffer, { type: 'array' })
        setWorkbook(wb)
        setActiveSheet(0)
      } catch (err: any) {
        if (!cancelled) {
          console.error('[XlsxPreview] Load failed:', err)
          setError('Could not load preview')
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    loadXlsx()
    return () => { cancelled = true }
  }, [downloadUrl])

  // Parse active sheet data
  const { headers, rows, totalRows, totalCols } = useMemo(() => {
    if (!workbook) return { headers: [] as string[], rows: [] as any[][], totalRows: 0, totalCols: 0 }

    const sheetName = workbook.SheetNames[activeSheet]
    const sheet = workbook.Sheets[sheetName]
    if (!sheet) return { headers: [] as string[], rows: [] as any[][], totalRows: 0, totalCols: 0 }

    const jsonData = XLSX.utils.sheet_to_json<any[]>(sheet, { header: 1 })
    if (jsonData.length === 0) return { headers: [] as string[], rows: [] as any[][], totalRows: 0, totalCols: 0 }

    const maxCols = 26 // A-Z cap
    const allCols = Math.max(0, ...jsonData.map(r => (r as any[]).length))
    const displayCols = Math.min(allCols, maxCols)

    const headerRow = (jsonData[0] as any[]) || []
    const hdrs = Array.from({ length: displayCols }, (_, i) =>
      headerRow[i] != null ? String(headerRow[i]) : `Column ${i + 1}`
    )

    const maxRows = compact ? 5 : 50
    const dataRows = jsonData.slice(1, 1 + maxRows).map(r =>
      Array.from({ length: displayCols }, (_, i) => (r as any[])[i] ?? '')
    )

    return {
      headers: hdrs,
      rows: dataRows,
      totalRows: jsonData.length - 1,
      totalCols: allCols,
    }
  }, [workbook, activeSheet, compact])

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-muted-foreground">
        <Table className="w-10 h-10 mb-2 opacity-30" />
        <p className="text-sm">{error}</p>
      </div>
    )
  }

  if (!workbook || totalRows === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-muted-foreground">
        <Table className="w-10 h-10 mb-2 opacity-30" />
        <p className="text-sm">Empty spreadsheet</p>
      </div>
    )
  }

  const sheetNames = workbook.SheetNames
  const maxDisplayRows = compact ? 5 : 50

  return (
    <div className="flex flex-col flex-1">
      {/* Sheet tabs — hidden in compact mode */}
      {!compact && sheetNames.length > 1 && (
        <div className="flex items-center gap-0.5 px-3 py-1.5 border-b border-border/30 bg-muted/10 overflow-x-auto scrollbar-none">
          {sheetNames.map((name, idx) => (
            <button
              key={name}
              onClick={() => setActiveSheet(idx)}
              className={cn(
                'px-2.5 py-1 rounded text-[11px] font-medium whitespace-nowrap transition-colors',
                idx === activeSheet
                  ? 'bg-foreground text-background'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
              )}
            >
              {name}
            </button>
          ))}
        </div>
      )}

      {/* Info bar — hidden in compact mode */}
      {!compact && (
        <div className="px-3 py-1.5 bg-muted/30 border-b border-border/40 flex items-center gap-2 text-[10px] text-muted-foreground">
          <Table className="h-3 w-3" />
          <span>
            Showing {Math.min(rows.length, maxDisplayRows)} of {totalRows} row{totalRows !== 1 ? 's' : ''}
          </span>
          <span>·</span>
          <span>{totalCols} column{totalCols !== 1 ? 's' : ''}</span>
          {totalCols > 26 && (
            <>
              <span>·</span>
              <span className="text-amber-500">+{totalCols - 26} columns</span>
            </>
          )}
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-muted/80 backdrop-blur-sm">
            <tr>
              {headers.map((h, i) => (
                <th key={i} className="px-3 py-2 text-left font-medium text-foreground/80 border-b border-border/40 whitespace-nowrap min-w-[80px]">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rIdx) => (
              <tr key={rIdx} className="border-b border-border/20 hover:bg-muted/30 transition-colors">
                {row.map((cell: any, cIdx: number) => (
                  <td
                    key={cIdx}
                    className={cn(
                      'px-3 py-1.5 text-foreground/80 whitespace-nowrap max-w-[200px] truncate min-w-[80px]',
                      typeof cell === 'number' && 'text-right tabular-nums'
                    )}
                  >
                    {cell != null ? String(cell) : ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export const DocumentDownloader: React.FC<DocumentDownloaderProps> = ({
  framework,
  title,
  code,
  downloadUrl,
  className,
  hideHeader = false,
  compact = false,
}) => {
  const { toast } = useToast()
  const [copied, setCopied] = useState(false)

  const canCopy = framework === 'csv' || framework === 'ics'

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      toast({ title: 'Copied', description: 'Content copied to clipboard' })
    } catch {
      toast({ title: 'Failed to copy', description: 'Could not copy to clipboard', variant: 'destructive' })
    }
  }, [code, toast])

  const handleDownload = useCallback(async () => {
    if (downloadUrl) {
      // Fetch with auth token and trigger blob download
      try {
        const resp = await fetchStream(downloadUrl)
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const blob = await resp.blob()
        const ext = framework === 'csv' ? '.csv' : framework === 'ics' ? '.ics' : framework === 'pdf' ? '.pdf' : framework === 'xlsx' ? '.xlsx' : '.docx'
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${title.replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').slice(0, 100)}${ext}`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
      } catch (err) {
        console.error('[DocumentDownloader] Download failed:', err)
        toast({ title: 'Download failed', description: 'Could not download the file', variant: 'destructive' })
      }
      return
    }

    // For csv/ics without a download URL, create a blob download from code
    if (framework === 'csv' || framework === 'ics') {
      const mimeType = framework === 'csv' ? 'text/csv' : 'text/calendar'
      const ext = framework === 'csv' ? '.csv' : '.ics'
      const blob = new Blob([code], { type: `${mimeType};charset=utf-8` })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${title.replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').slice(0, 100)}${ext}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }
  }, [downloadUrl, framework, code, title, toast])

  return (
    <div className={cn(
      'rounded-lg border overflow-hidden bg-background flex flex-col',
      className
    )}>
      {/* Header - hidden in compact/thumbnail mode or fullscreen dialog */}
      {!hideHeader && !compact && (
        <div className="flex items-center justify-between p-3 border-b border-border/40">
          <div className="flex items-center gap-3 min-w-0">
            <div className="min-w-0">
              <div className="font-medium text-sm truncate">{title}</div>
              <TypeBadge type={framework} />
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {canCopy && (
              <Button variant="ghost" size="sm" className="h-7 px-2 text-xs gap-1" onClick={handleCopy}>
                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                {copied ? 'Copied' : 'Copy'}
              </Button>
            )}
            <Button variant="outline" size="sm" className="h-7 px-3 text-xs gap-1.5" onClick={handleDownload}>
              <Download className="h-3 w-3" />
              Download
            </Button>
          </div>
        </div>
      )}

      {/* Preview */}
      <div className="min-h-[100px] flex-1 flex flex-col">
        {framework === 'csv' && <CSVPreview code={code} compact={compact} />}
        {framework === 'ics' && <ICSPreview code={code} compact={compact} />}
        {framework === 'pdf' && downloadUrl && (
          <PDFPreview url={downloadUrl} compact={compact} />
        )}
        {framework === 'pdf' && !downloadUrl && (
          <div className="flex flex-col items-center justify-center p-8 text-muted-foreground">
            <FileText className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-sm">PDF not yet generated</p>
            <p className="text-xs mt-1">The document will be available after execution</p>
          </div>
        )}
        {framework === 'docx' && (
          <div className="flex flex-col items-center justify-center p-8 text-muted-foreground">
            <FileText className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-sm">Word Document</p>
            <p className="text-xs mt-1">Download to view in Microsoft Word or compatible editor</p>
          </div>
        )}
        {framework === 'xlsx' && downloadUrl && (
          <XlsxPreview downloadUrl={downloadUrl} compact={compact} />
        )}
        {framework === 'xlsx' && !downloadUrl && (
          <div className="flex flex-col items-center justify-center p-8 text-muted-foreground">
            <Table className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-sm">Excel Spreadsheet</p>
            <p className="text-xs mt-1">The spreadsheet will be available after execution</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default DocumentDownloader
