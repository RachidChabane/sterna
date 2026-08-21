import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/sparks')({
  beforeLoad: () => {
    throw redirect({ to: '/creations', search: { tab: 'sparks' } })
  },
})
