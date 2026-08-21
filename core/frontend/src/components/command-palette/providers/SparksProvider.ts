import { Zap } from 'lucide-react'
import type { CommandProvider, SparkCommandItem } from '../types'
import { matchQuery, scoreMatch } from '../utils/search'
import { sparksAPI, type Spark } from '@/api/sparks'

/**
 * Sparks Provider
 *
 * Provides search for AI-generated Sparks (interactive React components)
 */
export class SparksProvider implements CommandProvider {
  id = 'sparks'
  name = 'Sparks'
  icon = Zap
  priority = 5

  private cache: Spark[] = []
  private lastFetch = 0
  private CACHE_TTL = 60000 // 1 minute

  private async loadSparks(): Promise<Spark[]> {
    const now = Date.now()

    // Use cache if fresh
    if (this.cache.length > 0 && now - this.lastFetch < this.CACHE_TTL) {
      return this.cache
    }

    try {
      const response = await sparksAPI.list({
        page: 1,
        page_size: 50,
      })
      this.cache = response.results
      this.lastFetch = now
      return this.cache
    } catch (error) {
      console.error('[SparksProvider] Failed to load sparks:', error)
      return this.cache
    }
  }

  async getItems(query: string): Promise<SparkCommandItem[]> {
    // Only search if there's a query
    if (!query || query.length < 2) return []

    const sparks = await this.loadSparks()

    // Filter by query (search title and framework)
    const filtered = sparks.filter((spark) => {
      const searchText = [spark.title, spark.framework].filter(Boolean).join(' ')
      return matchQuery(searchText, query)
    })

    // Sort by match score
    const scored = filtered.map((spark) => ({
      spark,
      score: scoreMatch(spark.title, query),
    }))

    scored.sort((a, b) => b.score - a.score)

    // Limit results
    const limited = scored.slice(0, 8)

    return limited.map(({ spark }) => ({
      id: `spark-${spark.id}`,
      type: 'spark' as const,
      title: spark.title,
      subtitle: `${spark.framework} \u00B7 v${spark.version}`,
      icon: Zap,
      sparkId: spark.id,
      framework: spark.framework,
      version: spark.version,
      onSelect: () => {
        // Store selected spark ID for the page to pick up
        sessionStorage.setItem('selected-spark', spark.id)
      },
    }))
  }
}
