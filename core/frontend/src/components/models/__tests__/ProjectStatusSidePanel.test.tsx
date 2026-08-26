import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { ProjectStatusSidePanel } from '../ProjectStatusSidePanel'
import { useProjectPanelStore, type AgentPlan } from '@/store/projectPanelStore'
import type { RepoStatusResponse } from '@/api/codeSession'

const getRepoStatus = vi.fn()
const getIssues = vi.fn()
const getPlans = vi.fn()
const getPullRequests = vi.fn()
const getGitHubStatus = vi.fn()

vi.mock('@/api/codeSession', async () => {
  const actual = await vi.importActual<typeof import('@/api/codeSession')>('@/api/codeSession')
  return {
    ...actual,
    codeSessionApi: {
      getRepoStatus: (...args: unknown[]) => getRepoStatus(...args),
      getIssues: (...args: unknown[]) => getIssues(...args),
      getPlans: (...args: unknown[]) => getPlans(...args),
      getPullRequests: (...args: unknown[]) => getPullRequests(...args),
      getGitHubStatus: (...args: unknown[]) => getGitHubStatus(...args),
      getRepos: vi.fn().mockResolvedValue({ data: { results: [] } }),
    },
  }
})

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/store/conversationStore', () => ({
  useConversationStore: (selector: (s: { activeConversation: null }) => unknown) => selector({ activeConversation: null }),
}))

vi.mock('@/api/conversations', () => ({
  conversationsAPI: {
    createConversation: vi.fn(),
    createChat: vi.fn(),
    updateConversation: vi.fn(),
  },
}))

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

vi.mock('@/hooks/useChatMessageDispatch', () => ({
  useChatMessageDispatch: () => ({
    requestPlanForIssue: vi.fn(),
    requestImplementPlan: vi.fn(),
  }),
}))

function pendingPromise<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

