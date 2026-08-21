import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/hanken-grotesk/index.css'
import '@fontsource-variable/bricolage-grotesque/index.css'
import './index.css'
import App from './App.tsx'
import { cleanupOrphanedIdeState, getLocalStorageStats } from './utils/cleanupLocalStorage'

// Suppress Monaco Editor "Canceled" errors that occur when language service operations
// are interrupted (e.g., when IDE closes, during cleanup, or worker disconnects).
// These are non-critical and just noise in the console.
const originalConsoleError = console.error
console.error = (...args: unknown[]) => {
  // Filter out Monaco "Canceled" errors (format: "ERR Canceled: Canceled" or just "Canceled")
  const firstArg = args[0]
  if (typeof firstArg === 'string' && (firstArg.includes('Canceled') || firstArg.includes('ERR Canceled'))) {
    return
  }
  if (firstArg instanceof Error && firstArg.message?.includes('Canceled')) {
    return
  }
  // Check stringified version for object errors
  const stringified = args.map(a => String(a)).join(' ')
  if (stringified.includes('Canceled')) {
    return
  }
  originalConsoleError.apply(console, args)
}

window.addEventListener('error', (event) => {
  if (event.message?.includes('Canceled') && event.filename?.includes('editor.api')) {
    event.preventDefault()
    return true
  }
})

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason
  if (reason?.message?.includes('Canceled') || reason?.name === 'Canceled') {
    event.preventDefault()
    return true
  }
})

// Cleanup orphaned localStorage items on startup (non-blocking)
// This runs asynchronously to not delay app startup
setTimeout(() => {
  try {
    const stats = getLocalStorageStats()
    

    cleanupOrphanedIdeState()
  } catch (error) {
    console.error('[Startup] localStorage cleanup failed:', error)
  }
}, 1000) // Run 1 second after app starts

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
