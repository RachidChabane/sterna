import { describe, it, expect } from 'vitest'
import { getReasoningDelta, cleanupStreamingSteps } from '../streamingStepHelpers'

describe('getReasoningDelta', () => {
  it('returns the full string when there is no previous content', () => {
    expect(getReasoningDelta('Thinking...', '')).toBe('Thinking...')
  })

  it('slices off the previously-seen prefix when content is accumulated', () => {
    expect(getReasoningDelta('Thinking about it further', 'Thinking about it')).toBe(' further')
  })

  it('returns the full current content when it does not extend the previous content', () => {
    // Model sent fresh (non-accumulated) reasoning content this time.
    expect(getReasoningDelta('A completely different thought', 'Thinking about it')).toBe('A completely different thought')
  })
})

describe('cleanupStreamingSteps', () => {
  it('returns an empty array for undefined steps', () => {
    expect(cleanupStreamingSteps(undefined)).toEqual([])
  })

  it('marks a still-executing tool_executions step as complete when nothing else duplicates it', () => {
    const steps = cleanupStreamingSteps([
      {
        type: 'tool_executions',
        isExecuting: true,
        executions: [{ tool_call: { id: 't1', type: 'function', function: { name: 'web_search', arguments: '{}' } }, result: null, success: null, isExecuting: true }],
      },
    ])
    expect(steps).toEqual([
      {
        type: 'tool_executions',
        isExecuting: false,
        executions: [{ tool_call: { id: 't1', type: 'function', function: { name: 'web_search', arguments: '{}' } }, result: null, success: null, isExecuting: false }],
      },
    ])
  })

  it('drops an orphaned executing step whose tool calls already have a completed duplicate', () => {
    const toolCall = { id: 't1', type: 'function' as const, function: { name: 'web_search', arguments: '{}' } }
    const steps = cleanupStreamingSteps([
      { type: 'tool_executions', isExecuting: true, executions: [{ tool_call: toolCall, result: null, success: null, isExecuting: true }] },
      { type: 'tool_executions', isExecuting: false, executions: [{ tool_call: toolCall, result: { ok: true }, success: true, isExecuting: false }] },
    ])
    expect(steps).toHaveLength(1)
    expect(steps[0].isExecuting).toBe(false)
  })

  it('leaves text and reasoning steps untouched', () => {
    const steps = cleanupStreamingSteps([
      { type: 'text', content: 'hello' },
      { type: 'reasoning', content: 'thinking', isStreaming: false },
    ])
    expect(steps).toEqual([
      { type: 'text', content: 'hello' },
      { type: 'reasoning', content: 'thinking', isStreaming: false },
    ])
  })
})
