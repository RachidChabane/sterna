import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useImmersiveModePreference } from '../useImmersiveModePreference'

describe('useImmersiveModePreference', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('returns the default value when nothing has been saved for the conversation', () => {
    const { result } = renderHook(() => useImmersiveModePreference())
    expect(result.current.loadImmersiveMode('conv-1', true)).toBe(true)
    expect(result.current.loadImmersiveMode('conv-1', false)).toBe(false)
  })

  it('round-trips a saved value for its own conversation id', () => {
    const { result } = renderHook(() => useImmersiveModePreference())
    result.current.saveImmersiveMode('conv-1', false)
    expect(result.current.loadImmersiveMode('conv-1', true)).toBe(false)
  })

  it('keeps preferences isolated per conversation id', () => {
    const { result } = renderHook(() => useImmersiveModePreference())
    result.current.saveImmersiveMode('conv-1', false)
    expect(result.current.loadImmersiveMode('conv-2', true)).toBe(true)
  })

  it('falls back to the default value when the stored JSON is corrupt', () => {
    window.localStorage.setItem('models.immersive_mode.conv-1', 'not-json')
    const { result } = renderHook(() => useImmersiveModePreference())
    expect(result.current.loadImmersiveMode('conv-1', true)).toBe(true)
  })

  it('does not throw when localStorage.setItem fails (e.g. storage disabled)', () => {
    const original = window.localStorage.setItem
    window.localStorage.setItem = () => {
      throw new Error('storage disabled')
    }
    const { result } = renderHook(() => useImmersiveModePreference())
    expect(() => result.current.saveImmersiveMode('conv-1', true)).not.toThrow()
    window.localStorage.setItem = original
  })

  it('keeps saveImmersiveMode and loadImmersiveMode referentially stable across re-renders', () => {
    const { result, rerender } = renderHook(() => useImmersiveModePreference())
    const firstSave = result.current.saveImmersiveMode
    const firstLoad = result.current.loadImmersiveMode
    rerender()
    expect(result.current.saveImmersiveMode).toBe(firstSave)
    expect(result.current.loadImmersiveMode).toBe(firstLoad)
  })
})
