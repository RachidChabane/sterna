import { commandRegistry } from '../registry'
import { ConversationsProvider } from './ConversationsProvider'
import { VoiceRoomsProvider } from './VoiceRoomsProvider'
import { IntegrationsProvider } from './IntegrationsProvider'
import { ImagesProvider } from './ImagesProvider'
import { VideosProvider } from './VideosProvider'
import { SparksProvider } from './SparksProvider'
import { createModelsProvider } from './ModelsProvider'
import useModelStore from '@/store/modelStore'

/**
 * Setup Command Providers
 *
 * Registers all providers with the command registry
 * Call this once on app initialization
 */
export function setupCommandProviders(): void {
  // Clear any existing providers
  commandRegistry.clear()

  // Register Conversations Provider
  commandRegistry.register(new ConversationsProvider())

  // Register Voice Rooms Provider
  commandRegistry.register(new VoiceRoomsProvider())

  // Register Models Provider (factory pattern for store injection)
  commandRegistry.register(
    createModelsProvider(() => useModelStore.getState())
  )

  // Register Integrations Provider (preconfigured MCP servers)
  commandRegistry.register(new IntegrationsProvider())

  // Register Images Provider
  commandRegistry.register(new ImagesProvider())

  // Register Videos Provider
  commandRegistry.register(new VideosProvider())

  // Register Sparks Provider
  commandRegistry.register(new SparksProvider())
}

// Re-export for convenience
export { commandRegistry }
