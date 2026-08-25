/**
 * Utility to cleanup orphaned and old localStorage items
 *
 * Run this periodically to free up space and improve performance
 */

/**
 * Remove all orphaned ide-state items from localStorage
 * These are leftover from deleted workspaces/files
 */
export function cleanupOrphanedIdeState(): number {
  let cleaned = 0
  const keysToRemove: string[] = []

  // Find all ide-state keys
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (key && key.startsWith('ide-state-')) {
      keysToRemove.push(key)
    }
  }

  // Remove them
  keysToRemove.forEach(key => {
    localStorage.removeItem(key)
    cleaned++
  })

  if (cleaned > 0) {
    
  }

  return cleaned
}

/**
 * Get localStorage usage statistics
 */
export function getLocalStorageStats(): {
  totalSizeBytes: number
  totalSizeKB: number
  totalSizeMB: number
  itemCount: number
  largestItems: Array<{ key: string; sizeKB: number }>
} {
  let totalSize = 0
  const items: Array<{ key: string; size: number; sizeKB: number }> = []

  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (!key) continue

    const value = localStorage.getItem(key)
    if (!value) continue

    const size = new Blob([value]).size
    totalSize += size

    items.push({
      key,
      size,
      sizeKB: parseFloat((size / 1024).toFixed(2))
    })
  }

  // Sort by size
  items.sort((a, b) => b.size - a.size)

  return {
    totalSizeBytes: totalSize,
    totalSizeKB: parseFloat((totalSize / 1024).toFixed(2)),
    totalSizeMB: parseFloat((totalSize / (1024 * 1024)).toFixed(4)),
    itemCount: items.length,
    largestItems: items.slice(0, 10).map(item => ({
      key: item.key,
      sizeKB: item.sizeKB
    }))
  }
}

