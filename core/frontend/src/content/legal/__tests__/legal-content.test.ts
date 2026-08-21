import { describe, it, expect } from 'vitest'
import { legalDocuments, legalNavigation } from '../index'

describe('legal content', () => {
  it('exports a document for each of the six expected slugs', () => {
    const slugs = ['privacy', 'terms', 'refunds', 'aup', 'dpa', 'cookies'] as const
    for (const slug of slugs) {
      expect(legalDocuments[slug]).toBeDefined()
      expect(legalDocuments[slug].body.length).toBeGreaterThan(200)
      expect(legalDocuments[slug].title.length).toBeGreaterThan(0)
      expect(legalDocuments[slug].version).toBe('1.0.0')
      expect(legalDocuments[slug].lastUpdated).toBe('2026-05-21')
    }
  })

  it('exposes a legalNavigation entry for each document', () => {
    expect(legalNavigation.map((n) => n.slug)).toEqual([
      'privacy',
      'terms',
      'refunds',
      'aup',
      'dpa',
      'cookies',
    ])
    for (const entry of legalNavigation) {
      expect(entry.href).toBe(`/legal/${entry.slug === 'refunds' ? 'refunds' : entry.slug}`)
    }
  })

  it('Privacy Policy contains the GDPR-required clauses', () => {
    const body = legalDocuments.privacy.body
    expect(body).toMatch(/data controller/i)
    expect(body).toMatch(/legitimate interest/i)
    expect(body).toMatch(/CNIL/)
    expect(body).toMatch(/30[- ]day/)
  })

  it('Terms of Service contain age, auto-renew, governing law, and notice clauses', () => {
    const body = legalDocuments.terms.body
    expect(body).toMatch(/16\+|sixteen/i)
    expect(body).toMatch(/auto[- ]renew/i)
    expect(body).toMatch(/governing law/i)
    expect(body).toMatch(/30[- ]day/)
  })

  it('Refund Policy cites the EU cooling-off directive', () => {
    const body = legalDocuments.refunds.body
    expect(body).toMatch(/14[- ]day/)
    expect(body).toMatch(/cooling[- ]off/i)
    expect(body).toMatch(/Directive 2011\/83\/EU/)
  })

  it('Acceptable Use Policy prohibits CSAM/NCII and scraping', () => {
    const body = legalDocuments.aup.body
    expect(body).toMatch(/CSAM|NCII/)
    expect(body).toMatch(/no scraping|not.*scrape/i)
  })

  it('DPA references sub-processors and SCCs', () => {
    const body = legalDocuments.dpa.body
    expect(body).toMatch(/sub[- ]processor/i)
    expect(body).toMatch(/Standard Contractual Clauses|SCCs/)
  })

  it('Cookie Policy distinguishes strictly necessary and analytics cookies', () => {
    const body = legalDocuments.cookies.body
    expect(body).toMatch(/strictly necessary/i)
    expect(body).toMatch(/analytic/i)
  })
})
