import { Link } from '@tanstack/react-router'
import { SternaLogo } from '@/components/icons/SternaLogo'

export function Hero() {
  return (
    <section className="relative py-20 sm:py-28 border-b-2 border-foreground/15">
      <div className="container mx-auto px-4 text-center">
        <p className="font-mono text-xs sm:text-sm uppercase tracking-[0.25em] text-muted-foreground mb-6">
          Sterna paradisaea&ensp;·&ensp;built for long journeys
        </p>
        <h1 className="font-display text-5xl sm:text-7xl font-bold tracking-tight leading-[1.05]">
          Your AI,{' '}
          <span className="relative inline-block bg-highlight text-highlight-foreground px-3 -rotate-1">
            your rules
          </span>
        </h1>
        <p className="mt-8 text-xl text-muted-foreground max-w-2xl mx-auto leading-relaxed">
          Chat, code, create, and discover — all in one place.
          Bring your own keys, own your data.
        </p>
        <div className="mt-10 flex gap-4 justify-center flex-wrap">
          <Link
            to="/signup"
            className="btn-premium inline-flex items-center justify-center rounded-md px-6 py-3 text-base font-semibold"
          >
            Try free
          </Link>
          <Link
            to="/pricing"
            className="inline-flex items-center justify-center rounded-md border-2 border-foreground/25 bg-background px-6 py-3 text-base font-medium hover:border-foreground/60 transition-colors"
          >
            See pricing
          </Link>
        </div>
      </div>
      {/* Flight path — the tern crossing the chart */}
      <div className="relative mt-16 sm:mt-20 mx-auto max-w-4xl px-4" aria-hidden="true">
        <div className="border-t-2 border-dashed border-foreground/25" />
        <SternaLogo
          size={26}
          className="absolute -top-[13px] left-[62%] text-foreground bg-background px-0.5"
        />
        <div className="flex justify-between font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-2">
          <span>66°N — Arctic</span>
          <span>every model, one route</span>
          <span>66°S — Antarctic</span>
        </div>
      </div>
    </section>
  )
}