describe('ProjectStatusSidePanel — repo status card', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectPanelStore.getState().reset()
    getIssues.mockResolvedValue({ data: { results: [] } })
    getPlans.mockResolvedValue({ data: { results: [] } })
    getPullRequests.mockResolvedValue({ data: { results: [] } })
    getGitHubStatus.mockResolvedValue({ data: { connected: false, username: null } })
  })

  it('does not show the "Connect your GitHub account" prompt for a conversation with an already-cloned repo, even though the panel was never opened', async () => {
    // isPanelOpen stays at its default (false) — the desktop layout still
    // mounts the card's content (it's hidden with width/translate CSS, not
    // unmounted), so the fetch that decides which card to show must not be
    // gated on isPanelOpen or this card lies about connection state.
    expect(useProjectPanelStore.getState().isPanelOpen).toBe(false)

    getRepoStatus.mockResolvedValue({
      data: {
        has_repo: true,
        id: 'repo-1',
        full_name: 'acme/widgets',
        clone_url: 'https://github.com/acme/widgets',
        default_branch: 'main',
        current_branch: 'main',
        workspace_path: '/workspace/chat-1',
        head_commit_sha: 'abc1234',
        head_commit_message: 'Initial commit',
        cloned_at: '2026-01-01T00:00:00Z',
      },
    })

    render(<ProjectStatusSidePanel conversationId="conv-1" chatId="chat-1" />)

    expect(getRepoStatus).toHaveBeenCalledWith('conv-1')

    await waitFor(() => {
      expect(screen.getByText('acme/widgets')).toBeInTheDocument()
    })

    expect(screen.queryByText(/Connect your GitHub account/i)).not.toBeInTheDocument()
    expect(useProjectPanelStore.getState().isPanelOpen).toBe(false)
  })

  it('shows a loading state (not the false connect prompt) while the repo status fetch is still in flight', async () => {
    const { promise, resolve } = pendingPromise<{ data: RepoStatusResponse }>()
    getRepoStatus.mockReturnValue(promise)

    render(<ProjectStatusSidePanel conversationId="conv-1" chatId="chat-1" />)

    await waitFor(() => {
      expect(useProjectPanelStore.getState().isLoadingRepo).toBe(true)
    })
    expect(screen.queryByText(/Connect your GitHub account/i)).not.toBeInTheDocument()

    resolve({ data: { has_repo: false } })
    await waitFor(() => {
      expect(screen.getByText(/Connect your GitHub account/i)).toBeInTheDocument()
    })
  })

  it('genuinely shows the connect prompt once the fetch resolves with no cloned repo', async () => {
    getRepoStatus.mockResolvedValue({ data: { has_repo: false } })

    render(<ProjectStatusSidePanel conversationId="conv-1" chatId="chat-1" />)

    await waitFor(() => {
      expect(screen.getByText(/Connect your GitHub account/i)).toBeInTheDocument()
    })
  })

  it('does not re-fetch repo status on every panel open/close toggle (avoids a fetch storm)', async () => {
    getRepoStatus.mockResolvedValue({ data: { has_repo: false } })

    render(<ProjectStatusSidePanel conversationId="conv-1" chatId="chat-1" />)

    await waitFor(() => expect(getRepoStatus).toHaveBeenCalledTimes(1))

    useProjectPanelStore.getState().openPanel()
    useProjectPanelStore.getState().closePanel()
    useProjectPanelStore.getState().openPanel()

    // isPanelOpen is a dependency of the repo-status effect (it drives a
    // retry after a *failed* fetch — see the "retries" test below), but a
    // conversation that already resolved successfully must short-circuit
    // before re-fetching on every toggle.
    expect(getRepoStatus).toHaveBeenCalledTimes(1)
  })

  it('retries the repo-status fetch when the panel is (re)opened after a previous attempt failed, instead of being stuck on the connect prompt forever', async () => {
    getRepoStatus
      .mockRejectedValueOnce(new Error('network blip'))
      .mockResolvedValueOnce({
        data: {
          has_repo: true,
          id: 'repo-1',
          full_name: 'acme/widgets',
          clone_url: 'https://github.com/acme/widgets',
          default_branch: 'main',
          current_branch: 'main',
          workspace_path: '/workspace',
          head_commit_sha: 'abc1234',
          head_commit_message: 'commit',
          cloned_at: '2026-01-01T00:00:00Z',
        },
      })

    render(<ProjectStatusSidePanel conversationId="conv-1" chatId="chat-1" />)

    await waitFor(() => expect(getRepoStatus).toHaveBeenCalledTimes(1))
    // The first attempt failed — the card would otherwise be stuck showing
    // the "not connected" prompt forever with no way to recover.
    await waitFor(() => {
      expect(screen.getByText(/Connect your GitHub account/i)).toBeInTheDocument()
    })

    // Simulates the user clicking the FolderGit2 toggle to open the panel —
    // that's the retry trigger.
    useProjectPanelStore.getState().openPanel()

    await waitFor(() => expect(getRepoStatus).toHaveBeenCalledTimes(2))
    await waitFor(() => {
      expect(screen.getByText('acme/widgets')).toBeInTheDocument()
    })
  })

  it('does not re-fetch repo status on a chat switch within the same conversation (repo status is conversation-scoped)', async () => {
    getRepoStatus.mockResolvedValue({
      data: {
        has_repo: true,
        id: 'repo-1',
        full_name: 'acme/widgets',
        clone_url: 'https://github.com/acme/widgets',
        default_branch: 'main',
        current_branch: 'main',
        workspace_path: '/workspace',
        head_commit_sha: 'abc1234',
        head_commit_message: 'commit',
        cloned_at: '2026-01-01T00:00:00Z',
      },
    })
    useProjectPanelStore.setState({ isPanelOpen: true })

    const { rerender } = render(<ProjectStatusSidePanel conversationId="conv-1" chatId="chat-1" />)
    await waitFor(() => expect(getRepoStatus).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(getPlans).toHaveBeenCalledWith({ chatId: 'chat-1' }))
    getPlans.mockClear()

    rerender(<ProjectStatusSidePanel conversationId="conv-1" chatId="chat-2" />)

    // Plans are chat-scoped, so switching chats within the same conversation
    // still refetches them — but repo status is conversation-scoped and
    // must not be re-fetched just because the active chat changed.
    await waitFor(() => expect(getPlans).toHaveBeenCalledWith({ chatId: 'chat-2' }))
    expect(getRepoStatus).toHaveBeenCalledTimes(1)
  })

  it('does not fetch PRs for the conversation being left using its stale repo name when switching conversations with the panel already open', async () => {
    // Regression check for a race the isPanelOpen fix could easily
    // reintroduce: when conversationId changes, the "clear stale data"
    // effect, the repo-status effect, and the plans/PRs effect all run in
    // the same passive-effect flush, before either's setState is visible
    // to a same-flush read. A boolean "isLoadingRepo" gate on the plans/PRs
    // effect would still read the *previous* conversation's "not loading"
    // state and its stale clonedRepo.full_name in that flush, firing once
    // for the conversation just left (with the old repo name) and again
    // for the real one.
    getRepoStatus.mockImplementation((conversationId: string) =>
      Promise.resolve({
        data: {
          has_repo: true,
          id: conversationId,
          full_name: conversationId === 'conv-1' ? 'acme/widgets' : 'acme/other-repo',
          clone_url: 'https://github.com/acme/x',
          default_branch: 'main',
          current_branch: 'main',
          workspace_path: '/workspace',
          head_commit_sha: 'abc1234',
          head_commit_message: 'commit',
          cloned_at: '2026-01-01T00:00:00Z',
        },
      })
    )
    useProjectPanelStore.setState({ isPanelOpen: true })

    const { rerender } = render(<ProjectStatusSidePanel conversationId="conv-1" chatId="chat-1" />)
    await waitFor(() => {
      expect(getPullRequests).toHaveBeenCalledWith({ repoFullName: 'acme/widgets' })
    })
    getPullRequests.mockClear()

    rerender(<ProjectStatusSidePanel conversationId="conv-2" chatId="chat-2" />)
    await waitFor(() => {
      expect(getPullRequests).toHaveBeenCalledWith({ repoFullName: 'acme/other-repo' })
    })

    expect(getPullRequests).not.toHaveBeenCalledWith({ repoFullName: 'acme/widgets' })
    expect(getPullRequests).toHaveBeenCalledTimes(1)
  })
})

