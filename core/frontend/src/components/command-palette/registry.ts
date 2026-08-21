import type { CommandProvider, GroupedCommandItems } from './types'

/**
 * Command Registry
 *
 * Central registry for managing command providers
 * Handles provider registration and search across all providers
 */
export class CommandRegistry {
  private providers = new Map<string, CommandProvider>()

  /**
   * Register a new command provider
   */
  register(provider: CommandProvider): void {
    if (this.providers.has(provider.id)) {
      console.warn(`Provider "${provider.id}" is already registered`)
      return
    }
    this.providers.set(provider.id, provider)
  }

  /**
   * Unregister a command provider
   */
  unregister(providerId: string): void {
    this.providers.delete(providerId)
  }

  /**
   * Search across all enabled providers
   * Returns grouped results sorted by provider priority
   */
  async search(query: string): Promise<GroupedCommandItems[]> {
    // Get all enabled providers
    const enabledProviders = Array.from(this.providers.values()).filter(
      (provider) => !provider.isEnabled || provider.isEnabled()
    )

    // Search in parallel
    const resultsPromises = enabledProviders.map(async (provider) => {
      try {
        const items = await provider.getItems(query)
        return { provider, items }
      } catch (error) {
        console.error(`Error fetching items from provider "${provider.id}":`, error)
        return { provider, items: [] }
      }
    })

    const results = await Promise.all(resultsPromises)

    // Filter out empty results and sort by priority
    return results
      .filter((result) => result.items.length > 0)
      .sort((a, b) => a.provider.priority - b.provider.priority)
  }

  /**
   * Get all registered providers
   */
  getProviders(): CommandProvider[] {
    return Array.from(this.providers.values())
  }

  /**
   * Get a specific provider by ID
   */
  getProvider(providerId: string): CommandProvider | undefined {
    return this.providers.get(providerId)
  }

  /**
   * Clear all providers
   */
  clear(): void {
    this.providers.clear()
  }
}

// Singleton instance
export const commandRegistry = new CommandRegistry()
