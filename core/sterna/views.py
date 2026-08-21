"""
Custom error handlers for the sterna project.
"""

from django.http import JsonResponse


def custom_404(request, exception):
    """Return JSON 404 response for API requests."""
    return JsonResponse(
        {
            "error": "Not found",
            "detail": "The requested resource was not found.",
        },
        status=404,
    )
