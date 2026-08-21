import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useConsentStore } from '@/store/consentStore'

const consentSaveMock = vi.fn()

vi.mock('@/api/endpoints', () => ({
  authApi: {
    consent: {
      get: vi.fn(),
      save: (...args: unknown[]) => consentSaveMock(...args),
      attach: vi.fn(),
    },
  },
}))

import { ConsentSettingsDialog } from '../ConsentSettingsDialog'

function resetStore(partial: Partial<ReturnType<typeof useConsentStore.getState>> = {}) {
  useConsentStore.setState({
    sessionId: 'fixed-session',
    categories: { essential: true, analytics: false, marketing: false },
    version: '',
    regionDefault: 'EU',
    hasDecided: false,
    isBannerOpen: false,
    isDialogOpen: false,
    ...partial,
  })
}

describe('ConsentSettingsDialog', () => {
  beforeEach(() => {
    localStorage.clear()
    consentSaveMock.mockReset()
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
  })

  afterEach(() => {
    resetStore({ isDialogOpen: false })
  })

  it('essential toggle is checked and disabled in modal mode', async () => {
    resetStore({ isDialogOpen: true })
    render(<ConsentSettingsDialog mode="modal" />)
    const essential = await screen.findByRole('switch', { name: /^essential$/i })
    expect(essential.getAttribute('aria-checked')).toBe('true')
    expect(essential).toBeDisabled()
  })

  it('analytics toggle reflects store state', async () => {
    resetStore({
      isDialogOpen: true,
      categories: { essential: true, analytics: true, marketing: false },
    })
    render(<ConsentSettingsDialog mode="modal" />)
    const analytics = await screen.findByRole('switch', { name: /analytics/i })
    expect(analytics.getAttribute('aria-checked')).toBe('true')
  })

  it('save preferences POSTs the current category state', async () => {
    resetStore({
      isDialogOpen: true,
      categories: { essential: true, analytics: true, marketing: false },
    })
    render(<ConsentSettingsDialog mode="modal" />)
    const analytics = await screen.findByRole('switch', { name: /analytics/i })
    await act(async () => {
      await userEvent.click(analytics)
    })
    const save = screen.getByRole('button', { name: /save preferences/i })
    await act(async () => {
      await userEvent.click(save)
    })
    expect(consentSaveMock).toHaveBeenCalled()
    const arg = consentSaveMock.mock.calls.at(-1)?.[0]
    expect(arg.categories.analytics).toBe(false)
  })

  it('renders in page mode without dialog chrome', () => {
    resetStore({ isDialogOpen: false })
    render(<ConsentSettingsDialog mode="page" />)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByRole('switch', { name: /analytics/i })).toBeInTheDocument()
  })
})
