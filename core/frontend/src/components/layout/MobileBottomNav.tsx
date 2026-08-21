/**
 * MobileBottomNav - Native-style bottom navigation for mobile
 *
 * Features:
 * - Thumb-friendly large touch targets (min 48px)
 * - Safe area inset support for notched devices
 * - Smooth animated active indicator
 * - Touch feedback on press
 * - Glassmorphism background
 */

import { memo, useCallback } from 'react'
import { Link, useRouterState } from '@tanstack/react-router'
import {
  Cpu,
  MessagesSquare,
  Mic,
  Puzzle,
  Code,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface NavItem {
  id: string
  name: string
  href: string
  icon: LucideIcon
}

// Primary navigation items for bottom bar (max 5 for thumb reach)
const primaryNavItems: NavItem[] = [
  { id: 'chats', name: 'Chats', href: '/chats', icon: MessagesSquare },
  { id: 'voice-rooms', name: 'Voice', href: '/voice-rooms', icon: Mic },
  { id: 'models', name: 'Models', href: '/models', icon: Cpu },
  { id: 'code', name: 'Code', href: '/code', icon: Code },
  { id: 'connectors', name: 'Tools', href: '/connectors', icon: Puzzle },
]

interface MobileBottomNavProps {
  className?: string
}

export const MobileBottomNav = memo(function MobileBottomNav({
  className,
}: MobileBottomNavProps) {
  const routerState = useRouterState()
  const pathname = routerState.location.pathname

  const isActive = useCallback(
    (href: string) => {
      if (href === '/') return pathname === '/'
      return pathname.startsWith(href)
    },
    [pathname]
  )

  return (
    <nav className={cn('mobile-bottom-nav', className)}>
      <div className="flex items-center justify-around px-2 h-14">
        {primaryNavItems.map((item) => {
          const active = isActive(item.href)
          const Icon = item.icon

          return (
            <Link
              key={item.id}
              to={item.href}
              className={cn('bottom-nav-item', active && 'active')}
              aria-current={active ? 'page' : undefined}
            >
              <Icon
                className={cn(
                  'nav-icon h-5 w-5',
                  active ? 'text-accent-brand' : 'text-muted-foreground'
                )}
                strokeWidth={active ? 2.5 : 2}
              />
              <span
                className={cn(
                  'nav-label',
                  active ? 'text-accent-brand' : 'text-muted-foreground'
                )}
              >
                {item.name}
              </span>
            </Link>
          )
        })}

      </div>
    </nav>
  )
})

export default MobileBottomNav
