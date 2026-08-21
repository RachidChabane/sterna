import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { Link, useRouterState, useNavigate } from '@tanstack/react-router'
import {
  X,
  Home,
  Play,
  TrendingUp,
  Cpu,
  Database,
  GitBranchPlus,
  MessagesSquare,
  User,
  LogOut,
  LogIn,
  Settings,
  Moon,
  Sun,
  Monitor,
  ChevronLeft,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  Image,
  Video,
  Plug,
  HelpCircle,
} from 'lucide-react'
import { useHelpDrawerStore } from '@/store/helpDrawerStore'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { SternaLogo } from '@/components/icons/SternaLogo'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ModelSelector } from '@/components/layout/ModelSelector'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { SortableNavItem } from '@/components/layout/SortableNavItem'
import { RecentActivity } from '@/components/layout/RecentActivity'
import { CommandPaletteSearchBar } from '@/components/command-palette/CommandPaletteSearchBar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/store/authStore'
import { useNavigationStore } from '@/store/navigationStore'
import type { NavigationItem } from '@/store/navigationStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useTheme } from '@/hooks/useTheme'
import { useOS } from '@/hooks/useOS'
import { useNavigationShortcuts } from '@/hooks/useNavigationShortcuts'
import { defaultNavigation } from '@/config/navigation'
import { ProfileEditModal } from '@/components/profile/ProfileEditModal'

