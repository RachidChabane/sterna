/**
 * User-friendly error message utilities
 *
 * Converts technical errors into user-friendly messages while preserving
 * technical details in console logs for debugging.
 */
/** Shape of the JSON body the backend returns alongside 4xx/5xx responses. */
interface ApiErrorPayload {
  error?: string
  detail?: string
  message?: string
}

/**
 * True for anything shaped like an axios error's `{ response: { data, status } }`
 * wrapper. Checked structurally (an object with a `response` property) rather
 * than with axios's own `isAxiosError` brand check, which only recognizes real
 * `AxiosError` instances: a plain object built to look like one — the common
 * shortcut in tests that reject a mocked call with `{ response: { data } }` —
 * carries the same shape without the brand, and callers need both to work.
 */
export function hasErrorResponse(error: unknown): error is { response?: { data?: unknown; status?: number } } {
  return typeof error === 'object' && error !== null && 'response' in error
}

function firstStringField(payload: ApiErrorPayload | undefined, ...keys: (keyof ApiErrorPayload)[]): string | undefined {
  for (const key of keys) {
    const value = payload?.[key]
    if (typeof value === 'string' && value.length > 0) return value
  }
  return undefined
}

/**
 * Returns the parsed JSON error body of an axios-shaped error, or undefined
 * for anything else (a non-HTTP throw, a response with no body, a network
 * error that never reached a server).
 */
export function getApiErrorData(error: unknown): ApiErrorPayload | undefined {
  if (!hasErrorResponse(error)) return undefined
  const data: unknown = error.response?.data
  return data && typeof data === 'object' ? (data as ApiErrorPayload) : undefined
}

/**
 * Extracts a display-safe message from an API call failure: the backend's
 * `error`/`detail`/`message` field when present, the caught value's own
 * message otherwise, and `fallback` only when neither yields anything.
 */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  const fromPayload = firstStringField(getApiErrorData(error), 'error', 'detail', 'message')
  if (fromPayload) return fromPayload
  return toErrorMessage(error) || fallback
}

/**
 * Extracts a display-safe message from a caught value of unknown shape.
 *
 * `catch` bindings are always `unknown` under `useUnknownInCatchVariables`;
 * this is the one place that narrows one down to a string, so call sites
 * never need to re-derive the `instanceof Error` check themselves.
 *
 * @param error - The raw value caught (Error, string, or anything else thrown)
 * @returns error.message when error is an Error, its string form otherwise
 */
export function toErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  return String(error)
}

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

