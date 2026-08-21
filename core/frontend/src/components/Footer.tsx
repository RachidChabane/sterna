import { Link } from '@tanstack/react-router'
import { SternaLogo } from '@/components/icons/SternaLogo'
import { legalNavigation } from '@/content/legal'
import { SITE_CONFIG } from '@/config/site'

interface FooterLink {
  label: string
  href: string
  external?: boolean
}

const productLinks: FooterLink[] = [
  { label: 'Chats', href: '/chats' },
  { label: 'Sparks', href: '/sparks' },
  { label: 'Agents', href: '/agents' },
]

const supportLinks: FooterLink[] = [
  { label: 'Email support', href: `mailto:${SITE_CONFIG.supportEmail}`, external: true },
  { label: 'Status page', href: SITE_CONFIG.statusPageUrl, external: true },
]

function FooterLinkItem({ link }: { link: FooterLink }) {
  if (link.external) {
    return (
      <a
        href={link.href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        {link.label}
      </a>
    )
  }
  return (
    <Link
      to={link.href}
      className="text-sm text-muted-foreground transition-colors hover:text-foreground"
    >
      {link.label}
    </Link>
  )
}

export function Footer() {
  const year = new Date().getFullYear()
  return (
    <footer
      role="contentinfo"
      className="border-t border-border/60 bg-background/95 mt-auto"
    >
      <div className="mx-auto max-w-6xl px-6 py-10">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-4">
          <div className="col-span-2 md:col-span-1">
            <Link to="/" className="flex items-center gap-2.5 group">
              <SternaLogo
                size={24}
                className="text-accent-brand transition-transform group-hover:scale-110"
              />
              <span className="text-base font-semibold tracking-tight text-foreground">
                Sterna
              </span>
            </Link>
            <p className="mt-3 text-sm text-muted-foreground max-w-xs leading-relaxed">
              A consumer AI platform for chat, voice, images, and coding agents.
            </p>
          </div>

          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Product
            </h2>
            <ul className="mt-3 space-y-2">
              {productLinks.map((link) => (
                <li key={link.href}>
                  <FooterLinkItem link={link} />
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Legal
            </h2>
            <ul className="mt-3 space-y-2">
              {legalNavigation.map((item) => (
                <li key={item.slug}>
                  <FooterLinkItem link={{ label: item.title, href: item.href }} />
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Support
            </h2>
            <ul className="mt-3 space-y-2">
              {supportLinks.map((link) => (
                <li key={link.href}>
                  <FooterLinkItem link={link} />
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-10 flex flex-col items-start gap-2 border-t border-border/60 pt-6 text-xs text-muted-foreground md:flex-row md:items-center md:justify-between">
          <span>© {year} Sterna. All rights reserved.</span>
          <span>v{__APP_VERSION__}</span>
        </div>
      </div>
    </footer>
  )
}
