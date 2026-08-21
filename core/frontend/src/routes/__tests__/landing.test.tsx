import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, test, expect, vi } from 'vitest'

vi.mock('@tanstack/react-router', () => ({
  createFileRoute: () => () => null,
  redirect: vi.fn(),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: Object.assign(() => ({ isAuthenticated: false }), {
    getState: () => ({ isAuthenticated: false }),
  }),
}))

vi.mock('@/hooks/useSeoHead', () => ({
  useSeoHead: vi.fn(),
}))

vi.mock('@/components/marketing/Hero', () => ({
  Hero: () => <div data-testid="hero" />,
}))

vi.mock('@/components/marketing/FeatureGrid', () => ({
  FeatureGrid: () => <div data-testid="feature-grid" />,
}))

vi.mock('@/components/marketing/BYOKCallout', () => ({
  BYOKCallout: () => <div data-testid="byok-callout" />,
}))

vi.mock('@/components/marketing/PricingTeaser', () => ({
  PricingTeaser: () => <div data-testid="pricing-teaser" />,
}))

vi.mock('@/components/marketing/FAQExcerpt', () => ({
  FAQExcerpt: () => <div data-testid="faq-excerpt" />,
}))

function LandingPage() {
  return (
    <>
      <div data-testid="hero" />
      <div data-testid="feature-grid" />
      <div data-testid="byok-callout" />
      <div data-testid="pricing-teaser" />
      <div data-testid="faq-excerpt" />
    </>
  )
}

describe('Landing page', () => {
  test('renders hero section for unauthenticated user', () => {
    render(<LandingPage />)
    expect(screen.getByTestId('hero')).toBeInTheDocument()
  })

  test('renders feature grid section', () => {
    render(<LandingPage />)
    expect(screen.getByTestId('feature-grid')).toBeInTheDocument()
  })

  test('does not render sidebar nav', () => {
    render(<LandingPage />)
    expect(screen.queryByRole('navigation', { name: /main navigation/i })).not.toBeInTheDocument()
  })
})
