// Secure API Key Service
// API keys are never stored client-side, only sent to server for validation
// Server responds with a session token that is used for subsequent requests

import apiClient from '@/api/client';

interface ValidateApiKeyResponse {
  valid: boolean;
  message?: string;
  sessionToken?: string;
}

export class ApiKeyService {
  private static SESSION_TOKEN_KEY = 'session_token';

  /**
   * Validates and configures an API key on the server
   * Returns a session token if successful
   */
  static async configureApiKey(apiKey: string): Promise<ValidateApiKeyResponse> {
    try {
      const response = await apiClient.post<ValidateApiKeyResponse>('/api/auth/configure-api-key', {
        apiKey
      });

      if (response.data.valid && response.data.sessionToken) {
        // Store session token in sessionStorage (not localStorage for better security)
        sessionStorage.setItem(this.SESSION_TOKEN_KEY, response.data.sessionToken);
      }

      return response.data;
    } catch (error) {
      console.error('Failed to configure API key:', error);
      return {
        valid: false,
        message: 'Failed to configure API key. Please try again.'
      };
    }
  }

  /**
   * Validates an existing session
   */
  static async validateSession(): Promise<boolean> {
    const sessionToken = sessionStorage.getItem(this.SESSION_TOKEN_KEY);

    if (!sessionToken) {
      return false;
    }

    try {
      const response = await apiClient.get<{ valid: boolean }>('/api/auth/validate-session');
      return response.data.valid;
    } catch (error) {
      console.error('Session validation failed:', error);
      return false;
    }
  }

  /**
   * Gets the current session token for authenticated requests
   */
  static getSessionToken(): string | null {
    return sessionStorage.getItem(this.SESSION_TOKEN_KEY);
  }

  /**
   * Clears the session
   */
  static clearSession(): void {
    sessionStorage.removeItem(this.SESSION_TOKEN_KEY);
  }

  /**
   * Check if a session exists
   */
  static hasSession(): boolean {
    return !!sessionStorage.getItem(this.SESSION_TOKEN_KEY);
  }
}