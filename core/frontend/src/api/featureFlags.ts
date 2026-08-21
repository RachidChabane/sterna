import apiClient from './client'

export type ReleaseStage = 'ga' | 'beta' | 'experimental' | 'preview' | 'hidden'

export interface FeatureFlagsResponse {
  features: Record<string, ReleaseStage>
}

export const featureFlagsApi = {
  async get(): Promise<Record<string, ReleaseStage>> {
    const response = await apiClient.get<FeatureFlagsResponse>('/feature-flags/')
    return response.data.features
  },
}

export function getReleaseStage(
  features: Record<string, ReleaseStage>,
  key: string
): ReleaseStage {
  return features[key] ?? 'ga'
}
