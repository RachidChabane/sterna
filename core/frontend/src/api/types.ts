// User and Authentication types
export interface User {
  id: string
  email: string
  full_name?: string
  first_name: string
  last_name: string
  avatar_url?: string | null
  is_active: boolean
  is_verified: boolean
  date_joined: string
  last_login?: string | null
}

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  access: string
  refresh: string
  user: User
  // Alternative property names from some backends
  access_token?: string
  refresh_token?: string
  created?: boolean
}

export interface RegisterRequest {
  email: string
  password: string
  password_confirm?: string
  full_name?: string
  // Cloudflare Turnstile captcha token. Optional in dev (backend bypass
  // when DEBUG=True or secret unset). Required in production.
  turnstile_token?: string
}

// API Response types
export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// Model catalog comparison (feature-based) types
export type PriorityLevel = 'off' | 'nice' | 'important' | 'critical'

interface CatalogModelScoreBreakdown {
  cost: number
  context: number
  capabilities: number
  multimodality: number
  availability: number
}

export interface CatalogModelScore {
  id: string  // model_id
  name: string
  provider: string
  score: number
  score_pct: number
  breakdown: CatalogModelScoreBreakdown
  cost_per_1k: number
  context_length: number
  context_str: string
  capabilities: string[]
  is_best: boolean
}

// Usage Quota types
// extended for task 9 — backend exposes more services + features than these
// originally listed.
type ServiceType =
  | 'openrouter'
  | 'elevenlabs_tts'
  | 'openai_tts'
  | 'deepgram_stt'
  | 'brave_search'
  | 'image_generation'
  | 'video_generation'
  | 'kb_embedding'
  | 'kb_query'
  | 'code_session'
  | 'mcp_tool_invocation'
  | 'google_maps'

type FeatureType =
  | 'chat'
  | 'voice_room'
  | 'code_session'
  | 'search'
  | 'consigliere'
  | 'knowledge_base'
  | 'other'

interface QuotaWeeklyInfo {
  limit_usd: string
  used_usd: string
  remaining_usd: string
  window_start: string
  window_end: string
}

interface QuotaSessionInfo {
  limit_usd: string
  used_usd: string
  remaining_usd: string
  window_start: string
  window_end: string
}

interface ServiceUsage {
  used_usd: string
  requests?: number
  characters?: number
  minutes?: number
  tokens?: number
}

interface FeatureUsage {
  used_usd: string
}

export interface QuotaInfo {
  plan: string
  plan_display_name: string
  weekly: QuotaWeeklyInfo
  session: QuotaSessionInfo
  by_service: Record<ServiceType, ServiceUsage>
  by_feature: Record<FeatureType, FeatureUsage>
}

export interface UsageLogEntry {
  id: string
  service: ServiceType
  service_display: string
  feature: FeatureType
  feature_display: string
  model_id: string
  cost_usd: string
  timestamp: string
  details: {
    prompt_tokens?: number
    completion_tokens?: number
    character_count?: number
    audio_seconds?: number
    request_count?: number
  }
}

export interface UsageSummary {
  total_cost_usd: string
  by_service: Record<ServiceType, {
    cost_usd: string
    count: number
  }>
  by_feature: Record<FeatureType, {
    cost_usd: string
    count: number
  }>
  period: {
    start: string
    end: string
  }
}

// --- Subscription tier types (task 9) ---

export interface PerFeatureLimits {
  voice_room: number | null
  code_session: number | null
  image_gen: number | null
  video_gen: number | null
  mcp: number | null
  kb_storage_mb: number | null
  kb_docs: number | null
}

export interface SubscriptionFeatures {
  chat: boolean
  search: boolean
  voice_rooms: boolean
  code_sessions: boolean
  knowledge_base: boolean
  image_gen: boolean
  video_gen: boolean
  sparks_view: boolean
  sparks_create: boolean
  mcp: boolean
  byok: boolean
  priority_coding_agent: boolean
}

export interface SubscriptionPlan {
  name: 'free' | 'plus' | 'pro'
  display_name: string
  description: string
  weekly_limit_usd: string
  session_limit_usd: string
  features: SubscriptionFeatures
  per_feature_limits: PerFeatureLimits
  stripe_price_id_monthly: string | null
  stripe_price_id_yearly: string | null
  is_active: boolean
}

export interface PerFeatureUsage {
  // `used` is null when the backend has no reliable count yet (task 10).
  used: number | null
  used_usd: string
  // `limit` is null when the feature is unlimited.
  limit: number | null
}

export interface SubscriptionUsage {
  weekly_used_usd: string
  weekly_limit_usd: string
  weekly_window_end: string
  session_used_usd: string
  session_limit_usd: string
  session_window_end: string
  per_feature: Record<keyof PerFeatureLimits, PerFeatureUsage>
}

// Stripe Checkout + Customer Portal (task 12)
export interface CheckoutSessionRequest {
  plan_slug: 'plus' | 'pro'
  billing_cycle: 'monthly' | 'yearly'
}

export interface CheckoutSessionResponse {
  url: string
}

export interface PortalSessionResponse {
  url: string
}

export interface SyncFromSessionResponse {
  plan: 'free' | 'plus' | 'pro'
  plan_display_name: string
  status: string
  current_period_end: number | null
  cancel_at_period_end: boolean
}

export interface BillingStatus {
  plan: 'free' | 'plus' | 'pro'
  plan_display_name: string
  plan_description: string
  is_paid: boolean
  current_period_end: number | null
  cancel_at_period_end: boolean
}

// Invoice history (task 14)
export interface Invoice {
  id: string
  number: string
  created: number  // unix seconds
  total: number  // minor units
  subtotal_excl_tax: number
  tax: number
  currency: string  // lowercase ISO-4217, e.g. "eur"
  status: 'draft' | 'open' | 'paid' | 'uncollectible' | 'void'
  hosted_invoice_url: string
  invoice_pdf: string
  plan_name: string
}

export interface InvoiceListResponse {
  results: Invoice[]
}

export interface ConsentCategories {
  essential: boolean
  analytics: boolean
  marketing: boolean
}

export interface ConsentRecord {
  session_id: string
  categories: ConsentCategories
  version: string
  created_at: string
  updated_at: string
}

export type ConsentRegionDefault = 'EU' | 'non-EU' | 'unknown'

export interface ConsentResponse {
  consent: ConsentRecord | null
  region_default: ConsentRegionDefault
}

export interface ConsentSaveRequest {
  session_id: string
  categories: ConsentCategories
  version: string
}
