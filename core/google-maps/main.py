"""
Google Maps API Service

Provides optimized access to Google Maps Platform APIs with caching and rate limiting.
Supports: Geocoding, Directions, Distance Matrix, Places, Air Quality, Weather, Street View.
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
import logging
import os
import json
import hashlib
from typing import Dict, Any, List, Optional, Literal
import redis.asyncio as redis

from _observability import RequestIDMiddleware, init_observability  # noqa: E402

init_observability(service="google-maps", app_loggers=("main",))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Google Maps API Service",
    description="Optimized Google Maps Platform APIs with caching",
    version="1.0.0"
)

# CORS
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

# Configuration
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "86400"))  # 24h default

# Redis client (initialized on startup)
redis_client: Optional[redis.Redis] = None


@app.on_event("startup")
async def startup_event():
    """Initialize Redis connection on startup."""
    global redis_client
    try:
        redis_client = await redis.from_url(
            f"redis://{REDIS_HOST}:{REDIS_PORT}",
            encoding="utf-8",
            decode_responses=True
        )
        await redis_client.ping()
        logger.info("[GoogleMaps] Connected to Redis for caching")
    except Exception as e:
        logger.error(f"[GoogleMaps] Failed to connect to Redis: {e}")
        redis_client = None


@app.on_event("shutdown")
async def shutdown_event():
    """Close Redis connection on shutdown."""
    global redis_client
    if redis_client:
        await redis_client.close()


def create_cache_key(prefix: str, params: Dict[str, Any]) -> str:
    """Create a deterministic cache key from params."""
    params_str = json.dumps(params, sort_keys=True)
    hash_key = hashlib.md5(params_str.encode()).hexdigest()
    return f"gmaps:{prefix}:{hash_key}"


async def get_cached(key: str) -> Optional[Dict[str, Any]]:
    """Get cached result from Redis."""
    if not redis_client:
        return None
    try:
        cached = await redis_client.get(key)
        if cached:
            logger.info(f"[GoogleMaps] Cache HIT: {key}")
            return json.loads(cached)
    except Exception as e:
        logger.error(f"[GoogleMaps] Cache get error: {e}")
    return None


async def set_cached(key: str, value: Dict[str, Any], ttl: int = CACHE_TTL):
    """Set cached result in Redis."""
    if not redis_client:
        return
    try:
        await redis_client.setex(key, ttl, json.dumps(value))
        logger.info(f"[GoogleMaps] Cache SET: {key} (TTL: {ttl}s)")
    except Exception as e:
        logger.error(f"[GoogleMaps] Cache set error: {e}")


async def call_google_maps_api(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Call Google Maps API with error handling."""
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google Maps API key not configured"
        )

    params["key"] = GOOGLE_MAPS_API_KEY
    base_url = "https://maps.googleapis.com/maps/api"
    url = f"{base_url}/{endpoint}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            logger.info(f"[GoogleMaps] Calling {endpoint} with params: {params}")
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Check for Google API errors
            if data.get("status") not in ["OK", "ZERO_RESULTS"]:
                logger.error(f"[GoogleMaps] API error: {data.get('status')} - {data.get('error_message')}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Google Maps API error: {data.get('status')}"
                )

            return data

        except httpx.HTTPStatusError as e:
            logger.error(f"[GoogleMaps] HTTP error {e.response.status_code}: {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Google Maps API error: {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"[GoogleMaps] Request error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to Google Maps API: {str(e)}"
            )


# ============================================================================
# MODELS
# ============================================================================

class GeocodingRequest(BaseModel):
    address: str = Field(..., description="Address to geocode")
    language: Optional[str] = Field("en", description="Language for results")


class ReverseGeocodingRequest(BaseModel):
    latitude: float = Field(..., description="Latitude")
    longitude: float = Field(..., description="Longitude")
    language: Optional[str] = Field("en", description="Language for results")


class DirectionsRequest(BaseModel):
    origin: str = Field(..., description="Starting location (address or lat,lng)")
    destination: str = Field(..., description="Ending location (address or lat,lng)")
    mode: Optional[Literal["driving", "walking", "bicycling", "transit"]] = Field("driving", description="Travel mode")
    alternatives: Optional[bool] = Field(False, description="Return alternative routes")
    language: Optional[str] = Field("en", description="Language for results")


