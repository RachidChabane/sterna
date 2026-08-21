/**
 * Model utility functions
 */

/**
 * Removes the provider prefix from a model name if present.
 *
 * Uses a two-step detection strategy:
 * 1. Try to match with the provided provider name (exact match, case insensitive)
 * 2. If no match, detect any generic "ProviderName: " pattern at the start
 *
 * Handles patterns like:
 * - "OpenAI: GPT-4" → "GPT-4"
 * - "Anthropic: Claude 3.5 Sonnet" → "Claude 3.5 Sonnet"
 * - "AionLabs: Aion-1.0" → "Aion-1.0" (even if provider in DB is "Aion")
 * - "GPT-4" → "GPT-4" (no prefix, unchanged)
 *
 * @param modelName - The full model name
 * @param provider - The provider name from database (optional)
 * @returns The model name with provider prefix removed
 */
export function removeProviderPrefix(modelName: string, provider?: string): string {
  if (!modelName) {
    return modelName
  }

  // Step 1: Try to match with the provided provider (case insensitive)
  if (provider) {
    const providerPattern = new RegExp(`^${escapeRegex(provider)}\\s*:\\s*`, 'i')
    if (providerPattern.test(modelName)) {
      return modelName.replace(providerPattern, '').trim()
    }
  }

  // Step 2: Fallback - detect any generic provider prefix pattern
  // Pattern: starts with a letter (capital or lowercase), followed by letters/digits/spaces/hyphens/dots/underscores, then ": "
  const genericPattern = /^[A-Za-z][a-zA-Z0-9\s.\-_]*:\s+/
  if (genericPattern.test(modelName)) {
    return modelName.replace(genericPattern, '').trim()
  }

  return modelName
}

/**
 * Escapes special regex characters in a string
 */
function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Check if a model is "new" (first seen within the last 48 hours).
 * Computes this client-side based on first_seen_at timestamp to avoid
 * stale cached values from the server.
 *
 * @param firstSeenAt - ISO timestamp string of when model was first seen
 * @returns true if model was first seen within last 48 hours
 */
export function isModelNew(firstSeenAt?: string | null): boolean {
  if (!firstSeenAt) {
    return false
  }

  const firstSeenDate = new Date(firstSeenAt)
  const now = new Date()
  const hoursDiff = (now.getTime() - firstSeenDate.getTime()) / (1000 * 60 * 60)

  return hoursDiff < 48
}
