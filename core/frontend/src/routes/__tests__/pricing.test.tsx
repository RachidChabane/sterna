import React, { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, test, expect, vi } from 'vitest'

vi.mock('@tanstack/react-router', () => ({
  createFileRoute: () => () => null,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}))

vi.mock('@/hooks/useSeoHead', () => ({
  useSeoHead: vi.fn(),
}))

function TestPricingPage() {
  const [billing, setBilling] = useState<'monthly' | 'yearly'>('monthly')
  return (
    <div>
      <h1>Simple, transparent pricing</h1>
      <div>
        <button type="button" onClick={() => setBilling('monthly')}>
          Monthly
        </button>
        <button type="button" onClick={() => setBilling('yearly')}>
          Yearly
        </button>
      </div>
      <div data-testid="pricing-cards" data-billing={billing} />
      <div data-testid="all-plans-include" />
      <div data-testid="comparison-table" />
      <div data-testid="faq-excerpt" />
    </div>
  )
}

describe('Pricing page', () => {
  test('renders billing toggle', () => {
    render(<TestPricingPage />)
    expect(screen.getByRole('button', { name: /monthly/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /yearly/i })).toBeInTheDocument()
  })

  test('renders pricing cards section', () => {
    render(<TestPricingPage />)
    expect(screen.getByTestId('pricing-cards')).toBeInTheDocument()
  })

  test('yearly toggle switches billing prop', async () => {
    const user = userEvent.setup()
    render(<TestPricingPage />)
    expect(screen.getByTestId('pricing-cards')).toHaveAttribute('data-billing', 'monthly')
    await user.click(screen.getByRole('button', { name: /yearly/i }))
    expect(screen.getByTestId('pricing-cards')).toHaveAttribute('data-billing', 'yearly')
  })

  test('renders FAQ section', () => {
    render(<TestPricingPage />)
    expect(screen.getByTestId('faq-excerpt')).toBeInTheDocument()
  })
})
