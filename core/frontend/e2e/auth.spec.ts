/**
 * Auth flows E2E test suite.
 *
 * Exercises the redesigned auth surface end-to-end:
 *   /login, /signup, /forgot-password, /verify-email, /oauth/callback
 *   plus the VerificationGate that blocks chat-send for unverified users.
 *
 * Requirements:
 *   - Dev server runs with `VITE_ENABLE_DEV_AUTH=true` (the
 *     globalSetup at `e2e/setup-env.ts` sets this so dev-auth's
 *     mock bypass is active). Without that, login.happy-path hits a
 *     real backend and fails.
 */

import { test, expect } from '@playwright/test'

test.describe('Auth flows', () => {
  test('login happy path @smoke', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Email address').fill('dev@example.com')
    await page.getByLabel('Password', { exact: true }).fill('password123')
    await page.getByRole('button', { name: /^sign in$/i }).click()
    await expect(page).toHaveURL(/\/chats/)
  })

  test('signup leads to verify-email pending state', async ({ page }) => {
    await page.goto('/signup')
    await page.getByLabel('First name').fill('Alice')
    await page.getByLabel('Last name').fill('Doe')
    await page.getByLabel('Email address').fill('alice+test@example.com')
    await page.getByLabel('Password', { exact: true }).fill('Abcd1234!')
    await page.getByLabel('Confirm password').fill('Abcd1234!')
    await page.getByLabel(/terms of service/i).check()
    await page.getByRole('button', { name: /create account/i }).click()
    await expect(page).toHaveURL(/\/verify-email\?.*pending=1/)
    await expect(page.getByText(/check your inbox/i)).toBeVisible()
  })

  test('password reset request shows success state', async ({ page }) => {
    await page.goto('/forgot-password')
    await page.getByLabel('Email address').fill('alice+test@example.com')
    await page.route('**/api/auth/password-reset/', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }),
    )
    await page.getByRole('button', { name: /send reset link/i }).click()
    await expect(page.getByText(/if an account exists/i)).toBeVisible()
  })

  test('OAuth callback success', async ({ page }) => {
    // Exercises the GitHub OAuth happy path. The HTTP layer must be
    // intercepted because dev-auth has no devGithubAuth bypass.
    const state = 'test-state-abc123'

    await page.addInitScript((s) => {
      sessionStorage.setItem('github_oauth_state', s)
      sessionStorage.setItem('github_auth_return_url', '/chats')
    }, state)

    await page.route('**/api/auth/github/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access: 'mock-access-token',
          refresh: 'mock-refresh-token',
          user: {
            id: '1',
            email: 'oauth@example.com',
            first_name: 'OAuth',
            last_name: 'User',
            is_active: true,
            is_verified: true,
            avatar_url: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        }),
      }),
    )

    await page.goto(`/oauth/callback?code=fake-code&state=${state}`)
    await expect(page).toHaveURL(/\/chats/)
  })

  test('OAuth callback rejects invalid state', async ({ page }) => {
    await page.goto('/oauth/callback?code=fake&state=invalid')
    await expect(page).toHaveURL(/\/login\?.*error=invalid_state/)
  })

  test('VerificationGate blocks chat-send before verification', async ({ page }) => {
    // STEP 1: Log in as the unverified mock user FIRST so that
    // `auth-storage` exists in localStorage. The model store reads
    // `auth-storage` via `createUserScopedStorage` and returns null if
    // no user is present at first hydration — seeding the model store
    // BEFORE login would be discarded.
    await page.goto('/login')
    await page.getByLabel('Email address').fill('unverified@example.com')
    await page.getByLabel('Password', { exact: true }).fill('password123')
    await page.getByRole('button', { name: /^sign in$/i }).click()
    await expect(page).toHaveURL(/\/chats/)

    // STEP 2: Seed the model store under the user-scoped key
    // `model-storage-1` (dev-auth's mockUser.id === '1'). Then reload
    // so the model store hydrates against the seeded entry.
    await page.evaluate(() => {
      const seedModel = {
        model_id: 'openai/gpt-4o-mini',
        name: 'GPT-4o mini',
        provider: 'openai',
        context_length: 128000,
      }
      const envelope = {
        state: {
          currentModel: seedModel,
          models: [seedModel],
          favorites: [],
          recentModels: [],
          recentChatModels: [],
          selectedModels: [],
          _hasHydrated: true,
        },
        version: 0,
      }
      localStorage.setItem('model-storage-1', JSON.stringify(envelope))
    })
    await page.reload()
    await expect(page).toHaveURL(/\/chats/)

    // STEP 3: The email-verification banner should be visible at top.
    await expect(page.getByRole('region', { name: /verification/i })).toBeVisible()

    // STEP 4: Attempt to send a chat message. The guard intercepts
    // before onSendMessage runs.
    const textarea = page.getByRole('textbox').first()
    await textarea.fill('hello world')
    await page.getByRole('button', { name: /^send$/i }).click()

    // STEP 5: Verification modal should appear; message should NOT be sent.
    await expect(page.getByRole('dialog')).toContainText(/verify your email first/i)
  })
})

test.describe('Auth visuals', () => {
  test.skip(
    ({ browserName }) => browserName !== 'chromium',
    'Screenshot cases run on chromium only',
  )

  test('login screenshot', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    await page.screenshot({
      path: 'playwright-report/screenshots/auth-after-login.png',
      fullPage: true,
    })
  })

  test('signup screenshot', async ({ page }) => {
    await page.goto('/signup')
    await page.waitForLoadState('networkidle')
    await page.screenshot({
      path: 'playwright-report/screenshots/auth-after-signup.png',
      fullPage: true,
    })
  })

  test('verify-email pending screenshot', async ({ page }) => {
    await page.goto('/verify-email?pending=1&email=alice%40example.com')
    await page.waitForLoadState('networkidle')
    await page.screenshot({
      path: 'playwright-report/screenshots/auth-after-verify-email.png',
      fullPage: true,
    })
  })

  test('forgot-password screenshot', async ({ page }) => {
    await page.goto('/forgot-password')
    await page.waitForLoadState('networkidle')
    await page.screenshot({
      path: 'playwright-report/screenshots/auth-after-forgot-password.png',
      fullPage: true,
    })
  })

  test('reset-password screenshot', async ({ page }) => {
    await page.goto('/reset-password?token=fake-token-for-design-pass')
    await page.waitForLoadState('networkidle')
    await page.screenshot({
      path: 'playwright-report/screenshots/auth-after-reset-password.png',
      fullPage: true,
    })
  })

  test('AuthModal screenshot', async ({ page }) => {
    // Visiting /chats while unauthenticated triggers the AuthModal.
    await page.goto('/chats')
    await page.waitForSelector('[role="dialog"]', { timeout: 10_000 }).catch(() => {})
    await page.screenshot({
      path: 'playwright-report/screenshots/auth-after-modal.png',
      fullPage: true,
    })
  })
})
