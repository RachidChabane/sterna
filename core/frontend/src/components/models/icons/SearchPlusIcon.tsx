/**
 * SearchPlusIcon Component
 *
 * Custom icon for Extended Search feature.
 * Displays a globe with a small plus symbol in the top-right corner.
 */

import { Globe, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SearchPlusIconProps {
  className?: string
}

export function SearchPlusIcon({ className }: SearchPlusIconProps) {
  return (
    <div className="relative inline-flex">
      <Globe className={className} />
      <Plus
        className={cn(
          "absolute -top-0.5 -right-0.5 bg-background rounded-full",
          className?.includes('w-') ? 'w-2 h-2' : 'w-2.5 h-2.5'
        )}
        strokeWidth={3}
      />
    </div>
  )
}
