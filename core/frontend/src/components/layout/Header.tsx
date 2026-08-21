import { useState, useEffect, useMemo } from 'react'
import { Link, useRouterState, useNavigate } from '@tanstack/react-router'
import {
  Menu,
  X,
  User,
  LogOut,
  Settings,
  Moon,
  Sun,
} from 'lucide-react'
import { SternaLogo } from '@/components/icons/SternaLogo'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ModelSelector } from '@/components/layout/ModelSelector'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/store/authStore'
import { useTheme } from '@/hooks/useTheme'
import { HelpDrawerTrigger } from '@/components/support/HelpDrawerTrigger'
import { useHelpDrawerStore } from '@/store/helpDrawerStore'

const navigation = [
  { name: 'Models', href: '/models' },
  { name: 'Chats', href: '/chats' },
]

export function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [isScrolled, setIsScrolled] = useState(false)
  const routerState = useRouterState()
  const pathname = routerState.location.pathname
  const navigate = useNavigate()
  const { isAuthenticated, user, logout } = useAuthStore()
  const { theme, toggleTheme } = useTheme()
  const openHelp = useHelpDrawerStore((s) => s.open)

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10)
    }
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const isActive = useMemo(() => {
    return (path: string) => {
      if (path === '/') {
        return pathname === '/'
      }
      return pathname.startsWith(path)
    }
  }, [pathname])

  // Don't render header on auth pages
  if (pathname === '/login' || pathname === '/signup') {
    return null
  }

  return (
    <header
      className={cn(
        "sticky top-0 z-50 w-full transition-all duration-200",
        isScrolled
          ? "glass border-b backdrop-blur-xl shadow-sm"
          : "bg-background/80 backdrop-blur-lg border-b dark:bg-background/95"
      )}
    >
      <nav className="container mx-auto px-4">
        <div className="flex h-16 items-center justify-between relative">
          {/* Logo and Brand - centered on mobile, left on desktop */}
          <div className="flex items-center gap-8 md:relative absolute left-1/2 -translate-x-1/2 md:left-0 md:translate-x-0">
            <Link to="/voice-rooms" className="flex items-center gap-2 group">
              <div className="p-1.5 rounded-lg gradient-brand group-hover:shadow-glow-brand transition-all">
                <SternaLogo size={24} className="text-white" />
              </div>
              <span className="text-xl font-bold text-gradient">
                Sterna
              </span>
            </Link>

            {/* Desktop Navigation */}
            <div className="hidden md:flex items-center gap-1">
              {navigation.map((item) => {
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    className={cn(
                      "px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200",
                      isActive(item.href)
                        ? "bg-secondary text-foreground"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                    )}
                  >
                    {item.name}
                  </Link>
                )
              })}
            </div>
          </div>

          {/* Desktop User Actions */}
          <div className="hidden md:flex items-center gap-3">
            <HelpDrawerTrigger />
            {isAuthenticated && <ModelSelector />}
            {isAuthenticated ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="relative h-9 w-9 rounded-full">
                    <div className="h-9 w-9 rounded-full gradient-primary flex items-center justify-center">
                      <User className="h-7 w-7 text-white" />
                    </div>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="w-56" align="end" forceMount>
                  <DropdownMenuLabel className="font-normal">
                    <div className="flex flex-col space-y-1">
                      <p className="text-sm font-medium leading-none">
                        {user?.first_name} {user?.last_name}
                      </p>
                      <p className="text-xs leading-none text-muted-foreground">
                        {user?.email}
                      </p>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem>
                    <Settings className="mr-2 h-4 w-4" />
                    <span>Settings</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                    <div className="flex items-center justify-between w-full">
                      <div className="flex items-center gap-2">
                        {theme === 'dark' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
                        <span>Theme</span>
                      </div>
                      <Switch checked={theme === 'dark'} onCheckedChange={toggleTheme} />
                    </div>
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={async () => {
                    await logout()
                    navigate({ to: '/login' })
                  }}>
                    <LogOut className="mr-2 h-4 w-4" />
                    <span>Log out</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <>
                <Link to="/login">
                  <Button variant="outline" className="hover:bg-secondary hover:border-border">
                    Sign In
                  </Button>
                </Link>
                <Link to="/onboarding">
                  <Button className="bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all">
                    Get Started
                  </Button>
                </Link>
              </>
            )}
          </div>

          {/* Mobile menu toggle */}
          <button
            className="md:hidden p-2 rounded-lg hover:bg-secondary transition-colors"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? (
              <X className="h-6 w-6 text-foreground" />
            ) : (
              <Menu className="h-6 w-6 text-foreground" />
            )}
          </button>
        </div>

        {/* Mobile Navigation Menu */}
        {mobileMenuOpen && (
          <div className="md:hidden py-4 border-t">
            <div className="flex flex-col space-y-2">
              {navigation.map((item) => {
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={cn(
                      "px-3 py-2 rounded-lg text-sm font-medium transition-all",
                      isActive(item.href)
                        ? "bg-secondary text-foreground"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                    )}
                  >
                    {item.name}
                  </Link>
                )
              })}

              {/* Mobile User Actions */}
              <div className="pt-4 border-t space-y-2">
                <button
                  onClick={() => {
                    openHelp('faq')
                    setMobileMenuOpen(false)
                  }}
                  className="w-full px-3 py-2 rounded-lg text-sm font-medium text-left text-muted-foreground hover:bg-secondary hover:text-foreground flex items-center gap-2 transition-all"
                >
                  Help & Support
                </button>
                {/* Model Selector */}
                {isAuthenticated && (
                  <div className="px-3 py-2">
                    <span className="text-sm font-medium text-muted-foreground mb-2 block">Model</span>
                    <ModelSelector />
                  </div>
                )}

                {isAuthenticated ? (
                  <>
                    <div className="px-3 py-2">
                      <p className="text-sm font-medium">{user?.first_name} {user?.last_name}</p>
                      <p className="text-xs text-muted-foreground">{user?.email}</p>
                    </div>
                    <div className="px-3 py-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {theme === 'dark' ? <Moon className="h-4 w-4 text-muted-foreground" /> : <Sun className="h-4 w-4 text-muted-foreground" />}
                        <span className="text-sm font-medium text-muted-foreground">Theme</span>
                      </div>
                      <Switch checked={theme === 'dark'} onCheckedChange={toggleTheme} />
                    </div>
                    <button
                      onClick={async () => {
                        await logout()
                        navigate({ to: '/login' })
                        setMobileMenuOpen(false)
                      }}
                      className="w-full px-3 py-2 rounded-lg text-sm font-medium text-left text-muted-foreground hover:bg-secondary hover:text-foreground flex items-center gap-2 transition-all"
                    >
                      <LogOut className="h-4 w-4" />
                      Log out
                    </button>
                  </>
                ) : (
                  <>
                    <Link to="/login" onClick={() => setMobileMenuOpen(false)}>
                      <Button variant="outline" className="w-full hover:bg-secondary">
                        Sign In
                      </Button>
                    </Link>
                    <Link to="/onboarding" onClick={() => setMobileMenuOpen(false)}>
                      <Button className="w-full bg-accent-brand text-white hover:bg-accent-brand/90">
                        Get Started
                      </Button>
                    </Link>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </nav>
    </header>
  )
}