import { createFileRoute } from '@tanstack/react-router'
import VoiceRoomPage from '@/components/voice-rooms/VoiceRoomPage'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'

type VoiceRoomsSearch = {
  room?: string
  new?: string
}

export const Route = createFileRoute('/voice-rooms')({
  validateSearch: (search: Record<string, unknown>): VoiceRoomsSearch => {
    return {
      room: typeof search.room === 'string' ? search.room : undefined,
      new: typeof search.new === 'string' ? search.new : undefined,
    }
  },
  component: () => (
    <ProtectedRoute>
      <VoiceRoomPage />
    </ProtectedRoute>
  ),
})
