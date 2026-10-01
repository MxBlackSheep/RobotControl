import { Page, test } from '@playwright/test';
import path from 'node:path';

/**
 * Screenshot review, not a behaviour check. What a reviewer looks for in the saved images:
 * - panel edges off the 12-column grid, panels in one row with different heights;
 * - headers, rows or controls off the 40/40/36px rhythm; rows that wrap to two lines;
 * - dark mode text or chips below comfortable contrast; light-only colours left in dark;
 * - phone (390px) overflow, clipped labels or controls below 44px.
 * Sample data is fixed so before/after images are comparable; the clock is frozen at 14:30.
 */
// Run from frontend/, like the configs' own paths.
const output = path.resolve('../test-output/visual/latest');
const now = new Date('2026-09-30T14:30:00');
const local = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
const ago = (minutes: number) => local(new Date(now.getTime() - minutes * 60000));
const ahead = (minutes: number) => local(new Date(now.getTime() + minutes * 60000));
const list = (name: string, fallback: string[]) => (process.env[name] ? process.env[name]!.split(',') : fallback);

const routes = list('VISUAL_ROUTES', ['/', '/scheduling', '/scheduling?section=history', '/scheduling?section=recovery', '/labware', '/camera',
  '/camera?section=archive', '/database', '/logfile', '/maintenance', '/system-status', '/admin']);
const widths = list('VISUAL_WIDTHS', ['1440', '1280', '390']).map(Number);
const modes = list('VISUAL_MODES', ['light', 'dark']);

