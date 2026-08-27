/**
 * Central re-export point for REST request/response types consumed
 * across the frontend, so callers import from one stable path
 * regardless of where a type's shape actually comes from. A type
 * backed by an annotated OpenAPI operation is aliased from the
 * generated schema; one with no matching generated shape is
 * re-exported from ./hand-written/rest instead — see that module's
 * docstring for why each remaining type stays hand-written.
 */
import type { components } from './generated/schema'

export type LoginRequest = components['schemas']['Login']
export type RegisterRequest = components['schemas']['Register']
export type ConsentCategories = components['schemas']['ConsentCategories']
export type ConsentRecord = components['schemas']['ConsentRecord']
export type ConsentResponse = components['schemas']['ConsentResponse']
export type ConsentSaveRequest = components['schemas']['Consent']

export type {
  User,
  LoginResponse,
  PaginatedResponse,
  PriorityLevel,
  CatalogComparisonRequest,
  CatalogModelScore,
  CatalogComparisonResponse,
  QuotaInfo,
  UsageLogEntry,
  UsageSummary,
  PerFeatureLimits,
  SubscriptionFeatures,
  SubscriptionPlan,
  PerFeatureUsage,
  SubscriptionUsage,
  CheckoutSessionRequest,
  CheckoutSessionResponse,
  PortalSessionResponse,
  SyncFromSessionResponse,
  BillingStatus,
  Invoice,
  InvoiceListResponse,
  ConsentRegionDefault,
} from './hand-written/rest'
