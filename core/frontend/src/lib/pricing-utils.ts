/**
 * Pricing utility functions.
 *
 * These utilities provide a centralized way to handle pricing calculations
 * and formatting, making it easy to switch between different pricing units.
 */

import { PRICING_CONFIG, getConversionFactor } from './pricing-config'

export const pricingUtils = {
  /**
   * Calculate the cost for a given number of tokens.
   *
   * @param tokens - Number of tokens
   * @param costPerUnit - Cost per display unit (e.g., per 1M tokens)
   * @returns Total cost in USD
   *
   * @example
   * ```ts
   * // If costPerUnit is $5 per 1M tokens
   * pricingUtils.calculateCost(100_000, 5) // Returns 0.5 (100K tokens = $0.50)
   * ```
   */
  calculateCost(tokens: number, costPerUnit: number | null | undefined): number {
    if (costPerUnit == null) return 0
    return (tokens / PRICING_CONFIG.TOKEN_DIVISOR) * costPerUnit
  },

  /**
   * Format a cost value with the pricing unit label.
   *
   * @param cost - Cost value to format
   * @param decimals - Number of decimal places (default: 2)
   * @returns Formatted string like "$5.00/1M"
   */
  formatCostWithUnit(cost: number | null | undefined, decimals = 2): string {
    if (cost == null) return 'N/A'
    if (cost === 0) return 'Free'
    return `$${cost.toFixed(decimals)}/${PRICING_CONFIG.DISPLAY_UNIT_LABEL}`
  },

  /**
   * Format a cost value without the unit (just the dollar amount).
   *
   * @param cost - Cost value to format
   * @param decimals - Number of decimal places (default: 2)
   * @returns Formatted string like "$5.00"
   */
  formatCost(cost: number | null | undefined, decimals = 2): string {
    if (cost == null) return 'N/A'
    if (cost === 0) return 'Free'
    if (cost < 0.01) return '<$0.01'
    return `$${cost.toFixed(decimals)}`
  },

  /**
   * Format a cost value without the dollar symbol (for use with $ icons).
   * Use this when displaying cost alongside a DollarSign icon to avoid duplicates.
   *
   * @param cost - Cost value to format
   * @param decimals - Number of decimal places (default: 2)
   * @returns Formatted string like "5.00" or "<0.01"
   */
  formatCostWithoutSymbol(cost: number | null | undefined, decimals = 2): string {
    if (cost == null) return 'N/A'
    if (cost === 0) return 'Free'
    if (cost < 0.01) return '<0.01'
    return cost.toFixed(decimals)
  },

  /**
   * Format a cost value with unit but without the dollar symbol.
   * Use this when displaying cost with unit alongside a DollarSign icon.
   *
   * @param cost - Cost value to format
   * @param decimals - Number of decimal places (default: 2)
   * @returns Formatted string like "5.00/1M" or "Free"
   */
  formatCostWithUnitNoSymbol(cost: number | null | undefined, decimals = 2): string {
    if (cost == null) return 'N/A'
    if (cost === 0) return 'Free'
    return `${cost.toFixed(decimals)}/${PRICING_CONFIG.DISPLAY_UNIT_LABEL}`
  },

  /**
   * Get the short unit label (e.g., "1M").
   */
  getUnitLabel(): string {
    return PRICING_CONFIG.DISPLAY_UNIT_LABEL
  },

  /**
   * Get the long unit label (e.g., "per 1M tokens").
   */
  getUnitLabelLong(): string {
    return PRICING_CONFIG.DISPLAY_UNIT_LABEL_LONG
  },

  /**
   * Convert a threshold value from API storage unit to display unit.
   *
   * The API stores thresholds in "per 1K tokens", but we may want to display
   * them in "per 1M tokens" (or vice versa).
   *
   * @param apiThreshold - Threshold value from API (in storage unit)
   * @returns Threshold value in display unit
   *
   * @example
   * ```ts
   * // API returns threshold of 0.1 (per 1K), we want per 1M
   * pricingUtils.convertThreshold(0.1) // Returns 100 (0.1 * 1000)
   * ```
   */
  convertThreshold(apiThreshold: number): number {
    return apiThreshold * getConversionFactor()
  },

  /**
   * Format a cost for comparison display, showing relative difference.
   * Always displays values in dollars (not cents).
   *
   * @param cost - Cost to display
   * @returns Formatted cost with appropriate precision
   */
  formatComparisonCost(cost: number): string {
    if (cost === 0) return 'Free'
    if (cost < 0.01) return '<$0.01'
    if (cost < 10) return `$${cost.toFixed(2)}`
    if (cost < 1000) return `$${cost.toFixed(1)}`
    return `$${cost.toFixed(0)}`
  },

  /**
   * Format a cost value for display with smart formatting.
   * Uses toLocaleString for large values to add thousands separators.
   *
   * @param cost - Cost value to format
   * @returns Formatted string like "$5.00" or "$1,234.56"
   */
  formatCostDisplay(cost: number): string {
    if (cost === 0) return 'Free'
    if (cost < 0.01) return '<$0.01'
    if (cost < 100) return `$${cost.toFixed(2)}`
    return `$${cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  },
}
