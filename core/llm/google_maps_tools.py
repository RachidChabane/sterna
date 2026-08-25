"""
Google Maps LangChain Tools

Provides LangChain tools for all Google Maps APIs via the google-maps service.
"""

from langchain_core.tools import tool
from pydantic import BaseModel, Field
import httpx
import json
import logging
from contextvars import ContextVar
from typing import Optional, Literal, Dict

logger = logging.getLogger(__name__)

GOOGLE_MAPS_SERVICE_URL = "http://google-maps:8005"

# Per-task user context, set by `agent_service.request_context` before tool invocation.
# Mirrors the Brave Search pattern at `brave_search_tools.py`.
GOOGLE_MAPS_USER_CONTEXT: ContextVar[Optional[Dict[str, str]]] = ContextVar(
    "google_maps_user_context", default=None
)


async def call_google_maps_service(endpoint: str, payload: dict) -> str:
    """Call Google Maps service and return JSON response."""
    url = f"{GOOGLE_MAPS_SERVICE_URL}/{endpoint}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            logger.info(f"[GoogleMapsTool] Calling {endpoint}")
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return json.dumps(data, ensure_ascii=False)

        except httpx.HTTPStatusError as e:
            logger.error(f"[GoogleMapsTool] HTTP error {e.response.status_code}: {e.response.text}")
            return json.dumps({
                "success": False,
                "error": f"Service error: {e.response.text}"
            })
        except httpx.RequestError as e:
            logger.error(f"[GoogleMapsTool] Request error: {str(e)}")
            return json.dumps({
                "success": False,
                "error": f"Connection failed: {str(e)}"
            })


# ============================================================================
# QUOTA HELPERS
# ============================================================================
# Distinct from MCP's `_resolve_user_by_id(user_id)` — Google Maps reads from
# a per-task ContextVar (set by `agent_service.request_context` before tool dispatch).
# Each module owns its own helper because the resolution signatures differ.


async def _resolve_user():
    ctx = GOOGLE_MAPS_USER_CONTEXT.get()
    if not ctx or not ctx.get("user_id"):
        return None
    from asgiref.sync import sync_to_async
    try:
        from authentication.models import User
    except ImportError:
        from django.contrib.auth import get_user_model
        User = get_user_model()
    try:
        return await sync_to_async(User.objects.get)(id=ctx["user_id"])
    except Exception:
        return None


async def _check_quota(user, endpoint: str):
    """Pre-call quota check. Returns None when allowed, an error string when denied."""
    if not user:
        return None
    try:
        from asgiref.sync import sync_to_async
        from usage_quota.billing.service import get_billing_service
        from usage_quota.exceptions import (
            FeatureNotAvailableException,
            QuotaExceededException,
        )
        from usage_quota.models import FeatureType, ServiceType
        from usage_quota.services.cost_calculator import get_cost_calculator
        # Cost lookup hits the DB (ServicePricing) — must be wrapped for
        # async context or SynchronousOnlyOperation kills the pre-check
        # silently (fail-open).
        cost = await sync_to_async(
            get_cost_calculator().calculate_google_maps_cost
        )(endpoint)
        try:
            await sync_to_async(get_billing_service().check_quota)(
                user=user,
                service=ServiceType.GOOGLE_MAPS,
                estimated_cost=cost,
                feature=FeatureType.CHAT,
                feature_name='maps_invocation',
            )
        except (FeatureNotAvailableException, QuotaExceededException) as exc:
            return f"{exc.code} ({exc.message})"
        return None
    except Exception:
        logger.error("[GoogleMapsTool] quota pre-check failed", exc_info=True)
        return None


async def _record(user, endpoint: str):
    if not user:
        return
    try:
        from asgiref.sync import sync_to_async
        from usage_quota.billing.service import get_billing_service
        from usage_quota.billing.operations import BillableOperation
        from usage_quota.models import ServiceType, FeatureType
        op = BillableOperation(
            service=ServiceType.GOOGLE_MAPS,
            feature=FeatureType.CHAT,
            model_id=endpoint,
            request_count=1,
        )
        # Google Maps is always platform-billed (platform-owned API key);
        # route through BillingService so the guard catches accidental BYOK.
        await sync_to_async(get_billing_service().record_usage)(
            user, op, billing_origin='platform',
        )
    except Exception:
        logger.error("[GoogleMapsTool] billing record_usage failed", exc_info=True)