export function Sidebar() {
  const [avatarError, setAvatarError] = useState(false)
  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const routerState = useRouterState()
  const pathname = routerState.location.pathname
  const navigate = useNavigate()
  const { isAuthenticated, user, logout } = useAuthStore()
  const { theme, setTheme } = useTheme()
  const openHelp = useHelpDrawerStore((s) => s.open)
  const { navigationOrder, setNavigationOrder, isCollapsed, setIsCollapsed, isMobileSidebarOpen, setMobileSidebarOpen } = useNavigationStore()
  const { openSettings } = useSettingsStore()
  const { isMac } = useOS()

  // Reset avatar error when user changes
  useEffect(() => {
    setAvatarError(false)
  }, [user?.avatar_url])

  // Initialize navigation order if empty
  useEffect(() => {
    if (navigationOrder.length === 0) {
      setNavigationOrder(defaultNavigation.map(item => item.id))
    }
  }, [navigationOrder, setNavigationOrder])

  // Swipe gesture handling for mobile sidebar
  const touchStartX = useRef(0)
  const touchStartY = useRef(0)
  const touchCurrentX = useRef(0)
  const touchCurrentY = useRef(0)

  const handleTouchStart = useCallback((e: TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
    touchStartY.current = e.touches[0].clientY
    touchCurrentX.current = e.touches[0].clientX
    touchCurrentY.current = e.touches[0].clientY
  }, [])

  const handleTouchMove = useCallback((e: TouchEvent) => {
    touchCurrentX.current = e.touches[0].clientX
    touchCurrentY.current = e.touches[0].clientY
  }, [])

  const handleTouchEnd = useCallback(() => {
    const deltaX = touchCurrentX.current - touchStartX.current
    const deltaY = touchCurrentY.current - touchStartY.current
    const absDeltaX = Math.abs(deltaX)
    const absDeltaY = Math.abs(deltaY)

    // Only trigger if horizontal movement is dominant and significant
    const isHorizontalSwipe = absDeltaX > absDeltaY && absDeltaX > 60

    // Swipe right from left edge to open (when closed)
    if (!isMobileSidebarOpen && touchStartX.current < 40 && deltaX > 60 && isHorizontalSwipe) {
      setMobileSidebarOpen(true)
    }
    // Swipe left to close (when open)
    else if (isMobileSidebarOpen && deltaX < -60 && isHorizontalSwipe) {
      setMobileSidebarOpen(false)
    }
  }, [isMobileSidebarOpen, setMobileSidebarOpen])

  // Add touch listeners for swipe gestures (mobile only)
  useEffect(() => {
    // Only add listeners on mobile
    const isMobile = window.innerWidth < 768
    if (!isMobile) return

    document.addEventListener('touchstart', handleTouchStart, { passive: true })
    document.addEventListener('touchmove', handleTouchMove, { passive: true })
    document.addEventListener('touchend', handleTouchEnd, { passive: true })

    return () => {
      document.removeEventListener('touchstart', handleTouchStart)
      document.removeEventListener('touchmove', handleTouchMove)
      document.removeEventListener('touchend', handleTouchEnd)
    }
  }, [handleTouchStart, handleTouchMove, handleTouchEnd])

  // Setup drag and drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  // Get ordered navigation items
  const orderedNavigation = useMemo(() => {
    if (navigationOrder.length === 0) return defaultNavigation

    const navMap = new Map(defaultNavigation.map(item => [item.id, item]))
    const ordered = navigationOrder
      .map(id => navMap.get(id))
      .filter((item): item is NavigationItem => item !== undefined)

    // Add any new items from defaultNavigation that aren't in navigationOrder yet
    const existingIds = new Set(ordered.map(item => item.id))
    const newItems = defaultNavigation.filter(item => !existingIds.has(item.id))

    return [...ordered, ...newItems]
  }, [navigationOrder])

  // Register keyboard shortcuts for sidebar navigation
  useNavigationShortcuts(orderedNavigation)

  // Sync navigationOrder with orderedNavigation when there are new items
  useEffect(() => {
    const currentIds = orderedNavigation.map(item => item.id)
    const hasNewItems = currentIds.length > navigationOrder.length
    const orderChanged = !currentIds.every((id, i) => id === navigationOrder[i])

    if (hasNewItems || orderChanged) {
      setNavigationOrder(currentIds)
    }
  }, [orderedNavigation, navigationOrder, setNavigationOrder])

  // Handle drag end
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      const oldIndex = navigationOrder.indexOf(active.id as string)
      const newIndex = navigationOrder.indexOf(over.id as string)

      const newOrder = arrayMove(navigationOrder, oldIndex, newIndex)
      setNavigationOrder(newOrder)
    }
  }

  const isActive = useMemo(() => {
    return (path: string, id?: string) => {
      // "New Chat" is an action link, never show as active
      if (id === 'new-chat') return false
      if (path === '/') {
        return pathname === '/'
      }
      // Strip query params for comparison
      const basePath = path.split('?')[0]
      return pathname.startsWith(basePath)
    }
  }, [pathname])

  // Don't render sidebar on auth pages
  if (pathname === '/login' || pathname === '/signup') {
    return null
  }

  const handleLogout = async () => {
    await logout()
    navigate({ to: '/login' })
  }

  return (
    <>
      {/* Desktop Sidebar */}
      <aside
        className={cn(
          "hidden md:flex flex-col bg-card border-r border-border transition-all duration-300",
          isCollapsed ? "w-16" : "w-64"
        )}
      >
        {/* Logo Section */}
        <div className="h-14 flex items-center justify-between px-2">
          {!isCollapsed ? (
            <>
              <Link to="/chats" className="flex items-center gap-2.5 group overflow-hidden px-2.5">
                <SternaLogo size={22} className="text-foreground flex-shrink-0" />
                <span className="text-base font-semibold text-foreground whitespace-nowrap transition-all duration-300">
                  Sterna
                </span>
              </Link>
              <button
                onClick={() => setIsCollapsed(true)}
                className="hidden lg:flex p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                title="Collapse sidebar"
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            </>
          ) : (
            <button
              onClick={() => setIsCollapsed(false)}
              className="hidden lg:flex items-center justify-center w-full group"
              title="Expand sidebar"
            >
              <SternaLogo size={22} className="text-foreground group-hover:hidden" />
              <PanelLeftOpen className="h-[22px] w-[22px] text-muted-foreground hidden group-hover:block" />
            </button>
          )}
        </div>

        {/* Navigation */}
        <nav aria-label="Main navigation" className="pb-2 flex-shrink-0 px-2">
          <TooltipProvider>
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={orderedNavigation.map(item => item.id)}
                strategy={verticalListSortingStrategy}
              >
                <div className={cn("space-y-0.5", isCollapsed && "flex flex-col items-center")}>
                  {orderedNavigation.map((item, i) => (
                    <SortableNavItem
                      key={item.id}
                      id={item.id}
                      name={item.name}
                      href={item.href}
                      icon={item.icon}
                      isActive={isActive(item.href, item.id)}
                      isCollapsed={isCollapsed}
                      comingSoon={item.comingSoon}
                      beta={item.beta}
                      shortcutNumber={i < 8 ? i + 1 : undefined}
                      isMac={isMac}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          </TooltipProvider>
        </nav>

        {/* Recent Activity - fills remaining space */}
        <RecentActivity isCollapsed={isCollapsed} />

        {/* Bottom Section */}
        <div className={cn("border-t border-border", isCollapsed ? "py-2 px-2 flex flex-col items-center gap-1" : "px-3 py-3.5 space-y-2")}>
          {/* Command Palette Search Bar */}
          {isAuthenticated && (
            <CommandPaletteSearchBar isCollapsed={isCollapsed} />
          )}

          {/* Model Selector */}
          {isAuthenticated && (
            <div className={cn(
              "space-y-1.5 overflow-hidden transition-all duration-300",
              isCollapsed ? "h-0 opacity-0" : "opacity-100"
            )}>
              <span className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider px-0.5 whitespace-nowrap leading-none">Model</span>
              <ModelSelector />
            </div>
          )}

          {/* User Menu */}
          {isAuthenticated && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className={cn(
                    "flex items-center rounded-md hover:bg-muted transition-colors",
                    isCollapsed ? "justify-center p-1" : "w-full gap-2.5 p-1.5"
                  )}
                >
                  {user?.avatar_url && !avatarError ? (
                    <img
                      src={user.avatar_url}
                      alt={`${user.first_name} ${user.last_name}`}
                      className="h-8 w-8 rounded-full object-cover flex-shrink-0 ring-1 ring-border"
                      crossOrigin="anonymous"
                      onError={() => setAvatarError(true)}
                    />
                  ) : (
                    <div className="h-8 w-8 rounded-full gradient-primary flex items-center justify-center flex-shrink-0">
                      <User className="h-4 w-4 text-white" />
                    </div>
                  )}
                  <div className={cn(
                    "flex-1 text-left overflow-hidden transition-all duration-300",
                    isCollapsed ? "w-0 opacity-0" : "opacity-100"
                  )}>
                    <p className="text-[13px] font-medium truncate whitespace-nowrap">
                      {user?.first_name} {user?.last_name}
                    </p>
                    <p className="text-[11px] text-muted-foreground truncate whitespace-nowrap">
                      {user?.email}
                    </p>
                  </div>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-56" align="end" side="right">
                <button
                  onClick={() => setProfileModalOpen(true)}
                  className="w-full px-2 py-1.5 text-left hover:bg-muted rounded-sm transition-colors cursor-pointer"
                >
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-medium leading-none">
                      {user?.first_name} {user?.last_name}
                    </p>
                    <p className="text-xs leading-none text-muted-foreground">
                      {user?.email}
                    </p>
                  </div>
                </button>
                <DropdownMenuSeparator />
                <div className="px-2 py-1.5">
                  <p className="text-[11px] font-medium text-muted-foreground mb-1.5">Theme</p>
                  <ToggleGroup type="single" value={theme} onValueChange={(value) => value && setTheme(value as 'light' | 'dark' | 'system')} className="justify-start gap-1">
                    <ToggleGroupItem value="light" aria-label="Light theme" className="h-7 w-7 p-0">
                      <Sun className="h-3.5 w-3.5" />
                    </ToggleGroupItem>
                    <ToggleGroupItem value="system" aria-label="System theme" className="h-7 w-7 p-0">
                      <Monitor className="h-3.5 w-3.5" />
                    </ToggleGroupItem>
                    <ToggleGroupItem value="dark" aria-label="Dark theme" className="h-7 w-7 p-0">
                      <Moon className="h-3.5 w-3.5" />
                    </ToggleGroupItem>
                  </ToggleGroup>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => openHelp('faq')}>
                  <HelpCircle className="mr-2 h-4 w-4" />
                  <span>Help &amp; Support</span>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => openSettings()}>
                  <Settings className="mr-2 h-4 w-4" />
                  <span>Settings</span>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleLogout}>
                  <LogOut className="mr-2 h-4 w-4" />
                  <span>Log out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          {/* Sign In Button & Theme - When not authenticated */}
          {!isAuthenticated && (
            <>
              <div className={cn(
                "space-y-1.5 overflow-hidden transition-all duration-300",
                isCollapsed ? "h-0 opacity-0" : "opacity-100"
              )}>
                <span className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider px-0.5 whitespace-nowrap">Theme</span>
                <ToggleGroup type="single" value={theme} onValueChange={(value) => value && setTheme(value as 'light' | 'dark' | 'system')} className="justify-start gap-1">
                  <ToggleGroupItem value="light" aria-label="Light theme" className="h-7 w-7 p-0">
                    <Sun className="h-3.5 w-3.5" />
                  </ToggleGroupItem>
                  <ToggleGroupItem value="system" aria-label="System theme" className="h-7 w-7 p-0">
                    <Monitor className="h-3.5 w-3.5" />
                  </ToggleGroupItem>
                  <ToggleGroupItem value="dark" aria-label="Dark theme" className="h-7 w-7 p-0">
                    <Moon className="h-3.5 w-3.5" />
                  </ToggleGroupItem>
                </ToggleGroup>
              </div>
              <Link
                to="/login"
                className={cn(
                  "signin-cta flex items-center rounded-md border border-accent-brand/20 bg-accent-brand/5 hover:bg-accent-brand/10 transition-colors overflow-hidden",
                  isCollapsed ? "justify-center p-2" : "w-full gap-2.5 px-3 py-2"
                )}
              >
                <LogIn className={cn("text-accent-brand flex-shrink-0 transition-all duration-300", isCollapsed ? "h-[18px] w-[18px]" : "h-4 w-4")} />
                <span className={cn(
                  "text-[13px] font-medium whitespace-nowrap transition-all duration-300",
                  isCollapsed ? "w-0 opacity-0" : "opacity-100"
                )}>Sign In</span>
              </Link>
            </>
          )}
        </div>
      </aside>


      {/* Mobile Menu - Slide in from left with overlay */}
      {/* Backdrop overlay */}
      <div
        className={cn(
          "md:hidden fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity duration-300",
          isMobileSidebarOpen
            ? "opacity-100"
            : "opacity-0 pointer-events-none"
        )}
        onClick={() => setMobileSidebarOpen(false)}
        aria-hidden="true"
      />

      {/* Sidebar panel */}
      <div
        className={cn(
          "md:hidden fixed inset-y-0 left-0 z-[51] w-[280px] max-w-[85vw] bg-background border-r border-border shadow-2xl transition-transform duration-300 ease-out",
          isMobileSidebarOpen
            ? "translate-x-0"
            : "-translate-x-full"
        )}
      >
        <div className="flex flex-col h-full">
            {/* Mobile Header */}
            <div className="flex h-14 items-center justify-between px-3">
              <Link to="/chats" className="flex items-center gap-2.5" onClick={() => setMobileSidebarOpen(false)}>
                <SternaLogo size={26} className="text-foreground" />
                <span className="text-base font-semibold text-foreground">
                  Sterna
                </span>
              </Link>
              <button
                className="p-1.5 rounded-md hover:bg-muted transition-colors"
                onClick={() => setMobileSidebarOpen(false)}
              >
                <X className="h-5 w-5 text-foreground" />
              </button>
            </div>

            {/* Mobile Navigation */}
            <nav className="px-2 pb-2 flex-shrink-0">
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
              >
                <SortableContext
                  items={orderedNavigation.map(item => item.id)}
                  strategy={verticalListSortingStrategy}
                >
                  <div className="space-y-1">
                    {orderedNavigation.map((item) => (
                      <SortableNavItem
                        key={item.id}
                        id={item.id}
                        name={item.name}
                        href={item.href}
                        icon={item.icon}
                        isActive={isActive(item.href, item.id)}
                        isCollapsed={false}
                        onClick={() => setMobileSidebarOpen(false)}
                        comingSoon={item.comingSoon}
                        beta={item.beta}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            </nav>

            {/* Mobile Recent Activity */}
            <RecentActivity isCollapsed={false} onItemClick={() => setMobileSidebarOpen(false)} />

            {/* Mobile Bottom Section - Compact */}
            <div className="p-3 space-y-2">
              {/* Search + Model in a row */}
              {isAuthenticated && (
                <div className="flex items-center gap-2">
                  <div className="flex-1">
                    <CommandPaletteSearchBar isCollapsed={false} />
                  </div>
                </div>
              )}

              {/* Model Selector - no label */}
              {isAuthenticated && (
                <ModelSelector />
              )}

              {/* User row: avatar + name + actions all in one line */}
              {isAuthenticated && (
                <div className="pt-2 border-t border-border">
                  <div className="flex items-center gap-2">
                    {/* Avatar + Name - clickable to open profile */}
                    <button
                      onClick={() => {
                        setProfileModalOpen(true)
                        setMobileSidebarOpen(false)
                      }}
                      className="flex items-center gap-2 flex-1 min-w-0 rounded-md hover:bg-muted transition-colors p-1 -ml-1"
                    >
                      {user?.avatar_url && !avatarError ? (
                        <img
                          src={user.avatar_url}
                          alt={`${user.first_name} ${user.last_name}`}
                          className="h-8 w-8 rounded-full object-cover flex-shrink-0 ring-1 ring-border"
                          crossOrigin="anonymous"
                          onError={() => setAvatarError(true)}
                        />
                      ) : (
                        <div className="h-8 w-8 rounded-full gradient-primary flex items-center justify-center flex-shrink-0">
                          <User className="h-4 w-4 text-white" />
                        </div>
                      )}
                      <span className="flex-1 text-sm font-medium truncate min-w-0 text-left">
                        {user?.first_name}
                      </span>
                    </button>

                    {/* Theme toggle - single button that cycles */}
                    <button
                      onClick={() => {
                        const next = theme === 'light' ? 'system' : theme === 'system' ? 'dark' : 'light'
                        setTheme(next)
                      }}
                      className="flex items-center justify-center h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      aria-label={`Theme: ${theme}`}
                    >
                      {theme === 'light' ? <Sun className="h-4 w-4" /> : theme === 'dark' ? <Moon className="h-4 w-4" /> : <Monitor className="h-4 w-4" />}
                    </button>

                    {/* Settings */}
                    <button
                      onClick={() => {
                        openSettings()
                        setMobileSidebarOpen(false)
                      }}
                      className="flex items-center justify-center h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      aria-label="Settings"
                    >
                      <Settings className="h-4 w-4" />
                    </button>

                    {/* Logout */}
                    <button
                      onClick={() => {
                        handleLogout()
                        setMobileSidebarOpen(false)
                      }}
                      className="flex items-center justify-center h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      aria-label="Log out"
                    >
                      <LogOut className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              )}

              {/* Sign In & Theme - When not authenticated */}
              {!isAuthenticated && (
                <div className="pt-2 border-t border-border">
                  <div className="flex items-center gap-2">
                    {/* Theme toggle - single button */}
                    <button
                      onClick={() => {
                        const next = theme === 'light' ? 'system' : theme === 'system' ? 'dark' : 'light'
                        setTheme(next)
                      }}
                      className="flex items-center justify-center h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      aria-label={`Theme: ${theme}`}
                    >
                      {theme === 'light' ? <Sun className="h-4 w-4" /> : theme === 'dark' ? <Moon className="h-4 w-4" /> : <Monitor className="h-4 w-4" />}
                    </button>

                    <div className="flex-1" />

                    {/* Sign In button */}
                    <Link
                      to="/login"
                      onClick={() => setMobileSidebarOpen(false)}
                      className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-accent-brand/30 bg-accent-brand/10 hover:bg-accent-brand/20 transition-colors"
                    >
                      <LogIn className="h-4 w-4 text-accent-brand" />
                      <span className="text-sm font-medium">Sign In</span>
                    </Link>
                  </div>
                </div>
              )}
            </div>
        </div>
      </div>

      {/* Profile Edit Modal */}
      <ProfileEditModal
        open={profileModalOpen}
        onOpenChange={setProfileModalOpen}
      />
    </>
  )
}
