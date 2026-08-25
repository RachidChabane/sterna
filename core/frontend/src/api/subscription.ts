import apiClient from './client'
import type { SubscriptionPlan, SubscriptionUsage } from './types'

export const subscriptionApi = {
  getPlan: async (): Promise<SubscriptionPlan> => {
    const response = await apiClient.get<SubscriptionPlan>('/subscription/plan/')
    return response.data
  },

  getUsage: async (): Promise<SubscriptionUsage> => {
    const response = await apiClient.get<SubscriptionUsage>('/subscription/usage/')
    return response.data
  },
}
