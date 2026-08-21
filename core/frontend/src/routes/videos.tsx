import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/videos')({
  beforeLoad: () => {
    throw redirect({ to: '/creations', search: { tab: 'videos' } })
  },
})
