/**
 * Billing flows E2E test suite (task 12).
 *
 * Two flows, both with mocked Stripe / backend:
 *   - free user clicks Upgrade on Pricing → POST creates Checkout Session
 *     → redirects to Stripe.
 *   - /billing/return → POSTs sync-from-session → renders welcome →
 *     auto-redirects to /settings/billing.
 *
 * Requires VITE_ENABLE_DEV_AUTH=true (set by e2e/setup-env.ts).
 */

import { test, expect } from '@playwright/test'

test.describe('Billing flows (mocked Stripe)', () => {
  test('free user → click Upgrade → posts checkout-session and redirects @smoke', async ({
    page,
  }) => {
    let body: unknown = null
    await page.route('**/api/billing/checkout-session/', async (route) => {
      body = route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          url: 'https://checkout.stripe.com/c/pay/cs_test_E2E',
        }),
      })
    })
    // Stop the actual Stripe redirect — we only need to see it was attempted.
    await page.route('https://checkout.stripe.com/**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<html>stripe</html>',
      }),
    )

    await page.goto('/login')
    await page.getByLabel('Email address').fill('dev@example.com')
    await page.getByLabel('Password', { exact: true }).fill('password123')
    await page.getByRole('button', { name: /^sign in$/i }).click()
    await expect(page).toHaveURL(/\/chats/)

    await page.goto('/pricing')
    await page
      .locator('[data-testid="tier-card-plus"]')
      .getByRole('button', { name: /upgrade/i })
      .click()

    await expect.poll(() => body).not.toBeNull()
    expect(body).toMatchObject({
      plan_slug: 'plus',
      billing_cycle: 'monthly',
    })
    await expect(page).toHaveURL(/checkout\.stripe\.com/)
  })

  test('return → sync → UI shows new plan + redirects @smoke', async ({ page }) => {
    await page.route('**/api/billing/sync-from-session/**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          plan: 'plus',
          plan_display_name: 'Plus',
          status: 'active',
          current_period_end: 1799999999,
          cancel_at_period_end: false,
        }),
      }),
    )
    // Mock /billing/status/ so settings.billing has something to render
    // when the auto-redirect fires.
    await page.route('**/api/billing/status/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          plan: 'plus',
          plan_display_name: 'Plus',
          plan_description: 'Plus tier',
          is_paid: true,
          current_period_end: 1799999999,
          cancel_at_period_end: false,
        }),
      }),
    )

    await page.goto('/login')
    await page.getByLabel('Email address').fill('dev@example.com')
    await page.getByLabel('Password', { exact: true }).fill('password123')
    await page.getByRole('button', { name: /^sign in$/i }).click()
    await expect(page).toHaveURL(/\/chats/)

    await page.goto('/billing/return?session_id=cs_test_RETURN')
    await expect(page.getByText(/welcome to plus/i)).toBeVisible()
    // After 3s, navigates to /settings/billing.
    await expect(page).toHaveURL(/\/settings\/billing/, { timeout: 5000 })
    // Scope to the plan heading: the page renders both "Plus" (h2) and
    // "Plus tier" (description), which trips getByText strict mode.
    await expect(page.getByRole('heading', { name: 'Plus' })).toBeVisible()
  })
})
