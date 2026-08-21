import { createFileRoute } from '@tanstack/react-router'
import ModelComparisonPage from '@/components/models/ModelComparisonPage'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'

type ChatsSearch = {
  conversation?: string
  new?: boolean
  fix_spark?: string
  fix_error?: string
  ignite?: string
  /** OAuth callback error code (e.g. invalid_state, github_connect_failed) */
  error?: string
}

export const Route = createFileRoute('/chats')({
  validateSearch: (search: Record<string, unknown>): ChatsSearch => {
    const newValue = search.new
    const isNew = newValue === true || newValue === 'true' || newValue === '"true"'
    return {
      conversation: typeof search.conversation === 'string' ? search.conversation : undefined,
      new: isNew || undefined,
      fix_spark: typeof search.fix_spark === 'string' ? search.fix_spark : undefined,
      fix_error: typeof search.fix_error === 'string' ? search.fix_error : undefined,
      ignite: typeof search.ignite === 'string' ? search.ignite : undefined,
      error: typeof search.error === 'string' ? search.error : undefined,
    }
  },
  component: () => (
    <ProtectedRoute>
      <ModelComparisonPage />
    </ProtectedRoute>
  ),
})