import type { Model } from '@/api/llm'
import type { ModelCatalogEntry } from '@/types/models'

/**
 * Normalize an api/llm `Model` into a `ModelCatalogEntry`.
 *
 * The backend models endpoint (llm.serializers.ModelCatalogSerializer) always
 * serializes the full catalog shape, but `llmApi.models()` declares only the
 * narrower `Model` view. Components built on the model store (which uses
 * `ModelCatalogEntry`) need the full shape, so this fills the catalog-only
 * fields with safe defaults and lets any values actually present on the
 * runtime object win via the spread.
 */
export function toModelCatalogEntry(model: Model): ModelCatalogEntry {
  return {
    modality: null,
    tokenizer: null,
    max_completion_tokens: null,
    is_moderated: false,
    default_parameters: {},
    fetched_at: '',
    ...model,
    output_modalities: model.output_modalities ?? [],
    tags: model.tags ?? [],
    cost_per_1m_prompt: coerceCost(model.cost_per_1m_prompt),
    cost_per_1m_completion: coerceCost(model.cost_per_1m_completion),
  }
}

/**
 * Defensive cost coercion: the API declares costs as `number | null`, but some
 * backends serialize decimals as strings, so handle that at runtime too.
 */
function coerceCost(value: number | null): number {
  if (value == null) return 0
  return typeof value === 'string' ? parseFloat(value) : value
}
