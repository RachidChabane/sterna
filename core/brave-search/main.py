"""
Brave Search MCP Service

Provides search capabilities using Brave Search API:
- Web search with rich results
- Image search
- Local/Places search
- Video search
- News search
"""

from fastapi import FastAPI, HTTPException, status, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
import logging
import os
import json
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime

from _observability import RequestIDMiddleware, init_observability  # noqa: E402

init_observability(service="brave-search", app_loggers=("main",))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Brave Search Service",
    description="MCP service for Brave Search API integration",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Read/mint X-Request-ID and expose it to the log filters (cross-service
# correlation with Django / api-gateway).
app.add_middleware(RequestIDMiddleware)

# Brave Search API configuration
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
BRAVE_API_BASE_URL = "https://api.search.brave.com/res/v1"

# Quota service configuration
QUOTA_SERVICE_URL = os.getenv("QUOTA_SERVICE_URL", "http://web:8000/api")
# Note: Cost is centralized in usage_quota.services.cost_calculator - not defined here

if not BRAVE_API_KEY:
    logger.warning("BRAVE_API_KEY not set - search functionality will be disabled")


# --- Quota Management ---

async def check_user_quota(user_id: str, auth_header: str) -> bool:
    """
    Check if user has sufficient quota for a search request.

    Args:
        user_id: User UUID
        auth_header: Authorization header to forward

    Returns:
        True if quota available, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{QUOTA_SERVICE_URL}/quota/check/",
                json={
                    "user_id": user_id,
                    "service": "brave_search",
                    "request_count": 1,  # Let server calculate cost from request count
                    "feature": "search",
                },
                headers={"Authorization": auth_header}
            )
            if response.status_code == 200:
                data = response.json()
                if not data.get("allowed"):
                    logger.warning(f"[BraveSearch] Quota exceeded for user {user_id}: {data.get('reason')}")
                    return False
                return True
            else:
                logger.error(f"[BraveSearch] Quota check failed: {response.status_code} - {response.text}")
                # Allow search on quota service error to avoid blocking users
                return True
    except Exception as e:
        logger.error(f"[BraveSearch] Quota check error: {e}")
        # Allow search on error to avoid blocking users
        return True


async def deduct_user_quota(user_id: str, auth_header: str) -> None:
    """
    Deduct usage from user's quota after successful search.

    Retries once on failure. If both attempts fail, emits a structured
    `brave_search.quota_deduction_dropped` error for ops alerting: this
    FastAPI sidecar has no access to the Django-side failed-deduction
    retry queue (`usage_quota.tasks.queue_failed_deduction` is
    Celery/Redis-internal, only reachable from Django process space), so
    recovery beyond the retry is intentionally handled by alerting on
    that event rather than a new internal endpoint.

    Args:
        user_id: User UUID
        auth_header: Authorization header to forward
    """
    payload = {
        "user_id": user_id,
        "service": "brave_search",
        "request_count": 1,  # Let server calculate cost from request count
        "feature": "search",
    }
    max_attempts = 2  # initial call + one retry
    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{QUOTA_SERVICE_URL}/quota/deduct/",
                    json=payload,
                    headers={"Authorization": auth_header}
                )
            if response.status_code == 200:
                data = response.json()
                cost = data.get("cost_usd", "0.005")
                logger.info(f"[BraveSearch] Quota deducted for user {user_id}: ${cost}")
                return
            logger.warning(
                "brave_search.quota_deduction_failed",
                extra={
                    "user_id": user_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "status_code": response.status_code,
                },
            )
        except Exception as e:
            logger.warning(
                "brave_search.quota_deduction_error",
                extra={
                    "user_id": user_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error": str(e),
                },
            )

    # Both attempts failed — this search's usage was NOT recorded.
    logger.error(
        "brave_search.quota_deduction_dropped",
        extra={
            "user_id": user_id,
            "service": "brave_search",
            "request_count": 1,
        },
    )


def extract_user_id(request: Request) -> Optional[str]:
    """Extract user ID from request headers."""
    # Check for X-User-ID header (set by API gateway/auth middleware)
    user_id = request.headers.get("X-User-ID")
    if user_id:
        return user_id

    # Check for user_id query parameter (for internal calls)
    user_id = request.query_params.get("user_id")
    if user_id:
        return user_id

    return None


# --- Request/Response Models ---

class WebSearchRequest(BaseModel):
    """Request for web search."""
    query: str = Field(..., description="Search query")
    count: Optional[int] = Field(10, ge=1, le=20, description="Number of results (1-20)")
    offset: Optional[int] = Field(0, ge=0, description="Pagination offset")
    safesearch: Optional[Literal["off", "moderate", "strict"]] = Field("moderate", description="Safe search filter")
    freshness: Optional[Literal["", "pd", "pw", "pm", "py"]] = Field("", description="Result freshness: pd=past day, pw=past week, pm=past month, py=past year")
    text_decorations: Optional[bool] = Field(True, description="Enable text highlights in results")
    goggles_id: Optional[str] = Field(None, description="Goggles ID to filter results")
    result_filter: Optional[str] = Field(None, description="Comma-separated list of result types to include (e.g., 'discussions,faq,infobox')")


class ImageSearchRequest(BaseModel):
    """Request for image search."""
    query: str = Field(..., description="Search query")
    count: Optional[int] = Field(10, ge=1, le=150, description="Number of results (1-150)")
    safesearch: Optional[Literal["off", "strict"]] = Field("off", description="Safe search filter")


class LocalSearchRequest(BaseModel):
    """Request for local/places search."""
    query: str = Field(..., description="Search query (business or place)")
    count: Optional[int] = Field(5, ge=1, le=20, description="Number of results (1-20)")
    search_lang: Optional[str] = Field(None, description="Search language (e.g., 'en', 'fr', 'de')")


class VideoSearchRequest(BaseModel):
    """Request for video search."""
    query: str = Field(..., description="Search query")
    count: Optional[int] = Field(10, ge=1, le=20, description="Number of results (1-20)")
    offset: Optional[int] = Field(0, ge=0, description="Pagination offset")
    safesearch: Optional[Literal["off", "strict"]] = Field("off", description="Safe search filter")


class NewsSearchRequest(BaseModel):
    """Request for news search."""
    query: str = Field(..., description="Search query")
    count: Optional[int] = Field(10, ge=1, le=20, description="Number of results (1-20)")
    offset: Optional[int] = Field(0, ge=0, description="Pagination offset")
    freshness: Optional[Literal["", "pd", "pw", "pm"]] = Field("", description="Result freshness")


class SearchResponse(BaseModel):
    """Generic search response."""
    success: bool
    results: List[Dict[str, Any]]
    query: str
    result_count: int
    error: Optional[str] = None


class EnrichedWebSearchResponse(BaseModel):
    """Enriched web search response with all Pro features."""
    success: bool
    query: str
    # Main results
    web_results: List[Dict[str, Any]] = []
    result_count: int = 0
    # Enrichments (Pro features)
    infobox: Optional[Dict[str, Any]] = None
    faq: Optional[Dict[str, Any]] = None
    discussions: List[Dict[str, Any]] = []
    locations: List[Dict[str, Any]] = []
    news_results: List[Dict[str, Any]] = []
    videos_results: List[Dict[str, Any]] = []
    # Metadata
    mixed: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# --- Helper Functions ---

async def call_brave_api(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call Brave Search API.

    Args:
        endpoint: API endpoint (e.g., 'web/search', 'images/search')
        params: Query parameters

    Returns:
        API response as dict

    Raises:
        HTTPException on API errors
    """
    if not BRAVE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Brave Search API key not configured"
        )

    url = f"{BRAVE_API_BASE_URL}/{endpoint}"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY
    }

    # Remove None values from params
    params = {k: v for k, v in params.items() if v is not None and v != ""}

    logger.info(f"[BraveSearch] Calling {endpoint} with params: {params}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"[BraveSearch] {endpoint} returned {len(data.get('results', data.get('web', {}).get('results', [])))} results")
            return data

    except httpx.HTTPStatusError as e:
        logger.error(f"[BraveSearch] API error {e.response.status_code}: {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Brave Search API error: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"[BraveSearch] Request error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to Brave Search API: {str(e)}"
        )


# --- API Endpoints ---

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "brave-search",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "api_key_configured": bool(BRAVE_API_KEY)
    }


