/**
 * FileIcon Component
 *
 * Displays VSCode-style icons based on file extensions
 * Uses jsDelivr CDN with aggressive browser caching hints
 */

import { get } from 'vscode-icons-svg'
import { useState, useEffect, useRef } from 'react'
import { File } from 'lucide-react'

interface FileIconProps {
  filename: string
  className?: string
}

// In-memory cache for icon URLs (survives component re-renders, not page refresh)
const iconUrlCache = new Map<string, string>()

// Preload icon to browser cache for instant display
const preloadIcon = (url: string) => {
  const link = document.createElement('link')
  link.rel = 'preload'
  link.as = 'image'
  link.href = url
  document.head.appendChild(link)
}

export function FileIcon({ filename, className = '' }: FileIconProps) {
  const [error, setError] = useState(false)
  const preloadedRef = useRef(false)

  // Get extension for cache key (multiple files with same extension = same icon)
  const extension = filename.split('.').pop()?.toLowerCase() || filename
  const cacheKey = extension

  // Check cache first
  let iconUrl = iconUrlCache.get(cacheKey)

  if (!iconUrl) {
    // Get returns the full URL to the icon on GitHub (raw.githubusercontent.com)
    // We replace it with jsDelivr CDN which is more reliable and doesn't get rate-limited
    const githubUrl = get(filename)

    // Transform GitHub raw URL to jsDelivr CDN URL
    // From: https://raw.githubusercontent.com/vscode-icons/vscode-icons/master/icons/[filename]
    // To:   https://cdn.jsdelivr.net/gh/vscode-icons/vscode-icons@master/icons/[filename]
    iconUrl = githubUrl.replace(
      'https://raw.githubusercontent.com/vscode-icons/vscode-icons/master/',
      'https://cdn.jsdelivr.net/gh/vscode-icons/vscode-icons@master/'
    )

    // Cache the URL
    iconUrlCache.set(cacheKey, iconUrl)
  }

  // Preload icon on mount for instant browser caching
  useEffect(() => {
    if (!preloadedRef.current && iconUrl) {
      preloadIcon(iconUrl)
      preloadedRef.current = true
    }
  }, [iconUrl])

  // Fallback to a generic file icon if image fails to load
  if (error) {
    return <File className={`${className} w-4 h-4`} />
  }

  return (
    <img
      src={iconUrl}
      alt={filename}
      className={`object-contain ${className}`}
      onError={() => setError(true)}
      loading="lazy"
      decoding="async"
    />
  )
}
