import {
  Terminal,
  Cpu,
  MessagesSquare,
  SquarePen,
  Mic,
  Puzzle,
  GalleryVerticalEnd,
  BookOpen,
  type LucideIcon,
} from 'lucide-react'

/**
 * Navigation Item with optional keywords for search
 */
export interface NavigationItemConfig {
  id: string
  name: string
  href: string
  icon: LucideIcon
  keywords?: string[]
  comingSoon?: boolean
  beta?: boolean
}

/**
 * Default Navigation Items
 *
 * Single source of truth for all navigation items in the app.
 * Used by:
 * - Sidebar navigation
 * - Command Palette search
 * - Mobile menu
 */
export const defaultNavigation: NavigationItemConfig[] = [
  {
    id: 'new-chat',
    name: 'New Chat',
    href: '/chats?new=true',
    icon: SquarePen,
    keywords: ['new', 'chat', 'conversation', 'message', 'compose'],
  },
  {
    id: 'chats',
    name: 'Chats',
    href: '/search',
    icon: MessagesSquare,
    keywords: ['conversations', 'search', 'history', 'messages'],
  },
  {
    id: 'models',
    name: 'Models',
    href: '/models',
    icon: Cpu,
    keywords: ['ai', 'llm', 'catalog', 'language models'],
  },
  {
    id: 'creations',
    name: 'Creations',
    href: '/creations',
    icon: GalleryVerticalEnd,
    keywords: ['sparks', 'artifacts', 'images', 'videos', 'generated', 'gallery', 'components', 'react', 'interactive'],
  },
  {
    id: 'knowledge',
    name: 'Knowledge',
    href: '/knowledge',
    icon: BookOpen,
    keywords: ['knowledge base', 'documents', 'rag', 'search', 'upload', 'pdf', 'files'],
  },
  {
    id: 'voice-rooms',
    name: 'Voice Rooms',
    href: '/voice-rooms',
    icon: Mic,
    keywords: ['voice', 'audio', 'speech', 'conversation', 'talk', 'agents'],
    beta: true,
  },
  {
    id: 'agents',
    name: 'Agents',
    href: '/agents',
    icon: Terminal,
    keywords: ['agents', 'sub-agents', 'automation', 'custom', 'delegation', 'sandbox'],
    beta: true,
  },
  {
    id: 'connectors',
    name: 'Connectors',
    href: '/connectors',
    icon: Puzzle,
    keywords: ['integrations', 'connectors', 'apps', 'tools', 'services', 'mcp', 'oauth', 'api'],
  },
]
