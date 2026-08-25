import privacyPolicyRaw from './privacy-policy.mdx?raw'
import termsOfServiceRaw from './terms-of-service.mdx?raw'
import refundPolicyRaw from './refund-policy.mdx?raw'
import acceptableUsePolicyRaw from './acceptable-use-policy.mdx?raw'
import dataProcessingAgreementRaw from './data-processing-agreement.mdx?raw'
import cookiePolicyRaw from './cookie-policy.mdx?raw'

export type LegalSlug =
  | 'privacy'
  | 'terms'
  | 'refunds'
  | 'aup'
  | 'dpa'
  | 'cookies'

export interface LegalDocument {
  slug: LegalSlug
  title: string
  lastUpdated: string
  version: string
  body: string
}

function parseMdx(raw: string, slug: LegalSlug): LegalDocument {
  const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/)
  if (!match) {
    return {
      slug,
      title: slug,
      lastUpdated: '',
      version: '',
      body: raw,
    }
  }
  const [, fm, body] = match
  const title = fm.match(/title:\s*(.+)/)?.[1]?.trim() ?? slug
  const lastUpdated = fm.match(/last_updated:\s*(.+)/)?.[1]?.trim() ?? ''
  const version = fm.match(/version:\s*(.+)/)?.[1]?.trim() ?? ''
  return { slug, title, lastUpdated, version, body: body.trim() }
}

export const legalDocuments: Record<LegalSlug, LegalDocument> = {
  privacy: parseMdx(privacyPolicyRaw, 'privacy'),
  terms: parseMdx(termsOfServiceRaw, 'terms'),
  refunds: parseMdx(refundPolicyRaw, 'refunds'),
  aup: parseMdx(acceptableUsePolicyRaw, 'aup'),
  dpa: parseMdx(dataProcessingAgreementRaw, 'dpa'),
  cookies: parseMdx(cookiePolicyRaw, 'cookies'),
}

export const legalNavigation: ReadonlyArray<{
  slug: LegalSlug
  title: string
  href: string
}> = [
  { slug: 'privacy', title: 'Privacy Policy', href: '/legal/privacy' },
  { slug: 'terms', title: 'Terms of Service', href: '/legal/terms' },
  { slug: 'refunds', title: 'Refund Policy', href: '/legal/refunds' },
  { slug: 'aup', title: 'Acceptable Use Policy', href: '/legal/aup' },
  { slug: 'dpa', title: 'Data Processing Agreement', href: '/legal/dpa' },
  { slug: 'cookies', title: 'Cookie Policy', href: '/legal/cookies' },
]
