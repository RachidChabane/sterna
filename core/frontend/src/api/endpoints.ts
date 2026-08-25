import apiClient from './client'
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  User,
  PaginatedResponse,
  QuotaInfo,
  UsageLogEntry,
  UsageSummary,
  ConsentResponse,
  ConsentRecord,
  ConsentSaveRequest,
} from './types'

// Authentication endpoints
export const authApi = {
  login: (data: LoginRequest) =>
    apiClient.post<LoginResponse>('/auth/login/', data),

  register: (data: RegisterRequest) =>
    apiClient.post<User>('/auth/register/', data),

  logout: () =>
    apiClient.post('/auth/logout/'),

  refresh: (refreshToken: string) =>
    apiClient.post('/auth/refresh/', { refresh: refreshToken }),

  resetPassword: (email: string) =>
    apiClient.post('/auth/password-reset/', { email }),

  verifyEmail: (token: string) =>
    apiClient.post('/auth/verify-email/', { token }),

  resendVerification: (email: string) =>
    apiClient.post('/auth/resend-verification/', { email }),

  confirmPasswordReset: (token: string, password: string, password_confirm: string) =>
    apiClient.post('/auth/password-reset/confirm/', { token, password, password_confirm }),

  // OAuth endpoints
  googleAuth: (credential: string) =>
    apiClient.post<LoginResponse>('/auth/google/', { credential }),

  googleOneTap: (credential: string) =>
    apiClient.post<LoginResponse>('/auth/google/one-tap/', { credential }),

  githubAuth: (code: string, state: string) =>
    apiClient.post<LoginResponse>('/auth/github/', { code, state }),

  requestOAuthState: () =>
    apiClient.post<{ state: string }>('/auth/oauth/state/'),

  getProfile: () =>
    apiClient.get<User>('/auth/profile/'),

  consent: {
    get: (sessionId: string) =>
      apiClient.get<ConsentResponse>('/auth/consent/', {
        params: { session_id: sessionId },
      }),
    save: (data: ConsentSaveRequest) =>
      apiClient.post<{ consent: ConsentRecord; region_default: string }>(
        '/auth/consent/',
        data,
      ),
    attach: (sessionId: string) =>
      apiClient.post<{ attached: number }>('/auth/consent/attach/', {
        session_id: sessionId,
      }),
  },
}

// OpenRouter endpoints
export const openRouterApi = {
  models: (params?: {
    page?: number;
    search?: string;
    provider?: string;
    available_only?: boolean;
    min_context_length?: number;
    supports_functions?: boolean;
    supports_streaming?: boolean;
    tags?: string[];
    sort_by?: 'none' | 'prompt_cost' | 'completion_cost' | 'overall_cost' | 'max_tokens' | 'provider';
    order?: 'asc' | 'desc';
  }) =>
    apiClient.get('/llm/models/', { params }),

  modelStats: () =>
    apiClient.get('/llm/models/stats/'),

  modelTiers: () =>
    apiClient.get('/llm/model-tiers/'),

  estimateCost: (data: { model: string; prompt_tokens: number; completion_tokens: number }) =>
    apiClient.post('/llm/estimate-cost/', data),

  compareCatalog: (data: import('./types').CatalogComparisonRequest) =>
    apiClient.post<import('./types').CatalogComparisonResponse>('/llm/models/compare/', data),
}

// Image generation model endpoints

// Usage Quota endpoints
export const usageQuotaApi = {
  getQuota: () =>
    apiClient.get<QuotaInfo>('/usage/quota/'),

  getSummary: (params?: { days?: number }) =>
    apiClient.get<UsageSummary>('/usage/summary/', { params }),

  getHistory: (params?: { page?: number; page_size?: number; service?: string; feature?: string }) =>
    apiClient.get<PaginatedResponse<UsageLogEntry>>('/usage/history/', { params }),
}
