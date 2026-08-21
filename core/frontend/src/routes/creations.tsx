import { createFileRoute } from '@tanstack/react-router'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { CreationsPage } from '@/components/creations/CreationsPage'

type CreationsSearch = {
  tab?: 'sparks' | 'images' | 'videos' | 'apps'
}

export const Route = createFileRoute('/creations')({
  validateSearch: (search: Record<string, unknown>): CreationsSearch => ({
    tab: ['sparks', 'images', 'videos', 'apps'].includes(search.tab as string)
      ? (search.tab as CreationsSearch['tab'])
      : undefined,
  }),
  component: () => (
    <ProtectedRoute>
      <CreationsPage />
    </ProtectedRoute>
  ),
})
