"""
Google Maps place-photo proxy: quota check, upstream fetch, and billing.
"""

import logging
import os

import httpx as httpx_sync
from rest_framework import status

logger = logging.getLogger(__name__)

GOOGLE_MAPS_SERVICE_URL = os.environ.get("GOOGLE_MAPS_SERVICE_URL", "http://google-maps:8005")


def fetch_place_photo(user, payload: dict):
    """Quota-check, proxy to the Google Maps service, and bill on success.

    `payload` is the already-whitelisted request body. Returns
    `(body, status_code)` for the view to wrap in a Response.
    """
    # Pre-check quota through the same GOOGLE_MAPS metering path as the
    # chat tools (google_maps_tools._check_quota, sync flavor here).
    from usage_quota.billing.service import get_billing_service
    from usage_quota.billing.operations import BillableOperation
    from usage_quota.exceptions import (
        FeatureNotAvailableException,
        QuotaExceededException,
    )
    from usage_quota.models import FeatureType, ServiceType
    from usage_quota.services.cost_calculator import get_cost_calculator

    endpoint = "places_photo"
    try:
        estimated_cost = get_cost_calculator().calculate_google_maps_cost(endpoint)
        get_billing_service().check_quota(
            user=user,
            service=ServiceType.GOOGLE_MAPS,
            estimated_cost=estimated_cost,
            feature=FeatureType.CHAT,
            feature_name='maps_invocation',
        )
    except (FeatureNotAvailableException, QuotaExceededException) as exc:
        return {"success": False, "error": exc.code}, status.HTTP_429_TOO_MANY_REQUESTS
    except Exception:
        logger.error("[GoogleMapsProxy] quota pre-check failed", exc_info=True)

    try:
        with httpx_sync.Client(timeout=10.0) as client:
            response = client.post(
                f"{GOOGLE_MAPS_SERVICE_URL}/places/search-photo",
                json=payload
            )
        body = response.json()
        # Post-record on success only (mirrors google_maps_tools._record).
        if response.status_code == 200 and isinstance(body, dict) and body.get("success"):
            try:
                op = BillableOperation(
                    service=ServiceType.GOOGLE_MAPS,
                    feature=FeatureType.CHAT,
                    model_id=endpoint,
                    request_count=1,
                )
                get_billing_service().record_usage(
                    user, op, billing_origin='platform',
                )
            except Exception:
                logger.error(
                    "[GoogleMapsProxy] billing record_usage failed",
                    exc_info=True,
                )
        return body, response.status_code
    except httpx_sync.TimeoutException:
        return {"success": False, "error": "Request timed out. Please try again."}, 504
    except Exception as e:
        logger.error(f"[GoogleMapsProxy] Error: {e}")
        return {"success": False, "error": "An error occurred. Please try again."}, 500
