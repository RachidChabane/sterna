import apiClient from './client'
import type {
  BillingStatus,
  CheckoutSessionRequest,
  CheckoutSessionResponse,
  InvoiceListResponse,
  PortalSessionResponse,
  SyncFromSessionResponse,
} from './types'

export const billingApi = {
  createCheckoutSession: async (
    body: CheckoutSessionRequest,
  ): Promise<CheckoutSessionResponse> => {
    const response = await apiClient.post<CheckoutSessionResponse>(
      '/billing/checkout-session/',
      body,
    )
    return response.data
  },

  createPortalSession: async (): Promise<PortalSessionResponse> => {
    const response = await apiClient.post<PortalSessionResponse>(
      '/billing/portal-session/',
    )
    return response.data
  },

  syncFromSession: async (
    sessionId: string,
  ): Promise<SyncFromSessionResponse> => {
    const response = await apiClient.post<SyncFromSessionResponse>(
      `/billing/sync-from-session/?session_id=${encodeURIComponent(sessionId)}`,
    )
    return response.data
  },

  getBillingStatus: async (): Promise<BillingStatus> => {
    const response = await apiClient.get<BillingStatus>('/billing/status/')
    return response.data
  },

  listInvoices: async (): Promise<InvoiceListResponse> => {
    const response = await apiClient.get<InvoiceListResponse>(
      '/billing/invoices/',
    )
    return response.data
  },
}
