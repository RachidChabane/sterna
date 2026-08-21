"""
Pricing configuration for LLM models.

This module centralizes all pricing-related constants to enable easy switching
between different pricing units (e.g., per 1K tokens vs per 1M tokens).

To change the display unit:
1. Modify PRICE_DISPLAY_UNIT (e.g., 1000 for 1K, 1_000_000 for 1M)
2. Update PRICE_UNIT_LABEL accordingly (e.g., "1K" or "1M")
"""

# Storage unit: how prices are stored in the database
PRICE_STORAGE_UNIT = 1000  # Prices stored as "per 1K tokens" in DB

# Display unit: how prices are exposed via API and shown in UI
PRICE_DISPLAY_UNIT = 1_000_000  # Exposed as "per 1M tokens"

# Conversion factor from storage to display unit
PRICE_CONVERSION_FACTOR = PRICE_DISPLAY_UNIT // PRICE_STORAGE_UNIT  # = 1000

# Human-readable label for the display unit
PRICE_UNIT_LABEL = "1M"
PRICE_UNIT_LABEL_LONG = "per 1M tokens"


def convert_to_display_unit(storage_value):
    """
    Convert a price from storage unit to display unit.

    Args:
        storage_value: Price in storage unit (per 1K tokens)

    Returns:
        Price in display unit (per 1M tokens)
    """
    if storage_value is None:
        return None
    return storage_value * PRICE_CONVERSION_FACTOR
