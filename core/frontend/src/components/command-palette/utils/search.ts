/**
 * Search Utilities
 *
 * Helpers for searching and scoring command items
 */

/**
 * Check if text matches a search query
 * Supports multi-term search (all terms must match)
 */
export function matchQuery(text: string, query: string): boolean {
  if (!query) return true

  const normalized = text.toLowerCase()
  const terms = query.toLowerCase().trim().split(/\s+/)

  return terms.every((term) => normalized.includes(term))
}

/**
 * Calculate match score for sorting results
 * Higher score = better match
 *
 * Scoring rules:
 * - Exact match: 100
 * - Starts with query: 80
 * - Word boundary match: 70
 * - Contains query: 60
 * - Fuzzy match: 40
 */
export function scoreMatch(text: string, query: string): number {
  if (!query) return 0

  const normalized = text.toLowerCase()
  const q = query.toLowerCase().trim()

  // Exact match
  if (normalized === q) return 100

  // Starts with query
  if (normalized.startsWith(q)) return 80

  // Word boundary match (query at start of a word)
  const words = normalized.split(/[\s-_/]+/)
  if (words.some((word) => word.startsWith(q))) return 70

  // Contains query
  if (normalized.includes(q)) return 60

  // Fuzzy match (all characters present in order)
  if (fuzzyMatch(normalized, q)) return 40

  return 0
}

/**
 * Check if all characters in query appear in text in order
 */
function fuzzyMatch(text: string, query: string): boolean {
  let textIndex = 0
  let queryIndex = 0

  while (textIndex < text.length && queryIndex < query.length) {
    if (text[textIndex] === query[queryIndex]) {
      queryIndex++
    }
    textIndex++
  }

  return queryIndex === query.length
}

/**
 * Highlight matching parts of text
 * Returns array of { text, highlighted } objects
 */
export function highlightMatches(
  text: string,
  query: string
): Array<{ text: string; highlighted: boolean }> {
  if (!query) return [{ text, highlighted: false }]

  const parts: Array<{ text: string; highlighted: boolean }> = []
  const normalized = text.toLowerCase()
  const q = query.toLowerCase()

  let lastIndex = 0
  let index = normalized.indexOf(q)

  while (index !== -1) {
    // Add non-matching part before
    if (index > lastIndex) {
      parts.push({
        text: text.substring(lastIndex, index),
        highlighted: false,
      })
    }

    // Add matching part
    parts.push({
      text: text.substring(index, index + q.length),
      highlighted: true,
    })

    lastIndex = index + q.length
    index = normalized.indexOf(q, lastIndex)
  }

  // Add remaining non-matching part
  if (lastIndex < text.length) {
    parts.push({
      text: text.substring(lastIndex),
      highlighted: false,
    })
  }

  return parts
}
