/**
 * Hook for dispatching messages to the chat input.
 * Provides named methods for plan/implement message dispatch (DRY).
 */
import { useCallback } from 'react'

function dispatchToChat(message: string) {
  window.dispatchEvent(
    new CustomEvent('setInputMessage', { detail: { message } })
  )
}

export function useChatMessageDispatch() {
  const requestPlanForIssue = useCallback((
    issue: { number: number; title: string; body?: string | null; html_url?: string },
    repo: { full_name: string; current_branch: string },
  ) => {
    let message = `@plan_implementation #${issue.number} ${issue.title}`
    if (issue.body) message += `\n\n**Issue Description:**\n${issue.body}`
    if (issue.html_url) message += `\n\n**Issue URL:** ${issue.html_url}`
    message += `\n\n**Repository:** ${repo.full_name} (branch: ${repo.current_branch})`
    dispatchToChat(message)
  }, [])

  const requestImplementPlan = useCallback((plan: { id: string; title: string }) => {
    const message = `@implement_plan plan:${plan.id} ${plan.title}`
    dispatchToChat(message)
  }, [])

  return { requestPlanForIssue, requestImplementPlan }
}
