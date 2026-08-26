/**
 * Pure message-level actions used by ImmersiveChatView: clipboard copy,
 * plain-text/JSON export, and cost/latency formatting. None of these close
 * over component state, so they are plain module functions rather than
 * hooks — a stable reference by construction, no memoization needed.
 */
import { toast } from 'sonner'
import { formatLatencyFromSeconds } from '@/utils/latency'
import { extractTextFromContent } from '@/utils/chatUtils'
import type { Message } from './types'

export function formatCost(cost?: number): string {
  if (!cost || cost === 0) return '$0.00'
  if (cost < 0.01) return '<$0.01'
  return `$${cost.toFixed(4)}`
}

export function formatLatency(latency?: number): string {
  return formatLatencyFromSeconds(latency)
}

export function copyMessageContent(content: Message['content']): void {
  navigator.clipboard.writeText(extractTextFromContent(content))
  toast.success('Copied to clipboard')
}

export function copyMessageMetadata(message: Message): void {
  navigator.clipboard.writeText(JSON.stringify(message, null, 2))
  toast.success('Metadata copied to clipboard')
}

export function exportMessageContent(content: Message['content'], model?: string): void {
  const blob = new Blob([extractTextFromContent(content)], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `message-${Date.now()}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

export function exportMessageMetadata(message: Message): void {
  const blob = new Blob([JSON.stringify(message, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `message-metadata-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}
