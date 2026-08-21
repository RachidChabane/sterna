import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { Menu, X } from 'lucide-react'
import { SternaLogo } from '@/components/icons/SternaLogo'

export function MarketingNav() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 border-b-2 border-foreground/15 bg-background">
      <div className="container mx-auto px-4 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 font-display font-bold text-lg">
          <SternaLogo size={28} className="text-primary" />
          <span>Sterna</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-6">
          <Link to="/pricing" className="font-mono text-xs uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors">
            Pricing
          </Link>
          <Link
            to="/login"
            className="font-mono text-xs uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
          >
            Log in
          </Link>
          <Link
            to="/signup"
            className="btn-premium inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-semibold"
          >
            Try free
          </Link>
        </nav>

        {/* Mobile hamburger */}
        <button
          type="button"
          className="md:hidden p-2 rounded-md text-muted-foreground hover:text-foreground"
          onClick={() => setMobileOpen((o) => !o)}
          aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="md:hidden border-t-2 border-foreground/15 bg-background px-4 py-4 space-y-3">
          <Link
            to="/pricing"
            className="block font-mono text-xs uppercase tracking-widest text-muted-foreground hover:text-foreground"
            onClick={() => setMobileOpen(false)}
          >
            Pricing
          </Link>
          <Link
            to="/login"
            className="block font-mono text-xs uppercase tracking-widest text-muted-foreground hover:text-foreground"
            onClick={() => setMobileOpen(false)}
          >
            Log in
          </Link>
          <Link
            to="/signup"
            className="btn-premium block w-full text-center rounded-md px-4 py-2 text-sm font-semibold"
            onClick={() => setMobileOpen(false)}
          >
            Try free
          </Link>
        </div>
      )}
    </header>
  )
}
