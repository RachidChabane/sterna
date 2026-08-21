// Lightweight IndexedDB cache for attachments to persist across refreshes
// Stores minimal metadata and content needed for previews

export interface CachedAttachment {
  id: string
  name: string
  size: number
  type?: string
  lastModified?: number
  base64?: string
  textContent?: string
}

const DB_NAME_BASE = 'attachments-cache'
const STORE_NAME = 'attachments'
const VERSION = 1

function getCurrentUserId(): string | null {
  try {
    const auth = localStorage.getItem('auth-storage')
    if (!auth) return null
    const parsed = JSON.parse(auth)
    return parsed?.state?.user?.id || null
  } catch {
    return null
  }
}

function getDBName(): string {
  const uid = getCurrentUserId()
  return uid ? `${DB_NAME_BASE}-${uid}` : `${DB_NAME_BASE}-anon`
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(getDBName(), VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export async function cacheSet(item: CachedAttachment): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    store.put(item)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

export async function cacheGet(id: string): Promise<CachedAttachment | undefined> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const store = tx.objectStore(STORE_NAME)
    const req = store.get(id)
    req.onsuccess = () => resolve(req.result as CachedAttachment | undefined)
    req.onerror = () => reject(req.error)
  })
}

export async function cacheDelete(id: string): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    store.delete(id)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

/**
 * Clear all cached attachments for the current user by deleting the DB
 */
export async function clearCurrentUserCache(): Promise<void> {
  return new Promise((resolve, reject) => {
    try {
      const req = indexedDB.deleteDatabase(getDBName())
      req.onsuccess = () => resolve()
      req.onerror = () => reject(req.error)
      req.onblocked = () => {
        // If blocked, resolve anyway to not hang logout
        console.warn('[AttachmentCache] DB deletion blocked; will resolve')
        resolve()
      }
    } catch (e) {
      console.warn('[AttachmentCache] Failed to delete DB:', e)
      resolve() // best-effort
    }
  })
}

// Helper to persist from Attachment objects (limited type duplication to avoid cross-import)
export async function saveFromAttachment(att: any): Promise<void> {
  try {
    if (!att || !att.id) return
    const file: File | undefined = att.file
    const cached: CachedAttachment = {
      id: att.id,
      name: file?.name || att.name || 'file',
      size: file?.size || att.size || 0,
      type: file?.type,
      lastModified: (file as any)?.lastModified,
      base64: att.base64,
      textContent: att.textContent,
    }
    await cacheSet(cached)
  } catch {
    // best-effort; ignore errors
  }
}
