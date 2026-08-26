/**
 * ExcelPreview - Interactive Excel file viewer and editor
 *
 * Features:
 * - Column resizing with drag handles
 * - Formula editing via formula bar
 * - Row/column headers with numbers
 * - Auto-sizing cells
 * - Fixed container with horizontal/vertical scroll
 * - Multi-sheet support
 */

import { useState, useEffect } from 'react'
import { Input } from '@/components/ui/input'
import { GripVertical } from 'lucide-react'
import { readExcel, updateCell, batchUpdateCells, type CellUpdate } from '@/api/excel'
import { useToast } from '@/hooks/use-toast'
import { toErrorMessage } from '@/utils/errorMessages'

/** A single spreadsheet cell's value, as the backend's JSON-serialized `readExcel` response carries it. */
type ExcelCellValue = string | number | boolean | null

interface ExcelPreviewProps {
  fileName: string
  filePath: string
  content: string
  userId?: string
  projectId?: string
}

export function ExcelPreview({ fileName, filePath, content, userId, projectId }: ExcelPreviewProps) {
  const { toast } = useToast()
  const [sheetData, setSheetData] = useState<ExcelCellValue[][]>([])
  const [sheetFormulas, setSheetFormulas] = useState<(string | null)[][]>([])
  const [sheetNames, setSheetNames] = useState<string[]>([])
  const [activeSheet, setActiveSheet] = useState(0)
  const [columnWidths, setColumnWidths] = useState<Record<number, number>>({})
  const [rowHeights, setRowHeights] = useState<Record<number, number>>({})
  const [resizingColumn, setResizingColumn] = useState<number | null>(null)
  const [resizingRow, setResizingRow] = useState<number | null>(null)
  const [resizeStartX, setResizeStartX] = useState(0)
  const [resizeStartY, setResizeStartY] = useState(0)
  const [resizeStartWidth, setResizeStartWidth] = useState(0)
  const [resizeStartHeight, setResizeStartHeight] = useState(0)
  const [selectedCell, setSelectedCell] = useState<{ row: number; col: number } | null>(null)
  const [selectionStart, setSelectionStart] = useState<{ row: number; col: number } | null>(null) // Start of multi-select range
  const [selectionEnd, setSelectionEnd] = useState<{ row: number; col: number } | null>(null) // End of multi-select range
  const [isDraggingSelection, setIsDraggingSelection] = useState(false) // Dragging to select
  const [formulaBarValue, setFormulaBarValue] = useState('')
  const [isEditMode, setIsEditMode] = useState(false) // Mode édition actif
  const [formulaBarRef, setFormulaBarRef] = useState<HTMLInputElement | null>(null)
  const [referencedCells, setReferencedCells] = useState<Set<string>>(new Set()) // Cells referenced in current formula
  const [inlineEditCell, setInlineEditCell] = useState<{ row: number; col: number } | null>(null) // Cell being edited inline
  const [inlineEditValue, setInlineEditValue] = useState('') // Inline edit value
  const [copiedCell, setCopiedCell] = useState<{ row: number; col: number } | null>(null) // Cell that was copied
  const [copiedRange, setCopiedRange] = useState<{ startRow: number; startCol: number; endRow: number; endCol: number } | null>(null) // Range of copied cells
  const [pasteMode, setPasteMode] = useState<'formula' | 'value'>('formula') // Paste mode
  const [isFillHandleDragging, setIsFillHandleDragging] = useState(false) // Fill handle dragging
  const [fillHandleEnd, setFillHandleEnd] = useState<{ row: number; col: number } | null>(null) // End cell for fill handle

  // Load Excel file using openpyxl API
  useEffect(() => {
    const loadExcelData = async () => {
      if (!userId || !projectId) return

      try {
        const result = await readExcel(userId, projectId, projectId, filePath, activeSheet)

        if (!result.success) {
          throw new Error(result.error || 'Failed to read Excel file')
        }

        setSheetNames(result.sheet_names)
        setSheetData(result.data)
        setSheetFormulas(result.formulas)
        setColumnWidths(result.column_widths || {})
      } catch (error) {
        console.error('Failed to load Excel file:', error)
        toast({
          title: 'Error',
          description: toErrorMessage(error) || 'Failed to load Excel file',
          variant: 'destructive',
        })
      }
    }

    loadExcelData()
  }, [userId, projectId, filePath, activeSheet])

  // Convert column index to Excel letter (0=A, 1=B, ..., 25=Z, 26=AA, etc.)
  const getColumnLetter = (index: number): string => {
    let letter = ''
    let num = index
    while (num >= 0) {
      letter = String.fromCharCode(65 + (num % 26)) + letter
      num = Math.floor(num / 26) - 1
    }
    return letter
  }

  // Parse cell references from formula (e.g., "=A1+B2" -> ["A1", "B2"])
  const parseCellReferences = (formula: string): Set<string> => {
    const refs = new Set<string>()
    // Match cell references like A1, B10, AA100, etc.
    const cellRegex = /\b([A-Z]+\d+)\b/g
    let match
    while ((match = cellRegex.exec(formula)) !== null) {
      refs.add(match[1])
    }
    return refs
  }

  // Check if a cell is in the selected range
  const isCellInRange = (row: number, col: number): boolean => {
    if (!selectionStart || !selectionEnd) return false
    const minRow = Math.min(selectionStart.row, selectionEnd.row)
    const maxRow = Math.max(selectionStart.row, selectionEnd.row)
    const minCol = Math.min(selectionStart.col, selectionEnd.col)
    const maxCol = Math.max(selectionStart.col, selectionEnd.col)
    return row >= minRow && row <= maxRow && col >= minCol && col <= maxCol
  }

  // Get the current selection range
  const getSelectionRange = () => {
    if (!selectionStart || !selectionEnd) return null
    return {
      startRow: Math.min(selectionStart.row, selectionEnd.row),
      endRow: Math.max(selectionStart.row, selectionEnd.row),
      startCol: Math.min(selectionStart.col, selectionEnd.col),
      endCol: Math.max(selectionStart.col, selectionEnd.col),
    }
  }

  // Update referenced cells when formula changes
  useEffect(() => {
    if (isEditMode && formulaBarValue.startsWith('=')) {
      setReferencedCells(parseCellReferences(formulaBarValue))
    } else {
      setReferencedCells(new Set())
    }
  }, [formulaBarValue, isEditMode])

  // Keyboard event handler for copy/paste
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if typing in an input field
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
        return
      }

      const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0
      const cmdOrCtrl = isMac ? e.metaKey : e.ctrlKey

      // Copy: Cmd+C / Ctrl+C
      if (cmdOrCtrl && e.key === 'c' && selectedCell && !isEditMode) {
        e.preventDefault()
        handleCopy()
      }

      // Paste: Cmd+V / Ctrl+V (formula)
      if (cmdOrCtrl && e.key === 'v' && !e.shiftKey && selectedCell && !isEditMode) {
        e.preventDefault()
        setPasteMode('formula')
        handlePaste()
      }

      // Paste values only: Cmd+Shift+V / Ctrl+Shift+V
      if (cmdOrCtrl && e.shiftKey && e.key === 'v' && selectedCell && !isEditMode) {
        e.preventDefault()
        setPasteMode('value')
        handlePaste()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [selectedCell, copiedCell, copiedRange, isEditMode, pasteMode])

  // Change active sheet
  const handleSheetChange = (index: number) => {
    setActiveSheet(index)
    setSelectedCell(null)
    setFormulaBarValue('')
    setIsEditMode(false)
    setReferencedCells(new Set())
  }

  // Handle cell selection
  const handleCellClick = (rowIndex: number, colIndex: number, shiftKey: boolean = false) => {
    // In edit mode: append cell reference to formula
    if (isEditMode && selectedCell) {
      const cellRef = `${getColumnLetter(colIndex)}${rowIndex + 1}`

      // Append the cell reference to current formula
      setFormulaBarValue(prev => {
        // If formula is empty or doesn't start with =, start a new formula
        if (!prev || !prev.startsWith('=')) {
          return `=${cellRef}`
        }
        // Otherwise, append the reference
        return `${prev}${cellRef}`
      })

      // Keep focus on formula bar by refocusing after a brief delay
      setTimeout(() => {
        const input = document.querySelector('input[placeholder*="Click a cell"]') as HTMLInputElement
        if (input) {
          input.focus()
          // Move cursor to end
          input.setSelectionRange(input.value.length, input.value.length)
        }
      }, 0)

      return
    }

    // Shift+Click: extend selection range
    if (shiftKey && selectionStart) {
      setSelectionEnd({ row: rowIndex, col: colIndex })
      setSelectedCell({ row: rowIndex, col: colIndex })
      return
    }

    // Normal mode: select the cell
    setSelectedCell({ row: rowIndex, col: colIndex })
    setSelectionStart({ row: rowIndex, col: colIndex })
    setSelectionEnd({ row: rowIndex, col: colIndex })
    const formula = sheetFormulas[rowIndex]?.[colIndex]
    const value = sheetData[rowIndex]?.[colIndex] ?? ''
    setFormulaBarValue(formula ? `=${formula}` : String(value))
    setIsEditMode(false)
    setInlineEditCell(null) // Exit inline edit if active
  }

  // Handle mouse down for drag selection
  const handleCellMouseDown = (rowIndex: number, colIndex: number, e: React.MouseEvent) => {
    if (e.button !== 0) return // Only left click
    if (isEditMode) return // Don't drag in edit mode
    if (isFillHandleDragging) return // Don't start cell selection if fill handle is being dragged

    setIsDraggingSelection(true)
    setSelectionStart({ row: rowIndex, col: colIndex })
    setSelectionEnd({ row: rowIndex, col: colIndex })
    setSelectedCell({ row: rowIndex, col: colIndex })
  }

  // Handle mouse enter during drag
  const handleCellMouseEnter = (rowIndex: number, colIndex: number) => {
    if (isDraggingSelection) {
      setSelectionEnd({ row: rowIndex, col: colIndex })
      setSelectedCell({ row: rowIndex, col: colIndex })
    }
    if (isFillHandleDragging) {
      setFillHandleEnd({ row: rowIndex, col: colIndex })
    }
  }

  // Handle mouse up to end drag
  useEffect(() => {
    const handleMouseUp = async () => {
      if (isDraggingSelection) {
        setIsDraggingSelection(false)
        // Update formula bar with first cell of selection
        if (selectionStart) {
          const formula = sheetFormulas[selectionStart.row]?.[selectionStart.col]
          const value = sheetData[selectionStart.row]?.[selectionStart.col] ?? ''
          setFormulaBarValue(formula ? `=${formula}` : String(value))
        }
      }

      // Handle fill handle drag complete
      if (isFillHandleDragging) {
        setIsFillHandleDragging(false)
        if (fillHandleEnd && selectionStart && selectionEnd) {
          await handleFillComplete()
        }
        setFillHandleEnd(null)
      }
    }

    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDraggingSelection, isFillHandleDragging, selectionStart, selectionEnd, fillHandleEnd, sheetFormulas, sheetData])

  // Change cursor to crosshair when fill handle is being dragged
  useEffect(() => {
    if (isFillHandleDragging) {
      document.body.style.cursor = 'crosshair'
    } else {
      document.body.style.cursor = ''
    }

    // Cleanup on unmount
    return () => {
      document.body.style.cursor = ''
    }
  }, [isFillHandleDragging])

  // Handle fill handle mouse enter
  const handleFillHandleMouseEnter = (rowIndex: number, colIndex: number) => {
    if (isFillHandleDragging) {
      setFillHandleEnd({ row: rowIndex, col: colIndex })
    }
  }

  // Complete fill operation (OPTIMIZED with batch update)
  const handleFillComplete = async () => {
    if (!fillHandleEnd || !selectionStart || !selectionEnd || !userId || !projectId) return

    const range = getSelectionRange()
    if (!range) return

    const fillStartRow = range.startRow
    const fillStartCol = range.startCol
    const fillEndRow = Math.max(range.endRow, fillHandleEnd.row)
    const fillEndCol = Math.max(range.endCol, fillHandleEnd.col)

    try {
      const updates: CellUpdate[] = []

      // Fill vertically (down)
      if (fillHandleEnd.row > range.endRow) {
        for (let col = fillStartCol; col <= fillEndCol; col++) {
          // Get the pattern from the source range
          const sourceValues = []
          const sourceFormulas = []
          for (let row = fillStartRow; row <= range.endRow; row++) {
            sourceValues.push(sheetData[row]?.[col] ?? '')
            sourceFormulas.push(sheetFormulas[row]?.[col])
          }

          // Fill down
          for (let row = range.endRow + 1; row <= fillEndRow; row++) {
            const sourceIndex = (row - fillStartRow) % sourceValues.length
            const sourceFormula = sourceFormulas[sourceIndex]
            const sourceValue = sourceValues[sourceIndex]

            updates.push({
              row,
              col,
              value: sourceFormula ? undefined : String(sourceValue),
              formula: sourceFormula || undefined,
            })
          }
        }
      }

      // Fill horizontally (right)
      if (fillHandleEnd.col > range.endCol) {
        for (let row = fillStartRow; row <= fillEndRow; row++) {
          // Get the pattern from the source range
          const sourceValues = []
          const sourceFormulas = []
          for (let col = fillStartCol; col <= range.endCol; col++) {
            sourceValues.push(sheetData[row]?.[col] ?? '')
            sourceFormulas.push(sheetFormulas[row]?.[col])
          }

          // Fill right
          for (let col = range.endCol + 1; col <= fillEndCol; col++) {
            const sourceIndex = (col - fillStartCol) % sourceValues.length
            const sourceFormula = sourceFormulas[sourceIndex]
            const sourceValue = sourceValues[sourceIndex]

            updates.push({
              row,
              col,
              value: sourceFormula ? undefined : String(sourceValue),
              formula: sourceFormula || undefined,
            })
          }
        }
      }

      // Batch update all cells in ONE request (MUCH faster!)
      const result = await batchUpdateCells(
        userId,
        projectId,
        projectId,
        filePath,
        activeSheet,
        updates
      )

      if (!result.success) {
        throw new Error(result.error || 'Failed to fill cells')
      }

      // Apply all updated values from backend
      const newData = [...sheetData]
      const newFormulas = [...sheetFormulas]

      if (result.updated_cells) {
        Object.entries(result.updated_cells).forEach(([cellKey, cellValue]) => {
          const [cellRow, cellCol] = cellKey.split('_').map(Number)
          if (!newData[cellRow]) newData[cellRow] = []
          newData[cellRow][cellCol] = cellValue
        })
      }

      // Update formulas for filled cells
      updates.forEach(update => {
        if (!newFormulas[update.row]) newFormulas[update.row] = []
        newFormulas[update.row][update.col] = update.formula || null
      })

      setSheetData(newData)
      setSheetFormulas(newFormulas)

      // Update selection to include filled range
      setSelectionEnd(fillHandleEnd)

      toast({
        title: `${updates.length} Cell${updates.length > 1 ? 's' : ''} Filled`,
        description: 'Auto-fill completed successfully',
      })
    } catch (error) {
      console.error('Failed to fill:', error)
      toast({
        title: 'Error',
        description: toErrorMessage(error) || 'Failed to fill cells',
        variant: 'destructive',
      })
    }
  }

  // Handle double-click for inline editing
  const handleCellDoubleClick = (rowIndex: number, colIndex: number) => {
    const formula = sheetFormulas[rowIndex]?.[colIndex]
    const value = sheetData[rowIndex]?.[colIndex] ?? ''
    const editValue = formula ? `=${formula}` : String(value)

    setInlineEditCell({ row: rowIndex, col: colIndex })
    setInlineEditValue(editValue)
    setSelectedCell({ row: rowIndex, col: colIndex })
    setFormulaBarValue(editValue)
    setIsEditMode(true)

    // Focus the inline input after render
    setTimeout(() => {
      const input = document.querySelector(`input[data-cell="${rowIndex}-${colIndex}"]`) as HTMLInputElement
      if (input) {
        input.focus()
        input.select()
      }
    }, 0)
  }

  // Handle inline edit value change
  const handleInlineEditChange = (value: string) => {
    setInlineEditValue(value)
    setFormulaBarValue(value)
    // Auto-enable edit mode when user types
    if (!isEditMode) {
      setIsEditMode(true)
    }
  }

  // Apply inline edit (Enter or Tab)
  const handleInlineEditKeyDown = async (e: React.KeyboardEvent, rowIndex: number, colIndex: number) => {
    // Escape: Cancel inline editing
    if (e.key === 'Escape') {
      e.preventDefault()
      setInlineEditCell(null)
      setIsEditMode(false)
      const formula = sheetFormulas[rowIndex]?.[colIndex]
      const value = sheetData[rowIndex]?.[colIndex] ?? ''
      setFormulaBarValue(formula ? `=${formula}` : String(value))
      return
    }

    // Enter or Tab: Apply and exit inline edit
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault()
      setInlineEditCell(null)
      // Trigger the formula bar key handler to save the value
      await handleFormulaBarKeyDown(e)
    }
  }

  // Exit inline edit on blur
  const handleInlineEditBlur = () => {
    setInlineEditCell(null)
  }

  // Copy cell or range
  const handleCopy = () => {
    if (!selectedCell) return

    const range = getSelectionRange()
    if (range && (range.startRow !== range.endRow || range.startCol !== range.endCol)) {
      // Multi-cell copy
      setCopiedRange(range)
      setCopiedCell(null)
      const cells = (range.endRow - range.startRow + 1) * (range.endCol - range.startCol + 1)
      toast({
        title: 'Range Copied',
        description: `${cells} cells copied to clipboard`,
      })
    } else {
      // Single cell copy
      setCopiedCell({ row: selectedCell.row, col: selectedCell.col })
      setCopiedRange(null)
      toast({
        title: 'Cell Copied',
        description: `${getColumnLetter(selectedCell.col)}${selectedCell.row + 1} copied to clipboard`,
      })
    }
  }

  // Paste cell or range
  const handlePaste = async () => {
    if (!selectedCell || !userId || !projectId) return
    if (!copiedCell && !copiedRange) return

    try {
      const newData = [...sheetData]
      const newFormulas = [...sheetFormulas]
      let pastedCells = 0

      // Single cell paste
      if (copiedCell) {
        const { row: fromRow, col: fromCol } = copiedCell
        const { row: toRow, col: toCol } = selectedCell

        const sourceFormula = sheetFormulas[fromRow]?.[fromCol]
        const sourceValue = sheetData[fromRow]?.[fromCol] ?? ''

        // Determine what to paste based on mode
        const pasteFormula = pasteMode === 'formula' && sourceFormula
        const pasteValue = pasteMode === 'value' || !sourceFormula

        const result = await updateCell(
          userId,
          projectId,
          projectId,
          filePath,
          activeSheet,
          toRow,
          toCol,
          pasteValue ? String(sourceValue) : undefined,
          pasteFormula ? sourceFormula : undefined
        )

        if (!result.success) {
          throw new Error(result.error || 'Failed to paste cell')
        }

        if (!newData[toRow]) newData[toRow] = []
        newData[toRow][toCol] = result.evaluated_value

        if (result.updated_cells) {
          Object.entries(result.updated_cells).forEach(([cellKey, cellValue]) => {
            const [cellRow, cellCol] = cellKey.split('_').map(Number)
            if (!newData[cellRow]) newData[cellRow] = []
            newData[cellRow][cellCol] = cellValue
          })
        }

        if (!newFormulas[toRow]) newFormulas[toRow] = []
        newFormulas[toRow][toCol] = pasteFormula ? sourceFormula : null

        setFormulaBarValue(pasteFormula ? `=${sourceFormula}` : String(result.evaluated_value))
        pastedCells = 1
      }
      // Range paste
      else if (copiedRange) {
        const { startRow: fromStartRow, startCol: fromStartCol, endRow: fromEndRow, endCol: fromEndCol } = copiedRange
        const { row: toRow, col: toCol } = selectedCell

        const rowCount = fromEndRow - fromStartRow + 1
        const colCount = fromEndCol - fromStartCol + 1

        // Paste each cell in the range
        for (let r = 0; r < rowCount; r++) {
          for (let c = 0; c < colCount; c++) {
            const srcRow = fromStartRow + r
            const srcCol = fromStartCol + c
            const destRow = toRow + r
            const destCol = toCol + c

            const sourceFormula = sheetFormulas[srcRow]?.[srcCol]
            const sourceValue = sheetData[srcRow]?.[srcCol] ?? ''

            const pasteFormula = pasteMode === 'formula' && sourceFormula
            const pasteValue = pasteMode === 'value' || !sourceFormula

            const result = await updateCell(
              userId,
              projectId,
              projectId,
              filePath,
              activeSheet,
              destRow,
              destCol,
              pasteValue ? String(sourceValue) : undefined,
              pasteFormula ? sourceFormula : undefined
            )

            if (result.success) {
              if (!newData[destRow]) newData[destRow] = []
              newData[destRow][destCol] = result.evaluated_value

              if (!newFormulas[destRow]) newFormulas[destRow] = []
              newFormulas[destRow][destCol] = pasteFormula ? sourceFormula : null

              pastedCells++
            }
          }
        }
      }

      setSheetData(newData)
      setSheetFormulas(newFormulas)

      toast({
        title: `${pastedCells} Cell${pastedCells > 1 ? 's' : ''} Pasted`,
        description: pasteMode === 'formula' ? 'Formulas pasted' : 'Values pasted',
      })
    } catch (error) {
      console.error('Failed to paste:', error)
      toast({
        title: 'Error',
        description: toErrorMessage(error) || 'Failed to paste',
        variant: 'destructive',
      })
    }
  }

  // Update cell from formula bar
  const handleFormulaBarChange = (value: string) => {
    setFormulaBarValue(value)
    // Sync with inline edit if active
    if (inlineEditCell) {
      setInlineEditValue(value)
    }
    // Auto-enable edit mode when user types
    if (!isEditMode) {
      setIsEditMode(true)
    }
  }

  // Handle formula bar focus
  const handleFormulaBarFocus = () => {
    setIsEditMode(true)
  }

  // Apply formula bar value to cell using openpyxl API
  const handleFormulaBarKeyDown = async (e: React.KeyboardEvent) => {
    if (!selectedCell) return

    // Escape: Cancel editing
    if (e.key === 'Escape') {
      e.preventDefault()
      setIsEditMode(false)
      // Restore original value
      const formula = sheetFormulas[selectedCell.row]?.[selectedCell.col]
      const value = sheetData[selectedCell.row]?.[selectedCell.col] ?? ''
      setFormulaBarValue(formula ? `=${formula}` : String(value))
      return
    }

    // Enter or Tab: Apply changes
    if ((e.key === 'Enter' || e.key === 'Tab') && selectedCell && userId && projectId) {
      e.preventDefault()
      const { row, col } = selectedCell
      const value = formulaBarValue
      setIsEditMode(false)

      try {
        const result = await updateCell(
          userId,
          projectId,
          projectId,
          filePath,
          activeSheet,
          row,
          col,
          value.startsWith('=') ? undefined : value,
          value.startsWith('=') ? value.substring(1) : undefined
        )

        if (!result.success) {
          throw new Error(result.error || 'Failed to update cell')
        }

        // Update local state with evaluated value
        const newData = [...sheetData]
        if (!newData[row]) newData[row] = []
        newData[row][col] = result.evaluated_value

        // Apply cascade updates from backend (all cells that were recalculated)
        if (result.updated_cells) {
          Object.entries(result.updated_cells).forEach(([cellKey, cellValue]) => {
            const [cellRow, cellCol] = cellKey.split('_').map(Number)
            if (!newData[cellRow]) newData[cellRow] = []
            newData[cellRow][cellCol] = cellValue
          })
        }

        setSheetData(newData)

        // Update formula state
        const newFormulas = [...sheetFormulas]
        if (!newFormulas[row]) newFormulas[row] = []
        newFormulas[row][col] = value.startsWith('=') ? value.substring(1) : null
        setSheetFormulas(newFormulas)

        const updatedCount = result.updated_cells ? Object.keys(result.updated_cells).length : 0
        toast({
          title: 'Cell Updated',
          description: updatedCount > 1
            ? `Cell updated with ${updatedCount} cascade recalculations`
            : 'Cell value updated successfully',
        })

        // Move selection after Enter/Tab
        const maxRows = sheetData.length
        const maxCols = Math.max(...sheetData.map(r => r?.length || 0))

        if (e.key === 'Enter') {
          // Enter: move down (or up with Shift)
          const newRow = e.shiftKey ? Math.max(0, row - 1) : Math.min(maxRows - 1, row + 1)
          setSelectedCell({ row: newRow, col })
          const newFormula = sheetFormulas[newRow]?.[col]
          const newValue = sheetData[newRow]?.[col] ?? ''
          setFormulaBarValue(newFormula ? `=${newFormula}` : String(newValue))
        } else if (e.key === 'Tab') {
          // Tab: move right (or left with Shift)
          const newCol = e.shiftKey ? Math.max(0, col - 1) : Math.min(maxCols - 1, col + 1)
          setSelectedCell({ row, col: newCol })
          const newFormula = sheetFormulas[row]?.[newCol]
          const newValue = sheetData[row]?.[newCol] ?? ''
          setFormulaBarValue(newFormula ? `=${newFormula}` : String(newValue))
        }
      } catch (error) {
        console.error('Failed to update cell:', error)
        toast({
          title: 'Error',
          description: toErrorMessage(error) || 'Failed to update cell',
          variant: 'destructive',
        })
      }
    }
  }

  // Column resize handlers
  const handleColumnResizeStart = (colIndex: number, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setResizingColumn(colIndex)
    setResizeStartX(e.clientX)
    setResizeStartWidth(columnWidths[colIndex] || 80)
  }

  // Row resize handlers
  const handleRowResizeStart = (rowIndex: number, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setResizingRow(rowIndex)
    setResizeStartY(e.clientY)
    setResizeStartHeight(rowHeights[rowIndex] || 28)
  }

  // Auto-resize column to fit content (Excel-like double-click behavior)
  const handleColumnAutoResize = (colIndex: number) => {
    // Calculate optimal width for this column
    let maxWidth = 50 // Minimum width

    // Check all rows in this column
    for (let rowIndex = 0; rowIndex < sheetData.length; rowIndex++) {
      const cellValue = String(sheetData[rowIndex]?.[colIndex] ?? '')
      const cellFormula = sheetFormulas[rowIndex]?.[colIndex]

      // Use formula length if present, otherwise value length
      const textToMeasure = cellFormula ? `=${cellFormula}` : cellValue

      // Estimate width: ~7px per character + padding (16px)
      const estimatedWidth = (textToMeasure.length * 7) + 16
      maxWidth = Math.max(maxWidth, estimatedWidth)
    }

    // Also check column header letter width
    const headerWidth = getColumnLetter(colIndex).length * 10 + 16
    maxWidth = Math.max(maxWidth, headerWidth)

    // Cap at reasonable maximum
    maxWidth = Math.min(maxWidth, 400)

    setColumnWidths(prev => ({ ...prev, [colIndex]: maxWidth }))
  }

  // Auto-resize row to fit content (Excel-like double-click behavior)
  const handleRowAutoResize = (rowIndex: number) => {
    // For now, use a simple heuristic based on content
    // In a full implementation, we'd measure actual rendered height
    let maxHeight = 20 // Minimum height

    const maxCols = Math.max(...sheetData.map(row => row?.length || 0))

    // Check all cells in this row
    for (let colIndex = 0; colIndex < maxCols; colIndex++) {
      const cellValue = String(sheetData[rowIndex]?.[colIndex] ?? '')
      const cellFormula = sheetFormulas[rowIndex]?.[colIndex]

      const textToMeasure = cellFormula ? `=${cellFormula}` : cellValue

      // Estimate height based on text length and column width
      const colWidth = columnWidths[colIndex] || 80
      const charsPerLine = Math.floor(colWidth / 7)
      const estimatedLines = Math.ceil(textToMeasure.length / charsPerLine)
      const estimatedHeight = (estimatedLines * 16) + 12 // 16px per line + padding

      maxHeight = Math.max(maxHeight, estimatedHeight)
    }

    // Cap at reasonable maximum
    maxHeight = Math.min(maxHeight, 200)

    setRowHeights(prev => ({ ...prev, [rowIndex]: maxHeight }))
  }

  useEffect(() => {
    if (resizingColumn === null) return

    const handleMouseMove = (e: MouseEvent) => {
      const delta = e.clientX - resizeStartX
      const newWidth = Math.max(50, resizeStartWidth + delta)
      setColumnWidths(prev => ({ ...prev, [resizingColumn]: newWidth }))
    }

    const handleMouseUp = () => {
      setResizingColumn(null)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [resizingColumn, resizeStartX, resizeStartWidth])

  useEffect(() => {
    if (resizingRow === null) return

    const handleMouseMove = (e: MouseEvent) => {
      const delta = e.clientY - resizeStartY
      const newHeight = Math.max(20, resizeStartHeight + delta)
      setRowHeights(prev => ({ ...prev, [resizingRow]: newHeight }))
    }

    const handleMouseUp = () => {
      setResizingRow(null)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [resizingRow, resizeStartY, resizeStartHeight])

  if (!sheetData.length) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-background text-muted-foreground">
        <p>Empty spreadsheet</p>
      </div>
    )
  }

  const maxCols = Math.max(...sheetData.map(row => row?.length || 0))
  const maxRows = sheetData.length

  // Calculate total table width to force horizontal scroll
  const rowNumberWidth = 48 // w-12 = 48px
  const totalColumnsWidth = Array.from({ length: maxCols }, (_, i) => columnWidths[i] || 80).reduce((sum, w) => sum + w, 0)
  const totalTableWidth = rowNumberWidth + totalColumnsWidth

  return (
    <div className="h-full w-full bg-background overflow-hidden flex">
      <div className="flex-1 p-4 min-w-0">
        <div className="flex flex-col rounded-lg border border-border bg-background h-full w-full min-w-0">
        {/* Formula Bar */}
        <div className="flex items-center gap-2 border-b border-border px-4 py-2 bg-slate-900 flex-shrink-0 rounded-t-lg min-w-0">
        <span className="text-xs font-medium text-slate-400 min-w-[60px] font-mono">
          {(() => {
            const range = getSelectionRange()
            if (range && (range.startRow !== range.endRow || range.startCol !== range.endCol)) {
              // Multi-cell selection
              const cellCount = (range.endRow - range.startRow + 1) * (range.endCol - range.startCol + 1)
              return `${cellCount} cells`
            } else if (selectedCell) {
              // Single cell
              return `${getColumnLetter(selectedCell.col)}${selectedCell.row + 1}`
            }
            return ''
          })()}
        </span>
        {isEditMode && (
          <span className="text-xs px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 font-medium whitespace-nowrap flex-shrink-0">
            Click cells to reference
          </span>
        )}
        {(copiedCell || copiedRange) && (
          <span className="text-xs px-2 py-0.5 rounded bg-green-500/20 text-green-300 font-medium whitespace-nowrap flex-shrink-0">
            {pasteMode === 'formula' ? 'Paste: Formula' : 'Paste: Value'} •
            {pasteMode === 'formula' ? 'Shift+' : ''}Cmd/Ctrl+V
          </span>
        )}
        <Input
          value={formulaBarValue}
          onChange={(e) => handleFormulaBarChange(e.target.value)}
          onKeyDown={handleFormulaBarKeyDown}
          onFocus={handleFormulaBarFocus}
          placeholder="Click a cell to edit formula or value..."
          className="flex-1 font-mono text-sm h-7 min-w-0"
          disabled={!selectedCell}
        />
      </div>

      {/* Sheet tabs and Save button */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2 flex-shrink-0 min-w-0">
        <div className="flex items-center gap-2 overflow-x-auto min-w-0 flex-1">
          {sheetNames.map((name, index) => (
            <button
              key={index}
              onClick={() => handleSheetChange(index)}
              className={`px-3 py-1 text-sm rounded transition-colors whitespace-nowrap ${
                activeSheet === index
                  ? 'bg-accent-brand text-slate-900 font-medium'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >
              {name}
            </button>
          ))}
        </div>
        <div className="text-xs text-muted-foreground ml-4 flex-shrink-0 whitespace-nowrap">
          Auto-saved
        </div>
      </div>

      {/* Spreadsheet container with fixed size and scroll */}
      <div className="flex-1 overflow-auto relative rounded-b-lg min-w-0">
        <table
          className="border-collapse border border-border"
          style={{
            minWidth: totalTableWidth,
          }}
        >
          <thead className="sticky top-0 z-10">
            <tr>
              {/* Empty corner cell */}
              <th className="border border-border bg-slate-800 px-2 py-1 text-xs font-medium text-slate-300 sticky left-0 z-20 w-12 min-w-[48px]">

              </th>

              {/* Column headers */}
              {Array.from({ length: maxCols }, (_, i) => (
                <th
                  key={i}
                  className="border border-border bg-slate-800 px-2 py-1 text-xs font-medium text-slate-300 relative"
                  style={{
                    width: columnWidths[i] || 80,
                    minWidth: columnWidths[i] || 80,
                    maxWidth: columnWidths[i] || 80,
                  }}
                >
                  {getColumnLetter(i)}

                  {/* Column Resize Handle */}
                  <div
                    className="absolute top-0 right-0 w-2 h-full cursor-col-resize hover:bg-accent-brand/30 group flex items-center justify-center"
                    onMouseDown={(e) => handleColumnResizeStart(i, e)}
                    onDoubleClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      handleColumnAutoResize(i)
                    }}
                    title="Drag to resize | Double-click to auto-fit"
                  >
                    <GripVertical className="h-3 w-3 text-transparent group-hover:text-accent-brand transition-colors" />
                  </div>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {sheetData.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                style={{
                  height: rowHeights[rowIndex] || 28,
                }}
              >
                {/* Row number */}
                <td className="border border-border bg-slate-800 px-2 py-1 text-xs font-medium text-slate-300 text-center sticky left-0 z-10 w-12 min-w-[48px] relative">
                  {rowIndex + 1}

                  {/* Row Resize Handle */}
                  <div
                    className="absolute bottom-0 left-0 w-full h-2 cursor-row-resize hover:bg-accent-brand/30 group flex items-center justify-center"
                    onMouseDown={(e) => handleRowResizeStart(rowIndex, e)}
                    onDoubleClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      handleRowAutoResize(rowIndex)
                    }}
                    title="Drag to resize | Double-click to auto-fit"
                  >
                    <div className="w-3 h-0.5 bg-transparent group-hover:bg-accent-brand transition-colors" />
                  </div>
                </td>

                {/* Data cells */}
                {Array.from({ length: maxCols }, (_, colIndex) => {
                  const isSelected = selectedCell?.row === rowIndex && selectedCell?.col === colIndex
                  const isInRange = isCellInRange(rowIndex, colIndex)
                  const cellFormula = sheetFormulas[rowIndex]?.[colIndex]
                  const displayValue = row?.[colIndex] ?? ''
                  const cellRef = `${getColumnLetter(colIndex)}${rowIndex + 1}`
                  const isReferenced = referencedCells.has(cellRef) && !isSelected && !isInRange
                  const isInlineEditing = inlineEditCell?.row === rowIndex && inlineEditCell?.col === colIndex
                  const isCopied = copiedCell?.row === rowIndex && copiedCell?.col === colIndex
                  const isInCopiedRange = copiedRange &&
                    rowIndex >= copiedRange.startRow && rowIndex <= copiedRange.endRow &&
                    colIndex >= copiedRange.startCol && colIndex <= copiedRange.endCol

                  // Check if this is the bottom-right cell of the selection (for fill handle)
                  const range = getSelectionRange()
                  const isBottomRightOfSelection = range &&
                    rowIndex === range.endRow &&
                    colIndex === range.endCol

                  // Check if this cell is in the fill preview area
                  const isInFillPreview = isFillHandleDragging && fillHandleEnd && range &&
                    ((fillHandleEnd.row > range.endRow && rowIndex > range.endRow && rowIndex <= fillHandleEnd.row &&
                      colIndex >= range.startCol && colIndex <= range.endCol) ||
                    (fillHandleEnd.col > range.endCol && colIndex > range.endCol && colIndex <= fillHandleEnd.col &&
                      rowIndex >= range.startRow && rowIndex <= range.endRow))

                  return (
                    <td
                      key={colIndex}
                      className="border border-border p-0"
                      style={{
                        width: columnWidths[colIndex] || 80,
                        minWidth: columnWidths[colIndex] || 80,
                        maxWidth: columnWidths[colIndex] || 80,
                        height: rowHeights[rowIndex] || 28,
                      }}
                    >
                      {isInlineEditing ? (
                        // Inline edit mode: show input field
                        <Input
                          data-cell={`${rowIndex}-${colIndex}`}
                          value={inlineEditValue}
                          onChange={(e) => handleInlineEditChange(e.target.value)}
                          onKeyDown={(e) => handleInlineEditKeyDown(e, rowIndex, colIndex)}
                          onBlur={handleInlineEditBlur}
                          className="h-full w-full border-0 rounded-none bg-accent-brand/20 ring-2 ring-inset ring-accent-brand font-mono text-sm px-2 py-1"
                        />
                      ) : (
                        // Normal display mode
                        <div
                          onClick={(e) => handleCellClick(rowIndex, colIndex, e.shiftKey)}
                          onDoubleClick={() => handleCellDoubleClick(rowIndex, colIndex)}
                          onMouseDown={(e) => handleCellMouseDown(rowIndex, colIndex, e)}
                          onMouseEnter={() => handleCellMouseEnter(rowIndex, colIndex)}
                          className={`px-2 py-1 text-sm cursor-pointer transition-colors overflow-hidden whitespace-nowrap text-ellipsis h-full flex items-center relative ${
                            isInFillPreview
                              ? 'bg-accent-brand/20 ring-1 ring-dashed ring-inset ring-accent-brand'
                              : isInRange
                              ? 'bg-accent-brand/10 ring-1 ring-inset ring-accent-brand/50'
                              : isCopied || isInCopiedRange
                              ? 'bg-green-500/10 ring-2 ring-inset ring-green-400 ring-dashed animate-pulse'
                              : isReferenced
                              ? 'bg-purple-500/10 ring-1 ring-inset ring-purple-400/50'
                              : 'bg-background hover:bg-slate-800/50'
                          }`}
                          title={cellFormula ? `=${cellFormula}` : String(displayValue)}
                        >
                          <span className={cellFormula ? 'font-medium text-accent-brand' : ''}>
                            {displayValue}
                          </span>

                          {/* Fill Handle - Optimized for better detection and responsiveness */}
                          {isBottomRightOfSelection && !isEditMode && (
                            <div
                              className="absolute -bottom-[2px] -right-[2px] w-4 h-4 cursor-crosshair z-50 group"
                              onMouseDown={(e) => {
                                e.preventDefault()
                                e.stopPropagation()
                                setIsFillHandleDragging(true)
                                setFillHandleEnd({ row: rowIndex, col: colIndex })
                              }}
                              title="Drag to auto-fill"
                            >
                              {/* Visible handle - small teal square */}
                              <div className="absolute bottom-1 right-1 w-2 h-2 bg-accent-brand border-2 border-slate-900 group-hover:w-2.5 group-hover:h-2.5 group-hover:bottom-0.5 group-hover:right-0.5 transition-all shadow-lg" />
                            </div>
                          )}
                        </div>
                      )}
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
    </div>
  )
}
