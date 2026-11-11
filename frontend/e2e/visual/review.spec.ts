import { Page, test } from '@playwright/test';
import path from 'node:path';
import { ago, sampleData } from './sampleData';

/**
 * Screenshot review, not a behaviour check. What a reviewer looks for in the saved images:
 * - panel edges off the 12-column grid, panels in one row with different heights;
 * - headers, rows or controls off the 40/40/36px rhythm; rows that wrap to two lines;
 * - dark mode text or chips below comfortable contrast; light-only colours left in dark;
 * - phone (390px, 375px) overflow, clipped labels or controls below 44px.
 * Sample data is fixed so before/after images are comparable; the clock is frozen at 14:30.
 * Phones use the iPhone heights (844, 667) and, like the owner's phone, a remote (tunnel) session;
 * desktops a local one. VISUAL_SESSION=remote or =local forces either for every width.
 * Some routes also save an opened item (a table, a log folder, a folder of recordings) as
 * `<route>-open`, with the owner's volumes: 32-row ActivePlateView, 2,000 log files.
 * The window never scrolls (only main does), so each image is one screen; `-end` shows the
 * bottom of main when it holds more than a screen.
 */
// Run from frontend/, like the configs' own paths.
const output = path.resolve('../test-output/visual/latest');
const list = (name: string, fallback: string[]) => (process.env[name] ? process.env[name]!.split(',') : fallback);

const routes = list('VISUAL_ROUTES', ['/', '/scheduling', '/scheduling?section=archived', '/scheduling?section=history', '/scheduling?section=recovery', '/labware', '/camera',
  '/camera?section=archive', '/database', '/database?section=procedures', '/database?section=retrieval', '/logfile', '/maintenance', '/system-status', '/admin', '/more', '/account', '/held']);
const widths = list('VISUAL_WIDTHS', ['1440', '1280', '390', '375']).map(Number);
const modes = list('VISUAL_MODES', ['light', 'dark']);
const localSession = (width: number) => process.env.VISUAL_SESSION ? process.env.VISUAL_SESSION !== 'remote' : width >= 900;
const heights: Record<number, number> = { 390: 844, 375: 667, 320: 568 };
const recordings = Array.from({ length: 15 }, (_, index) => ({ filename: `DailyTipWash_${String(index + 1).padStart(3, '0')}.mp4`,
  timestamp: '2026-09-30T13:00:00', size_bytes: 8.1e7 + index * 1e6, duration: 300 }));
const opened: Record<string, (page: Page) => Promise<void>> = {
  '/database': page => page.getByRole('button', { name: /dbo\.ActivePlateView/ }).click(),
  '/database?section=procedures': page => page.getByRole('button', { name: /InspectSamples/ }).click(),
  '/logfile': async page => {
    await page.getByRole('button', { name: /rotated/ }).click();
    await page.getByRole('button', { name: /robotcontrol_1999\.log/ }).waitFor();
  },
  '/camera?section=archive': async page => {
    await page.route('**/api/camera/recordings', route => route.fulfill({ json: { data: { experiment_folders: [
      { folder_name: '2026-09-30_DailyTipWash', video_count: recordings.length, total_size_bytes: 3.2e9, creation_time: ago(42), videos: recordings }] } } }));
    await page.reload();
    await page.getByRole('button', { name: /Open folder 2026-09-30_DailyTipWash/ }).click();
  },
};

/** The screen, and the end of the scroll area when there is more below. */
async function capture(page: Page, name: string) {
  await page.screenshot({ path: `${name}.png` });
  const main = page.locator('main');
  if (!await main.evaluate(element => element.scrollHeight > element.clientHeight + 1)) return;
  await main.evaluate(element => element.scrollTo(0, element.scrollHeight));
  await page.screenshot({ path: `${name}-end.png` });
  await main.evaluate(element => element.scrollTo(0, 0));
}

for (const mode of modes) {
  for (const width of widths) {
    test(`${mode} ${width}`, async ({ page }) => {
      await sampleData(page, mode, localSession(width));
      await page.setViewportSize({ width, height: heights[width] ?? 900 });
      const settle = async () => { await page.clock.runFor(1500); await page.waitForTimeout(300); };
      for (const route of routes) {
        const name = path.join(output, `${mode}-${width}${route.replace(/[^a-z0-9]/gi, '-')}`);
        await page.goto(route);
        await page.locator('main h1').waitFor();
        await settle();
        await capture(page, name);
        if (!opened[route]) continue;
        await opened[route](page);
        await settle();
        await capture(page, `${name}-open`);
      }
    });
  }
}
