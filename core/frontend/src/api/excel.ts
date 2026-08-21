/**
 * Excel API Client
 *
 * Communicates with the orchestrator for Excel operations using openpyxl
 */

import { getAccessToken, ORCHESTRATOR_URL } from './client'

export interface ExcelData {
  success: boolean
  sheet_names: string[]
  data: any[][]
  formulas: (string | null)[][]
  column_widths: Record<number, number>
  error?: string
}

export interface UpdateCellResult {
  success: boolean
  evaluated_value: any
  updated_cells?: Record<string, any>
  error?: string
}

export interface CellUpdate {
  row: number
  col: number
  value?: string
  formula?: string
}

export interface BatchUpdateResult {
  success: boolean
  updated_cells: Record<string, any>
  count: number
  error?: string
}

/**
 * Read an Excel file and get all data with formulas from the user's sandbox
 */
export async function readExcel(
  userId: string,
  conversationId: string,
  chatId: string,
  path: string,
  sheetIndex: number = 0
): Promise<ExcelData> {
  const token = getAccessToken()
  if (!token) throw new Error('No authentication token')

  const response = await fetch(`${ORCHESTRATOR_URL}/excel/read`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      user_id: userId,
      conversation_id: conversationId,
      chat_id: chatId,
      sync_mode: true,
      path,
      sheet_index: sheetIndex,
    }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to read Excel file')
  }

  return response.json()
}

/**
 * Update a cell with a value or formula in the user's sandbox
 */
export async function updateCell(
  userId: string,
  conversationId: string,
  chatId: string,
  path: string,
  sheetIndex: number,
  row: number,
  col: number,
  value?: string,
  formula?: string
): Promise<UpdateCellResult> {
  const token = getAccessToken()
  if (!token) throw new Error('No authentication token')

  const response = await fetch(`${ORCHESTRATOR_URL}/excel/update-cell`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      user_id: userId,
      conversation_id: conversationId,
      chat_id: chatId,
      sync_mode: true,
      path,
      sheet_index: sheetIndex,
      row,
      col,
      value,
      formula,
    }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to update cell')
  }

  return response.json()
}

/**
 * Batch update multiple cells at once (MUCH faster than multiple updateCell calls)
 */
export async function batchUpdateCells(
  userId: string,
  conversationId: string,
  chatId: string,
  path: string,
  sheetIndex: number,
  updates: CellUpdate[]
): Promise<BatchUpdateResult> {
  const token = getAccessToken()
  if (!token) throw new Error('No authentication token')

  const response = await fetch(`${ORCHESTRATOR_URL}/excel/batch-update`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      user_id: userId,
      conversation_id: conversationId,
      chat_id: chatId,
      sync_mode: true,
      path,
      sheet_index: sheetIndex,
      updates,
    }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to batch update cells')
  }

  return response.json()
}
