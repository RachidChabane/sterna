interface BillingToggleProps {
  value: 'monthly' | 'yearly'
  onChange: (v: 'monthly' | 'yearly') => void
}

export function BillingToggle({ value, onChange }: BillingToggleProps) {
  return (
    <div className="inline-flex items-center gap-1 rounded-md border-2 border-foreground/25 bg-muted p-1">
      <button
        type="button"
        onClick={() => onChange('monthly')}
        className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
          value === 'monthly'
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
        }`}
      >
        Monthly
      </button>
      <button
        type="button"
        onClick={() => onChange('yearly')}
        className={`flex items-center gap-2 rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
          value === 'yearly'
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
        }`}
      >
        Yearly
        <span className="rounded-sm bg-highlight px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase text-highlight-foreground">
          2 months free
        </span>
      </button>
    </div>
  )
}
