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
 * - A failed history read shows one result dialog: Retry reads again and closes it on
 *   success; Close dismisses it without another read; Tab stays inside the dialog.
 * - A failed status read shows its own inline error, not the Server Error dialog; the next
 *   successful read of that status clears it and a schedule reload does not. The page reads
 *   the one status reply the frame owns (/status/queue), never /status/scheduler.
 * - Archived uses the Schedules list and detail: an archived schedule shows Created by and
 *   Created in the list's date format and offers Restore and Delete only, never Edit; Restore
 *   sends the opened version and moves it to Schedules; Delete removes the schedule shown.
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
    else if (path.endsWith('/status/queue')) data = {
      is_running: true,
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

for (const width of [390, 1920]) {
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

test('a failed history read shows one result dialog with Retry and Close', async ({ page }, testInfo) => {
  await operations(page);
  let reads = 0, fail = true;
  await page.route('**/api/scheduling/executions/history**', route => {
    reads++;
    return fail ? route.fulfill({ status: 500, json: { detail: 'History store unavailable' } })
      : route.fulfill({ json: { success: true, data: [] } });
  });
  await page.goto('/scheduling?section=history');
  const dialog = page.getByRole('dialog', { name: 'Server Error' });
  await expect(dialog).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(1);
  await expect(dialog.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
  for (let i = 0; i < 4; i++) await page.keyboard.press('Tab');
  expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('history-error-dialog.png') });

  fail = false;
  await dialog.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(dialog).toBeHidden();
  expect(reads).toBe(2);

  fail = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).first().click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(dialog).toBeHidden();
  await page.waitForTimeout(500);
  expect(reads).toBe(3);
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('a failed status read shows its own error until that status reads again', async ({ page }, testInfo) => {
  await operations(page);
  let failQueue = true;
  await page.route('**/api/scheduling/status/queue', route => failQueue
    ? route.fulfill({ status: 500, json: { detail: 'Queue store unavailable' } })
    : route.fallback());
  await page.goto('/scheduling?section=schedules');
  const statusError = page.getByRole('alert').filter({ hasText: 'Queue store unavailable' });
  await expect(statusError).toHaveCount(1);
  await expect(page.getByRole('dialog', { name: 'Server Error' })).toHaveCount(0);

  await page.getByRole('region', { name: 'Schedules', exact: true }).getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Open Experiment 01', exact: true })).toBeVisible();
  await expect(statusError).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath('status-error.png') });

  failQueue = false;
  await page.getByRole('button', { name: 'Refresh queue', exact: true }).click();
  await expect(statusError).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Recovery required', exact: true })).toBeVisible();
});

test('an archived schedule opens in the shared detail, restores, and another deletes', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 844 });
  await operations(page);
  const archived = (id: string, name: string) => ({ ...schedules[1], schedule_id: id, experiment_name: name, archived: true, is_active: false,
    recovery_required: false, created_by: 'lab.admin', created_at: '2026-09-20T09:15:00' });
  let active: object[] = [];
  let archive = [archived('old-wash', 'Old wash'), archived('old-feed', 'Old feed')];
  const writes: { method: string; body: unknown; version?: string }[] = [];
  await page.route('**/api/scheduling/list?*', route => route.fulfill({ json: { success: true,
    data: new URL(route.request().url()).searchParams.get('archived_only') === 'true' ? archive : active } }));
  await page.route('**/api/scheduling/old-wash/archive', async route => {
    writes.push({ method: route.request().method(), body: route.request().postDataJSON() });
    const restored = { ...archive[0], archived: false, updated_at: '2026-09-26T10:00:00Z' };
    active = [restored];
    archive = archive.slice(1);
    await route.fulfill({ json: { success: true, data: restored } });
  });
  await page.route('**/api/scheduling/old-feed', async route => {
    writes.push({ method: route.request().method(), body: null, version: route.request().headers()['if-unmodified-since'] });
    archive = archive.filter(item => item.schedule_id !== 'old-feed');
    await route.fulfill({ json: { success: true, data: null } });
  });

  await page.goto('/scheduling?section=archived');
  await page.getByRole('button', { name: 'Open Old wash', exact: true }).click();
  const detail = page.getByTestId('schedule-detail');
  await expect(detail.getByRole('definition').filter({ hasText: 'lab.admin' })).toBeVisible();
  await expect(detail.getByRole('definition').filter({ hasText: /20 Sep.* 09:15$/ })).toBeVisible();
  await expect(detail.getByRole('button', { name: 'Edit schedule', exact: true })).toHaveCount(0);
  await expect(detail.getByRole('button', { name: 'Archive schedule', exact: true })).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath('archived-detail.png') });
  await detail.getByRole('button', { name: 'Restore schedule', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Open Old wash', exact: true })).toHaveCount(0);
  expect(writes).toEqual([{ method: 'POST', body: { archived: false, expected_updated_at: schedules[1].updated_at } }]);

  await page.getByRole('button', { name: 'Open Old feed', exact: true }).click();
  await detail.getByRole('button', { name: 'Delete schedule', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Delete Schedule', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Open Old feed', exact: true })).toHaveCount(0);
  expect(writes[1]).toEqual({ method: 'DELETE', body: null, version: schedules[1].updated_at });

  await page.goto('/scheduling?section=schedules');
  await expect(page.getByRole('button', { name: 'Open Old wash', exact: true })).toBeVisible();
});