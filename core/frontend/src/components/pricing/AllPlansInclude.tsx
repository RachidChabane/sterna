import { ShieldCheck } from 'lucide-react'

const ITEMS = [
  'BYOK supported',
  'Data export & deletion',
  'Cancel anytime',
]

export function AllPlansInclude() {
  return (
    <div className="rounded-md border-2 border-foreground/15 p-6">
      <p className="font-mono text-xs text-center text-muted-foreground mb-4 uppercase tracking-[0.25em]">
        All plans include
      </p>
      <div className="flex flex-wrap justify-center gap-6">
        {ITEMS.map((item) => (
          <div key={item} className="flex items-center gap-2 text-sm">
            <ShieldCheck className="h-4 w-4 text-brand-500 flex-shrink-0" />
            <span>{item}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
