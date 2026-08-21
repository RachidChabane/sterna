import { Mic } from 'lucide-react'
import type { CommandProvider, CommandItem } from '../types'
import { matchQuery, scoreMatch } from '../utils/search'
import useVoiceRoomStore from '@/store/voiceRoomStore'

/**
 * Format relative date
 */
function formatRelativeDate(date: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`
  return `${Math.floor(diffDays / 365)} years ago`
}

/**
 * Voice Rooms Provider
 *
 * Provides search for voice rooms
 */
export class VoiceRoomsProvider implements CommandProvider {
  id = 'voice-rooms'
  name = 'Voice Rooms'
  icon = Mic
  priority = 2 // Show after pages and conversations

  getItems(query: string): CommandItem[] {
    // Get rooms from store
    const rooms = useVoiceRoomStore.getState().rooms

    // Filter by query
    const filtered = rooms.filter((room) => {
      const nameMatch = matchQuery(room.name, query)
      const descMatch = room.description ? matchQuery(room.description, query) : false
      // Also match agent names
      const agentMatch = room.agents?.some((agent) =>
        matchQuery(agent.display_name, query)
      )
      return nameMatch || descMatch || agentMatch
    })

    // Sort by match score, then by date
    const scored = filtered.map((room) => ({
      room,
      score: Math.max(
        scoreMatch(room.name, query),
        room.description ? scoreMatch(room.description, query) : 0,
        ...(room.agents?.map((a) => scoreMatch(a.display_name, query)) || [])
      ),
    }))

    scored.sort((a, b) => {
      // First by score
      if (a.score !== b.score) return b.score - a.score
      // Then by date (newest first)
      const dateA = new Date(a.room.updated_at).getTime()
      const dateB = new Date(b.room.updated_at).getTime()
      return dateB - dateA
    })

    // Limit to 10 results for performance
    const limited = scored.slice(0, 10)

    // Convert to CommandItems
    return limited.map(({ room }) => {
      const agentCount = room.agents?.length || 0
      const agentNames = room.agents?.slice(0, 2).map((a) => a.display_name).join(', ')
      const subtitle = agentCount > 0
        ? `${agentNames}${agentCount > 2 ? ` +${agentCount - 2}` : ''} · ${formatRelativeDate(new Date(room.updated_at))}`
        : formatRelativeDate(new Date(room.updated_at))

      return {
        id: `voice-room-${room.id}`,
        type: 'action' as const,
        actionId: room.id,
        title: room.name,
        subtitle,
        icon: Mic,
        onSelect: () => {
          // Store the selected room ID for the voice rooms page to pick up
          sessionStorage.setItem('selected-voice-room', room.id)
        },
      }
    })
  }

  isEnabled(): boolean {
    // Only show if there are voice rooms
    return useVoiceRoomStore.getState().rooms.length > 0
  }
}
