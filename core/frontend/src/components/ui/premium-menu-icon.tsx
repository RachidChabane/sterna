/**
 * PremiumMenuIcon
 *
 * A minimal, modern menu icon with two offset lines.
 * More distinctive than the standard hamburger.
 */

import { cn } from '@/lib/utils'

interface PremiumMenuIconProps {
  className?: string
  size?: number
}

export function PremiumMenuIcon({ className, size = 16 }: PremiumMenuIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("text-current", className)}
    >
      {/* Top line - starts from left */}
      <rect
        x="2"
        y="5"
        width="10"
        height="2"
        rx="1"
        fill="currentColor"
      />
      {/* Bottom line - offset to the right */}
      <rect
        x="4"
        y="9"
        width="10"
        height="2"
        rx="1"
        fill="currentColor"
      />
    </svg>
  )
}
