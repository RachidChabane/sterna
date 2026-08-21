/**
 * User-friendly error message utilities
 *
 * Converts technical errors into user-friendly messages while preserving
 * technical details in console logs for debugging.
 */

/**
 * Convertit une erreur technique en message user-friendly
 *
 * @param error - L'erreur brute (Error, string, unknown)
 * @returns Message user-friendly sans détails techniques
 */
export function getUserFriendlyErrorMessage(error: unknown): string {
  // Convert error to string for pattern matching
  const errorStr = String(error).toLowerCase()

  // Never expose internal service URLs or provider names
  if (errorStr.includes('openrouter') || errorStr.includes('api/v1/chat/completions')) {
    if (errorStr.includes('400')) return 'Unable to process your request. Please try again.'
    if (errorStr.includes('401')) return 'Authentication error. Please check your settings.'
    if (errorStr.includes('429')) return 'Too many requests. Please wait a moment and try again.'
    return 'The AI service encountered an error. Please try again.'
  }

  // Network & HTTP errors
  if (errorStr.includes('400') || errorStr.includes('bad request')) {
    return 'Unable to process your request. Please try again.'
  }

  if (errorStr.includes('404') || errorStr.includes('not found')) {
    return 'The service is temporarily unavailable. Please try again.'
  }

  if (errorStr.includes('500') || errorStr.includes('server error') || errorStr.includes('internal server')) {
    return 'A server error occurred. Please try again later.'
  }

  if (errorStr.includes('502') || errorStr.includes('bad gateway')) {
    return 'The service is temporarily unavailable. Please try again.'
  }

  if (errorStr.includes('503') || errorStr.includes('service unavailable')) {
    return 'The service is temporarily unavailable. Please try again later.'
  }

  if (errorStr.includes('timeout') || errorStr.includes('timed out') || errorStr.includes('econnaborted')) {
    return 'The request took too long. Please try again.'
  }

  if (errorStr.includes('network') || errorStr.includes('connection') || errorStr.includes('econnrefused')) {
    return 'Connection failed. Please check your internet connection.'
  }

  // Authentication & Authorization
  if (errorStr.includes('unauthorized') || errorStr.includes('401')) {
    return 'Please sign in to continue.'
  }

  if (errorStr.includes('forbidden') || errorStr.includes('403')) {
    return 'You don\'t have permission to perform this action.'
  }

  // Rate limiting
  if (errorStr.includes('429') || errorStr.includes('rate limit') || errorStr.includes('too many requests')) {
    return 'Too many requests. Please wait a moment and try again.'
  }

  // Model-specific errors
  if (errorStr.includes('model not found') || errorStr.includes('model unavailable')) {
    return 'This model is currently unavailable. Please try a different model.'
  }

  if (errorStr.includes('context') || errorStr.includes('token limit') || errorStr.includes('too long')) {
    return 'Your message is too long. Please shorten it and try again.'
  }

  // Generic fallback
  return 'Something went wrong. Please try again.'
}

/**
 * Extrait un message user-friendly depuis une réponse API error
 *
 * @param apiError - Erreur Axios ou fetch response
 * @returns Message user-friendly
 */
export function getApiErrorMessage(apiError: any): string {
  // Try to extract user-friendly message from API response
  const userMessage = apiError?.response?.data?.error ||
                      apiError?.response?.data?.message ||
                      apiError?.message

  // If the API already returned a user-friendly message (short, no URLs, no technical jargon)
  if (userMessage && typeof userMessage === 'string' && userMessage.length < 200 &&
      !userMessage.includes('http') && !userMessage.includes('Error:') &&
      !userMessage.includes('Exception') && !userMessage.toLowerCase().includes('openrouter') &&
      !userMessage.includes('api/v1')) {
    return userMessage
  }

  // Otherwise, sanitize using our utility
  return getUserFriendlyErrorMessage(apiError)
}
