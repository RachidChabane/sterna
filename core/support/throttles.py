from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class SupportAnonThrottle(AnonRateThrottle):
    """5 submissions per hour per IP for anonymous users."""
    scope = "support_anon"


class SupportUserThrottle(UserRateThrottle):
    """10 submissions per day per authenticated user."""
    scope = "support_user"
