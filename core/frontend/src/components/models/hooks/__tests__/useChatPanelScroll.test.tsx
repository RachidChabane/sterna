import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useChatPanelScroll } from '../useChatPanelScroll'
import type { Message } from '../../types'

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    role: 'user',
    content: 'hi',
    timestamp: new Date('2026-01-01T00:00:00Z'),
    ...overrides,
  } as Message
}

function makeContainer() {
  const outer = document.createElement('div')
  const viewport = document.createElement('div')
  viewport.setAttribute('data-radix-scroll-area-viewport', '')
  viewport.scrollTo = vi.fn()
  Object.defineProperty(viewport, 'scrollHeight', { value: 500, configurable: true })
  outer.appendChild(viewport)
  document.body.appendChild(outer)
  return { outer, viewport }
}

describe('useChatPanelScroll', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('does nothing when there is no viewport element', () => {
    const ref = { current: document.createElement('div') }
    expect(() => renderHook(() => useChatPanelScroll(ref, [makeMessage()]))).not.toThrow()
  })

  it('does nothing when there are no messages', () => {
    const { outer, viewport } = makeContainer()
    const ref = { current: outer }
    renderHook(() => useChatPanelScroll(ref, []))
    expect(viewport.scrollTo).not.toHaveBeenCalled()
  })

  it('follows the bottom for a new assistant message', () => {
    const { outer, viewport } = makeContainer()
    const ref = { current: outer }
    const messages = [makeMessage({ role: 'assistant', content: 'hello' })]
    renderHook(() => useChatPanelScroll(ref, messages))
    expect(viewport.scrollTop).toBe(500)
  })

  it('scrolls the last user message into view (smooth) for a new user message', () => {
    const rafSpy = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
      cb(0)
      return 0
    })
    const { outer, viewport } = makeContainer()
    const userEl = document.createElement('div')
    userEl.setAttribute('data-message-role', 'user')
    viewport.appendChild(userEl)
    const ref = { current: outer }
    const messages = [makeMessage({ role: 'user' })]

    renderHook(() => useChatPanelScroll(ref, messages))

    expect(viewport.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'smooth' }))
    rafSpy.mockRestore()
  })

  it('registers a scroll listener on the viewport for clamping', () => {
    const { outer, viewport } = makeContainer()
    const addSpy = vi.spyOn(viewport, 'addEventListener')
    const ref = { current: outer }
    renderHook(() => useChatPanelScroll(ref, [makeMessage()]))
    expect(addSpy).toHaveBeenCalledWith('scroll', expect.any(Function))
  })
})
