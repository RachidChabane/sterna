/**
 * Model Name Utilities
 *
 * Display name mappings for models and fallback formatting.
 * Used for inline tool results where backend doesn't provide display names.
 */

/**
 * Display name mappings for known models.
 * These are used for tool execution results where the backend
 * doesn't provide a display_name field.
 */
const MODEL_DISPLAY_NAMES: Record<string, string> = {
  // Image generation models - Nano Banana branding
  'google/gemini-2.5-flash-image': 'Nano Banana',
  'google/gemini-3-pro-image-preview': 'Nano Banana Pro',
  'gemini-2.5-flash-image': 'Nano Banana',
  'gemini-3-pro-image-preview': 'Nano Banana Pro',
}

/**
 * Format a model ID into a human-readable name.
 * Checks explicit mappings first, then falls back to formatting.
 *
 * Examples:
 * - "google/gemini-2.5-flash-image" -> "Nano Banana"
 * - "openai/dall-e-3" -> "Dall E 3"
 * - "runway/gen4-turbo" -> "Gen4 Turbo"
 */
export function formatModelId(modelId: string | null | undefined): string {
  if (!modelId) return 'Unknown'

  // Check explicit mappings first
  if (MODEL_DISPLAY_NAMES[modelId]) {
    return MODEL_DISPLAY_NAMES[modelId]
  }

  // Normalize: strip "openrouter/" prefix if present (legacy data)
  let normalizedId = modelId
  if (normalizedId.startsWith('openrouter/')) {
    normalizedId = normalizedId.slice('openrouter/'.length)
  }

  // Check mapping for normalized ID
  if (MODEL_DISPLAY_NAMES[normalizedId]) {
    return MODEL_DISPLAY_NAMES[normalizedId]
  }

  // Extract the model name (after the last /)
  const name = normalizedId.split('/').pop() || normalizedId

  // Check mapping for just the model name part
  if (MODEL_DISPLAY_NAMES[name]) {
    return MODEL_DISPLAY_NAMES[name]
  }

  // Format: replace dashes/underscores with spaces, then title case
  return name
    .replace(/-/g, ' ')
    .replace(/_/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}
