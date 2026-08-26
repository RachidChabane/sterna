/**
 * Custom hook for running and aborting code in the active file.
 */

import { useRef, useState } from 'react'
import axios from 'axios'
import { toErrorMessage } from '@/utils/errorMessages'
import { getAccessToken, orchestratorClient } from '@/api/client'
import type { ExecutionResult, OpenFile } from '../types'
import { getExecutableLanguage } from '../types'

interface ToastFn {
  (options: { title: string; description?: string; variant?: 'default' | 'destructive' }): void
}

interface UseCodeExecutionParams {
  activeFile: OpenFile | undefined
  userId?: string
  projectId: string
  toast: ToastFn
  saveFile: (path: string) => Promise<void>
  onBeforeRun: () => void
}

export function useCodeExecution({ activeFile, userId, projectId, toast, saveFile, onBeforeRun }: UseCodeExecutionParams) {
  const [isExecuting, setIsExecuting] = useState(false)
  const [result, setResult] = useState<ExecutionResult | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const executionIdRef = useRef<string | null>(null)

  const handleRunFile = async () => {
    if (!activeFile || !userId) return

    const execLang = getExecutableLanguage(activeFile.path)
    if (!execLang) {
      toast({
        title: 'Cannot Execute',
        description: 'Only Python (.py), JavaScript (.js), and Shell (.sh) files can be executed',
        variant: 'destructive',
      })
      return
    }

    if (activeFile.isDirty) {
      await saveFile(activeFile.path)
    }

    setIsExecuting(true)
    setResult(null)
    // Open bottom panel with output tab when running code
    onBeforeRun()

    const executionId = `exec-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
    executionIdRef.current = executionId

    const abortController = new AbortController()
    abortControllerRef.current = abortController

    try {
      const token = getAccessToken()
      if (!token) {
        toast({
          title: 'Authentication Error',
          description: 'No authentication token found',
          variant: 'destructive',
        })
        return
      }

      const response = await orchestratorClient.post<ExecutionResult>('/execute', {
        code: activeFile.content,
        language: execLang,
        user_id: userId,
        conversation_id: projectId,
        chat_id: projectId,
        sync_mode: true,
        project_id: projectId,
        timeout: 30,
        execution_id: executionId,
      }, { signal: abortController.signal })

      const data = response.data
      setResult(data)

      if (data.exit_code !== 0) {
        toast({
          title: 'Execution Failed',
          description: `Exit code: ${data.exit_code}`,
          variant: 'destructive',
        })
      }
    } catch (error) {
      // Don't show error if execution was aborted by user (axios raises
      // a CanceledError; a bare AbortError is also handled defensively)
      if (axios.isCancel(error) || (error instanceof Error && error.name === 'AbortError')) {
        setResult({
          output: '',
          error: 'Execution cancelled by user',
          exit_code: 1,
          execution_time: 0,
        })
      } else {
        const message = axios.isAxiosError(error) && error.response
          ? `HTTP ${error.response.status}`
          : toErrorMessage(error) || 'Execution failed'
        setResult({
          output: '',
          error: message,
          exit_code: 1,
          execution_time: 0,
        })
      }
    } finally {
      setIsExecuting(false)
      abortControllerRef.current = null
      executionIdRef.current = null
    }
  }

  const handleAbort = async () => {
    if (!executionIdRef.current) return

    const executionId = executionIdRef.current
    const token = getAccessToken()
    if (!token) return

    setIsExecuting(false)

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    try {
      orchestratorClient.post(`/cancel/${executionId}`)
    } finally {
      abortControllerRef.current = null
      executionIdRef.current = null
    }
  }

  return {
    isExecuting,
    result,
    setResult,
    handleRunFile,
    handleAbort,
  }
}
