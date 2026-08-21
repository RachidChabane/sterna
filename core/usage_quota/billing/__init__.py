"""
Billing Package - Centralized billing for all billable operations.

This package provides:
- BillableOperation: Standard dataclass for all billable operations
- BillingService: Central entry point for quota checks and usage recording
- @billable decorator: Easy integration for any billable function
"""

from usage_quota.billing.operations import BillableOperation, QuotaStatus
from usage_quota.billing.service import BillingService, get_billing_service
from usage_quota.billing.decorators import billable, billable_async

# Re-export types from models for convenience
from usage_quota.models import ServiceType, FeatureType

__all__ = [
    'BillableOperation',
    'QuotaStatus',
    'BillingService',
    'get_billing_service',
    'billable',
    'billable_async',
    'ServiceType',
    'FeatureType',
]
