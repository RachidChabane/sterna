"""
Google Maps proxy endpoints.

These endpoints proxy requests to the Google Maps service for frontend display purposes.
This keeps all API calls going through the backend gateway while keeping display-only
data (like photos) separate from model context.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..services.google_maps_photo_service import fetch_place_photo


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def google_maps_place_photo(request):
    """
    Proxy endpoint for fetching place photos from Google Maps service.
    Used by frontend for display purposes - not sent to models.

    Authenticated + metered: every call hits the paid Google Places API
    (Text Search + photo), so the caller must be a known user and the
    request is billed as GOOGLE_MAPS/'places_photo' against their quota.
    Only whitelisted payload fields are forwarded upstream.
    """
    # Whitelist + validate the forwarded payload (never forward raw
    # client JSON to the internal service).
    data = request.data if isinstance(request.data, dict) else {}
    query = data.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > 256:
        return Response(
            {"success": False, "error": "Invalid 'query'."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    payload = {"query": query.strip()}
    for field, lo, hi in (("latitude", -90, 90), ("longitude", -180, 180)):
        value = data.get(field)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or not (lo <= value <= hi):
            return Response(
                {"success": False, "error": f"Invalid '{field}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload[field] = value
    max_width = data.get("max_width", 400)
    if not isinstance(max_width, int) or not (1 <= max_width <= 1600):
        max_width = 400
    payload["max_width"] = max_width

    body, status_code = fetch_place_photo(request.user, payload)
    return Response(body, status=status_code)
