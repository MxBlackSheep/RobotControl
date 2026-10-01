import { expect, test, type Page } from '@playwright/test';

/** Failure scenarios written before the camera implementation:
 * - Fit crops or distorts 4:3, widescreen or portrait images on desktop/phone.
 * - Expanding renders two frame subscribers or reconnects capture/recording.
 * - Fit width (formerly Fill, which cropped up to 40% of the frame) hides any part of the
 *   frame or ignores the expanded dialog's size; zoom crops without a visible warning;
 *   zoom/pan can lose the image; a smaller frame resets the viewer's sizing choice.
 * - Source dimensions change but the previous zoom/pan remains applied.
 * - Disconnect closes the inspection surface; stale images look live.
 * - Collapsing controls stops health polling or hides recording/errors.
 * - Small screens overflow, touch controls shrink, or keyboard focus is lost.
 * - An expired access token makes status polls and live-view start fail with 401 forever
 *   instead of renewing the sign-in once (a lab screen left open overnight).
 * Fixture contract: POST /__e2e/camera configures dimensions, send_frames,
 * disconnect and generation; only the isolated fixture handles these requests.
 */
test.beforeEach(async ({ page, request }) => {
  await request.post('/__e2e/camera', { data: { width: 640, height: 480, send_frames: true, disconnect: false, generation: 'g1' } });
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
});

/** Pixels of the image hidden by its stage, and the stage width. */
const wholeFrame = (page: Page) => page.getByAltText('Live camera stream').evaluate((image: HTMLImageElement) => {
  const r = image.getBoundingClientRect(), s = image.closest('[data-testid="camera-stage"]')!.getBoundingClientRect();
  return { clipped: Math.round(Math.max(0, s.top - r.top) + Math.max(0, r.bottom - s.bottom) + Math.max(0, s.left - r.left) + Math.max(0, r.right - s.right)),
    width: Math.round(s.width) };
});

async function openLiveView(page: Page) {
  await page.goto('/camera?section=live');
  await page.getByRole('button', { name: 'Start my live view', exact: true }).click();
  await expect(page.getByAltText('Live camera stream')).toBeVisible();
  await expect.poll(() => page.getByAltText('Live camera stream').evaluate((node: HTMLImageElement) => node.naturalWidth)).toBeGreaterThan(0);
  await expect(page.getByText('Live view receiving frames', { exact: true })).toBeVisible();
}

for (const viewport of [{ width: 1920, height: 1080 }, { width: 320, height: 568 }]) {
  for (const frame of [{ width: 640, height: 480 }, { width: 480, height: 800 }]) {
    test(`Fit preserves ${frame.width}x${frame.height} at ${viewport.width}px`, async ({ page, request }, testInfo) => {
      await page.setViewportSize(viewport);
      await request.post('/__e2e/camera', { data: frame });
      await openLiveView(page);
      const geometry = await page.getByAltText('Live camera stream').evaluate((image: HTMLImageElement) => {
        const rect = image.getBoundingClientRect();
        const surface = image.closest('[data-testid="camera-stage"]')!.getBoundingClientRect();
        return { width: rect.width, height: rect.height, naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight,
          inside: rect.left >= surface.left - 1 && rect.right <= surface.right + 1 && rect.top >= surface.top - 1 && rect.bottom <= surface.bottom + 1,
          pageOverflow: document.documentElement.scrollWidth > window.innerWidth + 1 };
      });
      expect(geometry.naturalWidth).toBe(frame.width);
      expect(geometry.width / geometry.height).toBeCloseTo(frame.width / frame.height, 2);
      expect(geometry.inside).toBe(true);
      expect(geometry.pageOverflow).toBe(false);
      await expect(page.getByText('Cropped view', { exact: true })).toHaveCount(0);
      await page.screenshot({ path: testInfo.outputPath('fit.png'), fullPage: true });
      await testInfo.attach('geometry', { body: JSON.stringify(geometry, null, 2), contentType: 'application/json' });
    });
  }
}