@app.post("/search/web", response_model=SearchResponse)
async def web_search(
    request_body: WebSearchRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    Perform web search using Brave Search API.

    Returns comprehensive web search results with rich snippets, images, and metadata.
    """
    # Extract user ID and check quota
    user_id = extract_user_id(request)
    auth_header = authorization or ""

    if user_id:
        quota_ok = await check_user_quota(user_id, auth_header)
        if not quota_ok:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Usage quota exceeded. Please wait or upgrade your plan."
            )

    params = {
        "q": request_body.query,
        "count": request_body.count,
        "offset": request_body.offset,
        "safesearch": request_body.safesearch,
        "text_decorations": str(request_body.text_decorations).lower()
    }

    if request_body.freshness:
        params["freshness"] = request_body.freshness
    if request_body.goggles_id:
        params["goggles_id"] = request_body.goggles_id
    if request_body.result_filter:
        params["result_filter"] = request_body.result_filter

    try:
        data = await call_brave_api("web/search", params)

        # Extract results from response
        web_results = data.get("web", {}).get("results", [])

        # Deduct quota after successful search
        if user_id:
            await deduct_user_quota(user_id, auth_header)

        return SearchResponse(
            success=True,
            results=web_results,
            query=request_body.query,
            result_count=len(web_results)
        )

    except HTTPException as e:
        logger.error(f"[BraveSearch] Web search failed: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"[BraveSearch] Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Web search failed: {str(e)}"
        )


@app.post("/search/web/enriched", response_model=EnrichedWebSearchResponse)
async def enriched_web_search(
    request_body: WebSearchRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    Perform enriched web search using Brave Search API Pro features.

    Returns web results plus all enrichments: infobox, FAQ, discussions, locations, news, videos.
    Requires Pro plan for full feature access.
    """
    # Extract user ID and check quota
    user_id = extract_user_id(request)
    auth_header = authorization or ""

    if user_id:
        quota_ok = await check_user_quota(user_id, auth_header)
        if not quota_ok:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Usage quota exceeded. Please wait or upgrade your plan."
            )

    params = {
        "q": request_body.query,
        "count": request_body.count,
        "offset": request_body.offset,
        "safesearch": request_body.safesearch,
        "text_decorations": str(request_body.text_decorations).lower()
    }

    if request_body.freshness:
        params["freshness"] = request_body.freshness
    if request_body.goggles_id:
        params["goggles_id"] = request_body.goggles_id
    if request_body.result_filter:
        params["result_filter"] = request_body.result_filter

    try:
        data = await call_brave_api("web/search", params)

        # Extract main web results
        web_results = data.get("web", {}).get("results", [])

        # Extract enrichments (Pro features)
        infobox = data.get("infobox")
        faq = data.get("faq")
        discussions = data.get("discussions", {}).get("results", [])
        locations = data.get("locations", {}).get("results", [])
        news_results = data.get("news", {}).get("results", [])
        videos_results = data.get("videos", {}).get("results", [])
        mixed = data.get("mixed")

        # Normalize infobox structure for frontend
        if infobox:
            logger.info(f"[BraveSearch] Raw infobox type: {infobox.get('type')}, keys: {list(infobox.keys())}")
            # Extract the actual infobox data from results array
            if infobox.get("type") == "graph" and infobox.get("results") and len(infobox["results"]) > 0:
                infobox_data = infobox["results"][0]

                # Extensive debug logging
                logger.info("[BraveSearch] === INFOBOX DEBUG START ===")
                logger.info(f"[BraveSearch] Raw infobox_data: {json.dumps(infobox_data, ensure_ascii=False, default=str)[:2000]}")
                logger.info("[BraveSearch] === INFOBOX DEBUG END ===")

                # Get values with proper empty string handling
                title = infobox_data.get("title") or infobox_data.get("label") or ""
                description = infobox_data.get("description") or ""
                long_desc = infobox_data.get("long_desc") or ""
                subtype = infobox_data.get("subtype") or ""
                url = infobox_data.get("url") or infobox_data.get("website_url") or ""

                # Get nested location data (contains most useful info for places)
                location_data = infobox_data.get("location", {}) if isinstance(infobox_data.get("location"), dict) else {}

                # Build description from available fields
                if not description:
                    # Try icon_category from location (e.g., "restaurant")
                    icon_category = location_data.get("icon_category", "")
                    if icon_category:
                        description = icon_category.replace("_", " ").title()
                    # Fallback to subtype
                    elif subtype:
                        description = subtype.replace("_", " ").title()

                # Normalize field names to match frontend expectations
                normalized = {
                    "title": title if title else None,
                    "description": description if description else None,
                    "long_desc": long_desc if long_desc else None,
                    "url": url if url else None,
                }

                # Build data array from attributes AND location data
                data_items = []

                # First, add any existing attributes
                attributes = infobox_data.get("attributes")
                if attributes:
                    logger.info(f"[BraveSearch] Attributes type: {type(attributes)}, value: {attributes}")
                    if isinstance(attributes, list):
                        data_items.extend([
                            {"label": attr[0], "value": attr[1]}
                            for attr in attributes
                            if isinstance(attr, (list, tuple)) and len(attr) >= 2
                        ])
                    elif isinstance(attributes, dict):
                        data_items.extend([
                            {"label": k, "value": v}
                            for k, v in attributes.items()
                        ])

                # Extract data from nested location object
                if location_data:
                    # Address
                    postal_address = location_data.get("postal_address", {})
                    if isinstance(postal_address, dict) and postal_address.get("displayAddress"):
                        data_items.append({"label": "Address", "value": postal_address["displayAddress"]})

                    # Phone
                    contact = location_data.get("contact", {})
                    if isinstance(contact, dict) and contact.get("telephone"):
                        data_items.append({"label": "Phone", "value": contact["telephone"]})

                    # Opening hours - format nicely
                    opening_hours = location_data.get("opening_hours", {})
                    if opening_hours and opening_hours.get("current_day"):
                        today_hours = opening_hours["current_day"]
                        if today_hours:
                            hours_str = ", ".join([f"{h.get('opens', '')}-{h.get('closes', '')}" for h in today_hours if h.get('opens')])
                            if hours_str:
                                day_name = today_hours[0].get("full_name", "Today") if today_hours else "Today"
                                data_items.append({"label": f"Hours ({day_name})", "value": hours_str})

                    # Timezone
                    if location_data.get("timezone"):
                        data_items.append({"label": "Timezone", "value": location_data["timezone"]})

                if data_items:
                    normalized["data"] = data_items

                # Build images array from thumbnail and images
                images = []
                if infobox_data.get("thumbnail"):
                    thumb = infobox_data["thumbnail"]
                    if isinstance(thumb, dict):
                        images.append({
                            "url": thumb.get("src") or thumb.get("original"),
                            "title": thumb.get("alt", "")
                        })
                    elif isinstance(thumb, str):
                        images.append({"url": thumb, "title": ""})

                if "images" in infobox_data:
                    for img in infobox_data["images"]:
                        if isinstance(img, dict):
                            images.append({
                                "url": img.get("src") or img.get("original"),
                                "title": img.get("alt", "")
                            })

                if images:
                    normalized["images"] = images

                # Add ratings if available
                if infobox_data.get("ratings"):
                    normalized["ratings"] = infobox_data["ratings"]

                # Add profiles (social links) if available
                profiles = infobox_data.get("profiles")
                if profiles:
                    logger.info(f"[BraveSearch] Profiles: {profiles}")
                    normalized["profiles"] = profiles

                # Add providers info - can be used to enrich description
                providers = infobox_data.get("providers")
                if providers:
                    logger.info(f"[BraveSearch] Providers: {providers}")
                    normalized["providers"] = providers
                    # If we still don't have a description, try to get one from providers
                    if not normalized.get("description") and isinstance(providers, list):
                        for provider in providers:
                            if isinstance(provider, dict) and provider.get("description"):
                                normalized["description"] = provider["description"]
                                break

                # Add coordinates if this is a location
                if infobox_data.get("coordinates"):
                    normalized["coordinates"] = infobox_data["coordinates"]

                # Replace the infobox with the normalized data
                infobox = normalized
                logger.info(f"[BraveSearch] Normalized infobox: {json.dumps(infobox, ensure_ascii=False, default=str)}")

        logger.info(f"[BraveSearch] Enriched search extracted: web={len(web_results)}, discussions={len(discussions)}, locations={len(locations)}, news={len(news_results)}, videos={len(videos_results)}, infobox={'yes' if infobox else 'no'}, faq={'yes' if faq else 'no'}")

        # Normalize location data
        for loc in locations:
            # Normalize coordinates format from [lat, lng] to {latitude, longitude}
            if "coordinates" in loc and isinstance(loc["coordinates"], list) and len(loc["coordinates"]) == 2:
                loc["coordinates"] = {
                    "latitude": loc["coordinates"][0],
                    "longitude": loc["coordinates"][1]
                }
            # Normalize postal_address -> address
            if "postal_address" in loc and not loc.get("address"):
                postal = loc["postal_address"]
                if isinstance(postal, dict):
                    loc["address"] = postal.get("displayAddress", "")
                elif isinstance(postal, str):
                    loc["address"] = postal
            # Normalize contact -> phone
            if "contact" in loc and not loc.get("phone"):
                contact = loc["contact"]
                if isinstance(contact, dict):
                    loc["phone"] = contact.get("telephone", "")
            # Normalize thumbnail - extract URL from object if needed
            if "thumbnail" in loc:
                thumb = loc["thumbnail"]
                if isinstance(thumb, dict) and "src" in thumb:
                    loc["thumbnail"] = thumb["src"]
            # Normalize rating - extract ratingValue from object if needed
            if "rating" in loc:
                rating = loc["rating"]
                if isinstance(rating, dict) and "ratingValue" in rating:
                    loc["rating"] = rating["ratingValue"]

        # Deduct quota after successful search
        if user_id:
            await deduct_user_quota(user_id, auth_header)

        return EnrichedWebSearchResponse(
            success=True,
            query=request_body.query,
            web_results=web_results,
            result_count=len(web_results),
            infobox=infobox,
            faq=faq,
            discussions=discussions,
            locations=locations,
            news_results=news_results,
            videos_results=videos_results,
            mixed=mixed
        )

    except HTTPException as e:
        logger.error(f"[BraveSearch] Enriched web search failed: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"[BraveSearch] Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Enriched web search failed: {str(e)}"
        )


