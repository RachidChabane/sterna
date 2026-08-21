import { create } from 'zustand'

interface VerificationGateState {
  isOpen: boolean
  reason: string
  open: (reason?: string) => void
  close: () => void
}

export const useVerificationGateStore = create<VerificationGateState>((set) => ({
  isOpen: false,
  reason: 'continue',
  open: (reason = 'continue') => set({ isOpen: true, reason }),
  close: () => set({ isOpen: false }),
}))
