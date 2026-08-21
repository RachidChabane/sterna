"""
Middleware for automatic audit logging.
"""

import time
import json
from django.utils.deprecation import MiddlewareMixin
from django.contrib.contenttypes.models import ContentType
from .models import AuditLog


# task-29 H1: client IP extraction lives in sterna.client_ip
# (CF-aware). Import lazily inside the middleware to avoid circular
# settings imports during Django startup.
from sterna.client_ip import get_client_ip  # noqa: E402, F401

# Shared sensitive-key scrub (single source of truth for the key
# list); query params are persisted into extra_data and must never
# carry a secret verbatim (e.g. a password passed as ?password=...).
from sterna.logging import redact_sensitive  # noqa: E402


class AuditLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to automatically log all mutations (POST, PUT, PATCH, DELETE).

    This middleware:
    1. Captures request details before processing
    2. Records response status after processing
    3. Logs significant actions automatically
    4. Tracks performance metrics
    """

    # Actions that should always be logged
    ALWAYS_LOG_ACTIONS = {
        "POST": ["login", "logout", "register", "password-reset", "verify-email"],
        "DELETE": True,  # Always log deletes
    }

    # Paths to skip logging
    SKIP_PATHS = [
        "/health",   # covers both "/health" and "/health/"
        "/livez",
        "/readyz",
        "/metrics",
        "/static/",
        "/media/",
        "/favicon.ico",
    ]

    # Path patterns for determining action type
    ACTION_PATTERNS = {
        "/api/auth/login/": "AUTH_LOGIN",
        # OAuth logins are logins too — without these they fell through
        # to the generic AUTH_CREATE action and were invisible to
        # login-focused audit queries.
        "/api/auth/google/one-tap/": "AUTH_LOGIN",
        "/api/auth/google/": "AUTH_LOGIN",
        "/api/auth/github/": "AUTH_LOGIN",
        "/api/auth/logout/": "AUTH_LOGOUT",
        "/api/auth/register/": "AUTH_REGISTER",
        "/api/auth/password-reset/": "AUTH_PASSWORD_RESET",
        "/api/auth/verify-email/": "AUTH_EMAIL_VERIFIED",
        "/api/projects/": {
            "POST": "PROJECT_CREATE",
            "PUT": "PROJECT_UPDATE",
            "PATCH": "PROJECT_UPDATE",
            "DELETE": "PROJECT_DELETE",
        },
        "/api/datasets/": {
            "POST": "DATASET_CREATE",
            "PUT": "DATASET_UPDATE",
            "DELETE": "DATASET_DELETE",
        },
        "/api/datasets/import/": "DATASET_IMPORTED",
        "/api/datasets/export/": "DATASET_EXPORTED",
        "/api/evaluations/runs/": {
            "POST": "RUN_STARTED",
        },
        "/api/rbac/permissions/grant/": "PERMISSION_GRANTED",
        "/api/rbac/permissions/revoke/": "PERMISSION_REVOKED",
        "/api/rbac/permissions/delegate/": "PERMISSION_DELEGATED",
    }

    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)

    def process_request(self, request):
        """Process request before view.

        NOTE: deliberately does NOT buffer request bodies. Nothing in
        this middleware ever read them, and capturing them meant login
        passwords and other raw payloads sat on the request object.
        """
        request.audit_start_time = time.time()

    def process_response(self, request, response):
        """Process response after view."""
        # Skip if path should not be logged
        if self._should_skip_path(request.path):
            return response

        # Skip read-only operations unless specifically configured
        if request.method in ["GET", "HEAD", "OPTIONS"] and not self._should_force_log(
            request
        ):
            return response

        # Calculate duration
        duration_ms = None
        if hasattr(request, "audit_start_time"):
            duration_ms = int((time.time() - request.audit_start_time) * 1000)

        # Determine action type
        action = self._determine_action(request, response)
        if not action:
            return response

        # Extract resource information
        resource_info = self._extract_resource_info(request, response)

        # Prepare audit log data
        audit_data = {
            "action": action,
            "user": request.user if request.user.is_authenticated else None,
            "user_ip": get_client_ip(request),
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
            "request_id": getattr(request, "request_id", None),
            "session_id": request.session.session_key
            if hasattr(request, "session")
            else None,
            "success": 200 <= response.status_code < 400,
            "duration_ms": duration_ms,
            "extra_data": {
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                # Scrubbed before persistence: a secret passed as a
                # query parameter must never be stored verbatim.
                "query_params": (
                    redact_sensitive(dict(request.GET))
                    if request.GET
                    else None
                ),
            },
        }

        # Add resource information if available
        if resource_info:
            audit_data.update(resource_info)

        # Add error message if failed
        if not audit_data["success"] and response.status_code >= 400:
            try:
                error_data = json.loads(response.content)
                if "error" in error_data:
                    audit_data["error_message"] = str(error_data["error"])[:500]
                elif "detail" in error_data:
                    audit_data["error_message"] = str(error_data["detail"])[:500]
            except Exception:
                audit_data["error_message"] = f"HTTP {response.status_code}"

        # Create audit log entry
        try:
            AuditLog.objects.log(**audit_data)
        except Exception:
            # Log error but don't fail the request
            import logging

            logger = logging.getLogger(__name__)
            logger.error("audit.log_create_failed", exc_info=True)

        return response

    def _should_skip_path(self, path):
        """Check if path should be skipped."""
        for skip_path in self.SKIP_PATHS:
            if path.startswith(skip_path):
                return True
        return False

    def _should_force_log(self, request):
        """Check if request should be logged regardless of method."""
        path = request.path.lower()
        method = request.method

        if method in self.ALWAYS_LOG_ACTIONS:
            actions = self.ALWAYS_LOG_ACTIONS[method]
            if actions is True:
                return True
            for action in actions:
                if action in path:
                    return True
        return False

    def _determine_action(self, request, response):
        """Determine the action type from request."""
        path = request.path
        method = request.method

        # Check specific patterns
        for pattern, action in self.ACTION_PATTERNS.items():
            if path.startswith(pattern):
                if isinstance(action, dict):
                    return action.get(
                        method, f"{method}_{pattern.strip('/').split('/')[-1].upper()}"
                    )
                return action

        # Generate generic action based on method and path
        if method in ["POST", "PUT", "PATCH", "DELETE"]:
            # Extract resource name from path
            path_parts = [p for p in path.split("/") if p and p != "api"]
            if path_parts:
                resource = path_parts[0].upper()
                if method == "POST":
                    return f"{resource}_CREATE"
                elif method in ["PUT", "PATCH"]:
                    return f"{resource}_UPDATE"
                elif method == "DELETE":
                    return f"{resource}_DELETE"

        return None

    def _extract_resource_info(self, request, response):
        """Extract resource information from response."""
        # Skip if not a successful mutation
        if response.status_code >= 400 or request.method == "GET":
            return None

        try:
            # Try to extract resource from response
            if hasattr(response, "data") and isinstance(response.data, dict):
                resource_data = response.data
            else:
                try:
                    resource_data = json.loads(response.content)
                except Exception:
                    return None

            # Look for ID in response
            resource_id = resource_data.get("id") or resource_data.get("uuid")
            if not resource_id:
                return None

            # Try to determine resource type from path
            path_parts = [p for p in request.path.split("/") if p and p != "api"]
            if path_parts:
                resource_type = path_parts[0].rstrip("s")  # Remove plural 's'

                # Map to actual model
                model_mapping = {
                    "project": "projects.Project",
                    "dataset": "datasets.Dataset",
                    "rubric": "rubrics.Rubric",
                    "evaluation": "evaluations.RunConfig",
                    "user": "authentication.User",
                }

                model_path = model_mapping.get(resource_type)
                if model_path:
                    app_label, model_name = model_path.split(".")
                    try:
                        content_type = ContentType.objects.get(
                            app_label=app_label, model=model_name.lower()
                        )
                        return {
                            "resource_type": content_type,
                            "resource_id": str(resource_id),
                        }
                    except ContentType.DoesNotExist:
                        pass

        except Exception:
            pass

        return None


# RequestIDMiddleware moved to sterna.middleware.request_id.