class DistanceMatrixRequest(BaseModel):
    origins: List[str] = Field(..., description="List of origin addresses")
    destinations: List[str] = Field(..., description="List of destination addresses")
    mode: Optional[Literal["driving", "walking", "bicycling", "transit"]] = Field("driving", description="Travel mode")
    language: Optional[str] = Field("en", description="Language for results")


class PlaceDetailsRequest(BaseModel):
    place_id: str = Field(..., description="Google Place ID")
    fields: Optional[List[str]] = Field(
        ["name", "formatted_address", "geometry", "rating", "photos", "opening_hours", "price_level", "reviews"],
        description="Fields to return"
    )
    language: Optional[str] = Field("en", description="Language for results")


class NearbySearchRequest(BaseModel):
    latitude: float = Field(..., description="Center latitude")
    longitude: float = Field(..., description="Center longitude")
    radius: Optional[int] = Field(1500, description="Search radius in meters (max 50000)")
    type: Optional[str] = Field(None, description="Place type (e.g., restaurant, cafe)")
    keyword: Optional[str] = Field(None, description="Search keyword")
    language: Optional[str] = Field("en", description="Language for results")


class AirQualityRequest(BaseModel):
    latitude: float = Field(..., description="Latitude")
    longitude: float = Field(..., description="Longitude")


class StreetViewRequest(BaseModel):
    latitude: float = Field(..., description="Latitude")
    longitude: float = Field(..., description="Longitude")
    size: Optional[str] = Field("600x400", description="Image size (e.g., 600x400)")
    heading: Optional[int] = Field(None, description="Camera heading (0-360)")
    pitch: Optional[int] = Field(0, description="Camera pitch (-90 to 90)")
    fov: Optional[int] = Field(90, description="Field of view (max 120)")


class PlacePhotoSearchRequest(BaseModel):
    query: str = Field(..., description="Place name or search query")
    latitude: Optional[float] = Field(None, description="Optional latitude for location bias")
    longitude: Optional[float] = Field(None, description="Optional longitude for location bias")
    max_width: Optional[int] = Field(400, description="Maximum width of the photo")


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "Google Maps API Service",
        "status": "operational",
        "apis": [
            "geocoding",
            "directions",
            "distance-matrix",
            "places",
            "air-quality",
            "street-view"
        ]
    }


@app.post("/geocoding/forward")
async def geocode_forward(request: GeocodingRequest):
    """
    Convert address to GPS coordinates.
    Cached for 24h to reduce costs.
    """
    cache_key = create_cache_key("geocode", {"address": request.address, "lang": request.language})

    # Check cache
    cached = await get_cached(cache_key)
    if cached:
        return cached

    # Call API
    params = {"address": request.address, "language": request.language}
    data = await call_google_maps_api("geocode/json", params)

    if data["status"] == "ZERO_RESULTS":
        return {"success": False, "error": "Address not found", "results": []}

    # Extract coordinates
    results = []
    for result in data.get("results", []):
        location = result["geometry"]["location"]
        results.append({
            "formatted_address": result["formatted_address"],
            "latitude": location["lat"],
            "longitude": location["lng"],
            "place_id": result["place_id"],
            "types": result.get("types", [])
        })

    response = {"success": True, "results": results, "result_count": len(results)}

    # Cache result
    await set_cached(cache_key, response)

    return response


@app.post("/geocoding/reverse")
async def geocode_reverse(request: ReverseGeocodingRequest):
    """
    Convert GPS coordinates to address.
    Cached for 24h.
    """
    cache_key = create_cache_key("reverse", {
        "lat": request.latitude,
        "lng": request.longitude,
        "lang": request.language
    })

    cached = await get_cached(cache_key)
    if cached:
        return cached

    params = {"latlng": f"{request.latitude},{request.longitude}", "language": request.language}
    data = await call_google_maps_api("geocode/json", params)

    if data["status"] == "ZERO_RESULTS":
        return {"success": False, "error": "Location not found", "results": []}

    results = []
    for result in data.get("results", []):
        results.append({
            "formatted_address": result["formatted_address"],
            "place_id": result["place_id"],
            "types": result.get("types", [])
        })

    response = {"success": True, "results": results, "result_count": len(results)}
    await set_cached(cache_key, response)

    return response


