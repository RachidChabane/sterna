/**
 * CachedAvatar Component
 *
 * Caches avatar images in localStorage as base64 for instant display.
 * Falls back to loading from URL if cache miss.
 */

import { useState, useEffect, useRef } from 'react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'
import { fetchStream } from '@/api/transport'

const AVATAR_CACHE_KEY = 'cached-avatar'
const CACHE_DURATION = 24 * 60 * 60 * 1000 // 24 hours

interface CachedAvatarProps {
  src?: string | null
  alt?: string
  fallback?: React.ReactNode
  className?: string
  fallbackClassName?: string
}

interface CachedAvatarData {
  base64: string
  url: string
  timestamp: number
}

function getCachedAvatar(url: string): string | null {
  try {
    const cached = localStorage.getItem(AVATAR_CACHE_KEY)
    if (!cached) return null

    const data: CachedAvatarData = JSON.parse(cached)

    // Check if cache is for the same URL and not expired
    if (data.url === url && Date.now() - data.timestamp < CACHE_DURATION) {
      return data.base64
    }

    return null
  } catch {
    return null
  }
}

function setCachedAvatar(url: string, base64: string): void {
  try {
    const data: CachedAvatarData = {
      base64,
      url,
      timestamp: Date.now(),
    }
    localStorage.setItem(AVATAR_CACHE_KEY, JSON.stringify(data))
  } catch {
    // Ignore storage errors
  }
}

export function CachedAvatar({
  src,
  alt = 'Avatar',
  fallback,
  className,
  fallbackClassName,
}: CachedAvatarProps) {
  const [imageSrc, setImageSrc] = useState<string | null>(() => {
    // Try to get from cache on initial render
    return src ? getCachedAvatar(src) : null
  })
  const [error, setError] = useState(false)
  const loadingRef = useRef(false)

  useEffect(() => {
    if (!src || loadingRef.current) return

    // If we already have a cached version, still fetch fresh in background
    const cachedSrc = getCachedAvatar(src)
    if (cachedSrc) {
      setImageSrc(cachedSrc)
    }

    // Fetch and cache the image
    loadingRef.current = true

    // `src` may point to a third-party avatar/icon CDN this app doesn't
    // own — never attach our bearer token to it.
    fetchStream(src, { auth: false })
      .then(res => {
        if (!res.ok) throw new Error('Failed to load avatar')
        return res.blob()
      })
      .then(blob => {
        const reader = new FileReader()
        reader.onloadend = () => {
          const base64 = reader.result as string
          setCachedAvatar(src, base64)
          setImageSrc(base64)
          setError(false)
        }
        reader.readAsDataURL(blob)
      })
      .catch(() => {
        setError(true)
        // If we don't have a cached version, try using the URL directly
        if (!cachedSrc) {
          setImageSrc(src)
        }
      })
      .finally(() => {
        loadingRef.current = false
      })
  }, [src])

  // Reset when src changes
  useEffect(() => {
    setError(false)
  }, [src])

  if (!src || error) {
    return (
      <Avatar className={className}>
        <AvatarFallback className={cn(fallbackClassName)}>
          {fallback}
        </AvatarFallback>
      </Avatar>
    )
  }

  return (
    <Avatar className={className}>
      {imageSrc && (
        <AvatarImage
          src={imageSrc}
          alt={alt}
          onError={() => setError(true)}
        />
      )}
      <AvatarFallback className={cn(fallbackClassName)}>
        {fallback}
      </AvatarFallback>
    </Avatar>
  )
}
