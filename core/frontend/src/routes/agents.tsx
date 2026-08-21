import { createFileRoute } from '@tanstack/react-router'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import SubAgentsPage from '@/pages/SubAgentsPage'

export const Route = createFileRoute('/agents')({
  component: () => (
    <ProtectedRoute>
      <SubAgentsPage />
    </ProtectedRoute>
  ),
})
