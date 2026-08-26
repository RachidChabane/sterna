import axios from 'axios'
import { getAccessToken, getRefreshToken, setTokens, handleUnauthorized } from './client'

/**
 * Fetch-based transport for endpoints the central axios client (`./client`)
 * cannot serve without losing information it needs: Server-Sent Event
 * streams consumed via `response.body.getReader()`, and binary media (TTS
 * audio, file downloads, cached avatars) consumed as a Blob or ArrayBuffer.
 * Both need the raw `Response`, not axios's parsed body, so they share this
 * thin fetch-with-auth wrapper instead of duplicating token injection and
 * 401 handling at every call site.
 */

export interface FetchStreamOptions extends RequestInit {
  /**
   * Attach the bearer access token, and retry once via the refresh-token
   * flow on a 401. Defaults to true.
   *
   * Set to false for a URL this app does not issue the request to on its
   * own authority — a presigned storage URL, or a third-party avatar/icon
   * CDN — where our Authorization header is either meaningless or, for a
   * presigned URL, can invalidate the request signature.
   */
  auth?: boolean
}

/**
 * Fetch that returns the raw `Response` for the caller to read as a stream
 * or a blob. With `auth` (the default), it attaches the current bearer
 * token and, on a 401, retries exactly once through the same refresh-token
 * flow the axios client's response interceptor uses, falling through to the
 * same centralized session-expired handling on failure.
 */
export async function fetchStream(url: string, options: FetchStreamOptions = {}): Promise<Response> {
  const { auth = true, ...init } = options

  if (!auth) {
    return fetch(url, init)
  }

  return fetchWithAuth(url, init)
}

async function fetchWithAuth(url: string, init: RequestInit, isRetry = false): Promise<Response> {
  const accessToken = getAccessToken()
  const response = await fetch(url, {
    ...init,
    headers: {
      ...init.headers,
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  })

  if (response.status === 401 && !isRetry) {
    const refreshToken = getRefreshToken()
    if (refreshToken) {
      try {
        const refreshResponse = await axios.post('/api/auth/token/refresh/', {
          refresh_token: refreshToken,
        })
        const access = refreshResponse.data.access || refreshResponse.data.access_token
        // Backend rotates the refresh token on each use; fall back to the
        // presented token only if the response omits it
        const refresh = refreshResponse.data.refresh || refreshResponse.data.refresh_token || refreshToken
        setTokens(access, refresh)

        return fetchWithAuth(url, init, true)
      } catch {
        handleUnauthorized()
        throw new Error('Session expired. Please sign in again.')
      }
    }

    handleUnauthorized()
    throw new Error('Session expired. Please sign in again.')
  }

  return response
}
