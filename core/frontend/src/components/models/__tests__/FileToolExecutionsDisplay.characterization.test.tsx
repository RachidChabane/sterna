/**
 * Characterization tests: record FileToolExecutionsDisplay's current
 * rendered output for every major tool-type branch. A snapshot diff means
 * the rendered output changed — investigate before updating the snapshot.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { FileToolExecutionsDisplay } from '../FileToolExecutionsDisplay'

// ---------------------------------------------------------------------------
// Mocks for heavy/leaf child components.
//
// These children are exercised by their own component trees; stubbing them
// here keeps this suite focused on FileToolExecutionsDisplay's own branch
// selection (which tool name renders which section, with which props) and
// keeps snapshots stable across syntax-highlighter/carousel library churn.
// ---------------------------------------------------------------------------
vi.mock('react-syntax-highlighter', () => ({
  Prism: ({ children }: { children?: React.ReactNode }) => (
    <pre data-mock="syntax-highlighter">{children}</pre>
  ),
}))

vi.mock('@/components/models/FileListDisplay', () => ({
  FileListDisplay: ({ result }: { result: unknown }) => (
    <div data-mock="file-list-display">{JSON.stringify(result)}</div>
  ),
}))

vi.mock('@/components/models/BraveSearchMediaCarousel', () => ({
  BraveSearchMediaCarousel: ({ items, title }: { items: unknown[]; title: string }) => (
    <div data-mock="brave-search-media-carousel" data-title={title} data-count={items.length} />
  ),
}))

vi.mock('@/components/models/CodingAgentDisplay', () => ({
  CodingAgentDisplay: (props: {
    task?: string
    status?: string
    jobId?: string
    steps?: unknown[]
    variant?: string
  }) => (
    <div
      data-mock="coding-agent-display"
      data-task={props.task}
      data-status={props.status}
      data-job-id={props.jobId ?? ''}
      data-step-count={props.steps?.length ?? 0}
      data-variant={props.variant}
    />
  ),
}))

vi.mock('@/components/models/ListToolResultsDisplay', async () => {
  const actual = await vi.importActual<typeof import('../ListToolResultsDisplay')>(
    '../ListToolResultsDisplay'
  )
  return {
    ...actual,
    ListToolResultsDisplay: ({ data }: { data: { toolName: string } }) => (
      <div data-mock="list-tool-results-display" data-tool-name={data.toolName} />
    ),
  }
})

// ---------------------------------------------------------------------------
// Fixture builder
// ---------------------------------------------------------------------------
interface ExecutionOverrides {
  success?: boolean | null
  isExecuting?: boolean
  display_name?: string
  server_icon_url?: string
  server_icon_invert?: boolean
  coding_agent_steps?: unknown[]
  coding_agent_result?: unknown
}

function makeExecution(
  toolName: string,
  args: Record<string, unknown>,
  result: unknown,
  overrides: ExecutionOverrides = {}
) {
  const { success = true, isExecuting = false, ...rest } = overrides
  return {
    tool_call: {
      id: `call-${toolName}`,
      type: 'function' as const,
      function: {
        name: toolName,
        arguments: JSON.stringify(args),
      },
      display_name: rest.display_name,
      server_icon_url: rest.server_icon_url,
      server_icon_invert: rest.server_icon_invert,
    },
    result,
    success,
    isExecuting,
    coding_agent_steps: rest.coding_agent_steps,
    coding_agent_result: rest.coding_agent_result,
  }
}

function renderExecutions(executions: ReturnType<typeof makeExecution>[]) {
  return render(<FileToolExecutionsDisplay executions={executions} />)
}

// ---------------------------------------------------------------------------
// File operations
// ---------------------------------------------------------------------------
describe('FileToolExecutionsDisplay — file operations', () => {
  it('renders read_file with a line count', () => {
    const execution = makeExecution(
      'read_file',
      { path: '/workspace/src/app.py' },
      { data: { content: 'line one\nline two\nline three', lines: 3 } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders write_file collapsed by default', () => {
    const execution = makeExecution(
      'write_file',
      { path: '/workspace/src/new_file.py', content: 'print("hello")\n' },
      { data: { success: true } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders edit_file collapsed by default', () => {
    const execution = makeExecution(
      'edit_file',
      { path: '/workspace/src/app.py', old_string: 'foo', new_string: 'bar' },
      { data: { success: true, diff: '-foo\n+bar' } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders delete_file as a plain file-path row (no special result section)', () => {
    const execution = makeExecution(
      'delete_file',
      { path: '/workspace/src/old_file.py' },
      { data: { success: true } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders create_directory as a plain file-path row', () => {
    const execution = makeExecution(
      'create_directory',
      { path: '/workspace/src/newdir' },
      { data: { success: true } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders rename_file showing old → new path', () => {
    const execution = makeExecution(
      'rename_file',
      { old_path: '/workspace/a.py', new_path: '/workspace/b.py' },
      { data: { success: true } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders list_files with a tree view (via FileListDisplay)', () => {
    const execution = makeExecution(
      'list_files',
      { path: '/workspace' },
      { data: { entries: [{ name: 'app.py', type: 'file' }] } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })
})

// ---------------------------------------------------------------------------
// Code execution
// ---------------------------------------------------------------------------
describe('FileToolExecutionsDisplay — code execution', () => {
  it('renders execute_code success collapsed by default', () => {
    const execution = makeExecution(
      'execute_code',
      { language: 'python', code: 'print(1 + 1)' },
      { result: { output: '2\n', error: null, exit_code: 0, execution_time: 0.12 } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders execute_code failure', () => {
    const execution = makeExecution(
      'execute_code',
      { language: 'python', code: 'raise ValueError("boom")' },
      { result: { output: '', error: 'ValueError: boom', exit_code: 1, execution_time: 0.03 } },
      { success: false }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders run_bash success with an expandable command', () => {
    const execution = makeExecution(
      'run_bash',
      { command: 'ls -la /workspace' },
      { output: 'app.py\nREADME.md\n', error: '', exit_code: 0 }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('flags run_bash as failed when output matches an error pattern even though success=true', () => {
    const execution = makeExecution(
      'run_bash',
      { command: 'cat missing.txt' },
      { output: 'cat: missing.txt: No such file or directory', error: '', exit_code: 0 },
      { success: true }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders execute_programming_task collapsed by default', () => {
    const execution = makeExecution(
      'execute_programming_task',
      { task_description: 'Compute the sum of 1..10', code: 'sum(range(1, 11))' },
      { success: true, output: '55', data: { message: 'done', items: [1, 2, 3] } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })
})

// ---------------------------------------------------------------------------
// Search / discovery tools
// ---------------------------------------------------------------------------
describe('FileToolExecutionsDisplay — search and discovery', () => {
  it('renders search_available_tools with a found count', () => {
    const execution = makeExecution(
      'search_available_tools',
      { query: 'weather', category: 'maps' },
      { found: 3, available: 2, tools: [{ name: 'get_air_quality' }, { name: 'get_directions' }] }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders search_code collapsed with a match count', () => {
    const execution = makeExecution(
      'search_code',
      { pattern: 'TODO' },
      {
        matches: [
          { file: 'src/app.py', line: 12, content: '# TODO: refactor this' },
          { file: 'src/utils.py', line: 4, content: '# TODO: add tests' },
        ],
        total_matches: 2,
      }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders brave_web_search as a generic icon+summary row', () => {
    const execution = makeExecution(
      'brave_web_search',
      { query: 'sterna ai' },
      { results: [{ title: 'Result A' }, { title: 'Result B' }] }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders brave_image_search with a media carousel', () => {
    const execution = makeExecution(
      'brave_image_search',
      { query: 'mountains' },
      {
        results: [
          { thumbnail: { src: 'https://example.com/thumb1.jpg' }, url: 'https://example.com/1.jpg', title: 'Mountain 1' },
          { thumbnail: { src: 'https://example.com/thumb2.jpg' }, url: 'https://example.com/2.jpg', title: 'Mountain 2' },
        ],
      }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders brave_video_search with a media carousel', () => {
    const execution = makeExecution(
      'brave_video_search',
      { query: 'ocean waves' },
      {
        results: [
          { thumbnail: { src: 'https://example.com/vthumb1.jpg' }, url: 'https://example.com/v1', title: 'Waves 1', duration: '1:20' },
        ],
      }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders brave_local_search as a generic icon+summary row', () => {
    const execution = makeExecution(
      'brave_local_search',
      { query: 'coffee shops near me' },
      { results: [{ title: 'Cafe One' }] }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders brave_news_search as a generic icon+summary row', () => {
    const execution = makeExecution(
      'brave_news_search',
      { query: 'AI news' },
      { results: [{ title: 'Headline A' }, { title: 'Headline B' }, { title: 'Headline C' }] }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders fetch_web_page with a page title summary', () => {
    const execution = makeExecution(
      'fetch_web_page',
      { url: 'https://example.com/article' },
      { success: true, title: 'An Interesting Article', url: 'https://example.com/article' }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })
})

// ---------------------------------------------------------------------------
// Maps / weather tools
// ---------------------------------------------------------------------------
describe('FileToolExecutionsDisplay — maps and weather', () => {
  it('renders geocode_address with coordinates summary', () => {
    const execution = makeExecution(
      'geocode_address',
      { address: '1 Infinite Loop, Cupertino, CA' },
      { latitude: 37.33182, longitude: -122.03118, formatted_address: '1 Infinite Loop, Cupertino, CA 95014' }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders get_directions with a duration/distance summary', () => {
    const execution = makeExecution(
      'get_directions',
      { origin: 'A', destination: 'B' },
      { duration: '18 mins', distance: '9.4 km' }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders search_nearby_places with a place count', () => {
    const execution = makeExecution(
      'search_nearby_places',
      { location: 'downtown', type: 'restaurant' },
      { places: [{ name: 'Place A' }, { name: 'Place B' }] }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders get_air_quality with no summary line (fields outside the count/total heuristic)', () => {
    const execution = makeExecution(
      'get_air_quality',
      { location: 'San Francisco' },
      { aqi: 42, category: 'Good' }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })
})

// ---------------------------------------------------------------------------
// Generation, sparks, knowledge base, coding agent
// ---------------------------------------------------------------------------
describe('FileToolExecutionsDisplay — generation and agent tools', () => {
  it('renders generate_image as a generic icon+summary row (no inline preview)', () => {
    const execution = makeExecution(
      'generate_image',
      { prompt: 'a red bicycle' },
      { success: true, url: 'https://example.com/generated.png' }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders generate_video as a generic icon+summary row (no inline preview)', () => {
    const execution = makeExecution(
      'generate_video',
      { prompt: 'a sunrise timelapse' },
      { success: true, url: 'https://example.com/generated.mp4' }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders update_todos with a task checklist', () => {
    const execution = makeExecution(
      'update_todos',
      {
        todos: [
          { text: 'Write tests', status: 'completed' },
          { text: 'Fix bug', status: 'in_progress' },
          { text: 'Ship it', status: 'pending' },
        ],
      },
      { data: { todos: [
        { text: 'Write tests', status: 'completed' },
        { text: 'Fix bug', status: 'in_progress' },
        { text: 'Ship it', status: 'pending' },
      ] } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders create_spark as a clickable summary row', () => {
    const execution = makeExecution(
      'create_spark',
      { title: 'Expense Tracker', framework: 'react' },
      { status: 'success', spark: { id: 'spark-1', title: 'Expense Tracker', version: 1 } }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders update_spark with an inline diff', () => {
    const execution = makeExecution(
      'update_spark',
      { spark_id: 'spark-1', instructions: 'add a total row' },
      {
        spark: {
          title: 'Expense Tracker',
          version: 2,
          old_code: 'const total = 0',
          code: 'const total = items.reduce((a, b) => a + b, 0)',
        },
      }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders query_knowledge_base with result chunks', () => {
    const execution = makeExecution(
      'query_knowledge_base',
      { query: 'refund policy' },
      {
        query: 'refund policy',
        total_results: 1,
        formatted_text: 'Refunds are processed within 5 business days.',
        results: [
          {
            chunk_id: 'chunk-1',
            document_id: 'doc-1',
            document_filename: 'policies.pdf',
            document_type: 'pdf',
            content: 'Refunds are processed within 5 business days.',
            full_content: 'Refunds are processed within 5 business days.',
            chunk_index: 0,
            page_number: 1,
            similarity_score: 0.92,
            token_count: 12,
          },
        ],
      }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders list_sparks via the shared list-tool results display', () => {
    const execution = makeExecution(
      'list_sparks',
      {},
      { sparks: [{ id: 'spark-1', title: 'Expense Tracker', framework: 'react', version: 1 }], total_sparks: 1 }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders list_processes with a process table', () => {
    const execution = makeExecution(
      'list_processes',
      {},
      { processes: [{ pid: 1234, command: 'node server.js', port: 3000, status: 'running' }] }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders a coding_agent tool call as the premium agent card, skipping the standard header row', () => {
    const execution = makeExecution(
      'coding_agent',
      { task: 'Add a health check endpoint' },
      {
        result: {
          success: true,
          data: {
            job_id: 'job-1',
            summary: 'Added /health endpoint',
            files_created: ['src/health.py'],
            files_modified: [],
            duration_ms: 4200,
            steps: [{ id: 'step-1' }],
          },
        },
      }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })
})

// ---------------------------------------------------------------------------
// GitHub tools and MCP server-provided tools
// ---------------------------------------------------------------------------
describe('FileToolExecutionsDisplay — GitHub and MCP tools', () => {
  it('renders github_list_issues with an issue count summary', () => {
    const execution = makeExecution(
      'github_list_issues',
      { repo: 'acme/widgets' },
      { issues: [{ number: 1 }, { number: 2 }, { number: 3 }] }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders an unrecognized github_-prefixed tool using a formatted fallback name', () => {
    const execution = makeExecution(
      'github_star_repo',
      { repo: 'acme/widgets' },
      { success: true }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders an MCP server tool using the server-provided icon and display name', () => {
    const execution = makeExecution(
      'mcp_custom_tool',
      { input: 'value' },
      { success: true },
      {
        display_name: 'Custom MCP Tool',
        server_icon_url: 'https://example.com/mcp-icon.png',
        server_icon_invert: true,
      }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })
})

// ---------------------------------------------------------------------------
// Execution lifecycle states (executing / failed), independent of tool type
// ---------------------------------------------------------------------------
describe('FileToolExecutionsDisplay — execution lifecycle states', () => {
  it('renders a spinner while a tool is still executing, with no result section yet', () => {
    const execution = makeExecution(
      'run_bash',
      { command: 'npm install' },
      null,
      { isExecuting: true, success: null }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders a failed-state indicator for a non-run_bash tool', () => {
    const execution = makeExecution(
      'search_code',
      { pattern: 'TODO' },
      { error: 'search index unavailable' },
      { success: false }
    )
    const { container } = renderExecutions([execution])
    expect(container).toMatchSnapshot()
  })

  it('renders nothing for an empty executions array', () => {
    const { container } = renderExecutions([])
    expect(container).toMatchSnapshot()
  })
})

// ---------------------------------------------------------------------------
// Component-level props: variant, showBraveSearchMedia
// ---------------------------------------------------------------------------
describe('FileToolExecutionsDisplay — display variants', () => {
  it('renders the "code" variant with dot-style status instead of check/x', () => {
    const execution = makeExecution(
      'read_file',
      { path: '/workspace/src/app.py' },
      { data: { content: 'print(1)', lines: 1 } }
    )
    const { container } = render(
      <FileToolExecutionsDisplay executions={[execution]} variant="code" />
    )
    expect(container).toMatchSnapshot()
  })

  it('suppresses the Brave Search media carousel when showBraveSearchMedia=false', () => {
    const execution = makeExecution(
      'brave_image_search',
      { query: 'mountains' },
      { results: [{ thumbnail: { src: 'https://example.com/thumb1.jpg' }, url: 'https://example.com/1.jpg' }] }
    )
    const { container } = render(
      <FileToolExecutionsDisplay executions={[execution]} showBraveSearchMedia={false} />
    )
    expect(container).toMatchSnapshot()
  })

  it('renders a mixed sequence of tool executions in order', () => {
    const executions = [
      makeExecution('read_file', { path: '/a.py' }, { data: { content: 'a', lines: 1 } }),
      makeExecution('run_bash', { command: 'pytest' }, { output: 'OK', error: '', exit_code: 0 }),
      makeExecution('update_todos', { todos: [{ text: 'Ship', status: 'pending' }] }, { data: { todos: [{ text: 'Ship', status: 'pending' }] } }),
    ]
    const { container } = renderExecutions(executions)
    expect(container).toMatchSnapshot()
  })
})
