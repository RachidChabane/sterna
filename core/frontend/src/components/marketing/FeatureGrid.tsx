import { MessageSquare, Mic, Zap, Database, Code2, Plug } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

interface Feature {
  icon: LucideIcon
  title: string
  desc: string
}

const FEATURES: Feature[] = [
  { icon: MessageSquare, title: 'Chat', desc: 'Multi-model conversations with full context control.' },
  { icon: Mic, title: 'Voice rooms', desc: 'Real-time AI voice sessions for hands-free workflows.' },
  { icon: Zap, title: 'Sparks', desc: 'One-click AI automations you build and share.' },
  { icon: Database, title: 'Knowledge base', desc: 'Upload docs; your AI cites them precisely.' },
  { icon: Code2, title: 'Coding agent', desc: 'Autonomous coding sessions in a sandboxed environment.' },
  { icon: Plug, title: 'MCP', desc: 'Connect any MCP-compatible tool in seconds.' },
]

export function FeatureGrid() {
  return (
    <section className="py-20">
      <div className="container mx-auto px-4">
        <p className="font-mono text-xs uppercase tracking-[0.25em] text-muted-foreground text-center mb-3">
          01 — Cargo manifest
        </p>
        <h2 className="font-display text-3xl sm:text-4xl font-bold text-center mb-12">Everything you need</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f, i) => {
            const Icon = f.icon
            return (
              <div
                key={f.title}
                className="rounded-md border-2 border-foreground/15 bg-background p-6 transition-all hover:border-foreground/70 hover:shadow-hard hover:-translate-x-[2px] hover:-translate-y-[2px]"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="inline-flex items-center justify-center rounded-sm border-2 border-foreground/70 bg-accent-brand/10 p-2">
                    <Icon className="h-5 w-5 text-primary" />
                  </div>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                </div>
                <h3 className="font-display font-bold mb-1">{f.title}</h3>
                <p className="text-sm text-muted-foreground">{f.desc}</p>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
