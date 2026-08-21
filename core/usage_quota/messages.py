"""
Centralized user-friendly quota error messages.

All quota-related user-facing messages should use these functions
to ensure consistency and avoid exposing internal details like USD amounts.
"""

from datetime import datetime
from typing import Optional
from django.utils import timezone


def format_quota_error_message(
    limit_type: str,
    window_end: Optional[datetime] = None,
) -> str:
    """
    Generate a user-friendly quota error message with relative reset time.

    Args:
        limit_type: "session" or "weekly"
        window_end: When the limit resets (datetime)

    Returns:
        User-friendly error message with reset time
    """
    if window_end:
        relative_time = _format_relative_time(window_end)
        if limit_type == "session":
            return f"Session limit reached. Resets {relative_time}."
        elif limit_type == "weekly":
            return f"Weekly limit reached. Resets {relative_time}."
        return f"Usage limit reached. Resets {relative_time}."

    # Fallbacks without specific time
    if limit_type == "session":
        return "Session limit reached. Please try again later."
    elif limit_type == "weekly":
        return "Weekly limit reached. Please try again next week."
    return "Usage limit reached. Please try again later."


def _format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time (e.g., 'in 2 hours')."""
    now = timezone.now()

    # Ensure both are timezone-aware for comparison
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)

    diff = dt - now

    # If already passed
    if diff.total_seconds() <= 0:
        return "shortly"

    total_minutes = int(diff.total_seconds() / 60)
    total_hours = int(diff.total_seconds() / 3600)
    total_days = int(diff.total_seconds() / 86400)

    if total_minutes < 1:
        return "in less than a minute"
    elif total_minutes == 1:
        return "in 1 minute"
    elif total_minutes < 60:
        return f"in {total_minutes} minutes"
    elif total_hours == 1:
        return "in 1 hour"
    elif total_hours < 24:
        return f"in {total_hours} hours"
    elif total_days == 1:
        return "in 1 day"
    else:
        return f"in {total_days} days"
