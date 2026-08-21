import React, { useCallback } from 'react'
import { useAuthStore } from '@/store/authStore'
import { useVerificationGateStore } from '@/store/verificationGateStore'

export function useVerificationGuard() {
  const isVerified = useAuthStore((s) => s.user?.is_verified ?? true)
  const openGate = useVerificationGateStore((s) => s.open)

  const guard = useCallback(
    <T extends (...args: any[]) => any>(fn: T, reason = 'continue'): T => {
      return ((...args: Parameters<T>) => {
        if (!isVerified) {
          openGate(reason)
          return undefined as ReturnType<T>
        }
        return fn(...args)
      }) as T
    },
    [isVerified, openGate],
  )

  return { guard, isVerified }
}

type GateChild = React.ReactElement<{ onClick?: (...args: any[]) => any }>

export function VerificationGate({
  children,
  reason = 'continue',
}: {
  children: GateChild
  reason?: string
}) {
  const { guard } = useVerificationGuard()
  const child = React.Children.only(children)
  return React.cloneElement(child, {
    onClick: guard(child.props.onClick ?? (() => {}), reason),
  })
}
