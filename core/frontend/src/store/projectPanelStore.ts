import { create } from 'zustand'

// Types for the project panel state
export interface ClonedRepo {
  id: string
  full_name: string
  clone_url: string
  default_branch: string
  current_branch: string
  workspace_path: string
  head_commit_sha: string
  head_commit_message: string
  cloned_at: string
}

interface PlanStep {
  id: string
  step_number: number
  title: string
  description: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  files_to_modify: string[]
  files_modified: string[]
  result_summary: string
}

export interface AgentPlan {
  id: string
  title: string
  slug: string
  task_description: string
  plan_content: string
  status: 'creating' | 'ready' | 'in_progress' | 'completed' | 'failed'
  current_step_index: number
  total_steps: number
  planning_job_id: string
  implementation_job_id: string
  implementation_branch: string
  github_issue_number: number | null
  github_issue_url: string
  github_issue_title: string
  chat_id: string | null
  source_plan_id: string | null
  conversation_name?: string
  created_at: string
  updated_at: string
  steps: PlanStep[]
  progress: {
    completed: number
    total: number
    percentage: number
  }
}

export interface CreatedPR {
  id: string
  pr_number: number
  pr_url: string
  pr_title: string
  head_branch: string
  base_branch: string
  created_at: string
  plan_title: string | null
  repo_full_name: string
}

type PanelSection = 'issues' | 'plans' | 'prs'

interface ProjectPanelState {
  // Panel state
  isPanelOpen: boolean
  activeSection: PanelSection

  // Data
  clonedRepo: ClonedRepo | null
  plans: AgentPlan[]
  pullRequests: CreatedPR[]
  selectedPlanId: string | null

  // Import
  importablePlans: AgentPlan[]
  showImportModal: boolean

  // Loading states
  isLoadingRepo: boolean
  isLoadingPlans: boolean
  isLoadingPRs: boolean

  // Actions
  openPanel: (section?: PanelSection) => void
  closePanel: () => void
  togglePanel: () => void
  setActiveSection: (section: PanelSection) => void

  setClonedRepo: (repo: ClonedRepo | null) => void
  setPlans: (plans: AgentPlan[]) => void
  addPlan: (plan: AgentPlan) => void
  updatePlan: (planId: string, updates: Partial<AgentPlan>) => void
  removePlan: (planId: string) => void
  updatePlanStep: (planId: string, stepId: string, status: PlanStep['status']) => void
  selectPlan: (planId: string | null) => void

  setPullRequests: (prs: CreatedPR[]) => void
  addPullRequest: (pr: CreatedPR) => void

  setImportablePlans: (plans: AgentPlan[]) => void
  setShowImportModal: (show: boolean) => void

  setLoadingRepo: (loading: boolean) => void
  setLoadingPlans: (loading: boolean) => void
  setLoadingPRs: (loading: boolean) => void

  // Reset
  reset: () => void
}

const initialState = {
  isPanelOpen: false,
  activeSection: 'issues' as PanelSection,
  clonedRepo: null,
  plans: [],
  pullRequests: [],
  selectedPlanId: null,
  importablePlans: [] as AgentPlan[],
  showImportModal: false,
  isLoadingRepo: false,
  isLoadingPlans: false,
  isLoadingPRs: false,
}

export const useProjectPanelStore = create<ProjectPanelState>((set, get) => ({
  ...initialState,

  openPanel: (section) => {
    set({
      isPanelOpen: true,
      ...(section && { activeSection: section }),
    })
  },

  closePanel: () => {
    set({ isPanelOpen: false })
  },

  togglePanel: () => {
    set((state) => ({ isPanelOpen: !state.isPanelOpen }))
  },

  setActiveSection: (section) => {
    set({ activeSection: section })
  },

  setClonedRepo: (repo) => {
    set({ clonedRepo: repo })
  },

  setPlans: (plans) => {
    set({ plans })
  },

  addPlan: (plan) => {
    set((state) => ({ plans: [plan, ...state.plans] }))
  },

  updatePlan: (planId, updates) => {
    set((state) => ({
      plans: state.plans.map((p) =>
        p.id === planId ? { ...p, ...updates } : p
      ),
    }))
  },

  removePlan: (planId) => {
    set((state) => ({
      plans: state.plans.filter((p) => p.id !== planId),
      selectedPlanId: state.selectedPlanId === planId ? null : state.selectedPlanId,
    }))
  },

  updatePlanStep: (planId, stepId, status) => {
    set((state) => ({
      plans: state.plans.map((plan) => {
        if (plan.id !== planId) return plan
        const updatedSteps = plan.steps.map((step) =>
          step.id === stepId ? { ...step, status } : step
        )
        const completed = updatedSteps.filter((s) => s.status === 'completed').length
        return {
          ...plan,
          steps: updatedSteps,
          progress: {
            completed,
            total: plan.total_steps,
            percentage: plan.total_steps > 0 ? Math.round((completed / plan.total_steps) * 100) : 0,
          },
        }
      }),
    }))
  },

  selectPlan: (planId) => {
    set({ selectedPlanId: planId })
  },

  setPullRequests: (prs) => {
    set({ pullRequests: prs })
  },

  addPullRequest: (pr) => {
    set((state) => ({ pullRequests: [pr, ...state.pullRequests] }))
  },

  setImportablePlans: (plans) => {
    set({ importablePlans: plans })
  },

  setShowImportModal: (show) => {
    set({ showImportModal: show })
  },

  setLoadingRepo: (loading) => {
    set({ isLoadingRepo: loading })
  },

  setLoadingPlans: (loading) => {
    set({ isLoadingPlans: loading })
  },

  setLoadingPRs: (loading) => {
    set({ isLoadingPRs: loading })
  },

  reset: () => {
    set(initialState)
  },
}))
