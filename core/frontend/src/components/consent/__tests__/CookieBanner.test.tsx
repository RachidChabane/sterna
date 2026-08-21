import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useConsentStore } from '@/store/consentStore'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))

const consentGetMock = vi.fn()
const consentSaveMock = vi.fn()
const consentAttachMock = vi.fn()

vi.mock('@/api/endpoints', () => ({
  authApi: {
    consent: {
      get: (...args: unknown[]) => consentGetMock(...args),
      save: (...args: unknown[]) => consentSaveMock(...args),
      attach: (...args: unknown[]) => consentAttachMock(...args),
    },
  },
}))

import { CookieBanner } from '../CookieBanner'

function resetStore(partial: Partial<ReturnType<typeof useConsentStore.getState>> = {}) {
  useConsentStore.setState({
    sessionId: null,
    categories: { essential: true, analytics: false, marketing: false },
    version: '',
    regionDefault: 'unknown',
    hasDecided: false,
    isBannerOpen: false,
    isDialogOpen: false,
    ...partial,
  })
}

describe('CookieBanner', () => {
  beforeEach(() => {
    localStorage.clear()
    consentGetMock.mockReset()
    consentSaveMock.mockReset()
    consentAttachMock.mockReset()
    consentSaveMock.mockResolvedValue({ data: { consent: null, region_default: 'EU' } })
  })

  afterEach(() => {
    resetStore()
  })

  it('does not render when hasDecided is true and version matches', async () => {
    resetStore({
      hasDecided: true,
      version: '1.0',
      sessionId: 'sess',
    })
    consentGetMock.mockResolvedValue({ data: { consent: null, region_default: 'EU' } })
    render(<CookieBanner />)
    await waitFor(() => {
      expect(screen.queryByRole('region', { name: /cookie consent/i })).toBeNull()
    })
  })

  it('renders when no decision has been made', async () => {
    resetStore()
    consentGetMock.mockResolvedValue({ data: { consent: null, region_default: 'EU' } })
    render(<CookieBanner />)
    await waitFor(() => {
      expect(screen.getByRole('region', { name: /cookie consent/i })).toBeInTheDocument()
    })
  })

  it('pre-checks analytics for non-EU visitors', async () => {
    resetStore()
    consentGetMock.mockResolvedValue({
      data: { consent: null, region_default: 'non-EU' },
    })
    render(<CookieBanner />)
    await waitFor(() => {
      expect(useConsentStore.getState().categories.analytics).toBe(true)
    })
  })

  it('pre-checks analytics off for EU visitors', async () => {
    resetStore()
    consentGetMock.mockResolvedValue({
      data: { consent: null, region_default: 'EU' },
    })
    render(<CookieBanner />)
    await waitFor(() => {
      expect(useConsentStore.getState().categories.analytics).toBe(false)
    })
  })

  it('Accept all sets all categories true and POSTs', async () => {
    resetStore()
    consentGetMock.mockResolvedValue({ data: { consent: null, region_default: 'EU' } })
    consentSaveMock.mockImplementation(async (payload) => ({
      data: {
        consent: {
          session_id: payload.session_id,
          categories: payload.categories,
          version: payload.version,
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
        },
        region_default: 'EU',
      },
    }))
    render(<CookieBanner />)
    const acceptBtn = await screen.findByRole('button', { name: /accept all cookies/i })
    await act(async () => {
      await userEvent.click(acceptBtn)
    })
    expect(consentSaveMock).toHaveBeenCalled()
    const arg = consentSaveMock.mock.calls.at(-1)?.[0]
    expect(arg.categories.analytics).toBe(true)
    expect(arg.categories.marketing).toBe(true)
  })

  it('Reject all sets analytics/marketing false and POSTs', async () => {
    resetStore()
    consentGetMock.mockResolvedValue({ data: { consent: null, region_default: 'EU' } })
    consentSaveMock.mockImplementation(async (payload) => ({
      data: {
        consent: {
          session_id: payload.session_id,
          categories: payload.categories,
          version: payload.version,
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
        },
        region_default: 'EU',
      },
    }))
    render(<CookieBanner />)
    const rejectBtn = await screen.findByRole('button', {
      name: /reject non-essential cookies/i,
    })
    await act(async () => {
      await userEvent.click(rejectBtn)
    })
    expect(consentSaveMock).toHaveBeenCalled()
    const arg = consentSaveMock.mock.calls.at(-1)?.[0]
    expect(arg.categories.analytics).toBe(false)
    expect(arg.categories.marketing).toBe(false)
  })

  it('Customize opens the ConsentSettingsDialog', async () => {
    resetStore()
    consentGetMock.mockResolvedValue({ data: { consent: null, region_default: 'EU' } })
    render(<CookieBanner />)
    const customizeBtn = await screen.findByRole('button', {
      name: /customize cookie preferences/i,
    })
    await act(async () => {
      await userEvent.click(customizeBtn)
    })
    expect(useConsentStore.getState().isDialogOpen).toBe(true)
  })

  it('renders a link to /legal/cookies', async () => {
    resetStore()
    consentGetMock.mockResolvedValue({ data: { consent: null, region_default: 'EU' } })
    render(<CookieBanner />)
    const cookieLink = await screen.findByRole('link', { name: /cookie policy/i })
    expect(cookieLink.getAttribute('href')).toBe('/legal/cookies')
  })
})