@app.post("/search/images", response_model=SearchResponse)
async def image_search(
    request_body: ImageSearchRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    Search for images using Brave Search API.

    Returns image results with URLs, thumbnails, dimensions, and source info.
    """
    # Extract user ID and check quota
    user_id = extract_user_id(request)
    auth_header = authorization or ""

    if user_id:
        quota_ok = await check_user_quota(user_id, auth_header)
        if not quota_ok:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Usage quota exceeded. Please wait or upgrade your plan."
            )

    params = {
        "q": request_body.query,
        "count": request_body.count,
        "safesearch": request_body.safesearch
    }

    try:
        data = await call_brave_api("images/search", params)

        # Extract results
        results = data.get("results", [])

        # Deduct quota after successful search
        if user_id:
            await deduct_user_quota(user_id, auth_header)

        return SearchResponse(
            success=True,
            results=results,
            query=request_body.query,
            result_count=len(results)
        )

    except HTTPException as e:
        logger.error(f"[BraveSearch] Image search failed: {e.detail}")
        raise


@app.post("/search/local", response_model=SearchResponse)
async def local_search(
    request_body: LocalSearchRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    Search for local businesses and places using Brave Search API.

    Returns location-based results with addresses, ratings, and AI descriptions.
    Note: Uses web search endpoint which returns location results for local queries.
    """
    # Extract user ID and check quota
    user_id = extract_user_id(request)
    auth_header = authorization or ""

    if user_id:
        quota_ok = await check_user_quota(user_id, auth_header)
        if not quota_ok:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Usage quota exceeded. Please wait or upgrade your plan."
            )

    params = {
        "q": request_body.query,
        "count": request_body.count,
        "result_filter": "locations,web"  # Request locations + web results
    }

    # Add search language if specified
    if request_body.search_lang:
        params["search_lang"] = request_body.search_lang

    try:
        # Local search uses the web search endpoint which returns location results
        data = await call_brave_api("web/search", params)

        # Log the structure to understand what we get
        logger.info(f"[BraveSearch] Local search response keys: {list(data.keys())}")

        # Check if we have POI locations in the response
        if "locations" in data and "results" in data["locations"]:
            logger.info(f"[BraveSearch] ✓ Found 'locations.results' with {len(data['locations']['results'])} items")
            if data["locations"]["results"]:
                sample = data["locations"]["results"][0]
                logger.info(f"[BraveSearch] Sample location keys: {list(sample.keys())}")
                logger.info(f"[BraveSearch] Sample location data: {json.dumps(sample, indent=2)[:300]}")
        else:
            logger.warning(f"[BraveSearch] ✗ No 'locations.results' in response. Full response keys: {list(data.keys())}")

        # Extract location results if available (Pro plan feature)
        locations = []

        # Priority 1: Check for dedicated locations section (Pro plan)
        if "locations" in data:
            locations = data["locations"].get("results", [])
            logger.info(f"[BraveSearch] Found {len(locations)} POI results in 'locations' field (Pro feature)")
            if locations:
                # Log first result to see structure
                logger.info(f"[BraveSearch] Sample location result keys: {list(locations[0].keys()) if locations else 'N/A'}")

        # Priority 2: Check mixed results for location data
        if not locations and "mixed" in data:
            mixed_data = data["mixed"]
            logger.info(f"[BraveSearch] mixed data structure: {json.dumps(mixed_data, indent=2)[:500]}")
            if isinstance(mixed_data, dict) and "main" in mixed_data:
                for item in mixed_data.get("main", []):
                    if item.get("type") == "locations":
                        locations = item.get("results", [])
                        logger.info(f"[BraveSearch] Found {len(locations)} results in 'mixed.main' field")
                        break

        # Priority 3: Fallback to web results if no dedicated location data
        if not locations and "web" in data:
            web_results = data["web"].get("results", [])
            # Filter for results that might be location-related
            locations = web_results
            logger.warning(f"[BraveSearch] No dedicated location results - using {len(locations)} web results as fallback. Consider upgrading to Pro plan for POI data with GPS coordinates.")

        # Normalize location data
        for loc in locations:
            # Normalize coordinates format from [lat, lng] to {latitude, longitude}
            if "coordinates" in loc and isinstance(loc["coordinates"], list) and len(loc["coordinates"]) == 2:
                loc["coordinates"] = {
                    "latitude": loc["coordinates"][0],
                    "longitude": loc["coordinates"][1]
                }
            # Normalize postal_address -> address
            if "postal_address" in loc and not loc.get("address"):
                postal = loc["postal_address"]
                if isinstance(postal, dict):
                    loc["address"] = postal.get("displayAddress", "")
                elif isinstance(postal, str):
                    loc["address"] = postal
            # Normalize contact -> phone
            if "contact" in loc and not loc.get("phone"):
                contact = loc["contact"]
                if isinstance(contact, dict):
                    loc["phone"] = contact.get("telephone", "")
            # Normalize thumbnail - extract URL from object if needed
            if "thumbnail" in loc:
                thumb = loc["thumbnail"]
                if isinstance(thumb, dict) and "src" in thumb:
                    loc["thumbnail"] = thumb["src"]
            # Normalize rating - extract ratingValue from object if needed
            if "rating" in loc:
                rating = loc["rating"]
                if isinstance(rating, dict) and "ratingValue" in rating:
                    loc["rating"] = rating["ratingValue"]

        # Deduct quota after successful search
        if user_id:
            await deduct_user_quota(user_id, auth_header)

        return SearchResponse(
            success=True,
            results=locations,
            query=request_body.query,
            result_count=len(locations)
        )

    except HTTPException as e:
        logger.error(f"[BraveSearch] Local search failed: {e.detail}")
        raise


