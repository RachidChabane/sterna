/**
 * Utility functions for provider icon management in the frontend.
 *
 * Performance optimized: Uses CDN URLs for rare providers that have no
 * locally vendored icon (see `lib/provider-icons.tsx` for the bundled set).
 */

/**
 * Normalize provider name for display.
 *
 * @param provider - The provider name
 * @returns Capitalized provider name
 *
 * @example
 * normalizeProviderName('openai') // 'OpenAI'
 * normalizeProviderName('meta-llama') // 'Meta-Llama'
 */
export function normalizeProviderName(provider: string): string {
  if (!provider) return 'Unknown'

  // Special cases for common providers
  const specialCases: Record<string, string> = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    google: 'Google',
    meta: 'Meta',
    'meta-llama': 'Meta',
    mistralai: 'Mistral',
    mistral: 'Mistral',
    cohere: 'Cohere',
    groq: 'Groq',
    perplexity: 'Perplexity',
    deepseek: 'DeepSeek',
    'x-ai': 'xAI',
  }

  const normalized = provider.toLowerCase()
  if (specialCases[normalized]) {
    return specialCases[normalized]
  }

  // Default: capitalize first letter of each word
  return provider
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}
