/**
 * User-scoped localStorage utility for Zustand persist middleware
 *
 * Automatically prefixes localStorage keys with the current user's ID
 * to ensure data isolation between users on the same browser.
 */

import type { PersistStorage, StorageValue } from 'zustand/middleware'

/**
 * Cache for user ID to avoid repeated localStorage reads and JSON parsing
 * This is critical for performance as getUserId is called on every Zustand persist getItem/setItem
 */
let cachedUserId: string | null | undefined = undefined
let lastAuthStorageValue: string | null = null

/**
 * Get the current authenticated user ID from auth-storage
 * Cached to avoid expensive localStorage.getItem + JSON.parse on every call
 */
export const getUserId = (): string | null => {
  if (typeof window === 'undefined') return null

  // Read current auth-storage value
  const authStorage = localStorage.getItem('auth-storage')

  // If auth-storage hasn't changed, return cached userId
  if (authStorage === lastAuthStorageValue && cachedUserId !== undefined) {
    return cachedUserId
  }

  // Update cache
  lastAuthStorageValue = authStorage

  if (authStorage) {
    try {
      const { state } = JSON.parse(authStorage)
      cachedUserId = state?.user?.id || null
      return cachedUserId ?? null
    } catch {
      cachedUserId = null
      return null
    }
  }

  cachedUserId = null
  return null
}

/**
 * Clear the getUserId cache (call this when user logs out)
 */
export const clearUserIdCache = () => {
  cachedUserId = undefined
  lastAuthStorageValue = null
}

/**
 * Create a user-scoped storage that automatically prefixes keys with user ID
 *
 * @param baseName - The base name for the storage key
 * @returns A StateStorage implementation that scopes data by user
 *
 * @example
 * ```typescript
 * persist(
 *   (set, get) => ({ ... }),
 *   {
 *     name: 'model-storage',
 *     storage: createUserScopedStorage('model-storage')
 *   }
 * )
 * ```
 */
export const createUserScopedStorage = <T>(baseName: string): PersistStorage<T> => ({
  getItem: (_name): StorageValue<T> | null => {
    const userId = getUserId()
    // Don't return any stored data if no user is authenticated
    // This prevents data leakage between users
    if (!userId) {
      return null
    }
    const key = `${baseName}-${userId}`
    const value = localStorage.getItem(key)
    if (!value) return null
    try {
      return JSON.parse(value) as StorageValue<T>
    } catch {
      return null
    }
  },

  setItem: (_name, value: StorageValue<T>) => {
    const userId = getUserId()
    // Don't persist data if no user is authenticated
    if (!userId) {
      console.warn(`[Storage] Cannot save ${baseName}: no authenticated user`)
      return
    }
    const key = `${baseName}-${userId}`
    localStorage.setItem(key, JSON.stringify(value))
  },

  removeItem: (_name) => {
    const userId = getUserId()
    if (!userId) {
      return
    }
    const key = `${baseName}-${userId}`
    localStorage.removeItem(key)
  },
})

/**
 * Clear all user-scoped storage for a specific user
 *
 * @param userId - The user ID whose storage should be cleared
 * @param storeNames - Array of base store names to clear
 */
export const clearUserStorage = (userId: string, storeNames: string[]) => {
  storeNames.forEach(baseName => {
    const key = `${baseName}-${userId}`
    localStorage.removeItem(key)
  })
}

/**
 * Migrate data from non-scoped keys to user-scoped keys
 * Called once on login to migrate old data
 *
 * @param userId - The user ID to migrate data for
 * @param storeNames - Array of base store names to migrate
 */
export const migrateToUserScopedStorage = (userId: string, storeNames: string[]) => {
  storeNames.forEach(baseName => {
    const oldKey = baseName
    const newKey = `${baseName}-${userId}`

    // If old key exists and new key doesn't, migrate
    const oldValue = localStorage.getItem(oldKey)
    const newValue = localStorage.getItem(newKey)

    if (oldValue && !newValue) {
      localStorage.setItem(newKey, oldValue)
      localStorage.removeItem(oldKey)
      
    }
  })
}

/**
 * Clean up old non-scoped storage keys
 * Called on login to remove shared keys
 *
 * @param storeNames - Array of base store names to clean
 */
export const cleanupLegacyStorage = (storeNames: string[]) => {
  storeNames.forEach(baseName => {
    localStorage.removeItem(baseName)
  })
}
