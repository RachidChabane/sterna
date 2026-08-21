import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { Footer } from '../Footer'

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

describe('Footer', () => {
  it('renders all six legal links', () => {
    render(<Footer />)
    expect(
      screen.getByRole('link', { name: 'Privacy Policy' }),
    ).toHaveAttribute('href', '/legal/privacy')
    expect(
      screen.getByRole('link', { name: 'Terms of Service' }),
    ).toHaveAttribute('href', '/legal/terms')
    expect(
      screen.getByRole('link', { name: 'Refund Policy' }),
    ).toHaveAttribute('href', '/legal/refunds')
    expect(
      screen.getByRole('link', { name: 'Acceptable Use Policy' }),
    ).toHaveAttribute('href', '/legal/aup')
    expect(
      screen.getByRole('link', { name: 'Data Processing Agreement' }),
    ).toHaveAttribute('href', '/legal/dpa')
    expect(
      screen.getByRole('link', { name: 'Cookie Policy' }),
    ).toHaveAttribute('href', '/legal/cookies')
  })

  it('renders the support mailto and external status link', () => {
    render(<Footer />)
    expect(
      screen.getByRole('link', { name: /email support/i }),
    ).toHaveAttribute('href', 'mailto:support@example.com')
    const statusLink = screen.getByRole('link', { name: /status page/i })
    expect(statusLink).toHaveAttribute('href', 'https://status.example.com')
    expect(statusLink).toHaveAttribute('target', '_blank')
    expect(statusLink).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('renders the build version string from __APP_VERSION__', () => {
    render(<Footer />)
    // Catches both regressions: missing prefix, and an empty version constant.
    expect(screen.getByText(/^v\S+$/)).toBeInTheDocument()
  })

  it('marks the footer with contentinfo role', () => {
    render(<Footer />)
    expect(screen.getByRole('contentinfo')).toBeInTheDocument()
  })
})
