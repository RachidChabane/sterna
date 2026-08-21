import { useState, useEffect } from 'react'

/**
 * Hook to detect the user's operating system
 *
 * Uses multiple detection methods for maximum compatibility:
 * - navigator.platform (legacy but widely supported)
 * - navigator.userAgent (fallback)
 * - navigator.userAgentData (modern API, not yet universal)
 *
 * @returns {Object} OS detection flags
 * @returns {boolean} isMac - True if running on macOS
 * @returns {boolean} isWindows - True if running on Windows
 * @returns {boolean} isLinux - True if running on Linux
 */
export function useOS() {
  const [os, setOS] = useState({
    isMac: false,
    isWindows: false,
    isLinux: false,
  })

  useEffect(() => {
    // Get platform info from various sources
    const platform = (navigator?.platform || '').toLowerCase()
    const userAgent = (navigator?.userAgent || '').toLowerCase()

    // Detect macOS
    const isMac =
      platform.includes('mac') ||
      userAgent.includes('mac') ||
      userAgent.includes('macintosh')

    // Detect Windows
    const isWindows =
      platform.includes('win') ||
      userAgent.includes('windows')

    // Detect Linux
    const isLinux =
      platform.includes('linux') ||
      userAgent.includes('linux')

    setOS({ isMac, isWindows, isLinux })
  }, [])

  return os
}
