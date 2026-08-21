import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { HelpDrawer } from '../HelpDrawer'
import { useHelpDrawerStore } from '@/store/helpDrawerStore'

vi.mock('@/api/support', () => ({
  supportApi: {
    createRequest: vi.fn().mockResolvedValue({ data: { id: 'abc', message: 'ok' } }),
  },
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: () => ({
    user: { email: 'test@example.com' },
    isAuthenticated: true,
  }),
}))

vi.mock('@tanstack/react-router', () => ({
  useRouterState: () => ({ location: { pathname: '/chats' } }),
}))

function openDrawer() {
  useHelpDrawerStore.getState().open('faq')
}

describe('HelpDrawer', () => {
  beforeEach(() => {
    useHelpDrawerStore.getState().close()
  })

  it('renders FAQ tab by default when opened', () => {
    openDrawer()
    render(<HelpDrawer />)
    expect(screen.getByText('FAQ')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Search FAQ…')).toBeInTheDocument()
  })

  it('filters FAQ articles on search', () => {
    openDrawer()
    render(<HelpDrawer />)
    const search = screen.getByPlaceholderText('Search FAQ…')
    fireEvent.change(search, { target: { value: 'billing' } })
    expect(screen.queryByText('Voice room audio quality is poor')).not.toBeInTheDocument()
  })

  it('switches to contact tab', async () => {
    const user = userEvent.setup()
    openDrawer()
    render(<HelpDrawer />)
    await user.click(screen.getByRole('tab', { name: 'Contact us' }))
    expect(screen.getByLabelText('Subject')).toBeInTheDocument()
    expect(screen.getByLabelText('Message')).toBeInTheDocument()
  })

  it('submits contact form and shows success state', async () => {
    const user = userEvent.setup()
    const { supportApi } = await import('@/api/support')
    openDrawer()
    render(<HelpDrawer />)
    await user.click(screen.getByRole('tab', { name: 'Contact us' }))
    await user.type(screen.getByLabelText('Subject'), 'My issue')
    await user.type(screen.getByLabelText('Message'), 'This is my detailed message here')
    await user.click(screen.getByRole('button', { name: /send message/i }))
    await waitFor(() => {
      expect(supportApi.createRequest).toHaveBeenCalledWith(
        expect.objectContaining({ subject: 'My issue' })
      )
    })
    expect(screen.getByText('Message received!')).toBeInTheDocument()
  })

  it('shows status tab with iframe', async () => {
    const user = userEvent.setup()
    openDrawer()
    render(<HelpDrawer />)
    await user.click(screen.getByRole('tab', { name: 'Status' }))
    const iframe = screen.getByTitle('Sterna Status Page')
    expect(iframe).toHaveAttribute('src', 'https://status.example.com')
  })
})
