import { createFileRoute } from '@tanstack/react-router'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { SearchPage } from '@/pages/SearchPage'

type SearchSearch = {
  q?: string
}

export const Route = createFileRoute('/search')({
  validateSearch: (search: Record<string, unknown>): SearchSearch => ({
    q: typeof search.q === 'string' ? search.q : undefined,
  }),
  component: () => (
    <ProtectedRoute>
      <SearchPage />
    </ProtectedRoute>
  ),
})
