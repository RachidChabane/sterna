/**
 * AssetImage Component
 *
 * Renders an image from the asset storage system.
 * Handles authentication by fetching via API and creating blob URLs.
 * Direct <img src="..."> doesn't work because browser doesn't send auth headers.
 */

import { useState, useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { assetsAPI } from '@/api/assets'

interface AssetImageProps {
  /** Asset ID to load from backend */
  assetId?: string
  /** Local base64 data (takes priority over assetId) */
  base64?: string
  /** Cached base64 from attachment cache */
  cachedBase64?: string
  /** Alt text for the image */
  alt?: string
  /** Additional class names */
  className?: string
  /** Click handler - receives the current image source URL */
  onClick?: (src: string) => void
  /** Callback when image is loaded with the blob URL */
  onLoad?: (blobUrl: string) => void
}

export function AssetImage({
  assetId,
  base64,
  cachedBase64,
  alt = 'image',
  className,
  onClick,
  onLoad,
}: AssetImageProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const loadingRef = useRef(false)  // Track loading without causing re-renders

  // Priority: base64 > cachedBase64 > loaded blob URL
  const src = base64 || cachedBase64 || blobUrl

  // Load from asset storage if needed
  useEffect(() => {
    // Use ref to check loading state to avoid dependency cycle
    if (src || !assetId || loadingRef.current) return

    let cancelled = false
    loadingRef.current = true
    setLoading(true)
    setError(false)

    assetsAPI.download(assetId).then(blob => {
      if (cancelled) return
      if (blob) {
        const url = URL.createObjectURL(blob)
        setBlobUrl(url)
        onLoad?.(url)
      } else {
        setError(true)
      }
    }).catch(() => {
      if (!cancelled) setError(true)
    }).finally(() => {
      if (!cancelled) {
        loadingRef.current = false
        setLoading(false)
      }
    })

    return () => {
      cancelled = true
      loadingRef.current = false
    }
  }, [assetId, src, onLoad])

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl)
      }
    }
  }, [blobUrl])

  if (loading) {
    return (
      <div className={cn(
        "flex items-center justify-center bg-muted/40",
        className
      )}>
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (src) {
    return (
      <img
        src={src}
        alt={alt}
        className={className}
        onClick={() => onClick?.(src)}
      />
    )
  }

  // No source available and not loading - show placeholder
  return (
    <div className={cn(
      "flex items-center justify-center bg-muted/40 text-muted-foreground text-xs",
      className
    )}>
      {error ? 'Failed to load' : alt}
    </div>
  )
}

export default AssetImage
