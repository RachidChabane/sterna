import type { Attachment } from '@/components/models/types'

// Simple character-based token approximation
export function approximateTokenCount(text: string): number {
  if (!text) return 0
  // Heuristic: ~4 characters per token
  return Math.max(0, Math.ceil(text.length / 4))
}

// Return concatenated text from text/code file attachments
export function buildTextFromTextAttachments(attachments: Attachment[]): string {
  const files = attachments.filter(a => a.type === 'file' && (a as any).textContent) as any[]
  if (files.length === 0) return ''
  return files
    .map(f => `\n\n--- Fichier attaché: ${f.file.name} ---\n${f.textContent}\n--- Fin du fichier ---`)
    .join('')
}

// Compute available completion capacity (tokens) given model max tokens and prompt tokens
export function computeAvailableCompletionCap(modelMaxTokens: number, promptTokens: number, safetyReserve: number = 32): number {
  const cap = Math.floor(modelMaxTokens - promptTokens - safetyReserve)
  return Math.max(0, cap)
}

export interface CompletionEstimateOptions {
  typedWeight?: number   // Weight factor for typed text tokens
  filesWeight?: number   // Weight factor for file-derived tokens
  minIfTypedSmall?: number // Minimum completion tokens when typed input is very short
  minIfTypedPresent?: number // Minimum completion tokens when typed input present
}

const DEFAULT_OPTIONS: CompletionEstimateOptions = {
  typedWeight: 1.3,
  filesWeight: 0.25,
  minIfTypedSmall: 50,
  minIfTypedPresent: 100,
}

// Estimate completion tokens from typed/file tokens and cap by available capacity
export function estimateCompletionTokens(
  typedText: string,
  filesText: string,
  availableCap: number,
  opts: CompletionEstimateOptions = {}
): { typedTokens: number; fileTokens: number; promptTokens: number; completionTokens: number } {
  const options = { ...DEFAULT_OPTIONS, ...opts }
  const typedTokens = approximateTokenCount(typedText)
  const fileTokens = approximateTokenCount(filesText)
  const promptTokens = typedTokens + fileTokens

  // Weighted base estimate: typed drives length; files contribute modestly
  const weighted = Math.ceil(typedTokens * options.typedWeight! + fileTokens * options.filesWeight!)
  // Minimums
  const hasTyped = typedTokens > 0
  const minFloor = hasTyped
    ? (typedTokens < 20 ? options.minIfTypedSmall! : options.minIfTypedPresent!)
    : 32 // tiny default if no typed text (pure attachments)

  const unclamped = Math.max(weighted, minFloor)
  const completionTokens = Math.max(0, Math.min(unclamped, availableCap))
  return { typedTokens, fileTokens, promptTokens, completionTokens }
}

