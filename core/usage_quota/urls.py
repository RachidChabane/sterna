"""URL configuration for Usage & Quota API."""

from django.urls import path

from . import views

app_name = 'usage_quota'

urlpatterns = [
    # User-facing endpoints
    path('usage/quota/', views.get_quota, name='quota'),
    path('usage/summary/', views.get_usage_summary, name='usage-summary'),
    path('usage/history/', views.get_usage_history, name='usage-history'),

    # Feature access check
    path('usage/feature/<str:feature_name>/', views.check_feature_access, name='feature-access'),

    # Feature release stages
    path('feature-flags/', views.get_feature_flags, name='feature-flags'),

    # Subscription tier + per-feature usage (task 9)
    path('subscription/plan/', views.get_subscription_plan, name='subscription-plan'),
    path('subscription/usage/', views.get_subscription_usage, name='subscription-usage'),

    # Stripe Checkout + Customer Portal (task 12)
    path('billing/checkout-session/', views.create_checkout_session,
         name='billing-checkout-session'),
    path('billing/portal-session/', views.create_portal_session,
         name='billing-portal-session'),
    path('billing/sync-from-session/', views.sync_from_session,
         name='billing-sync-from-session'),
    path('billing/status/', views.get_billing_status, name='billing-status'),

    # Stripe webhook (task 13) — unauthenticated; signature-verified.
    path('billing/webhook/', views.stripe_webhook, name='billing-webhook'),

    # Invoice history (task 14) — user-scoped list of Stripe invoices.
    path('billing/invoices/', views.invoices_list, name='billing-invoices'),

    # Internal endpoints (for service-to-service communication)
    path('quota/check/', views.check_quota, name='quota-check'),
    path('quota/deduct/', views.deduct_usage, name='quota-deduct'),
]
