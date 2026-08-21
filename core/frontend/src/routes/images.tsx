import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/images')({
  beforeLoad: () => {
    throw redirect({ to: '/creations', search: { tab: 'images' } })
  },
})
