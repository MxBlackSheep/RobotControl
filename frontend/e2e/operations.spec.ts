import { expect, test, type Page } from '@playwright/test';

/** Failure cases for Scheduling and archives:
 * - On a phone, a selected schedule's actions appear with it, not below the whole list;
 *   Back keeps the list position and resizing keeps the selection.
 * - Queue and recovery state stay visible beside details. Remote users get no editing
 *   controls; recovery-required schedules cannot be deleted or archived.
 * - The schedule editor fits a phone and keeps its draft on Escape, close and failed save.
 * - History, notification and method tables never widen the page; filters survive
 *   section switches; hidden history stops polling.
 * - Archive rows with long names stay readable; folders open without nested scroll areas
 *   and Back returns to the selected folder.
 * Camera cases are in camera.spec.ts.
 */
const schedules = Array.from({ length: 24 }, (_, index) => ({
  schedule_id: `schedule-${index}`, experiment_name: `Experiment ${String(index + 1).padStart(2, '0')}`,
  experiment_path: `C:\\Methods\\experiment-${index}.med`, schedule_type: 'interval', interval_hours: 6,
  estimated_duration: 20, is_active: true, created_by: 'operator', created_at: '2026-09-25T10:00:00Z',
  updated_at: '2026-09-25T10:00:00Z', next_run: '2026-09-27T10:00:00Z', prerequisites: [], notification_contacts: [],
  recovery_required: index === 0,
}));

async function operations(page: Page, local = true) {
  const writes: string[] = [];
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: {
    user_id: 'viewer-admin', username: 'operator', role: 'admin', session_is_local: local, session: { is_local: local },
  } } }));
  await page.route('**/api/scheduling/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET') {
      writes.push(`${route.request().method()} ${path}`);
      return route.fulfill({ status: 409, json: { detail: 'Schedule changed. Review the latest version.' } });
    }
    let data: unknown = [];
    if (path.endsWith('/list')) data = schedules;
    else if (path.endsWith('/status/scheduler')) data = { is_running: true };
    else if (path.endsWith('/status/queue')) data = {
      queue: { running_jobs: 1, queued_jobs: 2, running_job_details: [{ experiment_name: 'Running experiment', schedule_id: 'running' }], queued_job_details: [] },
      manual_recovery: { active: true, storage_healthy: true, safety_revision: 8, resume_required: true,
        pending_recoveries: [{ schedule_id: 'schedule-0', experiment_name: 'Experiment 01', note: 'Check robot before resuming' }] },
    };
    else if (path.endsWith('/experiments/available')) data = { experiments: [{ name: 'Experiment 02', path: 'C:\\Methods\\experiment-1.med' }] };
    else if (path.endsWith('/experiments/library')) data = { methods: [] };
    return route.fulfill({ json: { success: true, data } });
  });
  return writes;
}

for (const width of [390, 1280, 1920]) {
  test(`schedule selection keeps context and recovery visible at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const writes = await operations(page);
    await page.goto('/scheduling?section=schedules');
  await expect(page.getByRole('button', { name: 'Recovery required', exact: true })).toBeVisible();
    const queueDetails = page.getByRole('button', { name: 'Queue details', exact: true });
    await expect(queueDetails).toHaveAttribute('aria-expanded', 'false');
    await queueDetails.click();
    await expect(page.getByText('Running · Running experiment', { exact: true })).toBeVisible();
    await queueDetails.click();
    await page.getByRole('button', { name: 'Open Experiment 01', exact: true }).click();
    await expect(page.getByTestId('schedule-detail')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Delete schedule', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Archive schedule', exact: true })).toBeDisabled();
    if (width === 390) {
      await expect(page.getByTestId('schedule-collection')).not.toBeVisible();
      await page.getByRole('button', { name: 'Back to schedules', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Open Experiment 01', exact: true })).toBeFocused();
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    expect(writes).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath('schedules.png'), fullPage: true });
  });
}

test('phone schedule editor preserves a draft when closing or saving fails', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await operations(page);
  await page.goto('/scheduling?section=schedules');
  await page.getByRole('button', { name: 'Open Experiment 02', exact: true }).click();
  await page.getByRole('button', { name: 'Edit schedule', exact: true }).click();
  const editor = page.getByRole('dialog', { name: 'Edit schedule', exact: true });
  await expect(editor).toBeVisible();
  expect((await editor.boundingBox())!.width).toBe(390);
  await editor.getByLabel('Estimated duration (minutes)', { exact: true }).fill('42');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
  await expect(editor.getByLabel('Estimated duration (minutes)', { exact: true })).toHaveValue('42');
  await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
  await expect(page.getByText(/Schedule changed/).first()).toBeVisible();
  await expect(editor.getByLabel('Estimated duration (minutes)', { exact: true })).toHaveValue('42');
  await page.screenshot({ path: testInfo.outputPath('schedule-draft.png'), fullPage: true });
});

test('remote schedule inspection has no edit actions', async ({ page }) => {
  const writes = await operations(page, false);
  await page.goto('/scheduling?section=schedules');
  await page.getByRole('button', { name: 'Open Experiment 02', exact: true }).click();
  await expect(page.getByTestId('schedule-detail')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Edit schedule', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Create schedule', exact: true })).toHaveCount(0);
  expect(writes).toEqual([]);
});

test('phone archive opens files with readable rows and returns to folders', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await operations(page);
  const name = 'a-long-recording-name-that-must-remain-readable-without-overlapping-controls.mp4';
  await page.route('**/api/camera/recordings?**', route => route.fulfill({ json: { data: { experiment_folders: [{
    folder_name: 'Experiment recordings', video_count: 2, total_size_bytes: 2048, creation_time: '2026-09-25T10:00:00Z',
    videos: [0, 1].map(index => ({ filename: `${index}-${name}`, timestamp: '2026-09-25T10:00:00Z', size_bytes: 1024 })),
  }] } } }));
  await page.goto('/camera?section=archive');
  await page.getByRole('button', { name: /Open folder Experiment recordings/ }).click();
  await expect(page.getByRole('button', { name: 'Back to folders', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /Download 0-/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  await page.screenshot({ path: testInfo.outputPath('archive-files.png'), fullPage: true });
  await page.getByRole('button', { name: 'Back to folders', exact: true }).click();
  await expect(page.getByRole('button', { name: /Open folder Experiment recordings/ })).toBeFocused();
});
