import { Image } from 'lucide-react'
import type { CommandProvider, ImageCommandItem } from '../types'
import { matchQuery, scoreMatch } from '../utils/search'
import { assetsAPI, type GalleryAsset } from '@/api/assets'

/**
 * Images Provider
 *
 * Provides search for AI-generated images
 */
export class ImagesProvider implements CommandProvider {
  id = 'images'
  name = 'Images'
  icon = Image
  priority = 3

  private cache: GalleryAsset[] = []
  private lastFetch = 0
  private CACHE_TTL = 60000 // 1 minute

  private async loadImages(): Promise<GalleryAsset[]> {
    const now = Date.now()

    // Use cache if fresh
    if (this.cache.length > 0 && now - this.lastFetch < this.CACHE_TTL) {
      return this.cache
    }

    try {
      const response = await assetsAPI.listUserGeneratedImages({
        page: 1,
        page_size: 50,
      })
      this.cache = response.results
      this.lastFetch = now
      return this.cache
    } catch (error) {
      console.error('[ImagesProvider] Failed to load images:', error)
      return this.cache
    }
  }

  async getItems(query: string): Promise<ImageCommandItem[]> {
    // Only search if there's a query
    if (!query || query.length < 2) return []

    const images = await this.loadImages()

    // Filter by query (search prompt and model)
    const filtered = images.filter((img) => {
      const searchText = [
        img.generation_prompt,
        img.generation_model,
        img.generation_model_display_name,
      ]
        .filter(Boolean)
        .join(' ')
      return matchQuery(searchText, query)
    })

    // Sort by match score
    const scored = filtered.map((img) => ({
      img,
      score: scoreMatch(img.generation_prompt || '', query),
    }))

    scored.sort((a, b) => b.score - a.score)

    // Limit results
    const limited = scored.slice(0, 8)

    return limited.map(({ img }) => ({
      id: `image-${img.id}`,
      type: 'image' as const,
      title: truncatePrompt(img.generation_prompt || 'Generated image', 60),
      subtitle: img.generation_model_display_name || img.generation_model || undefined,
      icon: Image,
      imageId: img.id,
      prompt: img.generation_prompt ?? undefined,
      model: img.generation_model ?? undefined,
      onSelect: () => {
        // Store selected image ID for the gallery to pick up
        sessionStorage.setItem('selected-image', img.id)
      },
    }))
  }
}

function truncatePrompt(prompt: string, maxLength: number): string {
  if (prompt.length <= maxLength) return prompt
  return prompt.slice(0, maxLength - 3) + '...'
}
