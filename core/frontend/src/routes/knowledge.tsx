import { createFileRoute } from '@tanstack/react-router'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import KnowledgeBasePage from '@/pages/KnowledgeBasePage'

export const Route = createFileRoute('/knowledge')({
  component: () => (
    <ProtectedRoute>
      <KnowledgeBasePage />
    </ProtectedRoute>
  ),
})
