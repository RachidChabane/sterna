/**
 * Re-exports for the hand-written REST types under
 * ./hand-written/rest — kept at this path so existing imports do not
 * need to change. See that module's docstring for scope.
 */
export type {
  User,
  LoginRequest,
  LoginResponse,
  RegisterRequest,
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
  ConsentCategories,
  ConsentRecord,
  ConsentRegionDefault,
  ConsentResponse,
  ConsentSaveRequest,
} from './hand-written/rest'
