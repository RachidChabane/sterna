/**
 * Default values for LLM model parameters.
 *
 * ⚠️ BACKEND/FRONTEND SYNCHRONIZATION:
 * These values MUST be kept in sync with the backend configuration:
 * /core/consigliere/config.py -> ModelParametersDefaults
 *
 * Any changes here must be reflected in the backend and vice versa.
 * This ensures consistent behavior between API defaults and UI defaults.
 */

export const MODEL_PARAMETERS_DEFAULTS = {
  /**
   * Controls randomness in the output (0.0 = deterministic, 1.0+ = creative)
   * Range: 0.0 - 2.0 (typically 0.0 - 1.0)
   */
  TEMPERATURE: 0.7,

  /**
   * Maximum number of tokens in the response
   * This is a UI default only — the backend resolves to the model's
   * actual max_completion_tokens from the catalog.
   */
  MAX_TOKENS: 16384,

  /**
   * Nucleus sampling - probability mass to consider
   * Range: 0.0 - 1.0
   * 1.0 = consider all tokens
   */
  TOP_P: 1.0,

  /**
   * Top-K sampling - number of top tokens to consider
   * Range: 0 - infinity
   * 0 = disabled (consider all tokens)
   */
  TOP_K: 0,

  /**
   * Penalizes tokens based on their frequency in the text so far
   * Range: -2.0 - 2.0
   * Positive values decrease repetition
   */
  FREQUENCY_PENALTY: 0.0,

  /**
   * Penalizes tokens that have already appeared in the text
   * Range: -2.0 - 2.0
   * Positive values encourage topic diversity
   */
  PRESENCE_PENALTY: 0.0,

  /**
   * Penalizes repetition (alternative to frequency_penalty)
   * Range: 0.0 - 2.0
   * 1.0 = no penalty, >1.0 = penalize repetition
   */
  REPETITION_PENALTY: 1.0,

  /**
   * Minimum probability threshold for token selection
   * Range: 0.0 - 1.0
   * 0.0 = disabled
   */
  MIN_P: 0.0,

  /**
   * Top-A sampling parameter (advanced)
   * Range: 0.0 - 1.0
   * 0.0 = disabled
   */
  TOP_A: 0.0,

} as const

// Import the actual ModelParameters type from the source of truth
import type { ModelParameters } from '@/components/models/types'

/**
 * Get default model parameters as a complete ModelParameters object.
 * This includes all required fields from the ModelParameters interface.
 *
 * @returns Complete ModelParameters object with all default values
 */
export const getDefaultModelParameters = (): ModelParameters => ({
  // LLM sampling parameters (from constants)
  temperature: MODEL_PARAMETERS_DEFAULTS.TEMPERATURE,
  max_tokens: MODEL_PARAMETERS_DEFAULTS.MAX_TOKENS,
  top_p: MODEL_PARAMETERS_DEFAULTS.TOP_P,
  top_k: MODEL_PARAMETERS_DEFAULTS.TOP_K,
  frequency_penalty: MODEL_PARAMETERS_DEFAULTS.FREQUENCY_PENALTY,
  presence_penalty: MODEL_PARAMETERS_DEFAULTS.PRESENCE_PENALTY,
  repetition_penalty: MODEL_PARAMETERS_DEFAULTS.REPETITION_PENALTY,
  min_p: MODEL_PARAMETERS_DEFAULTS.MIN_P,
  top_a: MODEL_PARAMETERS_DEFAULTS.TOP_A,

  // Additional fields required by ModelParameters interface
  // All features enabled by default
  enable_streaming: true,
  enable_reasoning: true,
  reasoning_effort: 'medium' as const,
  enable_brave_search: true,
  enable_mcp_tools: true,
  enable_file_tools: true,
  enable_image_generation: true,
  enable_video_generation: true,
  enable_sparks: true,
  enable_knowledge_base: true,
  system_prompt: '',
  chat_memory: 8,
})
