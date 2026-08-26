import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { useChatAutoScroll } from '../useChatAutoScroll'
import type { Message } from '../../types'

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    role: 'user',
    content: 'hi',
    timestamp: new Date('2026-01-01T00:00:00Z'),
    message_id: 'msg-1',
    ...overrides,
  }
}

function mockRect(el: HTMLElement, rect: Partial<DOMRect>) {
  vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
    top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0,
    toJSON: () => ({}),
    ...rect,
  } as DOMRect)
}

interface HarnessProps {
  messages: Message[]
  isGenerating: boolean
  conversationId: string
}

function Harness({ messages, isGenerating, conversationId }: HarnessProps) {
  const { scrollContainerRef, contentEndRef, spacerRef } = useChatAutoScroll({
    messages,
    isGenerating,
    conversationId,
  })
  return (
    <div ref={scrollContainerRef} data-testid="scroll-container">
      <div data-message-role="user" data-testid="user-msg">user message</div>
      <div ref={contentEndRef} data-testid="content-end" />
      <div ref={spacerRef} data-testid="spacer" />
    </div>
  )
}

describe('useChatAutoScroll', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders without throwing and exposes bindable refs for an empty transcript', () => {
    const { getByTestId } = render(<Harness messages={[]} isGenerating={false} conversationId="conv-1" />)
    expect(getByTestId('scroll-container')).toBeInTheDocument()
    expect(getByTestId('spacer')).toBeInTheDocument()
  })

  it('clamps scrollTop back to the last user message top when scrolled past it', () => {
    const { getByTestId } = render(
      <Harness messages={[makeMessage()]} isGenerating={false} conversationId="conv-1" />
    )
    const container = getByTestId('scroll-container') as HTMLDivElement
    const userMsg = getByTestId('user-msg') as HTMLDivElement

    mockRect(container, { top: 0, bottom: 500 })
    Object.defineProperty(container, 'clientHeight', { value: 500, configurable: true })
    // The user message sits above the container's viewport (negative top/bottom),
    // so the clamp must pull scrollTop back down to it.
    mockRect(userMsg, { top: -200, bottom: -170 })

    Object.defineProperty(container, 'scrollTop', { value: 500, writable: true, configurable: true })
    container.dispatchEvent(new Event('scroll'))

    // lastUserMsgAbsoluteTop = 500 + (-200 - 0) = 300
    // lastMessageBottom = 500 + (-170 - 0) = 330; effectiveViewport = 500
    // maxScroll = max(300, 330 - 500) = 300 — scrollTop (500) exceeds it, so it clamps to 300.
    expect(container.scrollTop).toBe(300)
  })

  it('resets the spacer height when the conversation id changes', () => {
    const { getByTestId, rerender } = render(
      <Harness messages={[makeMessage()]} isGenerating={false} conversationId="conv-1" />
    )
    const spacer = getByTestId('spacer') as HTMLDivElement
    spacer.style.height = '42px'

    rerender(<Harness messages={[makeMessage()]} isGenerating={false} conversationId="conv-2" />)

    expect(spacer.style.height).toBe('0px')
  })
})
