import apiClient from './client'

export interface SupportRequestPayload {
  email: string
  subject: string
  message: string
  context?: {
    route?: string
    browser?: string
    userAgent?: string
    plan?: string
  }
}

export interface SupportRequestResponse {
  id: string
  message: string
}

export const supportApi = {
  createRequest: (data: SupportRequestPayload) =>
    apiClient.post<SupportRequestResponse>('/support/requests/', data),
}
