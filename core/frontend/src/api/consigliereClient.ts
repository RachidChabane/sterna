/**
 * Axios client for Consigliere microservice
 *
 * Routes through API Gateway at /api/v1/consigliere
 * Gateway forwards to consigliere:8001 with path rewrite
 */

import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { setTokens, clearTokens, getRefreshToken, handleUnauthorized } from './client'

// Create axios instance for Consigliere microservice
// Routes through API Gateway: /api/v1/consigliere -> consigliere:8001/api/consigliere
const consigliereClient = axios.create({
  baseURL: '/api/v1/consigliere',
  timeout: 180000, // 3 minutes for AI analysis operations (can take 60-120s with large conversations)
  headers: {
    'Content-Type': 'application/json',
  },
})

// Get tokens from localStorage (shared with main app)
const getAccessToken = () => localStorage.getItem('access_token')

// Request interceptor - Add auth token
consigliereClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Add auth token to request if available
    const accessToken = getAccessToken()
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor - Handle errors with token refresh
consigliereClient.interceptors.response.use(
  (response) => {
    return response
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean
    }

    // Log errors for debugging
    console.error('[Consigliere API Error]', {
      url: error.config?.url,
      status: error.response?.status,
      data: error.response?.data,
    })

    // Handle 401 errors - try to refresh token
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      // If we have a refresh token, try to refresh
      const refreshToken = getRefreshToken()
      if (refreshToken) {
        try {
          // Call main backend's auth refresh endpoint
          const response = await axios.post('/api/auth/token/refresh/', {
            refresh_token: refreshToken,
          })

          const access = response.data.access || response.data.access_token
          const refresh = response.data.refresh || response.data.refresh_token || refreshToken
          setTokens(access, refresh)

          // Retry original request with new token
          originalRequest.headers.Authorization = `Bearer ${access}`
          return consigliereClient(originalRequest)
        } catch {
          // Refresh failed - show session expired modal
          handleUnauthorized()
        }
      } else {
        // No refresh token - show session expired modal
        handleUnauthorized()
      }
    }

    return Promise.reject(error)
  }
)

export default consigliereClient