@app.post("/directions")
async def get_directions(request: DirectionsRequest):
    """
    Calculate route between two points.
    Cached for 1h (routes change less frequently).
    """
    cache_key = create_cache_key("directions", {
        "origin": request.origin,
        "dest": request.destination,
        "mode": request.mode,
        "lang": request.language
    })

    cached = await get_cached(cache_key)
    if cached:
        return cached

    params = {
        "origin": request.origin,
        "destination": request.destination,
        "mode": request.mode,
        "alternatives": "true" if request.alternatives else "false",
        "language": request.language
    }
    data = await call_google_maps_api("directions/json", params)

    if data["status"] == "ZERO_RESULTS":
        return {"success": False, "error": "No route found", "routes": []}

    routes = []
    for route in data.get("routes", []):
        leg = route["legs"][0]  # Single leg for simple A-B routes
        routes.append({
            "summary": route["summary"],
            "distance": leg["distance"]["text"],
            "distance_meters": leg["distance"]["value"],
            "duration": leg["duration"]["text"],
            "duration_seconds": leg["duration"]["value"],
            "start_address": leg["start_address"],
            "end_address": leg["end_address"],
            "polyline": route["overview_polyline"]["points"],
            "steps": [
                {
                    "instruction": step["html_instructions"],
                    "distance": step["distance"]["text"],
                    "duration": step["duration"]["text"]
                }
                for step in leg["steps"]
            ]
        })

    response = {"success": True, "routes": routes, "route_count": len(routes)}
    await set_cached(cache_key, response, ttl=3600)  # 1h cache

    return response


@app.post("/distance-matrix")
async def get_distance_matrix(request: DistanceMatrixRequest):
    """
    Calculate distances/durations between multiple points.
    Cached for 1h.
    """
    cache_key = create_cache_key("distmatrix", {
        "origins": request.origins,
        "dests": request.destinations,
        "mode": request.mode,
        "lang": request.language
    })

    cached = await get_cached(cache_key)
    if cached:
        return cached

    params = {
        "origins": "|".join(request.origins),
        "destinations": "|".join(request.destinations),
        "mode": request.mode,
        "language": request.language
    }
    data = await call_google_maps_api("distancematrix/json", params)

    results = []
    for i, row in enumerate(data.get("rows", [])):
        for j, element in enumerate(row.get("elements", [])):
            if element["status"] == "OK":
                results.append({
                    "origin": data["origin_addresses"][i],
                    "destination": data["destination_addresses"][j],
                    "distance": element["distance"]["text"],
                    "distance_meters": element["distance"]["value"],
                    "duration": element["duration"]["text"],
                    "duration_seconds": element["duration"]["value"]
                })

    response = {"success": True, "results": results, "result_count": len(results)}
    await set_cached(cache_key, response, ttl=3600)

    return response


