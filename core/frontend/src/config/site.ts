/**
 * Public site identity (domain, support email, status page).
 *
 * Kept out of individual components so a fork/fresh deployment only needs
 * to set VITE_SITE_DOMAIN once. Falls back to a neutral placeholder domain
 * rather than hardcoding a real one.
 */

const SITE_DOMAIN = import.meta.env.VITE_SITE_DOMAIN || 'example.com'

export const SITE_CONFIG = {
  domain: SITE_DOMAIN,
  supportEmail: `support@${SITE_DOMAIN}`,
  statusPageUrl: `https://status.${SITE_DOMAIN}`,
  docsUrl: `https://docs.${SITE_DOMAIN}`,
} as const
