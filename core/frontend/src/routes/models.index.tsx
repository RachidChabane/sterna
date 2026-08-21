import { createFileRoute } from '@tanstack/react-router'
import { ModelSelectionPage } from '@/pages/ModelSelectionPage'

export const Route = createFileRoute('/models/')({
  component: ModelSelectionPage,
})