@app.post("/places/details")
async def get_place_details(request: PlaceDetailsRequest):
    """
    Get detailed information about a place using Places API (New).
    Cached for 6h (place details change infrequently).
    """
    cache_key = create_cache_key("place", {
        "id": request.place_id,
        "fields": request.fields,
        "lang": request.language
    })

    cached = await get_cached(cache_key)
    if cached:
        return cached

    # Use Places API (New)
    url = f"https://places.googleapis.com/v1/places/{request.place_id}"

    # Map old field names to new API field mask
    field_mask = "id,displayName,formattedAddress,location,rating,userRatingCount,priceLevel,currentOpeningHours,photos,reviews,nationalPhoneNumber,websiteUri,types"

    headers = {
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": field_mask,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            logger.info(f"[GoogleMaps] Calling Places API (New) details: {url}")
            response = await client.get(url, headers=headers)

            if response.status_code == 404:
                return {"success": False, "error": "Place not found"}

            response.raise_for_status()
            result = response.json()

            # Extract photo URLs if photos exist (new format)
            photos = []
            if "photos" in result:
                for photo in result["photos"][:5]:  # Limit to 5 photos
                    photo_name = photo.get("name", "")
                    if photo_name:
                        photos.append({
                            "url": f"https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx=800&key={GOOGLE_MAPS_API_KEY}",
                            "width": photo.get("widthPx"),
                            "height": photo.get("heightPx")
                        })

            # Extract reviews (new format)
            reviews = []
            for review in result.get("reviews", [])[:5]:
                reviews.append({
                    "author_name": review.get("authorAttribution", {}).get("displayName"),
                    "rating": review.get("rating"),
                    "text": review.get("text", {}).get("text"),
                    "time": review.get("publishTime"),
                    "relative_time_description": review.get("relativePublishTimeDescription")
                })

            location = result.get("location", {})
            response_data = {
                "success": True,
                "place": {
                    "name": result.get("displayName", {}).get("text"),
                    "address": result.get("formattedAddress"),
                    "location": {
                        "lat": location.get("latitude"),
                        "lng": location.get("longitude")
                    },
                    "rating": result.get("rating"),
                    "user_ratings_total": result.get("userRatingCount"),
                    "price_level": result.get("priceLevel"),
                    "opening_hours": result.get("currentOpeningHours"),
                    "photos": photos,
                    "reviews": reviews,
                    "phone": result.get("nationalPhoneNumber"),
                    "website": result.get("websiteUri"),
                    "types": result.get("types", [])
                }
            }

            await set_cached(cache_key, response_data, ttl=21600)  # 6h cache

            return response_data

        except httpx.HTTPStatusError as e:
            logger.error(f"[GoogleMaps] Places details API error {e.response.status_code}: {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Places API error: {e.response.text}"
            )
        except Exception as e:
            logger.error(f"[GoogleMaps] Places details API error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Places API error: {str(e)}"
            )


@app.post("/places/nearby")
async def search_nearby(request: NearbySearchRequest):
    """
    Search for places near a location using Places API (New).
    Cached for 1h (nearby results change frequently).
    """
    cache_key = create_cache_key("nearby", {
        "lat": request.latitude,
        "lng": request.longitude,
        "radius": request.radius,
        "type": request.type,
        "keyword": request.keyword,
        "lang": request.language
    })

    cached = await get_cached(cache_key)
    if cached:
        return cached

    # Use Places API (New) - POST request with JSON body
    url = "https://places.googleapis.com/v1/places:searchNearby"

    # Build request body
    body = {
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": request.latitude,
                    "longitude": request.longitude
                },
                "radius": float(request.radius)
            }
        },
        "maxResultCount": 20,
        "languageCode": request.language
    }

    # Add type filter if specified
    if request.type:
        body["includedTypes"] = [request.type]

    # Add text query for keyword search
    if request.keyword:
        # Use searchText instead for keyword searches
        url = "https://places.googleapis.com/v1/places:searchText"
        body["textQuery"] = f"{request.keyword} near {request.latitude},{request.longitude}"
        body["locationBias"] = body.pop("locationRestriction")
        body.pop("maxResultCount", None)
        body["maxResultCount"] = 20

    # Field mask for response fields
    field_mask = "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.priceLevel,places.types,places.currentOpeningHours"

    headers = {
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": field_mask,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            logger.info(f"[GoogleMaps] Calling Places API (New): {url}")
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()

            results = []
            for place in data.get("places", []):
                location = place.get("location", {})
                results.append({
                    "place_id": place.get("id"),
                    "name": place.get("displayName", {}).get("text"),
                    "address": place.get("formattedAddress"),
                    "location": {
                        "lat": location.get("latitude"),
                        "lng": location.get("longitude")
                    },
                    "rating": place.get("rating"),
                    "user_ratings_total": place.get("userRatingCount"),
                    "price_level": place.get("priceLevel"),
                    "types": place.get("types", []),
                    "open_now": place.get("currentOpeningHours", {}).get("openNow")
                })

            response_data = {"success": True, "results": results, "result_count": len(results)}
            await set_cached(cache_key, response_data, ttl=3600)

            return response_data

        except httpx.HTTPStatusError as e:
            logger.error(f"[GoogleMaps] Places API error {e.response.status_code}: {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Places API error: {e.response.text}"
            )
        except Exception as e:
            logger.error(f"[GoogleMaps] Places API error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Places API error: {str(e)}"
            )


@app.post("/places/search-photo")
async def search_place_photo(request: PlacePhotoSearchRequest):
    """
    Search for a place by text and return its first photo URL.
    Useful for enriching location results with images.
    Cached for 24h.
    """
    cache_key = create_cache_key("place_photo", {
        "query": request.query,
        "lat": request.latitude,
        "lng": request.longitude,
        "width": request.max_width
    })

    cached = await get_cached(cache_key)
    if cached:
        return cached

    # Use Text Search API to find the place
    url = "https://places.googleapis.com/v1/places:searchText"

    body = {
        "textQuery": request.query,
        "maxResultCount": 1,
        "languageCode": "en"
    }

    # Add location bias if coordinates provided
    if request.latitude is not None and request.longitude is not None:
        body["locationBias"] = {
            "circle": {
                "center": {
                    "latitude": request.latitude,
                    "longitude": request.longitude
                },
                "radius": 500.0  # 500m radius for precise matching
            }
        }

    headers = {
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.photos",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()

            places = data.get("places", [])
            if not places:
                result = {"success": False, "photo_url": None, "error": "No place found"}
                await set_cached(cache_key, result, ttl=3600)  # Cache misses for 1h
                return result

            place = places[0]
            photos = place.get("photos", [])

            if not photos:
                result = {"success": False, "photo_url": None, "error": "No photos available"}
                await set_cached(cache_key, result, ttl=3600)
                return result

            # Get the first photo
            photo_name = photos[0].get("name", "")
            if not photo_name:
                result = {"success": False, "photo_url": None, "error": "Invalid photo data"}
                await set_cached(cache_key, result, ttl=3600)
                return result

            photo_url = f"https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx={request.max_width}&key={GOOGLE_MAPS_API_KEY}"

            result = {
                "success": True,
                "photo_url": photo_url,
                "place_name": place.get("displayName", {}).get("text")
            }

            await set_cached(cache_key, result, ttl=86400)  # 24h cache
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"[GoogleMaps] Place photo search error {e.response.status_code}: {e.response.text}")
            return {"success": False, "photo_url": None, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"[GoogleMaps] Place photo search error: {str(e)}")
            return {"success": False, "photo_url": None, "error": str(e)}


@app.post("/air-quality")
async def get_air_quality(request: AirQualityRequest):
    """
    Get air quality data for a location.
    Cached for 1h (air quality changes hourly).
    """
    cache_key = create_cache_key("airquality", {
        "lat": request.latitude,
        "lng": request.longitude
    })

    cached = await get_cached(cache_key)
    if cached:
        return cached

    # Air Quality API uses different base URL
    url = "https://airquality.googleapis.com/v1/currentConditions:lookup"

    payload = {
        "location": {
            "latitude": request.latitude,
            "longitude": request.longitude
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                json=payload,
                params={"key": GOOGLE_MAPS_API_KEY}
            )
            response.raise_for_status()
            data = response.json()

            # Extract relevant air quality info
            result = {
                "success": True,
                "aqi": data.get("indexes", [{}])[0].get("aqi"),
                "category": data.get("indexes", [{}])[0].get("category"),
                "dominant_pollutant": data.get("indexes", [{}])[0].get("dominantPollutant"),
                "datetime": data.get("dateTime"),
                "health_recommendations": data.get("healthRecommendations")
            }

            await set_cached(cache_key, result, ttl=3600)
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"[GoogleMaps] Air Quality API error: {e.response.status_code}")
            return {"success": False, "error": "Air quality data not available"}
        except Exception as e:
            logger.error(f"[GoogleMaps] Air Quality error: {str(e)}")
            return {"success": False, "error": str(e)}


@app.post("/street-view/metadata")
async def get_street_view_metadata(request: StreetViewRequest):
    """
    Check if Street View is available at a location.
    Returns metadata and image URL.
    """
    params = {
        "location": f"{request.latitude},{request.longitude}",
        "size": request.size
    }

    # Get metadata
    metadata = await call_google_maps_api("streetview/metadata", params)

    if metadata["status"] != "OK":
        return {"success": False, "available": False, "error": "Street View not available"}

    # Build image URL
    image_params = params.copy()
    if request.heading is not None:
        image_params["heading"] = request.heading
    if request.pitch is not None:
        image_params["pitch"] = request.pitch
    if request.fov is not None:
        image_params["fov"] = request.fov

    image_url = f"https://maps.googleapis.com/maps/api/streetview?{httpx.QueryParams(image_params)}&key={GOOGLE_MAPS_API_KEY}"

    return {
        "success": True,
        "available": True,
        "location": metadata["location"],
        "date": metadata.get("date"),
        "image_url": image_url
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
