/**
 * ShareMenu Component
 *
 * Desktop dropdown menu for creating and managing share links.
 * Creates a public share link via API and provides social sharing options.
 */

import { useState, useCallback, useEffect } from 'react'
import { Link, Check, Loader2, ExternalLink, Copy, Clock, XCircle } from 'lucide-react'
import { assetsAPI, type ShareLink } from '@/api/assets'
import { useSettingsStore } from '@/store/settingsStore'
import { cn } from '@/lib/utils'
import { toErrorMessage } from '@/utils/errorMessages'
import { SHARE_PLATFORMS, openSharePopup, PlatformBadge } from '@/lib/sharing'

interface ShareMenuProps {
  assetId: string
  isOpen: boolean
  onClose: () => void
  className?: string
}

export function ShareMenu({ assetId, isOpen, onClose, className }: ShareMenuProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [shareLink, setShareLink] = useState<ShareLink | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [linkCopied, setLinkCopied] = useState(false)

  // Get watermark settings from global settings
  const watermark = useSettingsStore((state) => state.watermark)

  // Create share link when menu opens
  useEffect(() => {
    if (isOpen && !shareLink && !isLoading) {
      createShareLink()
    }
  }, [isOpen])

  const createShareLink = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const link = await assetsAPI.createShareLink(assetId, {
        watermark_enabled: watermark.enabled,
        watermark_position: watermark.position,
      })
      setShareLink(link)
    } catch (err) {
      setError(toErrorMessage(err) || 'Failed to create share link')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCopyLink = useCallback(async () => {
    if (!shareLink) return
    try {
      await navigator.clipboard.writeText(shareLink.share_url)
      setLinkCopied(true)
      setTimeout(() => setLinkCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }, [shareLink])

  const handleRevokeLink = useCallback(async () => {
    if (!shareLink) return
    try {
      const success = await assetsAPI.revokeShareLink(shareLink.token)
      if (success) {
        setShareLink(null)
        onClose()
      }
    } catch (err) {
      console.error('Failed to revoke link:', err)
    }
  }, [shareLink, onClose])

  if (!isOpen) return null

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-30" onClick={onClose} />

      {/* Menu */}
      <div className={cn(
        "absolute right-0 top-full mt-2 z-40 w-72",
        "bg-background border border-border/50 rounded-xl shadow-2xl",
        "animate-in fade-in slide-in-from-top-2 duration-150",
        className
      )}>
        {/* Loading state */}
        {isLoading && (
          <div className="p-6 flex flex-col items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">Creating share link...</p>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="p-4">
            <div className="flex items-center gap-2 text-red-500 mb-3">
              <XCircle className="h-5 w-5" />
              <span className="text-sm font-medium">Error</span>
            </div>
            <p className="text-sm text-muted-foreground mb-3">{error}</p>
            <button
              onClick={createShareLink}
              className="text-sm text-primary hover:underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Share link created */}
        {shareLink && !isLoading && !error && (
          <>
            {/* Link display */}
            <div className="p-4 border-b border-border/50">
              <div className="flex items-center gap-2 mb-2">
                <Link className="h-4 w-4 text-green-500" />
                <span className="text-sm font-medium text-foreground">Share Link Created</span>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={shareLink.share_url}
                  readOnly
                  className="flex-1 px-3 py-2 text-xs bg-muted rounded-lg border-0 focus:ring-1 focus:ring-primary"
                  onClick={(e) => e.currentTarget.select()}
                />
                <button
                  onClick={handleCopyLink}
                  className={cn(
                    "p-2 rounded-lg transition-colors",
                    linkCopied
                      ? "bg-green-500/10 text-green-500"
                      : "bg-muted hover:bg-muted/80 text-foreground"
                  )}
                  title="Copy link"
                >
                  {linkCopied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </button>
              </div>
              {linkCopied && (
                <p className="text-xs text-green-500 mt-2">Link copied to clipboard!</p>
              )}
            </div>

            {/* Social share options */}
            <div className="p-2">
              <p className="px-2 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Share to
              </p>
              {SHARE_PLATFORMS.map((platform) => (
                <button
                  key={platform.id}
                  onClick={() => openSharePopup(platform, shareLink.share_url)}
                  className="w-full px-3 py-2 text-left text-sm flex items-center gap-3 rounded-lg hover:bg-muted/50 transition-colors"
                >
                  <PlatformBadge platform={platform} size="sm" />
                  <span>
                    {platform.id === 'twitter' ? 'Post on' : 'Share on'} {platform.displayName}
                  </span>
                  <ExternalLink className="h-3 w-3 ml-auto text-muted-foreground" />
                </button>
              ))}
            </div>

            {/* Link info and revoke */}
            <div className="p-3 border-t border-border/50 bg-muted/30">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {shareLink.expires_at ? `Expires ${new Date(shareLink.expires_at).toLocaleDateString()}` : 'No expiration'}
                </span>
                <button
                  onClick={handleRevokeLink}
                  className="text-red-400 hover:text-red-500 transition-colors"
                >
                  Revoke link
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}
