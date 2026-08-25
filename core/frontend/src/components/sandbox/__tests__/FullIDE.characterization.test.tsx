/**
 * Characterization tests: record FullIDE's current rendered output for a
 * set of representative prop states. A snapshot diff means the rendered
 * output changed — investigate before updating the snapshot.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { FullIDE } from '../FullIDE'
import type { Message } from '@/components/models/types'
import type { FileNode } from '../types'

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

const listFiles = vi.fn()
const restoreWorkspace = vi.fn()
const saveWorkspace = vi.fn().mockResolvedValue({ success: true })
const ensureRepo = vi.fn()

vi.mock('@/api/fs', () => ({
  fsAPI: {
    listFiles: (...args: unknown[]) => listFiles(...args),
    readFile: vi.fn(),
    writeFile: vi.fn(),
    restoreWorkspace: (...args: unknown[]) => restoreWorkspace(...args),
    saveWorkspace: (...args: unknown[]) => saveWorkspace(...args),
  },
}))

vi.mock('@/api/sandbox', () => ({
  getPreviewUrl: vi.fn(),
  fetchPreviewToken: vi.fn(),
}))

vi.mock('@/api/codeSession', () => ({
  codeSessionApi: {
    getRepoStatus: vi.fn(),
    ensureRepo: (...args: unknown[]) => ensureRepo(...args),
  },
}))

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    role: 'user',
    content: 'Add a health check endpoint',
    timestamp: new Date('2026-01-01T00:00:00Z'),
    message_id: 'msg-1',
    ...overrides,
  }
}

const emptyWorkspaceTree: FileNode[] = []

const populatedWorkspaceTree: FileNode[] = [
  { name: 'src', path: '/workspace/src', type: 'directory' },
  { name: 'app.py', path: '/workspace/app.py', type: 'file' },
  { name: 'README.md', path: '/workspace/README.md', type: 'file' },
]

describe('FullIDE — sandbox chat mode', () => {
  it('renders the default chat-mode IDE shell with no userId (workspace init skipped)', () => {
    listFiles.mockResolvedValue({ success: true, files: emptyWorkspaceTree })
    restoreWorkspace.mockResolvedValue({ success: true, files_synced: 0, bytes_synced: 0, errors: [] })
    ensureRepo.mockResolvedValue({ data: { action: 'none' } })

    const { container } = render(<FullIDE chatId="chat-1" conversationId="conv-1" />)
    expect(container).toMatchSnapshot()
  })

  it('renders a populated file tree once workspace initialization resolves', async () => {
    listFiles.mockResolvedValue({ success: true, files: populatedWorkspaceTree })
    restoreWorkspace.mockResolvedValue({ success: true, files_synced: 3, bytes_synced: 512, errors: [] })
    ensureRepo.mockResolvedValue({ data: { action: 'none' } })

    const { container } = render(
      <FullIDE userId="user-1" chatId="chat-1" conversationId="conv-1" />
    )

    await waitFor(() => expect(listFiles).toHaveBeenCalled())
    await screen.findByText('app.py')

    expect(container).toMatchSnapshot()
  })

  it('renders with message navigation data available', () => {
    listFiles.mockResolvedValue({ success: true, files: emptyWorkspaceTree })
    restoreWorkspace.mockResolvedValue({ success: true, files_synced: 0, bytes_synced: 0, errors: [] })
    ensureRepo.mockResolvedValue({ data: { action: 'none' } })

    const messages: Message[] = [
      makeMessage({ role: 'user', content: 'Add a health check endpoint', message_id: 'msg-1' }),
      makeMessage({ role: 'assistant', content: 'Added /health.', message_id: 'msg-2' }),
    ]
    const { container } = render(
      <FullIDE chatId="chat-1" conversationId="conv-1" messages={messages} />
    )
    expect(container).toMatchSnapshot()
  })
})

describe('FullIDE — code sessions mode', () => {
  it('renders in read-only code-session mode with git branch info', () => {
    listFiles.mockResolvedValue({ success: true, files: emptyWorkspaceTree })
    restoreWorkspace.mockResolvedValue({ success: true, files_synced: 0, bytes_synced: 0, errors: [] })
    ensureRepo.mockResolvedValue({ data: { action: 'none' } })

    const { container } = render(
      <FullIDE
        sessionId="session-1"
        mode="code"
        readOnly={true}
        workspacePath="/workspace/session-1"
        gitBranches={[
          { name: 'main', protected: true },
          { name: 'feature/health-check' },
        ]}
        gitCurrentBranch="feature/health-check"
        gitIsLoadingBranches={false}
        gitModifiedFiles={['src/health.py', 'src/app.py']}
        onGitBranchSelect={vi.fn()}
        onGitCreateBranch={vi.fn()}
      />
    )
    expect(container).toMatchSnapshot()
  })

  it('renders in editable code-session mode while branches are still loading', () => {
    listFiles.mockResolvedValue({ success: true, files: emptyWorkspaceTree })
    restoreWorkspace.mockResolvedValue({ success: true, files_synced: 0, bytes_synced: 0, errors: [] })
    ensureRepo.mockResolvedValue({ data: { action: 'none' } })

    const { container } = render(
      <FullIDE
        sessionId="session-2"
        mode="code"
        readOnly={false}
        gitIsLoadingBranches={true}
        onGitBranchSelect={vi.fn()}
        onGitCreateBranch={vi.fn()}
      />
    )
    expect(container).toMatchSnapshot()
  })
})
