import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { LegalLayout } from '../LegalLayout'
import type { LegalDocument } from '@/content/legal'

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    to,
    ...rest
  }: {
    children: React.ReactNode
    to: string
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))

vi.mock('@/components/icons/SternaLogo', () => ({
  SternaLogo: ({ className }: { className?: string }) => (
    <svg data-testid="sterna-logo" className={className} />
  ),
}))

const fixtureDoc: LegalDocument = {
  slug: 'privacy',
  title: 'Privacy Policy',
  lastUpdated: '2026-05-21',
  version: '1.0.0',
  body: `Some intro paragraph.

## First section

Body of first section. Includes [a link](/legal/terms) inline.

## Second section

Body of second section with **bold** text.
`,
}

describe('LegalLayout', () => {
  it('renders the document title', () => {
    render(<LegalLayout document={fixtureDoc} />)
    expect(
      screen.getByRole('heading', { level: 1, name: 'Privacy Policy' }),
    ).toBeInTheDocument()
  })

  it('renders the last-updated and version badges', () => {
    render(<LegalLayout document={fixtureDoc} />)
    expect(screen.getByText(/Last updated: 2026-05-21/)).toBeInTheDocument()
    expect(screen.getByText(/Version 1\.0\.0/)).toBeInTheDocument()
  })

  it('renders the markdown body, including h2 headings with stable ids', () => {
    render(<LegalLayout document={fixtureDoc} />)
    const firstHeading = screen.getByRole('heading', {
      level: 2,
      name: 'First section',
    })
    expect(firstHeading).toBeInTheDocument()
    expect(firstHeading).toHaveAttribute('id', 'first-section')
    expect(
      screen.getByRole('heading', { level: 2, name: 'Second section' }),
    ).toHaveAttribute('id', 'second-section')
  })

  it('renders a table of contents derived from the h2 headings', () => {
    render(<LegalLayout document={fixtureDoc} />)
    // The TOC is rendered both in the desktop sidebar and the mobile
    // <details>, hence the getAllByRole assertion.
    const tocLinks = screen.getAllByRole('link', { name: 'First section' })
    expect(tocLinks.length).toBeGreaterThanOrEqual(1)
    expect(tocLinks[0]).toHaveAttribute('href', '#first-section')
  })
})
