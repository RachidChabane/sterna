import { describe, it, expect } from 'vitest'
import { extractSparksFromToolResults, buildExecutionsFromToolResults } from '../toolResultProcessing'

function toolCall(name: string, id = 't1') {
  return { id, type: 'function' as const, function: { name, arguments: '{}' } }
}

describe('extractSparksFromToolResults', () => {
  it('extracts a spark from a successful create_spark result', () => {
    const sparks = extractSparksFromToolResults(
      [toolCall('create_spark')],
      [{ result: { status: 'success', spark: { id: 's1', title: 'My Spark', framework: 'react', code: '<div/>', version: 1 } } }],
    )
    expect(sparks).toEqual([{
      id: 's1', title: 'My Spark', framework: 'react', code: '<div/>', version: 1,
      assets: undefined, download_url: undefined,
    }])
  })

  it('also extracts from update_spark results', () => {
    const sparks = extractSparksFromToolResults(
      [toolCall('update_spark')],
      [{ result: { status: 'success', spark: { id: 's1', title: 'Updated', framework: 'html', code: '<p/>', version: 2 } } }],
    )
    expect(sparks).toHaveLength(1)
  })

  it('ignores unrelated tools and failed spark results', () => {
    const sparks = extractSparksFromToolResults(
      [toolCall('web_search'), toolCall('create_spark', 't2')],
      [{ result: { ok: true } }, { result: { status: 'error' } }],
    )
    expect(sparks).toEqual([])
  })
})

describe('buildExecutionsFromToolResults', () => {
  it('marks a plain tool execution as completed with its result', () => {
    const executions = buildExecutionsFromToolResults(
      [toolCall('web_search')],
      [{ success: true, data: { hits: 3 } }],
      [],
      null,
    )
    expect(executions).toEqual([{
      tool_call: toolCall('web_search'),
      result: { success: true, data: { hits: 3 } },
      success: true,
      isExecuting: false,
    }])
  })

  it('treats a missing success field as successful (only explicit false counts as failure)', () => {
    const executions = buildExecutionsFromToolResults([toolCall('web_search')], [{ data: {} }], [], null)
    expect(executions[0].success).toBe(true)
  })

  it('marks a result with success: false as failed', () => {
    const executions = buildExecutionsFromToolResults([toolCall('web_search')], [{ success: false }], [], null)
    expect(executions[0].success).toBe(false)
  })

  it('attaches coding_agent_steps/result from coding_agent_data for Coding Agent tools', () => {
    const executions = buildExecutionsFromToolResults(
      [toolCall('coding_agent')],
      [{ success: true, coding_agent_data: { steps: [{ type: 'thinking' }], summary: 'done' } }],
      [],
      null,
    )
    expect(executions[0]).toMatchObject({
      coding_agent_steps: [{ type: 'thinking' }],
      coding_agent_result: { steps: [{ type: 'thinking' }], summary: 'done' },
    })
  })

  it('falls back to the in-flight accumulated Coding Agent state when coding_agent_data is absent', () => {
    const accumulatedSteps = [{ job_id: 'job-1', step_index: 0, type: 'thinking' as const }]
    const accumulatedResult = { job_id: 'job-1', success: true, summary: 'partial', duration_ms: 42 }
    const executions = buildExecutionsFromToolResults(
      [toolCall('plan_implementation')],
      [{ success: true }],
      accumulatedSteps,
      accumulatedResult,
    )
    expect(executions[0]).toMatchObject({
      coding_agent_steps: accumulatedSteps,
      coding_agent_result: accumulatedResult,
    })
  })

  it('builds a synthetic result when neither coding_agent_data nor accumulated state is available', () => {
    const executions = buildExecutionsFromToolResults(
      [toolCall('implement_plan')],
      [{ success: false, summary: 'failed', files_created: ['a.ts'], files_modified: [] }],
      [],
      null,
    )
    expect(executions[0]).toMatchObject({
      coding_agent_steps: [],
      coding_agent_result: { success: false, summary: 'failed', files_created: ['a.ts'], files_modified: [] },
    })
  })
})
