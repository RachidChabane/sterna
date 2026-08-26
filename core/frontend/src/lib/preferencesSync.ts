/**
 * Preferences Synchronization Service
 *
 * Handles syncing user preferences between localStorage and backend
 * with optimistic updates, debouncing, queuing, and retry logic.
 */

import { preferencesApi } from '../api/preferencesClient'
import { getAccessToken } from '../api/client'

/**
 * Preference update item in queue
 */
interface PreferenceUpdate {
  key: string
  value: unknown
  category: string
  timestamp: number
  retries: number
}

/**
 * Sync configuration
 */
const SYNC_CONFIG = {
  DEBOUNCE_MS: 300, // Wait 300ms after last update before syncing
  MAX_RETRIES: 3,
  RETRY_DELAY_MS: 1000, // Initial retry delay
  BATCH_SIZE: 10, // Max items to batch in one request
}

/**
 * Preferences Sync Manager
 */
class PreferencesSyncManager {
  private updateQueue: Map<string, PreferenceUpdate> = new Map()
  private debounceTimers: Map<string, NodeJS.Timeout> = new Map()
  private isSyncing = false
  private isOnline = true

  constructor() {
    // Listen for online/offline events
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => this.handleOnline())
      window.addEventListener('offline', () => this.handleOffline())
      this.isOnline = navigator.onLine
    }
  }

  /**
   * Update a preference with optimistic local update + background sync
   */
  async update(key: string, value: unknown, category: string = 'general'): Promise<void> {
    // Check if user is authenticated before syncing
    const accessToken = getAccessToken()
    if (!accessToken) {
      
      return
    }

    // Add to queue
    this.updateQueue.set(key, {
      key,
      value,
      category,
      timestamp: Date.now(),
      retries: 0,
    })

    // Clear existing debounce timer for this key
    const existingTimer = this.debounceTimers.get(key)
    if (existingTimer) {
      clearTimeout(existingTimer)
    }

    // Set new debounce timer
    const timer = setTimeout(() => {
      this.processQueue()
      this.debounceTimers.delete(key)
    }, SYNC_CONFIG.DEBOUNCE_MS)

    this.debounceTimers.set(key, timer)
  }

  /**
   * Process the update queue and sync to backend
   */
  private async processQueue(): Promise<void> {
    if (this.isSyncing || !this.isOnline) {
      return
    }

    if (this.updateQueue.size === 0) {
      return
    }

    this.isSyncing = true

    try {
      // Get items from queue (up to BATCH_SIZE)
      const items = Array.from(this.updateQueue.values()).slice(0, SYNC_CONFIG.BATCH_SIZE)

      if (items.length === 1) {
        // Single update - use individual endpoint
        const item = items[0]
        try {
          await preferencesApi.updatePreference(item.key, item.value, item.category)
          this.updateQueue.delete(item.key)
          
        } catch (error) {
          await this.handleSyncError(item, error)
        }
      } else {
        // Bulk update
        const preferences = Object.fromEntries(items.map((item) => [item.key, item.value]))

        try {
          await preferencesApi.bulkUpdatePreferences(preferences)
          // Remove successful items from queue
          items.forEach((item) => this.updateQueue.delete(item.key))
          
        } catch (error) {
          // If bulk fails, retry individual items
          console.warn('[PreferencesSync] Bulk sync failed, retrying individually')
          for (const item of items) {
            try {
              await preferencesApi.updatePreference(item.key, item.value, item.category)
              this.updateQueue.delete(item.key)
            } catch (itemError) {
              await this.handleSyncError(item, itemError)
            }
          }
        }
      }
    } catch (error) {
      console.error('[PreferencesSync] Queue processing error:', error)
    } finally {
      this.isSyncing = false

      // If there are still items in queue, schedule next processing
      if (this.updateQueue.size > 0) {
        setTimeout(() => this.processQueue(), SYNC_CONFIG.RETRY_DELAY_MS)
      }
    }
  }

  /**
   * Handle sync error with retry logic
   */
  private async handleSyncError(item: PreferenceUpdate, error: unknown): Promise<void> {
    item.retries++

    if (item.retries >= SYNC_CONFIG.MAX_RETRIES) {
      console.error(
        `[PreferencesSync] Failed to sync ${item.key} after ${SYNC_CONFIG.MAX_RETRIES} retries`,
        error
      )
      // Remove from queue after max retries
      this.updateQueue.delete(item.key)
    } else {
      console.warn(
        `[PreferencesSync] Retry ${item.retries}/${SYNC_CONFIG.MAX_RETRIES} for ${item.key}`
      )
      // Keep in queue for retry
      this.updateQueue.set(item.key, item)
    }
  }

  /**
   * Force flush the queue (sync immediately)
   */
  async flush(): Promise<void> {
    // Clear all debounce timers
    this.debounceTimers.forEach((timer) => clearTimeout(timer))
    this.debounceTimers.clear()

    // Process queue immediately
    await this.processQueue()
  }

  /**
   * Load all preferences from backend
   */
  async loadAll(category?: string): Promise<Record<string, unknown>> {
    try {
      const response = await preferencesApi.getAllPreferences(category)
      
      return response.preferences
    } catch (error) {
      console.error('[PreferencesSync] Failed to load preferences from backend:', error)
      return {}
    }
  }

  /**
   * Get a single preference by key
   */
  async get(key: string): Promise<unknown | undefined> {
    try {
      const pref = await preferencesApi.getPreference(key)
      // Returns null if preference doesn't exist
      if (!pref) return undefined
      return pref.preference_value
    } catch (error) {
      console.error('[PreferencesSync] Failed to get preference:', key, error)
      throw error
    }
  }

  /**
   * Sync local data to backend (for migration)
   */
  async syncLocalToBackend(localData: Record<string, unknown>, category: string): Promise<void> {
    if (Object.keys(localData).length === 0) {
      return
    }

    try {
      await preferencesApi.bulkUpdatePreferences(localData)
      
    } catch (error) {
      console.error('[PreferencesSync] Failed to migrate local data to backend:', error)
      throw error
    }
  }

  /**
   * Handle going online
   */
  private handleOnline(): void {
    
    this.isOnline = true
    this.processQueue()
  }

  /**
   * Handle going offline
   */
  private handleOffline(): void {
    
    this.isOnline = false
  }

  /**
   * Get queue status (for debugging)
   */
  getStatus(): { queueSize: number; isSyncing: boolean; isOnline: boolean } {
    return {
      queueSize: this.updateQueue.size,
      isSyncing: this.isSyncing,
      isOnline: this.isOnline,
    }
  }
}

// Create singleton instance
export const preferencesSync = new PreferencesSyncManager()

