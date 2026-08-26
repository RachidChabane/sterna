import { create } from 'zustand'
import { usageQuotaApi } from '@/api/endpoints'
import { getApiErrorMessage } from '@/utils/errorMessages'
import type { QuotaInfo, UsageSummary, UsageLogEntry, PaginatedResponse } from '@/api/types'

interface UsageQuotaState {
  // Data
  quota: QuotaInfo | null
  summary: UsageSummary | null
  history: UsageLogEntry[]
  historyPagination: {
    count: number
    page: number
    pageSize: number
    hasMore: boolean
  }

  // Loading states
  isLoadingQuota: boolean
  isLoadingSummary: boolean
  isLoadingHistory: boolean

  // Error states
  quotaError: string | null
  summaryError: string | null
  historyError: string | null

  // Actions
  fetchQuota: () => Promise<void>
  fetchSummary: (days?: number) => Promise<void>
  fetchHistory: (params?: { page?: number; service?: string; feature?: string }) => Promise<void>
  loadMoreHistory: () => Promise<void>
  clearErrors: () => void
  reset: () => void
  // New: refresh quota status (call after message sends)
  refreshAfterUsage: () => Promise<void>
  // New: check if quota is low (warning threshold)
  isQuotaLow: () => boolean
}

const DEFAULT_PAGE_SIZE = 20

export const useUsageQuotaStore = create<UsageQuotaState>()((set, get) => ({
  // Initial state
  quota: null,
  summary: null,
  history: [],
  historyPagination: {
    count: 0,
    page: 1,
    pageSize: DEFAULT_PAGE_SIZE,
    hasMore: false,
  },
  isLoadingQuota: false,
  isLoadingSummary: false,
  isLoadingHistory: false,
  quotaError: null,
  summaryError: null,
  historyError: null,

  fetchQuota: async () => {
    set({ isLoadingQuota: true, quotaError: null })
    try {
      const response = await usageQuotaApi.getQuota()
      set({ quota: response.data, isLoadingQuota: false })
    } catch (error) {
      const message = getApiErrorMessage(error, 'Failed to fetch quota')
      set({ quotaError: message, isLoadingQuota: false })
    }
  },

  fetchSummary: async (days = 7) => {
    set({ isLoadingSummary: true, summaryError: null })
    try {
      const response = await usageQuotaApi.getSummary({ days })
      set({ summary: response.data, isLoadingSummary: false })
    } catch (error) {
      const message = getApiErrorMessage(error, 'Failed to fetch summary')
      set({ summaryError: message, isLoadingSummary: false })
    }
  },

  fetchHistory: async (params = {}) => {
    set({ isLoadingHistory: true, historyError: null })
    try {
      const { page = 1, service, feature } = params
      const response = await usageQuotaApi.getHistory({
        page,
        page_size: DEFAULT_PAGE_SIZE,
        service,
        feature,
      })
      const data = response.data as PaginatedResponse<UsageLogEntry>
      set({
        history: data.results,
        historyPagination: {
          count: data.count,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
          hasMore: data.next !== null,
        },
        isLoadingHistory: false,
      })
    } catch (error) {
      const message = getApiErrorMessage(error, 'Failed to fetch history')
      set({ historyError: message, isLoadingHistory: false })
    }
  },

  loadMoreHistory: async () => {
    const { historyPagination, isLoadingHistory } = get()
    if (isLoadingHistory || !historyPagination.hasMore) return

    set({ isLoadingHistory: true, historyError: null })
    try {
      const nextPage = historyPagination.page + 1
      const response = await usageQuotaApi.getHistory({
        page: nextPage,
        page_size: DEFAULT_PAGE_SIZE,
      })
      const data = response.data as PaginatedResponse<UsageLogEntry>
      set((state) => ({
        history: [...state.history, ...data.results],
        historyPagination: {
          count: data.count,
          page: nextPage,
          pageSize: DEFAULT_PAGE_SIZE,
          hasMore: data.next !== null,
        },
        isLoadingHistory: false,
      }))
    } catch (error) {
      const message = getApiErrorMessage(error, 'Failed to load more history')
      set({ historyError: message, isLoadingHistory: false })
    }
  },

  clearErrors: () => {
    set({ quotaError: null, summaryError: null, historyError: null })
  },

  reset: () => {
    set({
      quota: null,
      summary: null,
      history: [],
      historyPagination: {
        count: 0,
        page: 1,
        pageSize: DEFAULT_PAGE_SIZE,
        hasMore: false,
      },
      isLoadingQuota: false,
      isLoadingSummary: false,
      isLoadingHistory: false,
      quotaError: null,
      summaryError: null,
      historyError: null,
    })
  },

  // Refresh quota status after usage (non-blocking, silent errors)
  refreshAfterUsage: async () => {
    // Don't show loading state for background refresh
    try {
      const response = await usageQuotaApi.getQuota()
      set({ quota: response.data })
    } catch (error) {
      // Silent failure - don't interrupt user flow
      console.warn('[UsageQuotaStore] Failed to refresh quota after usage:', error)
    }
  },

  // Check if user's quota is running low (< 20% remaining)
  isQuotaLow: () => {
    const { quota } = get()
    if (!quota?.weekly) return false

    const weeklyRemaining = parseFloat(quota.weekly.remaining_usd) || 0
    const weeklyLimit = parseFloat(quota.weekly.limit_usd) || 1
    const percentRemaining = (weeklyRemaining / weeklyLimit) * 100

    return percentRemaining < 20
  },
}))
