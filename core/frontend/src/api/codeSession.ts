import apiClient from './client'
import type { ClonedRepo, AgentPlan, CreatedPR } from '@/store/projectPanelStore'

// Response types
interface RepoStatusResponse {
  has_repo: boolean
  id?: string
  full_name?: string | null
  clone_url?: string | null
  default_branch?: string | null
  current_branch?: string | null
  workspace_path?: string | null
  head_commit_sha?: string | null
  head_commit_message?: string | null
  cloned_at?: string | null
}

interface CloneRepoRequest {
  repo_url: string
  branch?: string
}

interface CloneRepoResponse {
  success: boolean
  full_name?: string
  branch?: string
  workspace_path?: string
  head_commit_sha?: string
  head_commit_message?: string
  error?: string
}

interface EnsureRepoResponse {
  action: 'none' | 'restored'
  success: boolean
  message?: string
  error?: string
  branch?: string
  commit_sha?: string
  committed?: boolean
}

interface GitHubStatusResponse {
  connected: boolean
  username: string | null
  avatar_url: string | null
  scopes: string[]
}

interface GitHubConnectResponse {
  authorization_url: string
  state: string
}

export interface GitHubRepo {
  id: number
  name: string
  full_name: string
  private: boolean
  description: string | null
  default_branch: string
  updated_at: string
}

interface GitHubReposResponse {
  results: GitHubRepo[]
  page: number
  per_page: number
}

export interface GitHubIssue {
  id: number
  number: number
  title: string
  body: string | null
  state: string
  html_url: string
  created_at: string
  updated_at: string
  labels: { name: string; color: string }[]
  user: { login: string; avatar_url: string }
}

