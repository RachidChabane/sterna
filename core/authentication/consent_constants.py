"""Consent-related constants shared between views, serializers, and tests."""

CONSENT_POLICY_VERSION = "1.0"

EU_REGION_SET = frozenset(
    {
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
        "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
        "PL", "PT", "RO", "SK", "SI", "ES", "SE",
        "IS", "LI", "NO",
        "GB", "CH",
    }
)

VALID_CATEGORIES = ("essential", "analytics", "marketing")
