import { Sparkles, Users, Settings2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/** One tab in the create/edit room wizard's step indicator. */
export interface ModalStep {
  id: number
  label: string
  icon: LucideIcon
}

export const MODAL_STEPS: ModalStep[] = [
  { id: 1, label: 'Basics', icon: Sparkles },
  { id: 2, label: 'Agents', icon: Users },
  { id: 3, label: 'Voice', icon: Settings2 },
]
