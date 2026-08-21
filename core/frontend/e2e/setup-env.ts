/**
 * Playwright globalSetup: enables the dev-auth mock bypass so the
 * auth e2e suite runs without a real backend. See
 * `core/frontend/src/api/dev-auth.ts`.
 */
export default async function globalSetup() {
  process.env.VITE_ENABLE_DEV_AUTH = 'true'
}
