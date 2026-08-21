import { createFileRoute } from '@tanstack/react-router'
import { AuthShell } from '@/components/auth/AuthShell'
import { SignupForm } from '@/components/auth/SignupForm'

type SignupSearch = { return_to?: string }

export const Route = createFileRoute('/signup')({
  validateSearch: (s: Record<string, unknown>): SignupSearch => ({
    return_to: typeof s.return_to === 'string' ? s.return_to : undefined,
  }),
  component: SignupPage,
})

function SignupPage() {
  return (
    <AuthShell
      title="Create your account"
      subtitle="Get started in seconds. No credit card required."
    >
      <SignupForm />
    </AuthShell>
  )
}