async def _invoke(endpoint: str, service_path: str, payload: dict) -> str:
    """Pre-check quota, call upstream, post-record on success."""
    user = await _resolve_user()
    err = await _check_quota(user, endpoint)
    if err:
        return json.dumps({"success": False, "error": err})
    result = await call_google_maps_service(service_path, payload)
    try:
        parsed = json.loads(result)
    except Exception:
        parsed = {}
    if parsed.get("success"):
        await _record(user, endpoint)
    return result


# ============================================================================
# TOOL INPUT SCHEMAS
# ============================================================================

class GeocodingInput(BaseModel):
    """Input for geocoding tool."""
    address: str = Field(..., description="Address to convert to GPS coordinates")


class DirectionsInput(BaseModel):
    """Input for directions tool."""
    origin: str = Field(..., description="Starting location (address or 'lat,lng')")
    destination: str = Field(..., description="Destination (address or 'lat,lng')")
    mode: Optional[Literal["driving", "walking", "bicycling", "transit"]] = Field(
        "driving",
        description="Travel mode"
    )


class PlaceSearchInput(BaseModel):
    """Input for nearby place search."""
    location: str = Field(..., description="Search location as 'latitude,longitude'")
    radius: Optional[int] = Field(1500, description="Search radius in meters")
    place_type: Optional[str] = Field(None, description="Place type (restaurant, cafe, museum, etc)")
    keyword: Optional[str] = Field(None, description="Search keyword")


class AirQualityInput(BaseModel):
    """Input for air quality tool."""
    location: str = Field(..., description="Location as 'latitude,longitude'")


class StreetViewInput(BaseModel):
    """Input for street view tool."""
    location: str = Field(..., description="Location as 'latitude,longitude'")


class PlaceDetailsInput(BaseModel):
    """Input for place details tool."""
    place_id: str = Field(..., description="Google Place ID (from search_nearby_places results)")


# ============================================================================
# LANGCHAIN TOOLS
# ============================================================================

@tool("geocode_address", args_schema=GeocodingInput)
async def geocode_address(address: str) -> str:
    """Convert address to GPS coordinates."""
    payload = {"address": address, "language": "en"}
    return await _invoke("geocoding", "geocoding/forward", payload)


@tool("get_directions", args_schema=DirectionsInput)
async def get_directions(
    origin: str,
    destination: str,
    mode: str = "driving"
) -> str:
    """Route directions with distance, duration, steps."""
    payload = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "alternatives": False,
        "language": "en"
    }
    return await _invoke("directions", "directions", payload)


@tool("search_nearby_places", args_schema=PlaceSearchInput)
async def search_nearby_places(
    location: str,
    radius: int = 1500,
    place_type: str = None,
    keyword: str = None
) -> str:
    """Find nearby places (POIs with ratings, address, open status)."""
    lat, lng = location.split(",")
    payload = {
        "latitude": float(lat.strip()),
        "longitude": float(lng.strip()),
        "radius": radius,
        "type": place_type,
        "keyword": keyword,
        "language": "en"
    }
    return await _invoke("places_nearby", "places/nearby", payload)


@tool("get_air_quality", args_schema=AirQualityInput)
async def get_air_quality(location: str) -> str:
    """Air quality index and health recommendations."""
    lat, lng = location.split(",")
    payload = {
        "latitude": float(lat.strip()),
        "longitude": float(lng.strip())
    }
    return await _invoke("air_quality", "air-quality", payload)


@tool("get_street_view", args_schema=StreetViewInput)
async def get_street_view(location: str) -> str:
    """Get Street View image URL for location."""
    lat, lng = location.split(",")
    payload = {
        "latitude": float(lat.strip()),
        "longitude": float(lng.strip()),
        "size": "600x400"
    }
    return await _invoke("street_view", "street-view/metadata", payload)


@tool("get_place_details", args_schema=PlaceDetailsInput)
async def get_place_details(place_id: str) -> str:
    """Get detailed info about a place: reviews, photos, hours, phone, website."""
    payload = {"place_id": place_id}
    return await _invoke("places_details", "places/details", payload)


# Export all tools
GOOGLE_MAPS_TOOLS = [
    geocode_address,
    get_directions,
    search_nearby_places,
    get_place_details,
    get_air_quality,
    get_street_view
]
