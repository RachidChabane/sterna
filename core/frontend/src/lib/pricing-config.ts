/**
 * Pricing configuration for LLM models.
 *
 * This module centralizes all pricing-related constants to enable easy switching
 * between different pricing units (e.g., per 1K tokens vs per 1M tokens).
 *
 * To change the display unit:
 * 1. Modify DISPLAY_UNIT (e.g., 1000 for 1K, 1_000_000 for 1M)
 * 2. Update DISPLAY_UNIT_LABEL accordingly (e.g., "1K" or "1M")
 * 3. Update DISPLAY_UNIT_LABEL_LONG for full text
 */

export const PRICING_CONFIG = {
  /**
   * The unit used for displaying prices (1M = 1,000,000 tokens)
   * Change this to 1000 to display prices per 1K tokens instead
   */
  DISPLAY_UNIT: 1_000_000,

  /**
   * Short label for the display unit (shown in compact UI)
   */
  DISPLAY_UNIT_LABEL: '1M',

  /**
   * Long label for the display unit (shown in detailed UI)
   */
  DISPLAY_UNIT_LABEL_LONG: 'per 1M tokens',

  /**
   * Divisor used to calculate costs from token counts
   * Must match DISPLAY_UNIT for correct calculations
   */
  TOKEN_DIVISOR: 1_000_000,

  /**
   * Storage unit on the backend (always per 1K tokens)
   * Used for converting API thresholds to display unit
   */
  STORAGE_UNIT: 1000,

  /**
   * Cost estimation scenarios for comparison purposes
   */
  COMPARISON_SCENARIOS: {
    /**
     * Typical request scenario for cost per 1000 requests calculation
     * Based on common usage patterns: moderate prompt, detailed response
     */
    TYPICAL_REQUEST: {
      /** Average prompt tokens in a typical request */
      PROMPT_TOKENS: 500,
      /** Average completion tokens in a typical response */
      COMPLETION_TOKENS: 1500,
      /** Number of requests to calculate batch cost for */
      REQUEST_COUNT: 1000,
    },
  },

  /**
   * Performance score weights for model comparison
   * Used to calculate relative performance scores across models
   */
  PERFORMANCE_WEIGHTS: {
    /** Multiplier for cost efficiency score */
    COST_SCORE_MULTIPLIER: 100,
    /** Divisor for normalizing token capacity */
    TOKEN_SCORE_DIVISOR: 100000,
    /** Multiplier for token capacity contribution to score */
    TOKEN_SCORE_MULTIPLIER: 50,
    /** Score points awarded per supported capability */
    CAPABILITY_SCORE_PER_FEATURE: 25,
  },

  /**
   * Heuristics for classifying models into pricing-oriented quality tiers
   * Thresholds are expressed in display unit pricing (per 1M tokens by default)
   */
  QUALITY_TIER_THRESHOLDS: {
    BUDGET_MAX_USD_PER_DISPLAY_UNIT: 1,
    BALANCED_MAX_USD_PER_DISPLAY_UNIT: 10,
  },
} as const

/**
 * Get the conversion factor from storage unit to display unit
 */
export const getConversionFactor = () =>
  PRICING_CONFIG.DISPLAY_UNIT / PRICING_CONFIG.STORAGE_UNIT
