/**
 * Sharing Module
 *
 * Centralized sharing functionality following SOLID principles:
 * - Single Responsibility: Each platform handles its own URL generation
 * - Open/Closed: Easy to add new platforms without modifying existing code
 * - DRY: Shared configuration and utilities used by all components
 */

export { SHARE_PLATFORMS } from './platforms'

export { openSharePopup, triggerNativeShare, isNativeShareSupported } from './utils'

export { PlatformBadge } from './components'