@app.post("/search/videos", response_model=SearchResponse)
async def video_search(
    request_body: VideoSearchRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    Search for videos using Brave Search API.

    Returns video results with titles, descriptions, durations, and view counts.
    """
    # Extract user ID and check quota
    user_id = extract_user_id(request)
    auth_header = authorization or ""

    if user_id:
        quota_ok = await check_user_quota(user_id, auth_header)
        if not quota_ok:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Usage quota exceeded. Please wait or upgrade your plan."
            )

    params = {
        "q": request_body.query,
        "count": request_body.count,
        "offset": request_body.offset,
        "safesearch": request_body.safesearch
    }

    try:
        data = await call_brave_api("videos/search", params)

        # Extract results
        results = data.get("results", [])

        # Deduct quota after successful search
        if user_id:
            await deduct_user_quota(user_id, auth_header)

        return SearchResponse(
            success=True,
            results=results,
            query=request_body.query,
            result_count=len(results)
        )

    except HTTPException as e:
        logger.error(f"[BraveSearch] Video search failed: {e.detail}")
        raise


@app.post("/search/news", response_model=SearchResponse)
async def news_search(
    request_body: NewsSearchRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    Search for news articles using Brave Search API.

    Returns recent news with freshness controls.
    """
    # Extract user ID and check quota
    user_id = extract_user_id(request)
    auth_header = authorization or ""

    if user_id:
        quota_ok = await check_user_quota(user_id, auth_header)
        if not quota_ok:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Usage quota exceeded. Please wait or upgrade your plan."
            )

    params = {
        "q": request_body.query,
        "count": request_body.count,
        "offset": request_body.offset
    }

    if request_body.freshness:
        params["freshness"] = request_body.freshness

    try:
        data = await call_brave_api("news/search", params)

        # Extract results
        results = data.get("results", [])

        # Deduct quota after successful search
        if user_id:
            await deduct_user_quota(user_id, auth_header)

        return SearchResponse(
            success=True,
            results=results,
            query=request_body.query,
            result_count=len(results)
        )

    except HTTPException as e:
        logger.error(f"[BraveSearch] News search failed: {e.detail}")
        raise


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
