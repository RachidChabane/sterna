/**
 * Sharing Utilities
 *
 * Helper functions for sharing content to social platforms.
 */

import { DEFAULT_SHARE_CONFIG, type SharePlatform } from './platforms'

/**
 * Open a share popup window for a platform
 */
export function openSharePopup(
  platform: SharePlatform,
  shareUrl: string,
  options?: {
    text?: string
    title?: string
  }
): void {
  const url = platform.getShareUrl({
    url: shareUrl,
    text: options?.text ?? DEFAULT_SHARE_CONFIG.text,
    title: options?.title ?? DEFAULT_SHARE_CONFIG.title,
  })

  window.open(
    url,
    '_blank',
    `width=${DEFAULT_SHARE_CONFIG.popupWidth},height=${DEFAULT_SHARE_CONFIG.popupHeight}`
  )
}

/**
 * Trigger native share dialog (mobile)
 * Returns true if share was successful, false if cancelled or failed
 */
export async function triggerNativeShare(shareUrl: string): Promise<boolean> {
  if (!navigator.share) {
    return false
  }

  try {
    await navigator.share({
      title: DEFAULT_SHARE_CONFIG.title,
      text: DEFAULT_SHARE_CONFIG.text,
      url: shareUrl,
    })
    return true
  } catch {
    // User cancelled or share failed
    return false
  }
}

/**
 * Check if native sharing is supported
 */
export function isNativeShareSupported(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.share
}
