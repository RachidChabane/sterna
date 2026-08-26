/**
 * Excel API Client
 *
 * Communicates with the orchestrator for Excel operations using openpyxl
 */

import axios from 'axios'
import { getAccessToken, orchestratorClient } from './client'

/** A single spreadsheet cell's value, as the backend's JSON-serialized `read`/`update` responses carry it. */
type ExcelCellValue = string | number | boolean | null

export interface ExcelData {
  success: boolean
  sheet_names: string[]
  data: ExcelCellValue[][]
  formulas: (string | null)[][]
  column_widths: Record<number, number>
  error?: string
}

export interface UpdateCellResult {
  success: boolean
  evaluated_value: ExcelCellValue
  updated_cells?: Record<string, ExcelCellValue>
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
  updated_cells: Record<string, ExcelCellValue>
  count: number
  error?: string
}

function requireToken(): void {
  if (!getAccessToken()) throw new Error('No authentication token')
}

/**
 * Read the backend-supplied `detail` off a failed orchestratorClient
 * request, falling back to `fallback` — mirrors the `error.detail ||
 * fallback` pattern the raw `fetch()` calls this client replaces used
 * against the parsed JSON error body.
 */
function detailError(err: unknown, fallback: string): Error {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: string } | undefined)?.detail
    if (detail) return new Error(detail)
  }
  return new Error(fallback)
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
  requireToken()

  try {
    const response = await orchestratorClient.post<ExcelData>('/excel/read', {
      user_id: userId,
      conversation_id: conversationId,
      chat_id: chatId,
      sync_mode: true,
      path,
      sheet_index: sheetIndex,
    })
    return response.data
  } catch (err) {
    throw detailError(err, 'Failed to read Excel file')
  }
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
  requireToken()

  try {
    const response = await orchestratorClient.post<UpdateCellResult>('/excel/update-cell', {
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
    })
    return response.data
  } catch (err) {
    throw detailError(err, 'Failed to update cell')
  }
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
  requireToken()

  try {
    const response = await orchestratorClient.post<BatchUpdateResult>('/excel/batch-update', {
      user_id: userId,
      conversation_id: conversationId,
      chat_id: chatId,
      sync_mode: true,
      path,
      sheet_index: sheetIndex,
      updates,
    })
    return response.data
  } catch (err) {
    throw detailError(err, 'Failed to batch update cells')
  }
}
