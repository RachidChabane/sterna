import type { LucideIcon } from 'lucide-react'
import type { ModelCatalogEntry } from '@/types/models'
import type { MCPPreconfiguredServer } from '@/api/mcp'

/**
 * Command Palette Types
 *
 * Type definitions for the extensible command palette system
 */

// Supported item types
type CommandItemType = 'page' | 'conversation' | 'model' | 'action' | 'integration' | 'image' | 'video' | 'spark'

// Base command item interface
interface BaseCommandItem {
  id: string
  type: CommandItemType
  title: string
  subtitle?: string
  icon: LucideIcon | React.ReactNode
  keywords?: string[] // Additional search terms
  badge?: string // Display badge (e.g., "Current", "Favorite")
  onSelect: () => void
}

// Page navigation item
interface PageCommandItem extends BaseCommandItem {
  type: 'page'
  href: string
}

// Conversation/chat item
export interface ConversationCommandItem extends BaseCommandItem {
  type: 'conversation'
  conversationId: string
  preview?: string // First message preview
  updatedAt: Date
}

// Model item with actions
export interface ModelCommandItem extends BaseCommandItem {
  type: 'model'
  modelId: string
  provider: string
  isFavorite: boolean
  isSelected: boolean
  isCurrent: boolean
  actions?: CommandItemAction[]
  /** Full model data used for rendering the model icon */
  _modelData?: ModelCatalogEntry
}

// Action item (quick actions)
export interface ActionCommandItem extends BaseCommandItem {
  type: 'action'
  actionId: string
}

// Integration item (MCP servers/integrations)
export interface IntegrationCommandItem extends BaseCommandItem {
  type: 'integration'
  integrationId: string
  category?: string
  isConnected?: boolean
  toolsCount?: number
  /** Full server data used for rendering the server icon */
  _serverData?: MCPPreconfiguredServer
}

// Action for model items
interface CommandItemAction {
  label: string
  icon: LucideIcon
  onClick: (e: React.MouseEvent) => void
}

// Image item
export interface ImageCommandItem extends BaseCommandItem {
  type: 'image'
  imageId: string
  prompt?: string
  model?: string
  thumbnailUrl?: string
}

// Video item
export interface VideoCommandItem extends BaseCommandItem {
  type: 'video'
  videoId: string
  prompt?: string
  model?: string
  duration?: number
}

// Spark item
export interface SparkCommandItem extends BaseCommandItem {
  type: 'spark'
  sparkId: string
  framework: string
  version: number
}

// Union type for all command items
export type CommandItem =
  | PageCommandItem
  | ConversationCommandItem
  | ModelCommandItem
  | ActionCommandItem
  | IntegrationCommandItem
  | ImageCommandItem
  | VideoCommandItem
  | SparkCommandItem

// Provider interface
export interface CommandProvider {
  id: string
  name: string
  icon: LucideIcon
  priority: number // Display order (lower = first)
  getItems(query: string): Promise<CommandItem[]> | CommandItem[]
  isEnabled?(): boolean // Optional: dynamic enable/disable
}

// Grouped results from providers
export interface GroupedCommandItems {
  provider: CommandProvider
  items: CommandItem[]
}
