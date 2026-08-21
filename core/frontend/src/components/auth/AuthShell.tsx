import React from 'react'
import { Link } from '@tanstack/react-router'
import { Sparkles, Shield, Zap } from 'lucide-react'
import { SternaLogo } from '@/components/icons/SternaLogo'

interface AuthShellProps {
  children: React.ReactNode
  title: string
  subtitle?: string
  /** Renders the aside on lg+; pass `false` for narrow forms like /forgot-password */
  showAside?: boolean
}

export function AuthShell({ children, title, subtitle, showAside = true }: AuthShellProps) {
  return (
    <div className="min-h-dvh flex bg-background">
      {showAside && (
        <aside className="hidden lg:flex lg:w-[44%] relative bg-card border-r-2 border-foreground/15 p-12 overflow-hidden">
          <div className="relative z-10 flex flex-col justify-between w-full">
            <Link to="/" className="flex items-center gap-3 group">
              <SternaLogo size={32} className="text-accent-brand transition-transform group-hover:scale-110" />
              <span className="text-xl font-semibold text-foreground tracking-tight">Sterna</span>
            </Link>

            <div className="space-y-10">
              <div className="space-y-3">
                <h2 className="font-display text-3xl xl:text-4xl font-semibold text-foreground leading-tight">
                  Build with{' '}
                  <span className="inline-block bg-highlight text-highlight-foreground px-2 -rotate-1">confidence</span>
                </h2>
                <p className="text-base text-muted-foreground max-w-md leading-relaxed">
                  Your AI, your rules. Every top model in one place — chat, coding agent, voice, and images.
                </p>
              </div>

              <div className="space-y-5">
                <FeatureItem
                  icon={<Sparkles className="h-5 w-5" />}
                  title="Every top model"
                  description="Switch between leading AI models mid-conversation"
                />
                <FeatureItem
                  icon={<Shield className="h-5 w-5" />}
                  title="Secure by default"
                  description="Sandboxed execution and least-privilege access"
                />
                <FeatureItem
                  icon={<Zap className="h-5 w-5" />}
                  title="Bring your own key"
                  description="Use your own API keys on any plan"
                />
              </div>
            </div>

            <p className="text-xs text-muted-foreground">© 2026 Sterna</p>
          </div>
        </aside>
      )}
      <main className="w-full lg:flex-1 overflow-y-auto">
        <div className="min-h-full flex items-center justify-center p-6 sm:p-8 lg:p-12">
          <div className="w-full max-w-[440px] space-y-6 lg:space-y-8">
            <div className="lg:hidden flex items-center gap-3 justify-center">
              <SternaLogo size={28} className="text-accent-brand" />
              <span className="text-lg font-semibold">Sterna</span>
            </div>
            <header className="space-y-1.5">
              <h1 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight">{title}</h1>
              {subtitle && <p className="text-muted-foreground">{subtitle}</p>}
            </header>
            {children}
          </div>
        </div>
      </main>
    </div>
  )
}

function FeatureItem({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode
  title: string
  description: string
}) {
  return (
    <div className="flex items-start gap-4 group">
      <div className="flex-shrink-0 w-10 h-10 rounded-sm border-2 border-foreground/60 bg-accent-brand/10 flex items-center justify-center text-accent-brand group-hover:bg-accent-brand/20 transition-colors">
        {icon}
      </div>
      <div>
        <h3 className="font-medium text-foreground">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  )
}
