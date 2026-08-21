import { Link } from '@tanstack/react-router'
import { TIERS } from '@/lib/pricingData'

export function PricingTeaser() {
  return (
    <section className="py-20 bg-muted/30">
      <div className="container mx-auto px-4">
        <h2 className="font-display text-3xl font-bold text-center mb-4">Simple pricing</h2>
        <p className="text-center text-muted-foreground mb-12">
          Start free. Upgrade when you're ready.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-3xl mx-auto">
          {TIERS.map((tier) => (
            <Link
              to="/pricing"
              key={tier.slug}
              className={`rounded-md border p-6 text-center bg-background transition-all hover:shadow-hard-sm hover:-translate-x-[1px] hover:-translate-y-[1px] ${
                tier.highlighted
                  ? 'border-2 border-foreground/80 shadow-hard-sm'
                  : 'border-2 border-foreground/15'
              }`}
            >
              {tier.highlighted && (
                <span className="inline-block font-mono text-[10px] font-bold uppercase tracking-widest text-primary mb-2">
                  Most popular
                </span>
              )}
              <p className="font-bold text-lg">{tier.name}</p>
              <p className="text-2xl font-bold mt-2">
                {tier.monthlyPrice === 0 ? 'Free' : `$${tier.monthlyPrice}/mo`}
              </p>
              <p className="text-xs text-muted-foreground mt-2">{tier.description}</p>
            </Link>
          ))}
        </div>
        <p className="text-center mt-8">
          <Link to="/pricing" className="text-sm text-primary hover:underline">
            See full comparison →
          </Link>
        </p>
      </div>
    </section>
  )
}
