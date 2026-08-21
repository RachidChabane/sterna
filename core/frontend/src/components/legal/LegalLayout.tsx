import { Children } from 'react'
import { Link } from '@tanstack/react-router'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Badge } from '@/components/ui/badge'
import { SternaLogo } from '@/components/icons/SternaLogo'
import { slugify } from '@/lib/utils'
import { LegalTableOfContents } from './LegalTableOfContents'
import { legalNavigation, type LegalDocument } from '@/content/legal'

interface LegalLayoutProps {
  document: LegalDocument
}

function nodeToText(node: React.ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node)
  }
  if (Array.isArray(node)) {
    return node.map(nodeToText).join('')
  }
  if (
    node &&
    typeof node === 'object' &&
    'props' in node &&
    (node as { props: { children?: React.ReactNode } }).props
  ) {
    return nodeToText((node as { props: { children?: React.ReactNode } }).props.children)
  }
  return ''
}

const markdownComponents: Components = {
  h2: ({ children }) => {
    const text = Children.toArray(children).map(nodeToText).join('')
    return <h2 id={slugify(text)}>{children}</h2>
  },
  h3: ({ children }) => {
    const text = Children.toArray(children).map(nodeToText).join('')
    return <h3 id={slugify(text)}>{children}</h3>
  },
  a: ({ href, children }) => {
    if (href && href.startsWith('/')) {
      return (
        <Link to={href} className="text-accent-brand underline-offset-4 hover:underline">
          {children}
        </Link>
      )
    }
    return (
      <a
        href={href}
        target={href?.startsWith('http') ? '_blank' : undefined}
        rel={href?.startsWith('http') ? 'noopener noreferrer' : undefined}
        className="text-accent-brand underline-offset-4 hover:underline"
      >
        {children}
      </a>
    )
  },
}

export function LegalLayout({ document }: LegalLayoutProps) {
  // h-dvh + overflow-y-auto: the global app shell locks html/body/#root
  // (index.css), so legal pages must be their own scroll container.
  return (
    <div className="h-dvh overflow-y-auto flex flex-col bg-background">
      <header className="border-b-2 border-foreground/15 bg-background">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link to="/" className="flex items-center gap-3 group">
            <SternaLogo
              size={28}
              className="text-accent-brand transition-transform group-hover:scale-110"
            />
            <span className="text-lg font-semibold tracking-tight text-foreground">
              Sterna
            </span>
          </Link>
          <nav aria-label="Legal pages" className="hidden md:flex items-center gap-1 text-sm">
            {legalNavigation.map((item) => (
              <Link
                key={item.slug}
                to={item.href}
                className={
                  item.slug === document.slug
                    ? 'rounded-md px-3 py-1.5 text-foreground bg-muted'
                    : 'rounded-md px-3 py-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/60'
                }
              >
                {item.title}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">
        <div className="mb-8">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">
            {document.title}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
            {document.lastUpdated && (
              <Badge variant="secondary">
                Last updated: {document.lastUpdated}
              </Badge>
            )}
            {document.version && (
              <Badge variant="secondary">Version {document.version}</Badge>
            )}
          </div>
        </div>

        <div className="lg:grid lg:grid-cols-[14rem_minmax(0,1fr)] lg:gap-10">
          <aside className="hidden lg:block">
            <div className="sticky top-24">
              <LegalTableOfContents body={document.body} />
            </div>
          </aside>

          <details className="lg:hidden mb-6 rounded-lg border border-border/60 bg-card px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium text-foreground">
              On this page
            </summary>
            <div className="mt-3">
              <LegalTableOfContents body={document.body} />
            </div>
          </details>

          <article className="prose prose-sm dark:prose-invert max-w-3xl">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {document.body}
            </ReactMarkdown>
          </article>
        </div>
      </main>
    </div>
  )
}
