import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
const evidence = '../recovery/report-wizard-verification';
const handler = `import openpyxl
def run(context, inputs):
    book = openpyxl.Workbook()
    book.active.append([inputs['plate'], inputs['culture']])
    book.save(context.output_dir / 'selection.xlsx')
    return 'selection.xlsx'
`;
async function login(page: any) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', (route: any) => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'Fixture', role: 'admin', session_is_local: true } } }));
  await page.route('**/api/database/tables?*', (route: any) => route.fulfill({ json: { success: true, data: { table_details: [] } } }));
}
async function choose(page: any, label: string, option: string) {
  await page.getByRole('combobox', { name: label, exact: false }).click();
  await page.getByRole('option', { name: option, exact: true }).click();
}

test('report author resumes a draft, configures dependent inputs and installs a tried report', async ({ page }) => {
  mkdirSync(evidence, { recursive: true });
  await login(page);
  await page.goto('/database?section=packages');
  await page.getByRole('button', { name: 'Create report', exact: true }).click();
  await page.getByLabel('Report name', { exact: true }).fill('Selection export');
  await page.getByLabel('Package ID', { exact: true }).fill('selection-export');
  await page.getByLabel('Original Python', { exact: true }).setInputFiles({ name: 'original.py', mimeType: 'text/x-python', buffer: Buffer.from('raise RuntimeError("original must not run")') });
  await expect(page.getByText('Original script saved.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await page.getByLabel('Names used in Python (comma separated)').fill('primary, plates');
  await choose(page, 'Connection for primary', 'Primary');
  await choose(page, 'Connection for plates', 'Plates');
  for (const [i, name, label, source, query] of [
    [0, 'plate', 'Plate', 'primary', 'SELECT DISTINCT PlateID AS value, CAST(PlateID AS nvarchar(40)) AS label FROM Cultures'],
    [1, 'culture', 'Culture', 'plates', 'SELECT CultureID AS value, WellID AS label FROM Cultures WHERE PlateID=?'],
  ] as const) {
    await page.getByRole('button', { name: 'Add input', exact: true }).click();
    await page.getByLabel('Input name in Python', { exact: true }).nth(i).fill(name);
    await page.getByLabel('Label', { exact: true }).nth(i).fill(label);
    await page.getByRole('combobox', { name: 'Input type', exact: false }).nth(i).click();
    await page.getByRole('option', { name: 'Database choices', exact: true }).click();
    await page.getByRole('combobox', { name: 'Source', exact: false }).nth(i).click();
    await page.getByRole('option', { name: source, exact: true }).click();
    await page.getByRole('combobox', { name: 'Value type', exact: false }).nth(i).click();
    await page.getByRole('option', { name: 'integer', exact: true }).click();
    await page.getByLabel('Choice query', { exact: true }).nth(i).fill(query);
  }
  await page.getByRole('combobox', { name: 'Depends on (parameter order)', exact: false }).nth(1).click();
  await page.getByRole('option', { name: 'Plate', exact: true }).click(); await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Save and close', exact: true }).click();
  await page.reload();
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(page.getByLabel('Input name in Python').nth(1)).toHaveValue('culture');
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  const starter = page.waitForEvent('download'); await page.getByRole('button', { name: 'Download starter', exact: true }).click();
  expect((await starter).suggestedFilename()).toBe('handler.py');
  await page.getByLabel('Completed handler', { exact: true }).setInputFiles({ name: 'handler.py', mimeType: 'text/x-python', buffer: Buffer.from(handler) });
  await expect(page.getByText('Handler saved.', { exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Culture', exact: true })).toBeDisabled();
  await page.getByRole('combobox', { name: 'Plate', exact: true }).click();
  await page.getByRole('option', { name: '20 · 20', exact: true }).click();
  await page.getByRole('combobox', { name: 'Culture', exact: true }).click();
  await page.getByRole('option', { name: 'A1 · 3', exact: true }).click();
  await page.getByRole('combobox', { name: 'Plate', exact: true }).fill('10');
  await page.getByRole('option', { name: '10 · 10', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Culture', exact: true })).toHaveValue('');
  await page.getByRole('combobox', { name: 'Culture', exact: true }).click();
  await page.getByRole('option', { name: 'A2 · 2', exact: true }).click();
  await page.getByRole('button', { name: 'Try report', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Download Excel', exact: true })).toBeVisible();
  await page.screenshot({ path: `${evidence}/wizard-desktop.png`, animations: 'disabled', fullPage: true });
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  const exported = page.waitForEvent('download'); await page.getByRole('button', { name: 'Export package', exact: true }).click();
  expect((await exported).suggestedFilename()).toBe('selection-export-1.0.0.zip');
  await page.getByRole('button', { name: 'Review installation', exact: true }).click();
  await page.getByRole('button', { name: 'Install report', exact: true }).click();
  await expect(page.getByText('Report installed. It is available in Data retrieval.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Save and close', exact: true }).click();
  await page.goto('/database?section=retrieval');
  await choose(page, 'Report', 'Selection export');
  await page.getByRole('combobox', { name: 'Plate', exact: true }).click();
  await page.getByRole('option', { name: '10 · 10', exact: true }).click();
  await page.getByRole('combobox', { name: 'Culture', exact: true }).click();
  await page.getByRole('option', { name: 'A1 · 1', exact: true }).click();
  await page.getByRole('button', { name: 'Generate Excel', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Download Excel', exact: true })).toBeVisible();
  await page.screenshot({ path: `${evidence}/multiple-reports.png`, animations: 'disabled' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/database?section=packages');
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(page.getByText('Selection export · 1.0.0')).toBeVisible();
  await page.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(page.getByText(/Handler saved ·/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `${evidence}/wizard-phone.png`, animations: 'disabled', fullPage: true });
  await page.getByRole('button', { name: 'Save and close', exact: true }).click();
  await page.getByRole('button', { name: 'Remove draft', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Installed reports are kept');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Resume', exact: true })).toBeVisible();
});
