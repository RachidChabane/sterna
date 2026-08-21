/**
 * Sharing UI Components
 *
 * Reusable components for share platform buttons.
 */

import { type SharePlatform } from './platforms'

interface PlatformIconProps {
  platform: SharePlatform
  size?: number
}

/**
 * Renders the platform icon with brand colors
 */
export function PlatformIcon({ platform, size = 16 }: PlatformIconProps) {
  return (
    <svg
      className="text-white"
      style={{ width: size, height: size }}
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <path d={platform.iconPath} />
    </svg>
  )
}

interface PlatformBadgeProps {
  platform: SharePlatform
  size?: 'sm' | 'md' | 'lg'
}

const badgeSizes = {
  sm: { container: 'w-8 h-8', icon: 16 },
  md: { container: 'w-10 h-10', icon: 18 },
  lg: { container: 'w-12 h-12', icon: 20 },
}

/**
 * Renders a circular badge with platform icon and brand color
 */
export function PlatformBadge({ platform, size = 'md' }: PlatformBadgeProps) {
  const { container, icon } = badgeSizes[size]

  return (
    <div
      className={`${container} rounded-full flex items-center justify-center`}
      style={{ backgroundColor: platform.color }}
    >
      <PlatformIcon platform={platform} size={icon} />
    </div>
  )
}
