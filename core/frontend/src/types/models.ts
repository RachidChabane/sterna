/**
 * Model-related types for OpenRouter model selection
 */

export interface ModelCatalogEntry {
  id: string
  model_id: string
  name: string
  provider: string
  provider_icon_slug?: string
  provider_icon_url?: string
  model_icon_slug?: string
  model_icon_url?: string
  cost_per_1m_prompt: number
  cost_per_1m_completion: number
  max_tokens: number
  supports_streaming: boolean
  supports_functions: boolean
  supports_structured_outputs: boolean
  supports_reasoning: boolean
  supports_prompt_caching: boolean
  supports_stream_cancellation: boolean
  modality: string | null
  input_modalities: string[]
  output_modalities: string[]
  tokenizer: string | null
  max_completion_tokens: number | null
  is_moderated: boolean
  default_parameters: Record<string, any>
  description?: string
  tags: string[]
  is_available: boolean
  is_new?: boolean              // True if model was first seen within 48h
  first_seen_at?: string | null // ISO timestamp of when model was first seen
  fetched_at: string
  // Performance stats (from OpenRouter)
  latency_p50?: number | null   // Median latency (time-to-first-token) in milliseconds
  latency_p90?: number | null   // 90th percentile latency in milliseconds
  throughput_p50?: number | null // Median throughput in tokens per second
  throughput_p90?: number | null // 90th percentile throughput in tokens per second
  stats_updated_at?: string | null // When performance stats were last updated
}

export interface ModelFilter {
  search?: string
  provider?: string
  capabilities?: {
    streaming?: boolean
    functions?: boolean
    structured_outputs?: boolean
    reasoning?: boolean
    prompt_caching?: boolean
    stream_cancellation?: boolean
  }
  modality?: string
  input_modalities?: string[]  // For filtering by vision, audio, etc.
  priceRange?: {
    min: number
    max: number
  }
  tags?: string[]
  minContextLength?: number
  availableOnly?: boolean
  sortBy?: 'none' | 'prompt_cost' | 'completion_cost' | 'overall_cost' | 'max_tokens' | 'provider' | 'latency' | 'throughput'
  order?: 'asc' | 'desc'
}

export interface ModelFavorite {
  model_id: string
  added_at: string
  notes?: string
  details?: ModelCatalogEntry  // Store complete model details for quick access
}

export interface RecentModel {
  model_id: string
  used_at: string
  usage_count: number
  details?: ModelCatalogEntry  // Store complete model details for quick access
}


