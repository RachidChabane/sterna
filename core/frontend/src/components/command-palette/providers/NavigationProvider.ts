import { Compass } from 'lucide-react'
import type { CommandProvider, PageCommandItem } from '../types'
import { matchQuery, scoreMatch } from '../utils/search'
import { defaultNavigation } from '@/config/navigation'

/**
 * Navigation Provider
 *
 * Provides search for app pages/routes
 */
export class NavigationProvider implements CommandProvider {
  id = 'navigation'
  name = 'Pages'
  icon = Compass
  priority = 0 // Show first

  getItems(query: string): PageCommandItem[] {
    // Filter out coming soon items and filter navigation items by query
    const availableItems = defaultNavigation.filter(item => !item.comingSoon)

    const filtered = availableItems.filter((item) => {
      // Match against name or keywords
      const nameMatch = matchQuery(item.name, query)
      const keywordMatch = item.keywords?.some((keyword) => matchQuery(keyword, query))
      return nameMatch || keywordMatch
    })

    // Sort by match score
    const scored = filtered.map((item) => ({
      item,
      score: Math.max(
        scoreMatch(item.name, query),
        ...(item.keywords?.map((k) => scoreMatch(k, query)) || [])
      ),
    }))

    scored.sort((a, b) => b.score - a.score)

    // Convert to PageCommandItems
    return scored.map(({ item }) => ({
      id: item.id,
      type: 'page' as const,
      title: item.name,
      icon: item.icon,
      href: item.href,
      onSelect: () => {
        // Navigation will be handled by the component using useNavigate
        // We just provide the href
      },
    }))
  }
}
