import React, { useCallback } from 'react'
import { useAuthStore } from '@/store/authStore'
import { useVerificationGateStore } from '@/store/verificationGateStore'

export function useVerificationGuard() {
  const isVerified = useAuthStore((s) => s.user?.is_verified ?? true)
  const openGate = useVerificationGateStore((s) => s.open)

  const guard = useCallback(
    <Args extends unknown[], R>(fn: (...args: Args) => R, reason = 'continue') => {
      return (...args: Args): R | undefined => {
        if (!isVerified) {
          openGate(reason)
          return undefined
        }
        return fn(...args)
      }
    },
    [isVerified, openGate],
  )

  return { guard, isVerified }
}

type GateChild = React.ReactElement<{ onClick?: (...args: unknown[]) => unknown }>

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
