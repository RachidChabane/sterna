"""
Sandbox API Views

Provides REST endpoints for:
- Skills execution (via orchestrator)
- Artifact retrieval

These endpoints proxy requests to the sandbox microservices:
- Orchestrator (http://orchestrator:8003)
"""

import logging
import requests
from typing import Dict, Any, Optional
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)

# Service URLs from environment or defaults
ORCHESTRATOR_URL = getattr(
    settings, 'ORCHESTRATOR_URL', 'http://orchestrator:8003'
)

# Request timeout in seconds
REQUEST_TIMEOUT = 30


def proxy_request(
    method: str,
    url: str,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = REQUEST_TIMEOUT
) -> Response:
    """
    Proxy request to sandbox service and return DRF Response.

    Args:
        method: HTTP method (GET, POST, DELETE, etc.)
        url: Full URL to proxy to
        data: JSON data to send (for POST/PUT)
        params: Query parameters
        timeout: Request timeout in seconds

    Returns:
        Response: DRF Response with proxied data
    """
    try:
        logger.info(f"Proxying {method} request to {url}")

        response = requests.request(
            method=method,
            url=url,
            json=data,
            params=params,
            timeout=timeout
        )

        # Log if not successful
        if response.status_code >= 400:
            logger.error(
                f"Sandbox service error: {response.status_code} - {response.text}"
            )

        # Return response with same status code and data
        try:
            response_data = response.json()
        except ValueError:
            response_data = {"detail": response.text}

        return Response(response_data, status=response.status_code)

    except requests.exceptions.Timeout:
        logger.error(f"Request timeout to {url}")
        return Response(
            {"detail": "Sandbox service timeout"},
            status=status.HTTP_504_GATEWAY_TIMEOUT
        )
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error to {url}")
        return Response(
            {"detail": "Sandbox service unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except Exception as e:
        logger.exception(f"Unexpected error proxying request: {e}")
        return Response(
            {"detail": f"Internal error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )




# ===========================
# Artifacts API
# ===========================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_artifacts(request, user_id: str, project_id: str):
    """
    List all artifacts for user × project.

    GET /api/sandbox/artifacts/{user_id}/{project_id}

    Args:
        user_id: User identifier
        project_id: Project identifier

    Returns:
        List of artifacts with metadata
    """
    url = f"{ORCHESTRATOR_URL}/artifacts/{user_id}/{project_id}"
    return proxy_request('GET', url)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_artifact_download_url(request, user_id: str, project_id: str, artifact_name: str):
    """
    Get download URL for a specific artifact.

    GET /api/sandbox/artifacts/{user_id}/{project_id}/{artifact_name}

    Args:
        user_id: User identifier
        project_id: Project identifier
        artifact_name: Name of the artifact file

    Returns:
        {
            "artifact_name": "string",
            "download_url": "string",
            "size": int (optional),
            "content_type": "string" (optional)
        }
    """
    url = f"{ORCHESTRATOR_URL}/artifacts/{user_id}/{project_id}/{artifact_name}/download"
    return proxy_request('GET', url)
