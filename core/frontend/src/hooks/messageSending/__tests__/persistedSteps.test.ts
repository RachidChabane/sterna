import { describe, it, expect } from 'vitest'
import { buildPersistedSteps } from '../persistedSteps'

describe('buildPersistedSteps', () => {
  it('prepends a reasoning step only when reasoning content is present', () => {
    const withReasoning = buildPersistedSteps('some thoughts', [], { filterIncomplete: false })
    expect(withReasoning).toEqual([{ type: 'reasoning', content: 'some thoughts', isStreaming: false }])

    const withoutReasoning = buildPersistedSteps('', [], { filterIncomplete: false })
    expect(withoutReasoning).toEqual([])
  })

  it('drops blank text steps but keeps non-blank ones', () => {
    const steps = buildPersistedSteps('', [
      { type: 'text', content: '   ' },
      { type: 'text', content: 'hello' },
    ], { filterIncomplete: false })
    expect(steps).toEqual([{ type: 'text', content: 'hello' }])
  })

  it('when filterIncomplete is false, persists every execution and marks it not-executing', () => {
    const steps = buildPersistedSteps('', [
      {
        type: 'tool_executions',
        executions: [
          { tool_call: { id: 't1' }, result: null, success: null, isExecuting: true },
          { tool_call: { id: 't2' }, result: { ok: true }, success: true, isExecuting: false },
        ],
      },
    ], { filterIncomplete: false })

    expect(steps).toEqual([{
      type: 'tool_executions',
      isExecuting: false,
      executions: [
        { tool_call: { id: 't1' }, result: null, success: null, isExecuting: false },
        { tool_call: { id: 't2' }, result: { ok: true }, success: true, isExecuting: false },
      ],
    }])
  })

  it('when filterIncomplete is true, drops executions that are still executing with no result', () => {
    const steps = buildPersistedSteps('', [
      {
        type: 'tool_executions',
        executions: [
          { tool_call: { id: 't1' }, result: null, success: null, isExecuting: true },
          { tool_call: { id: 't2' }, result: { ok: true }, success: true, isExecuting: false },
        ],
      },
    ], { filterIncomplete: true })

    expect(steps).toEqual([{
      type: 'tool_executions',
      isExecuting: false,
      executions: [
        { tool_call: { id: 't2' }, result: { ok: true }, success: true, isExecuting: false },
      ],
    }])
  })

  it('when filterIncomplete is true and every execution is incomplete, the whole step is dropped', () => {
    const steps = buildPersistedSteps('', [
      {
        type: 'tool_executions',
        executions: [{ tool_call: { id: 't1' }, result: null, success: null, isExecuting: true }],
      },
    ], { filterIncomplete: true })

    expect(steps).toEqual([])
  })

  it('preserves coding_agent_steps / coding_agent_result on executions that carry them', () => {
    const steps = buildPersistedSteps('', [
      {
        type: 'tool_executions',
        executions: [{
          tool_call: { id: 't1' },
          result: { ok: true },
          success: true,
          isExecuting: false,
          coding_agent_steps: [{ type: 'thinking' }],
          coding_agent_result: { success: true },
        }],
      },
    ], { filterIncomplete: false })

    expect(steps[0].executions[0]).toMatchObject({
      coding_agent_steps: [{ type: 'thinking' }],
      coding_agent_result: { success: true },
    })
  })

  it('preserves the interleaved order of reasoning, text and tool_executions steps', () => {
    const steps = buildPersistedSteps('thinking', [
      { type: 'text', content: 'first' },
      { type: 'tool_executions', executions: [{ tool_call: { id: 't1' }, result: { ok: true }, success: true, isExecuting: false }] },
      { type: 'text', content: 'second' },
    ], { filterIncomplete: false })

    expect(steps.map((s) => s.type)).toEqual(['reasoning', 'text', 'tool_executions', 'text'])
  })
})
