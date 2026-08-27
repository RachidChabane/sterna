"""Celery configuration for Sterna.

This module configures Celery for background task processing,
primarily used for code job execution in the code_sessions feature.
"""

import os

from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]
from celery.signals import (  # type: ignore[import-untyped]
    before_task_publish,
    setup_logging,
    task_postrun,
    task_prerun,
)

# Set the default Django settings module for Celery
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sterna.settings.dev")

# Create the Celery app
app = Celery("sterna")

# Load configuration from Django settings with CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Belt and braces with the setup_logging handler below: never let the
# worker replace the root logger with its own plain-text handler
# (which would bypass JSON structure AND secret redaction).
app.conf.worker_hijack_root_logger = False


@setup_logging.connect
def configure_structured_logging(**kwargs):
    """Re-apply the Django LOGGING dictConfig inside celery workers.

    Connecting ANY receiver to ``setup_logging`` stops Celery from
    hijacking the root logger with a plain-text handler. Re-running the
    project dictConfig gives worker logs the same JSON structure,
    request-id stamping and sensitive-key redaction as web logs.
    """
    import logging.config

    from django.conf import settings

    logging_config = getattr(settings, "LOGGING", None)
    if logging_config:
        logging.config.dictConfig(logging_config)


# --- Request-id propagation into tasks -----------------------------------
# The web process copies the active request id into the task message
# headers at publish time; the worker restores it into the ContextVar
# read by RequestIDFilter, so task logs correlate with the HTTP request
# that enqueued them.

REQUEST_ID_HEADER = "request_id"


@before_task_publish.connect
def propagate_request_id_to_task(headers=None, **kwargs):
    """Copy the current request id into the outgoing task headers."""
    if not isinstance(headers, dict) or headers.get(REQUEST_ID_HEADER):
        return
    try:
        from sterna.middleware.request_id import current_request_id

        rid = current_request_id.get()
    except Exception:
        rid = None
    if rid:
        headers[REQUEST_ID_HEADER] = rid


@task_prerun.connect
def restore_request_id_in_worker(task=None, **kwargs):
    """Restore the publisher's request id into the worker ContextVar."""
    rid = None
    request = getattr(task, "request", None)
    if request is not None:
        getter = getattr(request, "get", None)
        if callable(getter):
            rid = getter(REQUEST_ID_HEADER)
        if not rid:
            hdrs = getattr(request, "headers", None)
            if isinstance(hdrs, dict):
                rid = hdrs.get(REQUEST_ID_HEADER)
    try:
        from sterna.middleware.request_id import current_request_id

        current_request_id.set(rid or None)
    except Exception:
        pass


@task_postrun.connect
def clear_request_id_in_worker(task=None, **kwargs):
    """Clear the request id so it never bleeds into the next task."""
    try:
        from sterna.middleware.request_id import current_request_id

        current_request_id.set(None)
    except Exception:
        pass

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Task routing - route code jobs to dedicated queue
app.conf.task_routes = {
    "code_sessions.tasks.*": {"queue": "code_jobs"},
}

# Task annotations for specific tasks
app.conf.task_annotations = {
    "code_sessions.tasks.execute_code_job": {
        "rate_limit": "10/m",  # Max 10 jobs per minute per worker
        "time_limit": 1800,  # 30 minutes hard limit
        "soft_time_limit": 1500,  # 25 minutes soft limit
    },
}

# Task result expiration
app.conf.result_expires = 3600  # 1 hour

# Task retry settings
app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True

# Beat schedule (task 22 — R2 backup + health monitoring)
app.conf.beat_schedule = {
    "backup-r2-user-assets-daily-0300-utc": {
        "task": "storage.tasks.backup_r2_user_assets",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "celery", "expires": 6 * 3600},
    },
    "r2-backup-health-check-every-6h": {
        "task": "storage.tasks.r2_backup_health_check",
        "schedule": crontab(minute=0, hour="*/6"),
        "options": {"queue": "celery"},
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery."""
    print(f"Request: {self.request!r}")
