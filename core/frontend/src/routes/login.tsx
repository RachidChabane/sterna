import { createFileRoute } from '@tanstack/react-router'
import { AuthShell } from '@/components/auth/AuthShell'
import { LoginForm } from '@/components/auth/LoginForm'

export const Route = createFileRoute('/login')({
  component: LoginPage,
})

function LoginPage() {
  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to your Sterna account"
    >
      <LoginForm />
    </AuthShell>
  )
}
