import { Plug } from 'lucide-react'
import type { CommandProvider, IntegrationCommandItem } from '../types'
import { matchQuery, scoreMatch } from '../utils/search'
import { mcpApi, type MCPPreconfiguredServer } from '@/api/mcp'

/**
 * Connectors Provider
 *
 * Provides search for preconfigured MCP servers/connectors
 * Allows users to discover and connect to available connectors
 */

// Cache for preconfigured servers
let cachedServers: MCPPreconfiguredServer[] = []
let cacheTimestamp = 0
const CACHE_TTL = 5 * 60 * 1000 // 5 minutes

async function getPreconfiguredServers(): Promise<MCPPreconfiguredServer[]> {
  const now = Date.now()

  // Return cached data if still valid
  if (cachedServers.length > 0 && now - cacheTimestamp < CACHE_TTL) {
    return cachedServers
  }

  try {
    const response = await mcpApi.listPreconfiguredServers({ page_size: 100 })
    cachedServers = response.data.results
    cacheTimestamp = now
    return cachedServers
  } catch (error) {
    console.error('Failed to fetch preconfigured servers:', error)
    // Return cached data even if stale, or empty array
    return cachedServers
  }
}

export class IntegrationsProvider implements CommandProvider {
  id = 'connectors'
  name = 'Connectors'
  icon = Plug
  priority = 3 // Show after models

  async getItems(query: string): Promise<IntegrationCommandItem[]> {
    const servers = await getPreconfiguredServers()

    if (servers.length === 0) {
      return []
    }

    // Filter servers by query
    const filtered = servers.filter((server) => {
      const nameMatch = matchQuery(server.name, query)
      const descMatch = matchQuery(server.description || '', query)
      const categoryMatch = matchQuery(server.category || '', query)
      return nameMatch || descMatch || categoryMatch
    })

    // Score and sort
    const scored = filtered.map((server) => ({
      server,
      score: Math.max(
        scoreMatch(server.name, query),
        scoreMatch(server.description || '', query) * 0.8,
        scoreMatch(server.category || '', query) * 0.6
      ),
    }))

    scored.sort((a, b) => b.score - a.score)

    // Limit to 15 connectors for performance
    const limited = scored.slice(0, 15)

    // Convert to IntegrationCommandItems
    return limited.map(({ server }) => ({
      id: server.id,
      type: 'integration' as const,
      title: server.name,
      subtitle: server.description || server.category_display,
      icon: Plug,
      integrationId: server.id,
      category: server.category,
      toolsCount: server.tools_count,
      // Store server data for rendering custom icon
      _serverData: server,
      onSelect: () => {
        // Navigate to MCP/connectors page with the search pre-filled
        window.location.href = `/connectors?search=${encodeURIComponent(server.name)}`
      },
    } as IntegrationCommandItem & { _serverData: MCPPreconfiguredServer }))
  }

  isEnabled(): boolean {
    return true
  }
}
