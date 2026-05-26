const { test, expect } = require('@playwright/test');

const adminUsername = process.env.PLAYWRIGHT_ADMIN_USERNAME || 'admin';
const adminPassword = process.env.PLAYWRIGHT_ADMIN_PASSWORD || 'adminpass123456';
const e2eDeviceId = 'e2e-map-unmapped';
const e2eLocation = 'Playwright & Pine';
const e2eLatitude = '40.7128';
const e2eLongitude = '-74.0060';

test('auth gate and workspace navigation stay functional', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', (error) => {
    pageErrors.push(error.message);
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page.locator('[title^="Connection Error:"]')).toHaveCount(0);

  const loginRequired = await page.getByText('Operator not authenticated.').count() > 0;
  if (loginRequired) {
    await expect(page.getByRole('heading', { name: 'Access' })).toBeVisible();
    await expect(page.getByPlaceholder('Operator sign-in name')).toBeVisible();
    await expect(page.getByPlaceholder('Operator sign-in password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();

    await page.getByPlaceholder('Operator sign-in name').fill(adminUsername);
    await page.getByPlaceholder('Operator sign-in password').fill(adminPassword);
    await page.getByRole('button', { name: 'Sign In' }).click();
  } else {
    await expect(page.getByText('ROLE ADMIN')).toBeVisible();
  }

  await expect(page.getByText('ROLE ADMIN')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Overview', exact: true })).toBeVisible();
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

  await page.getByRole('textbox', { name: 'Controller ID', exact: true }).fill(e2eDeviceId);
  await page.getByRole('textbox', { name: 'Display name', exact: true }).fill('Playwright Unmapped');
  await page.getByRole('textbox', { name: 'Location label / intersection', exact: true }).fill(e2eLocation);
  await page.getByRole('textbox', { name: 'IP address', exact: true }).fill('10.0.0.50');
  await page.getByRole('button', { name: 'Add Profile' }).click();
  await expect(page.getByText(`Saved controller profile ${e2eDeviceId}.`)).toBeVisible();

  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Network Overview' })).toBeVisible();
  await page.getByRole('button', { name: new RegExp(e2eLocation) }).first().click();

  await expect(page.getByRole('heading', { name: 'Controllers' }).first()).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Controller ID', exact: true })).toHaveValue(e2eDeviceId);
  await expect(page.getByRole('textbox', { name: 'Location label / intersection', exact: true })).toHaveValue(e2eLocation);
  await page.getByRole('textbox', { name: 'Latitude', exact: true }).fill(e2eLatitude);
  await page.getByRole('textbox', { name: 'Longitude', exact: true }).fill(e2eLongitude);
  await page.getByRole('button', { name: 'Update Profile' }).click();
  await expect(page.getByText(`Saved controller profile ${e2eDeviceId}.`)).toBeVisible();

  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Network Overview' })).toBeVisible();
  await expect(page.getByText(/Showing \d+ mapped controller/)).toBeVisible();
  const mapFrame = page.frameLocator('iframe');
  await expect(mapFrame.locator('.leaflet-container')).toBeVisible();
  await expect(mapFrame.locator('.leaflet-interactive')).toHaveCount(1);
  await mapFrame.locator('.leaflet-interactive').first().click({ force: true });
  await expect(page.getByRole('heading', { name: 'Intersection Detail' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Controller ID', exact: true })).toHaveValue(e2eDeviceId);
  await page.getByRole('button', { name: '← Overview' }).click();
  await expect(page.getByRole('heading', { name: 'Network Overview' })).toBeVisible();

  await page.getByRole('button', { name: 'Access' }).click();
  await expect(page.getByRole('heading', { name: 'Access' })).toBeVisible();
  if (loginRequired) {
    await expect(page.getByText(`Authenticated as admin (${adminUsername}).`)).toBeVisible();
  } else {
    await expect(page.getByText('Login disabled for local development.')).toBeVisible();
  }

  await page.getByRole('button', { name: 'Sign Out' }).click();
    if (loginRequired) {
      await expect(page.getByPlaceholder('Operator sign-in name')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
      await expect(page.getByText('Operator not authenticated.')).toBeVisible();
    } else {
      await expect(page.getByText('Login remains disabled for local development.')).toBeVisible();
    }

  await expect(pageErrors).toEqual([]);
});