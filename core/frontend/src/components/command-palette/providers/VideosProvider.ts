import { Film } from 'lucide-react'
import type { CommandProvider, VideoCommandItem } from '../types'
import { matchQuery, scoreMatch } from '../utils/search'
import { assetsAPI, type GalleryAsset } from '@/api/assets'

/**
 * Videos Provider
 *
 * Provides search for AI-generated videos
 */
export class VideosProvider implements CommandProvider {
  id = 'videos'
  name = 'Videos'
  icon = Film
  priority = 4

  private cache: GalleryAsset[] = []
  private lastFetch = 0
  private CACHE_TTL = 60000 // 1 minute

  private async loadVideos(): Promise<GalleryAsset[]> {
    const now = Date.now()

    // Use cache if fresh
    if (this.cache.length > 0 && now - this.lastFetch < this.CACHE_TTL) {
      return this.cache
    }

    try {
      const response = await assetsAPI.listUserGeneratedVideos({
        page: 1,
        page_size: 50,
      })
      this.cache = response.results
      this.lastFetch = now
      return this.cache
    } catch (error) {
      console.error('[VideosProvider] Failed to load videos:', error)
      return this.cache
    }
  }

  async getItems(query: string): Promise<VideoCommandItem[]> {
    // Only search if there's a query
    if (!query || query.length < 2) return []

    const videos = await this.loadVideos()

    // Filter by query (search prompt and model)
    const filtered = videos.filter((vid) => {
      const searchText = [
        vid.generation_prompt,
        vid.generation_model,
        vid.generation_model_display_name,
      ]
        .filter(Boolean)
        .join(' ')
      return matchQuery(searchText, query)
    })

    // Sort by match score
    const scored = filtered.map((vid) => ({
      vid,
      score: scoreMatch(vid.generation_prompt || '', query),
    }))

    scored.sort((a, b) => b.score - a.score)

    // Limit results
    const limited = scored.slice(0, 8)

    return limited.map(({ vid }) => ({
      id: `video-${vid.id}`,
      type: 'video' as const,
      title: truncatePrompt(vid.generation_prompt || 'Generated video', 60),
      subtitle: formatDuration(vid.duration_seconds) + (vid.generation_model_display_name ? ` \u00B7 ${vid.generation_model_display_name}` : ''),
      icon: Film,
      videoId: vid.id,
      prompt: vid.generation_prompt ?? undefined,
      model: vid.generation_model ?? undefined,
      duration: vid.duration_seconds || undefined,
      onSelect: () => {
        // Store selected video ID for the gallery to pick up
        sessionStorage.setItem('selected-video', vid.id)
      },
    }))
  }
}

function truncatePrompt(prompt: string, maxLength: number): string {
  if (prompt.length <= maxLength) return prompt
  return prompt.slice(0, maxLength - 3) + '...'
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}
