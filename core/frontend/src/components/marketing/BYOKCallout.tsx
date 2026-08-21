import { Link } from '@tanstack/react-router'
import { Key } from 'lucide-react'

export function BYOKCallout() {
  return (
    <section className="py-12">
      <div className="container mx-auto px-4">
        <div className="rounded-md border-2 border-foreground/70 bg-highlight/15 shadow-hard p-6 flex flex-col sm:flex-row items-start sm:items-center gap-6 justify-between">
          <div className="flex items-start gap-4">
            <div className="rounded-sm border-2 border-foreground/70 bg-highlight p-2 flex-shrink-0">
              <Key className="h-5 w-5 text-highlight-foreground" />
            </div>
            <div>
              <p className="font-display font-bold">Bring your own API key</p>
              <p className="text-sm text-muted-foreground mt-1">
                Use GPT-4o, Claude, Gemini — pay the provider directly. We never markup tokens.
              </p>
            </div>
          </div>
          <Link
            to="/signup"
            className="btn-premium inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-semibold whitespace-nowrap"
          >
            Get started
          </Link>
        </div>
      </div>
    </section>
  )
}