describe('ProjectStatusSidePanel — plan detail markdown width', () => {
  function makePlan(overrides: Partial<AgentPlan> = {}): AgentPlan {
    return {
      id: 'plan-1',
      title: 'Add billing settlement job',
      slug: 'add-billing-settlement-job',
      task_description: 'Reconcile coding-agent cost settlement',
      plan_content: '# Plan\n\nSome steps with a `code span` and a table.',
      status: 'ready',
      current_step_index: 0,
      total_steps: 0,
      planning_job_id: '',
      implementation_job_id: '',
      implementation_branch: '',
      github_issue_number: null,
      github_issue_url: '',
      github_issue_title: '',
      chat_id: 'chat-1',
      source_plan_id: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      steps: [],
      progress: { completed: 0, total: 0, percentage: 0 },
      ...overrides,
    }
  }

  beforeEach(() => {
    vi.clearAllMocks()
    useProjectPanelStore.getState().reset()
    getIssues.mockResolvedValue({ data: { results: [] } })
    getPlans.mockResolvedValue({ data: { results: [] } })
    getPullRequests.mockResolvedValue({ data: { results: [] } })
    getGitHubStatus.mockResolvedValue({ data: { connected: false, username: null } })
    // Matches the clonedRepo seeded into the store below — the component's
    // own mount-time fetch (see the previous describe block) will resolve
    // and overwrite whatever we seed, so it must agree with it.
    getRepoStatus.mockResolvedValue({
      data: {
        has_repo: true,
        id: 'repo-1',
        full_name: 'acme/widgets',
        clone_url: 'https://github.com/acme/widgets',
        default_branch: 'main',
        current_branch: 'main',
        workspace_path: '/workspace/chat-1',
        head_commit_sha: 'abc1234',
        head_commit_message: 'Initial commit',
        cloned_at: '2026-01-01T00:00:00Z',
      },
    })
  })

  it('keeps the plan markdown pinned to the panel width instead of letting it dictate a wider layout', async () => {
    const plan = makePlan()
    getPlans.mockResolvedValue({ data: { results: [plan] } })
    useProjectPanelStore.setState({ activeSection: 'plans', isPanelOpen: true })

    const { container } = render(<ProjectStatusSidePanel conversationId="conv-1" chatId="chat-1" />)

    // Let the component's own mount-time fetches (repo status, then plans)
    // populate the store, the same way a real user would land on this
    // screen, before selecting the plan the way PlanCard's onClick does.
    await waitFor(() => {
      expect(useProjectPanelStore.getState().plans).toEqual([plan])
    })
    useProjectPanelStore.getState().selectPlan(plan.id)

    await waitFor(() => {
      expect(screen.getByText(plan.title)).toBeInTheDocument()
    })

    // Radix ScrollArea's Viewport wraps children in an internal
    // `display: table` box that sizes to its widest descendant (long code
    // lines, GFM tables) instead of the panel's width. `min-w-0`/
    // `break-words` alone can't shrink that ancestor since a child can
    // never constrain its own parent's box — only decoupling this
    // element's own layout width from its content (`w-0 min-w-full`) plus
    // a contained horizontal scrollbar (`overflow-x-auto`) does. See the
    // comment above this element in ProjectStatusSidePanel.tsx for the
    // full explanation and how it was verified.
    const markdownWrap = container.querySelector('.prose-sm')
    expect(markdownWrap).toBeTruthy()
    expect(markdownWrap).toHaveClass('w-0', 'min-w-full', 'overflow-x-auto', 'break-words')
  })
})
