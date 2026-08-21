import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { BetaDisclaimerModal, hasBetaDisclaimerBeenSeen } from '../BetaDisclaimerModal'

const defaultProps = {
  featureName: 'Test Feature',
  featureKey: 'test_feature',
  limitations: ['Limitation one', 'Limitation two'],
  open: true,
  onContinue: vi.fn(),
  onCancel: vi.fn(),
}

describe('BetaDisclaimerModal', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  it('renders when open=true', () => {
    render(<BetaDisclaimerModal {...defaultProps} />)
    expect(screen.getByText('Test Feature is in Beta')).toBeInTheDocument()
    expect(screen.getByText('Limitation one')).toBeInTheDocument()
  })

  it('does not render content when open=false', () => {
    render(<BetaDisclaimerModal {...defaultProps} open={false} />)
    expect(screen.queryByText('Test Feature is in Beta')).not.toBeInTheDocument()
  })

  it('calls onContinue and sets sessionStorage when "Got it" clicked', () => {
    render(<BetaDisclaimerModal {...defaultProps} />)
    fireEvent.click(screen.getByText('Got it, continue'))
    expect(defaultProps.onContinue).toHaveBeenCalledTimes(1)
    expect(sessionStorage.getItem('betaDisclaimerSeen:test_feature')).toBe('1')
  })

  it('calls onCancel when "Cancel" clicked', () => {
    render(<BetaDisclaimerModal {...defaultProps} />)
    fireEvent.click(screen.getByText('Cancel'))
    expect(defaultProps.onCancel).toHaveBeenCalledTimes(1)
  })

  it('hasBetaDisclaimerBeenSeen returns false before dismissal', () => {
    expect(hasBetaDisclaimerBeenSeen('test_feature')).toBe(false)
  })

  it('hasBetaDisclaimerBeenSeen returns true after sessionStorage is set', () => {
    sessionStorage.setItem('betaDisclaimerSeen:test_feature', '1')
    expect(hasBetaDisclaimerBeenSeen('test_feature')).toBe(true)
  })

  it('renders "Report a problem" as a mailto link', () => {
    render(<BetaDisclaimerModal {...defaultProps} />)
    const link = screen.getByText('Report a problem')
    expect(link.tagName).toBe('A')
    expect(link.getAttribute('href')).toContain('mailto:support@example.com')
  })
})
