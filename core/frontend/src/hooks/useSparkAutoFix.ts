/**
 * useSparkAutoFix Hook
 *
 * Tracks spark render errors and manages automatic fix attempts.
 * Provides state and helpers for the auto-fix flow.
 *
 * Key features:
 * - Tracks errors per spark ID
 * - Limits retry attempts to MAX_ATTEMPTS (3)
 * - Tracks fix-in-progress state per spark
 * - Provides helpers to check/update fix status
 */

import { useState, useCallback, useRef } from 'react'

const MAX_ATTEMPTS = 3

export interface SparkError {
  sparkId: string
  code: string
  error: string
  attempts: number
  isFixing: boolean
}

export interface UseSparkAutoFixReturn {
  /** Register a new error for a spark */
  registerError: (sparkId: string, code: string, error: string) => void
  /** Check if a spark is currently being fixed */
  isFixing: (sparkId: string) => boolean
  /** Get number of fix attempts for a spark */
  getAttempts: (sparkId: string) => number
  /** Check if auto-fix should be triggered (< MAX_ATTEMPTS) */
  shouldAutoFix: (sparkId: string) => boolean
  /** Mark that a fix attempt was made for a spark */
  markFixAttempted: (sparkId: string) => void
  /** Mark that a fix is in progress for a spark */
  setFixing: (sparkId: string, fixing: boolean) => void
  /** Clear error tracking for a spark (e.g., on successful render) */
  clearError: (sparkId: string) => void
  /** Get all tracked errors */
  errors: Map<string, SparkError>
}

export function useSparkAutoFix(): UseSparkAutoFixReturn {
  const [errors, setErrors] = useState<Map<string, SparkError>>(new Map())

  // Track which errors we've already auto-fixed to prevent duplicate triggers
  const processedErrorsRef = useRef<Set<string>>(new Set())

  const registerError = useCallback((sparkId: string, code: string, error: string) => {
    setErrors((prev) => {
      const existing = prev.get(sparkId)
      const newMap = new Map(prev)

      // Generate a unique key for this specific error to prevent duplicate processing
      const errorKey = `${sparkId}:${error}`

      if (existing) {
        // If same error and already processed, don't re-register
        if (existing.error === error && processedErrorsRef.current.has(errorKey)) {
          return prev
        }
        // Update existing entry, keep attempt count
        newMap.set(sparkId, {
          ...existing,
          code,
          error,
          isFixing: false,
        })
      } else {
        // New error entry
        newMap.set(sparkId, {
          sparkId,
          code,
          error,
          attempts: 0,
          isFixing: false,
        })
      }

      return newMap
    })
  }, [])

  const isFixing = useCallback(
    (sparkId: string) => {
      return errors.get(sparkId)?.isFixing ?? false
    },
    [errors]
  )

  const getAttempts = useCallback(
    (sparkId: string) => {
      return errors.get(sparkId)?.attempts ?? 0
    },
    [errors]
  )

  const shouldAutoFix = useCallback(
    (sparkId: string) => {
      const entry = errors.get(sparkId)
      if (!entry) return false
      // Only auto-fix if under attempt limit and not already fixing
      return entry.attempts < MAX_ATTEMPTS && !entry.isFixing
    },
    [errors]
  )

  const markFixAttempted = useCallback((sparkId: string) => {
    setErrors((prev) => {
      const existing = prev.get(sparkId)
      if (!existing) return prev

      const newMap = new Map(prev)
      const errorKey = `${sparkId}:${existing.error}`
      processedErrorsRef.current.add(errorKey)

      newMap.set(sparkId, {
        ...existing,
        attempts: existing.attempts + 1,
      })
      return newMap
    })
  }, [])

  const setFixing = useCallback((sparkId: string, fixing: boolean) => {
    setErrors((prev) => {
      const existing = prev.get(sparkId)
      if (!existing) return prev

      const newMap = new Map(prev)
      newMap.set(sparkId, {
        ...existing,
        isFixing: fixing,
      })
      return newMap
    })
  }, [])

  const clearError = useCallback((sparkId: string) => {
    setErrors((prev) => {
      const newMap = new Map(prev)
      newMap.delete(sparkId)
      return newMap
    })
    // Clear processed errors for this spark
    processedErrorsRef.current.forEach((key) => {
      if (key.startsWith(`${sparkId}:`)) {
        processedErrorsRef.current.delete(key)
      }
    })
  }, [])

  return {
    registerError,
    isFixing,
    getAttempts,
    shouldAutoFix,
    markFixAttempted,
    setFixing,
    clearError,
    errors,
  }
}

export default useSparkAutoFix
