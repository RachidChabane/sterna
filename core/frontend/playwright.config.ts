import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for the frontend E2E suites.
 *
 * baseURL comes from PLAYWRIGHT_BASE_URL when set (CI exports it; a
 * deployed URL can also be targeted), falling back to the local Vite
 * dev server. The webServer block only spins up `npm run dev` when the
 * target IS the local dev server — pointing PLAYWRIGHT_BASE_URL at a
 * deployed environment must not try to boot Vite.
 */
const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173'
const isLocalTarget = /^https?:\/\/(localhost|127\.0\.0\.1):5173\/?$/.test(baseURL)

export default defineConfig({
  testDir: './e2e',
  // Relative path (resolved against this config file) — require.resolve
  // is unavailable now that the config loads as ESM.
  globalSetup: './e2e/setup-env.ts',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    // Mobile viewports
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],
  webServer: isLocalTarget
    ? {
        command: 'npm run dev',
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
        // The auth/billing suites need the dev-auth mock bypass.
        // Passed here (not only via globalSetup) because the webServer
        // process boots before globalSetup runs, and .env.development
        // pins VITE_ENABLE_DEV_AUTH=false.
        env: { VITE_ENABLE_DEV_AUTH: 'true' },
      }
    : undefined,
})
