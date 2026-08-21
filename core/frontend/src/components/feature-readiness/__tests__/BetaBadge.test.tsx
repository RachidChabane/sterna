import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { BetaBadge } from '../BetaBadge'

describe('BetaBadge', () => {
  it('renders "Beta" label for beta variant', () => {
    render(<BetaBadge variant="beta" />)
    expect(screen.getByText('Beta')).toBeInTheDocument()
  })

  it('renders "Experimental" label for experimental variant', () => {
    render(<BetaBadge variant="experimental" />)
    expect(screen.getByText('Experimental')).toBeInTheDocument()
  })

  it('renders "Preview" label for preview variant', () => {
    render(<BetaBadge variant="preview" />)
    expect(screen.getByText('Preview')).toBeInTheDocument()
  })

  it('defaults to beta variant', () => {
    render(<BetaBadge />)
    expect(screen.getByText('Beta')).toBeInTheDocument()
  })

  it('applies custom className to badge', () => {
    render(<BetaBadge variant="beta" className="my-custom-class" />)
    const badge = screen.getByText('Beta')
    expect(badge.className).toContain('my-custom-class')
  })

  it('shows tooltip text on hover', async () => {
    const user = userEvent.setup()
    render(<BetaBadge variant="beta" />)
    const badge = screen.getByText('Beta')
    await user.hover(badge)
    const tooltipTexts = await screen.findAllByText(/Some deploys may fail/)
    expect(tooltipTexts.length).toBeGreaterThan(0)
  })
})
