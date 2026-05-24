const { test, expect } = require('@playwright/test');

const adminUsername = process.env.PLAYWRIGHT_ADMIN_USERNAME || 'admin';
const adminPassword = process.env.PLAYWRIGHT_ADMIN_PASSWORD || 'adminpass123456';

test('auth gate and workspace navigation stay functional', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page.locator('[title^="Connection Error:"]')).toHaveCount(0);

  await expect(page.getByText('SIGN-IN REQUIRED')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Access' })).toBeVisible();
  await expect(page.getByText('Operator not authenticated.')).toBeVisible();

  await page.getByPlaceholder('Operator sign-in name').fill(adminUsername);
  await page.getByPlaceholder('Operator sign-in password').fill(adminPassword);
  await page.getByRole('button', { name: 'Sign In' }).click();

  await expect(page.getByText('ROLE ADMIN')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Overview' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Network Overview' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Signal Map' })).toBeVisible();

  await page.getByRole('button', { name: 'Signal Control' }).click();
  await expect(page.getByRole('heading', { name: 'Signal Control' })).toBeVisible();
  await expect(page.getByText('Command Safety')).toBeVisible();

  await page.getByRole('button', { name: 'Maintenance' }).click();
  await expect(page.getByRole('heading', { name: 'System Maintenance' })).toBeVisible();
  await expect(page.getByText('System Health')).toBeVisible();
  await expect(page.getByText('Runtime health not refreshed yet.')).toBeVisible();
  await page.getByRole('button', { name: 'Refresh Health' }).click();
  await expect(page.getByText('Runtime health not refreshed yet.')).not.toBeVisible();
  await expect(page.getByText(/Scheduler:/)).toBeVisible();

  await page.getByRole('button', { name: 'Alarms & Events' }).click();
  await expect(page.getByRole('heading', { name: 'Alarms & Events' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Active Alarms' })).toBeVisible();

  await page.getByRole('button', { name: 'Controllers' }).click();
  await expect(page.getByRole('heading', { name: 'Controllers' }).first()).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Controller Profiles' })).toBeVisible();

  await page.getByRole('button', { name: 'Access' }).click();
  await expect(page.getByRole('heading', { name: 'Access' })).toBeVisible();
  await expect(page.getByText('Authenticated as admin (admin).')).toBeVisible();

  await page.getByRole('button', { name: 'Sign Out' }).click();
  await expect(page.getByText('SIGN-IN REQUIRED')).toBeVisible();
  await expect(page.getByText('Operator not authenticated.')).toBeVisible();
});