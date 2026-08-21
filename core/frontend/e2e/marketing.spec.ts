import { test, expect } from '@playwright/test'

test.describe('Marketing pages', () => {
  test('/ serves landing for unauthenticated user @smoke', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    // Landing is shown, not app shell — sidebar nav must be absent
    await expect(page.locator('nav[aria-label="Main navigation"]')).not.toBeVisible()
  })

  test('clicking "Try free" navigates to /signup', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('link', { name: /try free/i }).first().click()
    await expect(page).toHaveURL(/\/signup/)
  })

  test('/pricing renders 3 tiers @smoke', async ({ page }) => {
    await page.goto('/pricing')
    const cards = page.locator('[data-testid^="tier-card-"]')
    await expect(cards).toHaveCount(3)
  })

  test('monthly/yearly toggle changes displayed prices', async ({ page }) => {
    await page.goto('/pricing')
    // Default is monthly — scope assertion to Plus card
    const plusCard = page.locator('[data-testid="tier-card-plus"]')
    await expect(plusCard.getByText('$20')).toBeVisible()
    // Switch to yearly — Plus is $200/yr = $16/mo displayed
    await page.getByRole('button', { name: /yearly/i }).click()
    await expect(plusCard.getByText('$16')).toBeVisible()
  })

  test('SEO: / has title and description meta', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/Sterna/)
    const desc = await page.locator('meta[name="description"]').getAttribute('content')
    expect(desc).toBeTruthy()
  })

  test('SEO: /pricing has title and og:image', async ({ page }) => {
    await page.goto('/pricing')
    await expect(page).toHaveTitle(/Pricing.*Sterna/)
    const ogImage = await page.locator('meta[property="og:image"]').getAttribute('content')
    expect(ogImage).toContain('og-image.png')
  })
})