interface GitHubIssuesResponse {
  results: GitHubIssue[]
  page: number
  per_page: number
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

interface StartImplementationResponse {
  success: boolean
  conversation_id: string
  chat_id: string
  suggested_message: string
  clone_result: {
    full_name: string
    branch: string
    head_commit_sha: string
  }
}

// Coding agent progress types
export interface CodingAgentProgressStep {
  type: string  // 'text', 'tool_call', 'tool_result', 'thinking', 'error', 'system', 'result'
  tool: string | null
  content: string | null
  input?: Record<string, unknown>  // Tool input parameters
  output?: string  // Tool output/result
}

export interface CodingAgentProgressResponse {
  found: boolean
  step_count: number
  total_steps: number
  completed: boolean
  exit_code: number | null
  files_created: string[]
  files_modified: string[]
  files_read: string[]
  files_deleted: string[]
  steps: CodingAgentProgressStep[]  // All steps with full content
  error: string | null
  summary: string | null
  total_cost_usd: number
  total_tokens: number
  pending_question?: {
    question: string
    options?: { label: string; description: string }[]
  } | null
}

// Code Session API endpoints
export const codeSessionApi = {
  // Repo status
  getRepoStatus: (conversationId: string) =>
    apiClient.get<RepoStatusResponse>(`/code-sessions/conversations/${conversationId}/repo/`),

  // Clone repository
  cloneRepo: (conversationId: string, data: CloneRepoRequest) =>
    apiClient.post<CloneRepoResponse>(`/code-sessions/conversations/${conversationId}/clone/`, data, {
      timeout: 300000, // 5 minutes for large repos
    }),

  // Ensure repo exists in sandbox (re-clone if container recycled)
  ensureRepo: (conversationId: string) =>
    apiClient.post<EnsureRepoResponse>(`/code-sessions/conversations/${conversationId}/ensure-repo/`, {}, {
      timeout: 120000, // 2 minutes for re-clone + restore + reconcile
    }),

  // GitHub connection
  getGitHubStatus: () =>
    apiClient.get<GitHubStatusResponse>('/code-sessions/github/status/'),

  connectGitHub: () =>
    apiClient.get<GitHubConnectResponse>('/code-sessions/github/connect/'),

  disconnectGitHub: () =>
    apiClient.delete<{ success: boolean; deleted: boolean }>('/code-sessions/github/disconnect/'),

  // Get user's GitHub repos
  getRepos: (page: number = 1, perPage: number = 30) =>
    apiClient.get<GitHubReposResponse>('/code-sessions/github/repos/', {
      params: { page, per_page: perPage },
    }),

  // Get repo issues
  getIssues: (owner: string, repo: string, page: number = 1, perPage: number = 30, state: string = 'open') =>
    apiClient.get<GitHubIssuesResponse>(`/code-sessions/github/repos/${owner}/${repo}/issues/`, {
      params: { page, per_page: perPage, state },
    }),

  // Plans
  getPlans: (params: { conversationId?: string; repoFullName?: string; chatId?: string }) =>
    apiClient.get<PaginatedResponse<AgentPlan>>('/code-sessions/plans/', {
      params: {
        ...(params.chatId && { chat_id: params.chatId }),
        ...(params.repoFullName && { repo_full_name: params.repoFullName }),
        ...(params.conversationId && { conversation_id: params.conversationId }),
      },
    }),

  getPlan: (planId: string) =>
    apiClient.get<AgentPlan>(`/code-sessions/plans/${planId}/`),

  getPlanSteps: (planId: string) =>
    apiClient.get<{ steps: AgentPlan['steps'] }>(`/code-sessions/plans/${planId}/steps/`),

  // Plan import
  getImportablePlans: (chatId: string, repoFullName: string) =>
    apiClient.get<{ results: AgentPlan[] }>('/code-sessions/plans/importable/', {
      params: { chat_id: chatId, repo_full_name: repoFullName },
    }),

  importPlan: (planId: string, chatId: string) =>
    apiClient.post<AgentPlan>('/code-sessions/plans/import/', { plan_id: planId, chat_id: chatId }),

  // Pull requests
  getPullRequests: (params: { conversationId?: string; repoFullName?: string }) =>
    apiClient.get<PaginatedResponse<CreatedPR>>('/code-sessions/pull-requests/', {
      params: {
        ...(params.repoFullName && { repo_full_name: params.repoFullName }),
        ...(params.conversationId && { conversation_id: params.conversationId }),
      },
    }),

  getPullRequest: (prId: string) =>
    apiClient.get<CreatedPR>(`/code-sessions/pull-requests/${prId}/`),

  // Implementation workflow
  startImplementation: (data: {
    repo_full_name: string
    branch: string
    issue_number: number
    issue_title: string
    issue_body?: string
    issue_url: string
  }) =>
    apiClient.post<StartImplementationResponse>('/code-sessions/start-implementation/', data),

  // Update plan content
  updatePlanContent: (planId: string, planContent: string) =>
    apiClient.patch<AgentPlan>(`/code-sessions/plans/${planId}/content/`, { plan_content: planContent }),

  // Coding agent progress
  getCodingAgentProgress: (chatId: string, jobId?: string) =>
    apiClient.post<CodingAgentProgressResponse>('/code-sessions/coding-agent/progress/', {
      chat_id: chatId,
      ...(jobId && { job_id: jobId }),
    }),

  // Coding agent answer (for ask_user MCP tool)
  sendCodingAgentAnswer: (chatId: string, answer: string) =>
    apiClient.post('/code-sessions/coding-agent/answer/', {
      chat_id: chatId,
      answer,
    }),

  // Delete a plan
  deletePlan: (planId: string) =>
    apiClient.delete(`/code-sessions/plans/${planId}/delete/`),

  // Create PR from plan
  createPRFromPlan: (planId: string, data?: { title?: string; body?: string; draft?: boolean }) =>
    apiClient.post<CreatedPR>(`/code-sessions/plans/${planId}/create-pr/`, data || {}),

  // Get branches
  getBranches: (owner: string, repo: string) =>
    apiClient.get<{ branches: { name: string; protected: boolean }[] }>(
      `/code-sessions/github/repos/${owner}/${repo}/branches/`
    ),

  // Get branch commits
  getBranchCommits: (owner: string, repo: string, branch: string, perPage: number = 20) =>
    apiClient.get<{ results: GitHubCommit[] }>(`/code-sessions/github/repos/${owner}/${repo}/commits/`, {
      params: { sha: branch, per_page: perPage },
    }),
}

/** A commit as returned by GitHub's commits API, passed through unchanged by the backend proxy. */
export interface GitHubCommit {
  sha: string
  commit: {
    message: string
    author?: { name?: string; date?: string }
  }
}

// Helper to transform API response to store type
export function transformRepoStatus(response: RepoStatusResponse): ClonedRepo | null {
  if (!response.has_repo || !response.id) {
    return null
  }
  return {
    id: response.id,
    full_name: response.full_name || '',
    clone_url: response.clone_url || '',
    default_branch: response.default_branch || 'main',
    current_branch: response.current_branch || 'main',
    workspace_path: response.workspace_path || '',
    head_commit_sha: response.head_commit_sha || '',
    head_commit_message: response.head_commit_message || '',
    cloned_at: response.cloned_at || '',
  }
}
