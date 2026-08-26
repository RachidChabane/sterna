/**
 * Axios client for User Preferences microservice
 *
 * Routes through API Gateway at /api/v1/preferences
 * Gateway forwards to user-preferences:8002 with path rewrite
 * Handles user preferences storage with JWT authentication
 */

import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { getAccessToken, handleUnauthorized } from '@/api/client'
import { hasErrorResponse } from '@/utils/errorMessages'

// Create axios instance for User Preferences microservice
// Routes through API Gateway: /api/v1/preferences/* -> user-preferences:8002/api/v1/preferences/*
const preferencesClient = axios.create({
  baseURL: '/api/v1',
  timeout: 10000, // 10 seconds
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor - Add auth token
preferencesClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Add auth token to request if available
    const accessToken = getAccessToken()
    
    

    if (accessToken) {
      
      config.headers.Authorization = `Bearer ${accessToken}`
    } else {
      console.warn('[PreferencesClient] No access token found in localStorage')
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor - Handle errors
preferencesClient.interceptors.response.use(
  (response) => {
    
    return response
  },
  async (error: AxiosError) => {
    // Don't log 404 errors - they're expected for preferences that don't exist yet
    if (error.response?.status === 404) {
      return Promise.reject(error)
    }

    // Log other errors for debugging
    console.error('[Preferences API Error]', {
      url: error.config?.url,
      method: error.config?.method?.toUpperCase(),
      status: error.response?.status,
      statusText: error.response?.statusText,
      data: error.response?.data,
      headers: error.response?.headers,
      sentHeaders: error.config?.headers,
    })

    // Additional context for 403 errors
    if (error.response?.status === 403) {
      console.error('[PreferencesClient] 403 Forbidden - Possible causes:')
      console.error('  1. JWT_SECRET_KEY mismatch between Django and user-preferences service')
      console.error('  2. Token is expired or invalid')
      console.error('  3. User does not exist in user-preferences database')
      console.error('  4. Token was sent:', !!error.config?.headers?.Authorization)
    }

    // Handle 401 errors - show session expired modal
    if (error.response?.status === 401) {
      console.error('[PreferencesClient] 401 Unauthorized - token may be invalid or expired')
      handleUnauthorized()
    }

    return Promise.reject(error)
  }
)

/**
 * Preference types
 */
export interface Preference {
  preference_key: string
  preference_value: unknown
  category?: string
  created_at?: string
  updated_at?: string
}

export interface PreferenceListResponse {
  preferences: Record<string, unknown>
  count: number
}

/**
 * API Methods
 */
export const preferencesApi = {
  /**
   * Get all preferences for the authenticated user
   */
  async getAllPreferences(category?: string): Promise<PreferenceListResponse> {
    const params = category ? { category } : {}
    const response = await preferencesClient.get<PreferenceListResponse>('/preferences', {
      params,
    })
    return response.data
  },

  /**
   * Get a specific preference by key
   * Returns null if preference doesn't exist (404)
   */
  async getPreference(key: string): Promise<Preference | null> {
    try {
      const response = await preferencesClient.get<Preference>(`/preferences/${key}`)
      return response.data
    } catch (error) {
      // Return null for 404 (preference not found) - this is expected for new preferences
      if (hasErrorResponse(error) && error.response?.status === 404) {
        return null
      }
      throw error
    }
  },

  /**
   * Update or create a preference
   */
  async updatePreference(
    key: string,
    value: unknown,
    category?: string
  ): Promise<Preference> {
    const response = await preferencesClient.put<Preference>(`/preferences/${key}`, {
      preference_value: value,
      category,
    })
    return response.data
  },

  /**
   * Bulk update multiple preferences
   */
  async bulkUpdatePreferences(
    preferences: Record<string, any>
  ): Promise<PreferenceListResponse> {
    const response = await preferencesClient.put<PreferenceListResponse>('/preferences', {
      preferences,
    })
    return response.data
  },

  /**
   * Delete a preference
   */
  async deletePreference(key: string): Promise<void> {
    await preferencesClient.delete(`/preferences/${key}`)
  },
}
