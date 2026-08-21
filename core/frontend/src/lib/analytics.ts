import { useConsentStore } from '@/store/consentStore'

function isAnalyticsAllowed(): boolean {
  return useConsentStore.getState().categories.analytics === true
}

export function track(event: string, props?: Record<string, unknown>): void {
  if (!isAnalyticsAllowed()) return
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.debug('[analytics] track', event, props)
  }
  // TODO: when a real SDK is wired up, the call goes here.
  // Example: posthog.capture(event, props)
}

export function identify(
  userId: string,
  traits?: Record<string, unknown>,
): void {
  if (!isAnalyticsAllowed()) return
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.debug('[analytics] identify', userId, traits)
  }
  // TODO: posthog.identify(userId, traits)
}

export function page(name?: string, props?: Record<string, unknown>): void {
  if (!isAnalyticsAllowed()) return
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.debug('[analytics] page', name, props)
  }
  // TODO: posthog.capture('$pageview', { ...props, $current_url: window.location.href })
}
