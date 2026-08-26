/**
 * Sandbox API Client
 *
 * Provides API methods for process management inside a running sandbox.
 */
import axios from 'axios'
import { orchestratorClient } from './client'

// ===========================
// Process Management API
// ===========================

export interface ProcessInfo {
  pid: number
  port: number
  command: string
  started_at: string
  status: 'running' | 'stopped'
}

/**
 * Read the backend-supplied `detail` off a failed orchestratorClient
 * request, falling back to `fallback` when the response has none —
 * mirrors the `err.detail || fallback` pattern the raw `fetch()` calls
 * this client replaces used against the parsed JSON error body.
 */
function detailError(err: unknown, fallback: string): Error {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: string } | undefined)?.detail
    if (detail) return new Error(detail)
  }
  return new Error(fallback)
}

/**
 * Start a background process in the sandbox and register its port
 */
export async function startProcess(params: {
  user_id: string
  conversation_id: string
  chat_id?: string
  command: string
  port: number
}): Promise<ProcessInfo> {
  try {
    const response = await orchestratorClient.post<ProcessInfo>('/processes/start', { ...params, sync_mode: true })
    return response.data
  } catch (err) {
    const status = axios.isAxiosError(err) ? err.response?.status : undefined
    throw detailError(err, `Failed to start process (${status})`)
  }
}

/**
 * List running processes with registered ports
 */
export async function listProcesses(userId: string, chatId: string): Promise<ProcessInfo[]> {
  try {
    const response = await orchestratorClient.get<ProcessInfo[]>(`/processes/${userId}`, {
      params: { chat_id: chatId },
      // Callers already swallow any failure and fall back to an empty
      // list — an expired session here shouldn't interrupt with a modal.
      suppressUnauthorizedModal: true,
    })
    return response.data
  } catch {
    return []
  }
}

/**
 * Stop a background process by PID
 */
export async function stopProcess(params: {
  user_id: string
  conversation_id: string
  chat_id?: string
  pid: number
}): Promise<{ success: boolean }> {
  try {
    const response = await orchestratorClient.post<{ success: boolean }>('/processes/stop', { ...params, sync_mode: true })
    return response.data
  } catch (err) {
    const status = axios.isAxiosError(err) ? err.response?.status : undefined
    throw detailError(err, `Failed to stop process (${status})`)
  }
}

/**
 * Stop a background process by port (looks up PID from registry)
 */
export async function stopProcessByPort(userId: string, conversationId: string, port: number): Promise<{ success: boolean }> {
  try {
    const response = await orchestratorClient.post<{ success: boolean }>('/processes/stop-by-port', {
      user_id: userId,
      conversation_id: conversationId,
      port,
    })
    return response.data
  } catch (err) {
    const status = axios.isAxiosError(err) ? err.response?.status : undefined
    throw detailError(err, `Failed to stop process (${status})`)
  }
}

/**
 * Restart a process atomically (stop + wait + start handled by orchestrator)
 */
export async function restartProcess(params: {
  user_id: string
  conversation_id: string
  chat_id?: string
  command: string
  port: number
}): Promise<ProcessInfo> {
  try {
    const response = await orchestratorClient.post<ProcessInfo>('/processes/restart', { ...params, sync_mode: true })
    return response.data
  } catch (err) {
    const status = axios.isAxiosError(err) ? err.response?.status : undefined
    throw detailError(err, `Failed to restart process (${status})`)
  }
}

/**
 * Build the preview URL for a running process port.
 * Uses direct orchestrator URL to bypass API gateway header-only auth.
 * SECURITY: Uses short-lived preview token instead of main JWT (CWE-598).
 */
const ORCHESTRATOR_DIRECT_URL = import.meta.env.VITE_ORCHESTRATOR_URL_DIRECT
  || 'http://localhost:8003'

/**
 * Check if a process is listening on a port inside the sandbox (TCP check).
 */
export async function checkProcessHealth(userId: string, port: number): Promise<boolean> {
  try {
    const response = await orchestratorClient.get<{ ready?: boolean }>('/processes/health', {
      params: { user_id: userId, port },
      // This is polled in a tight loop while waiting for a preview server
      // to come up; a session that expires mid-poll should fail this
      // check silently rather than pop the session-expired modal.
      suppressUnauthorizedModal: true,
    })
    return response.data.ready === true
  } catch {
    return false
  }
}

/**
 * Fetch a short-lived preview token scoped to a specific port.
 * Requires the main JWT (sent via Authorization header).
 */
export async function fetchPreviewToken(userId: string, port: number): Promise<string> {
  try {
    const response = await orchestratorClient.post<{ token: string }>('/preview/token', null, {
      params: { user_id: userId, port },
    })
    return response.data.token
  } catch {
    throw new Error('Failed to get preview token')
  }
}

/**
 * Build preview URL using a scoped preview token (not the main JWT).
 */
export function getPreviewUrl(userId: string, port: number, token: string, path?: string): string {
  const base = `${ORCHESTRATOR_DIRECT_URL}/preview/${userId}/${port}/${path || ''}`
  return `${base}?token=${encodeURIComponent(token)}`
}
