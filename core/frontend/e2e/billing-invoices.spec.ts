/**
 * Invoice history E2E test suite (task 14).
 *
 * /settings/billing renders an "Invoice history" section for paid users,
 * pulling from GET /api/billing/invoices. Locale-resilient assertions —
 * Intl.NumberFormat output varies between en-US ("23.80") and de-DE/fr-FR
 * ("23,80"); see plan §5.10.
 *
 * Requires VITE_ENABLE_DEV_AUTH=true (set by e2e/setup-env.ts).
 */

import { test, expect } from '@playwright/test'

async function loginDev(page: any) {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('dev@example.com')
  await page.getByLabel('Password', { exact: true }).fill('password123')
  await page.getByRole('button', { name: /^sign in$/i }).click()
  await expect(page).toHaveURL(/\/chats/)
}

test.describe('settings/billing — invoice history (task 14)', () => {
  test('renders invoice history for a paid user', async ({ page }) => {
    await page.route('**/api/billing/status/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          plan: 'plus',
          plan_display_name: 'Plus',
          plan_description: 'Plus tier',
          is_paid: true,
          current_period_end: 1714060800,
          cancel_at_period_end: false,
        }),
      })
    })
    await page.route('**/api/billing/invoices/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            {
              id: 'in_1',
              number: 'INV-0001',
              created: 1700000000,
              total: 2380,
              subtotal_excl_tax: 2000,
              tax: 380,
              currency: 'eur',
              status: 'paid',
              hosted_invoice_url: 'https://invoice.stripe.com/i/test',
              invoice_pdf: 'https://invoice.stripe.com/p/test/pdf',
              plan_name: 'Plus',
            },
          ],
        }),
      })
    })

    await loginDev(page)
    await page.goto('/settings/billing')
    await expect(
      page.getByRole('heading', { name: 'Invoice history' }),
    ).toBeVisible()
    // Locale-resilient: en-US -> "23.80", de-DE / fr-FR -> "23,80".
    await expect(page.getByRole('cell', { name: /23[,.]80/ })).toBeVisible()
    await expect(page.getByRole('cell', { name: /3[,.]80/ })).toBeVisible()
    const viewLink = page.getByRole('link', { name: /View/i })
    await expect(viewLink).toHaveAttribute(
      'href',
      'https://invoice.stripe.com/i/test',
    )
  })

  test('hides invoice history section for a free user', async ({ page }) => {
    await page.route('**/api/billing/status/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          plan: 'free',
          plan_display_name: 'Free',
          plan_description: 'Free tier',
          is_paid: false,
          current_period_end: null,
          cancel_at_period_end: false,
        }),
      })
    })

    await loginDev(page)
    await page.goto('/settings/billing')
    await expect(
      page.getByRole('heading', { name: 'Invoice history' }),
    ).toHaveCount(0)
  })

  test('client-side paginates at 12 per page', async ({ page }) => {
    await page.route('**/api/billing/status/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          plan: 'plus',
          plan_display_name: 'Plus',
          plan_description: '',
          is_paid: true,
          current_period_end: 1714060800,
          cancel_at_period_end: false,
        }),
      })
    })
    await page.route('**/api/billing/invoices/', async (route) => {
      const results = Array.from({ length: 24 }, (_, i) => ({
        id: `in_${i}`,
        number: `INV-${String(i + 1).padStart(4, '0')}`,
        created: 1700000000 + i * 86400,
        total: 2400,
        subtotal_excl_tax: 2000,
        tax: 400,
        currency: 'eur',
        status: 'paid',
        hosted_invoice_url: `https://invoice.stripe.com/i/${i}`,
        invoice_pdf: '',
        plan_name: 'Plus',
      }))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ results }),
      })
    })

    await loginDev(page)
    await page.goto('/settings/billing')
    await expect(page.getByText('Page 1 of 2')).toBeVisible()
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page.getByText('Page 2 of 2')).toBeVisible()
  })
})