test('inspection actions preserve the session and keep crop/zoom explicit', async ({ page, request }, testInfo) => {
  const writes: string[] = [];
  page.on('request', req => { if (req.method() !== 'GET' && req.url().includes('/api/camera/')) writes.push(`${req.method()} ${new URL(req.url()).pathname}`); });
  await openLiveView(page);
  await page.getByRole('button', { name: 'Expand live view', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Live camera inspection' })).toBeVisible();
  await expect(page.getByAltText('Live camera stream')).toHaveCount(1);
  // Fit width shows the whole frame at the dialog's width and scrolls; only zoom crops.
  await page.getByRole('button', { name: 'Fit width', exact: true }).click();
  await expect(page.getByText('Cropped view', { exact: true })).toHaveCount(0);
  expect(await wholeFrame(page)).toEqual({ clipped: 0, width: page.viewportSize()!.width });
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await expect(page.getByText('Cropped view', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Reset view', exact: true }).click();
  // A smaller frame (the server lowers resolution under load) keeps the viewer's choice.
  await request.post('/__e2e/camera', { data: { width: 320, height: 240 } });
  await expect.poll(() => page.getByAltText('Live camera stream').evaluate((node: HTMLImageElement) => node.naturalWidth)).toBe(320);
  await expect(page.getByRole('button', { name: 'Fit width', exact: true })).toHaveAttribute('aria-pressed', 'true');
  expect(await wholeFrame(page)).toEqual({ clipped: 0, width: page.viewportSize()!.width });
  await request.post('/__e2e/camera', { data: { width: 640, height: 480 } });
  await expect.poll(() => page.getByAltText('Live camera stream').evaluate((node: HTMLImageElement) => node.naturalWidth)).toBe(640);
  await page.getByRole('button', { name: 'Fit entire frame', exact: true }).click();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.getByRole('button', { name: 'Pan up', exact: true }).click();
  await page.getByTestId('camera-stage').focus();
  await page.keyboard.press('ArrowDown');
  await page.getByRole('button', { name: 'Reset view', exact: true }).click();
  await expect(page.getByText('1×', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await request.post('/__e2e/camera', { data: { width: 480, height: 800 } });
  await expect.poll(() => page.getByAltText('Live camera stream').evaluate((node: HTMLImageElement) => node.naturalWidth)).toBe(480);
  await expect(page.getByText('1×', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  // Hold the source-change gap open: disabling the focused zoom control must
  // keep keyboard focus inside the dialog, including before new frames arrive.
  await request.post('/__e2e/camera', { data: { generation: 'g2', send_frames: false } });
  await expect(page.getByText('1×', { exact: true })).toBeVisible({ timeout: 8000 });
  await expect(page.getByRole('button', { name: 'Zoom in', exact: true })).toBeDisabled();
  await expect(page.getByTestId('camera-stage')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Expand live view', exact: true })).toBeFocused();
  expect(writes).toEqual(['POST /api/camera/streaming/session']);
  await testInfo.attach('camera-mutations', { body: JSON.stringify(writes, null, 2), contentType: 'application/json' });
  await page.screenshot({ path: testInfo.outputPath('inspection.png'), fullPage: true });
});

test('stale and disconnected views remain recoverable in the expanded reader', async ({ page, request }, testInfo) => {
  await openLiveView(page);
  await page.getByRole('button', { name: 'Expand live view', exact: true }).click();
  await request.post('/__e2e/camera', { data: { send_frames: false } });
  await expect(page.getByText(/Stale image/)).toBeVisible({ timeout: 15000 });
  await request.post('/__e2e/camera', { data: { disconnect: true } });
  await expect(page.getByRole('dialog', { name: 'Live camera inspection' })).toBeVisible();
  await expect(page.getByText('Live view disconnected', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reconnect live view', exact: true })).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath('disconnected.png'), fullPage: true });
});

test('collapsed controls keep polling and phone controls remain touchable', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let healthRequests = 0;
  page.on('request', req => { if (req.url().includes('/api/camera/control-status')) healthRequests++; });
  await openLiveView(page);
  await expect(page.getByText('Camera: Connected · Recording: Recording', { exact: true })).toBeVisible();
  const before = healthRequests;
  await expect.poll(() => healthRequests, { timeout: 8000 }).toBeGreaterThan(before);
  await page.getByRole('button', { name: 'Camera and recording settings', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Selected camera' })).toBeVisible();
  await page.getByRole('button', { name: 'Camera and recording settings', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Selected camera' })).not.toBeVisible();
  const targets = await page.getByTestId('camera-toolbar').getByRole('button').evaluateAll(buttons => buttons.map(button => ({ label: button.getAttribute('aria-label') ?? button.textContent, height: button.getBoundingClientRect().height })));
  for (const target of targets) expect(target.height, target.label ?? 'camera control').toBeGreaterThanOrEqual(44);
  await testInfo.attach('touch-targets', { body: JSON.stringify(targets, null, 2), contentType: 'application/json' });
  await page.screenshot({ path: testInfo.outputPath('phone-controls.png'), fullPage: true });
});

test('an expired sign-in is renewed and live view still starts', async ({ page }, testInfo) => {
  await page.addInitScript(() => localStorage.setItem('refresh_token', 'saved-refresh'));
  let expired = false, refreshes = 0;
  const rejected: string[] = [];
  await page.route('**/api/auth/refresh', route => {
    refreshes++;
    return route.fulfill({ json: { success: true, data: { access_token: 'e2e-admin' } } });
  });
  await page.route('**/api/camera/**', route => {
    if (expired && route.request().headers().authorization === 'Bearer viewer-admin') {
      rejected.push(new URL(route.request().url()).pathname);
      return route.fulfill({ status: 401, json: { detail: 'Expired' } });
    }
    return route.fallback();
  });
  await page.goto('/camera?section=live');
  await expect(page.getByText(/^Camera: Connected/).first()).toBeVisible();
  expired = true;
  await expect.poll(() => rejected.length, { timeout: 15_000 }).toBeGreaterThan(0);
  await expect.poll(() => page.evaluate(() => localStorage.getItem('access_token'))).toBe('e2e-admin');
  await page.getByRole('button', { name: 'Start my live view', exact: true }).click();
  await expect(page.getByAltText('Live camera stream')).toBeVisible();
  await expect(page.getByText(/\(401\)|Failed to create streaming session/)).toHaveCount(0);
  expect(refreshes).toBe(1);
  await page.screenshot({ path: testInfo.outputPath('renewed-sign-in.png') });
});
