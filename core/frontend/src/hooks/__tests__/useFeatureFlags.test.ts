import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useFeatureFlags, useFeatureFlagsStore } from '../useFeatureFlags'
import { featureFlagsApi } from '@/api/featureFlags'

vi.mock('@/api/featureFlags', () => ({
  featureFlagsApi: { get: vi.fn() },
  getReleaseStage: (features: Record<string, string>, key: string) => features[key] ?? 'ga',
}))

describe('useFeatureFlags', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useFeatureFlagsStore.setState({ flags: {}, loaded: false })
  })

  it('returns loaded=false and ga stage before fetch resolves', () => {
    vi.mocked(featureFlagsApi.get).mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useFeatureFlags())
    expect(result.current.loaded).toBe(false)
    expect(result.current.getStage('spark_deploy')).toBe('ga')
  })

  it('returns beta stage for spark_deploy after fetch resolves', async () => {
    vi.mocked(featureFlagsApi.get).mockResolvedValue({ spark_deploy: 'beta' })
    const { result } = renderHook(() => useFeatureFlags())
    await waitFor(() => expect(result.current.loaded).toBe(true))
    expect(result.current.getStage('spark_deploy')).toBe('beta')
  })

  it('defaults to ga for missing keys after fetch resolves', async () => {
    vi.mocked(featureFlagsApi.get).mockResolvedValue({})
    const { result } = renderHook(() => useFeatureFlags())
    await waitFor(() => expect(result.current.loaded).toBe(true))
    expect(result.current.getStage('unknown_feature')).toBe('ga')
  })

  it('sets loaded=true and defaults to ga on fetch error', async () => {
    vi.mocked(featureFlagsApi.get).mockRejectedValue(new Error('network'))
    const { result } = renderHook(() => useFeatureFlags())
    await waitFor(() => expect(result.current.loaded).toBe(true))
    expect(result.current.getStage('spark_deploy')).toBe('ga')
  })
})
