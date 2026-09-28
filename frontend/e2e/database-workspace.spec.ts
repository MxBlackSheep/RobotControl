import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
const evidence = '../recovery/database-workspace-verification';
async function login(page: any) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', (route: any) => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'Fixture', role: 'admin', session_is_local: true } } }));
}

test('upload-first example needs no database and access creation has a review', async ({ page }) => {
  mkdirSync(evidence, { recursive: true }); await login(page);
  await page.goto('/database?section=packages');
  await page.getByRole('button', { name: 'Database connections', exact: true }).click();
  await page.getByRole('combobox', { name: 'Account setup' }).click();
  await page.getByRole('option', { name: 'Create read-only account', exact: true }).click();
  await page.getByLabel('Name', { exact: true }).fill('New lab');
  await page.getByLabel('Server', { exact: true }).fill('LAB-SQL');
  await page.getByRole('textbox', { name: 'Database', exact: true }).fill('LabResults');
  await page.getByLabel('New account name', { exact: true }).fill('lab_reports');
  await page.getByRole('button', { name: 'Review access', exact: true }).click();
  await expect(page.getByText('Review read-only access', { exact: true })).toBeVisible();
  await expect(page.getByText('LAB-SQL / LabResults', { exact: true })).toBeVisible();
  await page.screenshot({ path: `${evidence}/access-review.png`, fullPage: true });
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Create report', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Upload Python', exact: true })).toBeVisible();
  await page.screenshot({ path: `${evidence}/upload-first.png`, fullPage: true });
  await page.getByRole('button', { name: 'Try an example', exact: true }).click();
  await expect(page.getByText('Report entry point found. Ready to configure and try.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: 'Uses a database' })).not.toBeChecked();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Download starter', exact: true })).toHaveCount(0);
  await page.getByLabel('Sample name', { exact: false }).fill('Demo');
  await page.getByRole('button', { name: 'Try report', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Download Excel', exact: true })).toBeVisible();
  await page.screenshot({ path: `${evidence}/example-desktop.png`, fullPage: true });
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download Excel', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('example.xlsx');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `${evidence}/example-phone.png`, fullPage: true });
  await page.getByRole('button', { name: 'Save and close', exact: true }).click();
  await page.getByRole('button', { name: 'Remove draft', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Remove draft', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('switching viewer database clears the previous table and leaves restore separate', async ({ page }) => {
  await login(page);
  await page.route('**/api/database/tools/viewer-sources', route => route.fulfill({ json: [
    { id: 'a', name: 'Lab A', server: 'SQL-A', database: 'ResultsA' }, { id: 'b', name: 'Lab B', server: 'SQL-B', database: 'ResultsB' },
  ] }));
  await page.route('**/api/database/tables?*', route => route.fulfill({ json: { success: true, data: { table_details: [{ name: new URL(route.request().url()).searchParams.get('source_id') === 'a' ? '[dbo].[Samples]' : '[other].[Readings]' }] } } }));
  await page.route('**/api/database/tables/*?*', route => route.fulfill({ json: { success: true, data: { columns: ['value'], rows: [{ value: 'Sample A' }], total_count: 1 } } }));
  await page.goto('/database');
  await page.getByRole('button', { name: '[dbo].[Samples]', exact: false }).click();
  await expect(page.getByText('Sample A', { exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: 'Database connection' }).click();
  await page.getByRole('option', { name: 'Lab B · SQL-B / ResultsB' }).click();
  await expect(page.getByRole('button', { name: '[other].[Readings]', exact: false })).toBeVisible();
  await expect(page.getByText('Sample A', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('listbox')).toHaveCount(0);
  await page.screenshot({ path: `${evidence}/viewer-target.png`, animations: 'disabled', fullPage: true });
  await page.goto('/database?section=restore');
  await expect(page.getByRole('combobox', { name: 'Database connection' })).toHaveCount(0);
});
