/**
 * Sandbox API Client
 *
 * Provides API methods for process management inside a running sandbox.
 */

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

const ORCHESTRATOR_URL = import.meta.env.VITE_ORCHESTRATOR_URL || '/api/v1/sandbox'

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
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
  const response = await fetch(`${ORCHESTRATOR_URL}/processes/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ ...params, sync_mode: true }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to start process (${response.status})`)
  }
  return response.json()
}

/**
 * List running processes with registered ports
 */
export async function listProcesses(userId: string, chatId: string): Promise<ProcessInfo[]> {
  const response = await fetch(
    `${ORCHESTRATOR_URL}/processes/${userId}?chat_id=${encodeURIComponent(chatId)}`,
    { headers: getAuthHeaders() },
  )
  if (!response.ok) return []
  return response.json()
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
  const response = await fetch(`${ORCHESTRATOR_URL}/processes/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ ...params, sync_mode: true }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to stop process (${response.status})`)
  }
  return response.json()
}

/**
 * Stop a background process by port (looks up PID from registry)
 */
export async function stopProcessByPort(userId: string, conversationId: string, port: number): Promise<{ success: boolean }> {
  const response = await fetch(`${ORCHESTRATOR_URL}/processes/stop-by-port`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ user_id: userId, conversation_id: conversationId, port }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to stop process (${response.status})`)
  }
  return response.json()
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
  const response = await fetch(`${ORCHESTRATOR_URL}/processes/restart`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ ...params, sync_mode: true }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to restart process (${response.status})`)
  }
  return response.json()
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
    const response = await fetch(
      `${ORCHESTRATOR_URL}/processes/health?user_id=${encodeURIComponent(userId)}&port=${port}`,
      { headers: getAuthHeaders() },
    )
    if (!response.ok) return false
    const data = await response.json()
    return data.ready === true
  } catch {
    return false
  }
}

/**
 * Fetch a short-lived preview token scoped to a specific port.
 * Requires the main JWT (sent via Authorization header).
 */
export async function fetchPreviewToken(userId: string, port: number): Promise<string> {
  const response = await fetch(
    `${ORCHESTRATOR_URL}/preview/token?user_id=${encodeURIComponent(userId)}&port=${port}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json', ...getAuthHeaders() } },
  )
  if (!response.ok) throw new Error('Failed to get preview token')
  const data = await response.json()
  return data.token
}

/**
 * Build preview URL using a scoped preview token (not the main JWT).
 */
export function getPreviewUrl(userId: string, port: number, token: string, path?: string): string {
  const base = `${ORCHESTRATOR_DIRECT_URL}/preview/${userId}/${port}/${path || ''}`
  return `${base}?token=${encodeURIComponent(token)}`
}
