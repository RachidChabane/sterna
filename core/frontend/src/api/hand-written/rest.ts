/**
 * Request and response shapes maintained by hand against the API.
 *
 * Billing, usage quota, and subscription views return responses
 * without a `serializer_class`/`@extend_schema` annotation, so
 * drf-spectacular emits no schema for them and openapi-typescript has
 * nothing to generate for that whole surface. The handful of
 * authentication types below are the exception — their endpoints are
 * annotated, but the generated shape doesn't line up closely enough to
 * replace these; see the comment on each for why.
 */

// User and Authentication types

// The generated `User` schema marks `first_name`/`last_name` optional
// (`UserSerializer` re-derives them from `full_name` with
// `required=False`), which is looser than every call site here
// expects, so this shape stays hand-written.
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

// Login responses take one of two shapes depending on how the session
// was created: password login returns `access_token`/`refresh_token`/
// `token_type`/`expires_in`, while the Google/GitHub OAuth callbacks
// return `access`/`refresh`/`created`. No single generated schema
// component covers both, so this type documents the union by hand.
export interface LoginResponse {
  access: string
  refresh: string
  user: User
  // Alternative property names from some backends
  access_token?: string
  refresh_token?: string
  created?: boolean
}

// API Response types
export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// Model catalog comparison (feature-based) types. The compare action's
// OpenAPI operation is annotated with the ViewSet's default
// serializer_class (ModelCatalog, a catalog entry), not the request
// shape the view actually reads — the generated schema exists but does
// not describe this endpoint, so it is not usable here either.
export type PriorityLevel = 'off' | 'nice' | 'important' | 'critical'

export interface CatalogComparisonRequest {
  model_ids: string[]
  priorities?: {
    cost?: PriorityLevel
    context?: PriorityLevel
    capabilities?: PriorityLevel
    multimodality?: PriorityLevel
    availability?: PriorityLevel
  }
  constraints?: {
    mustSupportFunctions?: boolean
    mustSupportStructuredOutputs?: boolean
    mustSupportReasoning?: boolean
    mustSupportPromptCaching?: boolean
    mustSupportStreamCancellation?: boolean
    mustBeAvailable?: boolean
    mustBeMultimodal?: boolean
    minContextTokens?: number | null
    maxCostPer1MTokens?: number | null
  }
  costDirection?: 'lower' | 'higher'
  capabilityWeights?: Partial<{
    functions: number
    structured_outputs: number
    reasoning: number
    prompt_caching: number
    stream_cancellation: number
  }>
}

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

export interface CatalogComparisonResponse {
  scores: CatalogModelScore[]
  best_model_id: string | null
  considered: number
}

// Usage Quota types. The service/feature catalogs below are the
// superset the backend accepts; not every value appears in every
// response.
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

// Subscription tier types

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
  // `used` is null when the backend has no reliable count for the
  // feature yet.
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

// Stripe Checkout + Customer Portal
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

// Invoice history
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

// 'unknown' is a client-side default held before the consent endpoint
// has responded; the backend itself only ever returns 'EU' or
// 'non-EU' (see the generated `RegionDefaultEnum`), so this widened
// union stays hand-written to cover that local sentinel value.
export type ConsentRegionDefault = 'EU' | 'non-EU' | 'unknown'