async function sampleData(page: Page, mode: string) {
  await page.clock.install({ time: now });
  await page.addInitScript(value => { localStorage.setItem('access_token', 'viewer-admin'); localStorage.setItem('robotcontrol-appearance', value); }, mode);
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'operator', role: 'admin', session_is_local: true, session: { is_local: true } } } }));
  const manual = { active: true, storage_healthy: true, safety_revision: 4, resume_required: true,
    pending_recoveries: [{ schedule_id: 'feed2', experiment_name: 'Cell feeding · stack 2', triggered_at: ago(208), note: 'No log activity for 3 min.' }] };
  await page.route('**/api/scheduling/status/queue', route => route.fulfill({ json: { success: true, data: {
    queue: { queued_jobs: 1, running_job_details: [{ schedule_id: 'wash', experiment_name: 'Daily tip wash', experiment_path: 'C:\\Methods\\Wash\\DailyTipWash.hsl', estimated_duration: 60,
      monitoring: { state: 'monitoring', launched_at: ago(42), inactivity_seconds: 18, threshold_minutes: 3 } }] },
    hamilton: { is_running: true }, manual_recovery: manual } } }));
  await page.route('**/api/scheduling/status/scheduler', route => route.fulfill({ json: { success: true, data: { is_running: true, manual_recovery: manual } } }));
  const schedule = (id: string, name: string, type: string, next: number, extra: object = {}) => ({ schedule_id: id, experiment_name: name,
    experiment_path: `C:\\Methods\\${name.replace(/[^A-Za-z]/g, '')}.hsl`, schedule_type: type, interval_hours: type === 'interval' ? 12 : null,
    estimated_duration: type === 'daily' ? 60 : 45, log_inactivity_threshold_minutes: 3, created_by: 'admin', created_at: '2026-09-01T10:00:00', updated_at: '2026-09-01T10:00:00',
    is_active: true, archived: false, timeout_config: { timeout_minutes: null, action: 'continue' }, prerequisites: [], notification_contacts: [], recovery_required: false,
    next_run: ahead(next), last_run: ago(20 * 60), ...extra });
  await page.route('**/api/scheduling/list?*', route => route.fulfill({ json: { success: true, data: new URL(route.request().url()).searchParams.get('archived_only') === 'true' ? [] : [
    schedule('deck', 'Weekly deck cleanup', 'weekly', 60), schedule('qc', 'Plate reader QC', 'once', 90, { is_active: false }),
    schedule('feed1', 'Cell feeding · stack 1', 'interval', 330), schedule('feed2', 'Cell feeding · stack 2', 'interval', 330, { recovery_required: true }),
    schedule('wash', 'Daily tip wash', 'daily', 23 * 60 + 15),
    // Next year: the longest dayTime label ("13 Jan 2027 …"), which Up next must not clip.
    schedule('calibration', 'Pipette calibration', 'once', 105 * 24 * 60 - 330)] } }));
  const run = (id: string, name: string, status: string, started: number, minutes: number) => ({ execution_id: id, schedule_id: id, experiment_name: name, status, start_time: ago(started), duration_minutes: minutes });
  await page.route('**/api/scheduling/executions/history?*', route => route.fulfill({ json: { success: true, data: [
    run('e1', 'Cell feeding · stack 2', 'recovery_required', 255, 47), run('e2', 'Cell feeding · stack 1', 'completed', 390, 44),
    run('e3', 'Daily tip wash', 'completed', 25 * 60 + 45, 58), run('e4', 'Plate reader QC', 'failed', 46 * 60, 4), run('e5', 'Weekly deck cleanup', 'completed', 7 * 24 * 60, 31)] } }));
  await page.route('**/api/monitoring/system-health', route => route.fulfill({ json: { data: { sampled_at: now.toISOString(),
    system: { cpu_percent: 23, memory_percent: 61, disk_percent: 48, memory_used_gb: 9.8, memory_total_gb: 16, disk_used_gb: 240, disk_total_gb: 500 },
    database: { is_connected: true, mode: 'primary', database_name: 'EvoYeast', server_name: 'LAB-PC\\HAMILTON' } } } }));
  // Ended present: the widest Latest experiment row (Started, Ended and Duration).
  await page.route('**/api/experiments/latest', route => route.fulfill({ json: { success: true, data: { run_guid: '7f3c2a91-5d4e-4b8a-9c1f-2e6d8a0b4c71',
    method_name: 'C:\\Methods\\CellCulture\\CellFeedingStack2_MediaExchange.hsl', start_time: ago(255), end_time: ago(208), run_state: 128 } } }));
  await page.route('**/api/monitoring/databases', route => route.fulfill({ json: { data: { checked_at: now.toISOString(),
    built_in: { id: 'built-in', name: 'Built-in Hamilton connection', access: 'built-in', server: 'LAB-PC\\HAMILTON', database: 'EvoYeast',
      uses: ['Hamilton run records', 'Labware', 'Backup and restore'], state: 'connected' },
    connections: [
      { id: 'reader', name: 'EvoYeast reader', access: 'read', server: 'LAB-PC\\HAMILTON', database: 'EvoYeast',
        uses: ['Tables and Stored procedures', 'Culture history', 'Select EvoYeast experiment'], state: 'connected' },
      { id: 'writer', name: 'EvoYeast writer', access: 'operation', server: 'LAB-PC\\HAMILTON', database: 'EvoYeast',
        uses: ['Delete Experiment (changes)', 'Select EvoYeast experiment (changes)', 'Before-run step of 2 active schedules'], state: 'connected' },
      { id: 'archive', name: 'Archive reader', access: 'read', server: 'ARCHIVE-SQL', database: 'EvoYeastArchive', uses: [], state: 'failed',
        message: "Cannot use connection 'Archive reader'. Check the connection settings, account permissions and query." }] } } }));
  await page.route('**/api/monitoring/experiments', route => route.fulfill({ json: { data: [] } }));
  await page.route('**/api/camera/streaming/status', route => route.fulfill({ json: { data: { status: { enabled: true, active_session_count: 1, max_sessions: 4 } } } }));
  await page.route('**/api/camera/recordings?**', route => route.fulfill({ json: { data: { experiment_folders: [
    { folder_name: '2026-09-30_DailyTipWash', video_count: 3, total_size_bytes: 3.2e9, creation_time: ago(42) },
    { folder_name: '2026-09-30_CellFeeding2', video_count: 1, total_size_bytes: 9e8, creation_time: ago(255) },
    { folder_name: '2026-09-29_DailyTipWash', video_count: 3, total_size_bytes: 3e9, creation_time: ago(25 * 60) }] } } }));
  await page.route('**/api/admin/users', route => route.fulfill({ json: [
    { username: 'admin', email: 'lab-admin@example.org', role: 'admin', created_at: '2026-01-10T09:00:00', last_login: ago(180) },
    { username: 'operator.day', email: 'day@example.org', role: 'user', created_at: '2026-02-01T09:00:00', last_login: ago(22 * 60) },
    { username: 'viewer', email: 'viewer@example.org', role: 'viewer', created_at: '2026-03-01T09:00:00', last_login: null }] }));
  await page.route('**/api/maintenance/hxrun', route => route.fulfill({ json: { enabled: false, reason: '', updated_by: 'admin', updated_at: ago(28 * 60 + 30), permissions: { can_edit: true } } }));
  const statuses = ['clean', 'empty', 'dirty', 'rinsed', 'washed', 'reserved', 'unclear'];
  const left = ['VER_HT_0005', 'VER_HT_0001', 'VER_HT_0002', 'VER_HT_0006', 'VER_HT_0009'];
  const right = ['VER_HT_0003', 'VER_HT_0004', 'VER_HT_0007', 'VER_HT_0008', 'VER_HT_0010'];
  await page.route('**/api/labware/tip-tracking', route => route.fulfill({ json: { data: {
    grid: { rows: 8, cols: 12, positions_per_rack: 96 }, auto_refresh_ms: 600000, status_order: statuses,
    status_colors: { clean: '#22C55E', empty: '#CBD2DB', dirty: '#EF4444', rinsed: '#3B82F6', washed: '#A855F7', reserved: '#F59E0B', unclear: '#6B7280' },
    unknown_status: 'unclear', refreshed_at: ago(30), permissions: { role: 'admin', is_local_session: true, can_update: true },
    families: [{ family_id: 'tips1000', display_name: '1000 µL tips', left_racks: left, right_racks: right, reset_map: {},
      tips: Object.fromEntries([...left, ...right].map((rack, r) => [rack, Object.fromEntries(Array.from({ length: 96 }, (_, i) => [String(i + 1), statuses[(Math.floor(i / 8) * 3 + r * 2) % 7]]))])) },
    { family_id: 'tips300', display_name: '300 µL tips', left_racks: left, right_racks: right, reset_map: {}, tips: {} }] } } }));
}

for (const mode of modes) {
  for (const width of widths) {
    test(`${mode} ${width}`, async ({ page }) => {
      await sampleData(page, mode);
      await page.setViewportSize({ width, height: width < 600 ? 844 : 900 });
      for (const route of routes) {
        await page.goto(route);
        await page.locator('main h1').waitFor();
        await page.clock.runFor(1500);
        await page.waitForTimeout(300);
        await page.screenshot({ path: path.join(output, `${mode}-${width}${route.replace(/[^a-z0-9]/gi, '-')}.png`), fullPage: true });
      }
    });
  }
}
