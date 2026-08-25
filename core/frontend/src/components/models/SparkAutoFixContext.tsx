/**
 * SparkAutoFixContext
 *
 * Provides auto-fix functionality for Sparks at the chat level.
 * This context gives nested spark-rendering components access to
 * trigger fix requests to the LLM when a Spark fails to render.
 *
 * Usage:
 * 1. Wrap chat content with SparkAutoFixProvider
 * 2. Pass sendSparkFixRequest function to the provider
 * 3. Spark-rendering components consume this context to trigger auto-fixes
 *
 * Architecture:
 * - The fix request metadata (spark_id, spark_title, error) is sent to the backend
 * - The backend prompt builder injects the appropriate fix instructions
 * - This avoids hardcoding prompts in the frontend
 */

import { createContext, useCallback, useMemo, type ReactNode } from 'react'
import { useSparkAutoFix, type UseSparkAutoFixReturn } from '@/hooks/useSparkAutoFix'

/** Spark fix request data sent to backend */
export interface SparkFixRequest {
  spark_id: string
  spark_title: string
  error: string
}

export interface SparkAutoFixContextValue extends UseSparkAutoFixReturn {
  /** Request the LLM to fix a broken spark */
  requestFix: (sparkId: string, sparkTitle: string, code: string, error: string) => Promise<void>
  /** Whether auto-fix is enabled (sparks feature must be on) */
  isAutoFixEnabled: boolean
}

const SparkAutoFixContext = createContext<SparkAutoFixContextValue | null>(null)

interface SparkAutoFixProviderProps {
  children: ReactNode
  /**
   * Function to send a spark fix request to the LLM.
   * The parent component is responsible for passing this through to the API
   * with the spark_fix_request metadata.
   */
  sendSparkFixRequest: (content: string, sparkFixRequest: SparkFixRequest) => Promise<void>
  /** Whether the sparks feature is enabled */
  sparksEnabled?: boolean
  /** Whether the chat is currently loading/generating */
  isLoading?: boolean
}

/**
 * Provider component that enables auto-fix functionality for Sparks
 */
export function SparkAutoFixProvider({
  children,
  sendSparkFixRequest,
  sparksEnabled = true,
  isLoading = false,
}: SparkAutoFixProviderProps) {
  const sparkAutoFix = useSparkAutoFix()

  const requestFix = useCallback(
    async (sparkId: string, sparkTitle: string, code: string, error: string) => {
      // Don't trigger if already fixing or if chat is loading
      if (sparkAutoFix.isFixing(sparkId) || isLoading) {
        return
      }

      // Don't trigger if we've exceeded max attempts
      if (!sparkAutoFix.shouldAutoFix(sparkId)) {
        return
      }

      // Mark as fixing
      sparkAutoFix.setFixing(sparkId, true)
      sparkAutoFix.markFixAttempted(sparkId)

      // Send fix request with metadata (backend handles the prompt)
      const sparkFixRequest: SparkFixRequest = {
        spark_id: sparkId,
        spark_title: sparkTitle,
        error,
      }

      // Minimal message content - the backend will use spark_fix_request metadata
      // to inject the proper fix instructions into the system prompt
      const messageContent = `Please fix the "${sparkTitle}" spark component.`

      try {
        await sendSparkFixRequest(messageContent, sparkFixRequest)
      } catch (err) {
        console.error('[SparkAutoFix] Failed to send fix request:', err)
      } finally {
        // Reset fixing state after a delay to allow for response processing
        // The actual success/failure will be determined by the next render
        setTimeout(() => {
          sparkAutoFix.setFixing(sparkId, false)
        }, 1000)
      }
    },
    [sendSparkFixRequest, sparkAutoFix, isLoading]
  )

  const value = useMemo<SparkAutoFixContextValue>(
    () => ({
      ...sparkAutoFix,
      requestFix,
      isAutoFixEnabled: sparksEnabled,
    }),
    [sparkAutoFix, requestFix, sparksEnabled]
  )

  return <SparkAutoFixContext.Provider value={value}>{children}</SparkAutoFixContext.Provider>
}
