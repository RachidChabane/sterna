import { slugify } from '@/lib/utils'

interface LegalTableOfContentsProps {
  body: string
}

interface TocItem {
  text: string
  slug: string
}

function extractHeadings(body: string): TocItem[] {
  const matches = body.match(/^## (.+)$/gm) ?? []
  return matches.map((line) => {
    const text = line.replace(/^## /, '').trim()
    return { text, slug: slugify(text) }
  })
}

export function LegalTableOfContents({ body }: LegalTableOfContentsProps) {
  const items = extractHeadings(body)

  if (items.length === 0) {
    return null
  }

  return (
    <nav aria-label="Table of contents" className="text-sm">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        On this page
      </p>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.slug}>
            <a
              href={`#${item.slug}`}
              className="block text-muted-foreground transition-colors hover:text-foreground"
            >
              {item.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
