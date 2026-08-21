import { Link } from '@tanstack/react-router'
import { SternaLogo } from '@/components/icons/SternaLogo'

export function MarketingFooter() {
  return (
    <footer className="border-t-2 border-foreground/15 bg-background">
      <div className="container mx-auto px-4 py-10 flex flex-col md:flex-row justify-between gap-8">
        <div className="space-y-2">
          <div className="flex items-center gap-2 font-display font-bold">
            <SternaLogo size={24} />
            <span>Sterna</span>
          </div>
          <p className="text-sm text-muted-foreground max-w-xs">
            Your AI, your rules. Every top model in one place.
          </p>
          <p className="text-xs text-muted-foreground">© 2026 Sterna</p>
        </div>

        <nav className="flex flex-col gap-2 text-sm">
          <Link to="/pricing" className="text-muted-foreground hover:text-foreground transition-colors">
            Pricing
          </Link>
          <Link to="/login" className="text-muted-foreground hover:text-foreground transition-colors">
            Log in
          </Link>
          <Link to="/legal/privacy" className="text-muted-foreground hover:text-foreground transition-colors">
            Privacy Policy
          </Link>
          <Link to="/legal/terms" className="text-muted-foreground hover:text-foreground transition-colors">
            Terms of Service
          </Link>
        </nav>
      </div>
    </footer>
  )
}
