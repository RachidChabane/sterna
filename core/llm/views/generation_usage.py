"""
OpenRouter generation usage lookup endpoint.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..services.generation_usage_service import fetch_generation_usage


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_generation_usage(request, generation_id):
    """Query OpenRouter for exact usage/cost of a generation (even interrupted ones).

    OpenRouter takes ~15-20 seconds to finalize generation data after stream completion.
    This endpoint retries with backoff until the data is available.
    """
    from llm.services.api_key_resolver import get_api_key_for_user

    api_key = get_api_key_for_user(request.user)
    if not api_key:
        return Response({"error": "No API key configured"}, status=400)

    body, status_code = fetch_generation_usage(api_key, generation_id)
    return Response(body, status=status_code)
