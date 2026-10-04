import { writeFileSync } from 'node:fs';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

/** Failure scenarios written before the camera implementation:
 * - Fit crops or distorts 4:3, widescreen or portrait images on desktop/phone.
 * - Expanding renders two frame subscribers or reconnects capture/recording.
 * - Fit width (formerly Fill, which cropped up to 40% of the frame) hides any part of the
 *   frame or ignores the expanded dialog's size; zoom crops without a visible warning;
 *   zoom/pan can lose the image; a smaller frame resets the viewer's sizing choice.
 * - Source dimensions change but the previous zoom/pan remains applied.
 * - Disconnect closes the inspection surface; stale images look live; a dropped stream
 *   clears the image or stays stopped instead of reconnecting by itself; Stop is undone
 *   by an automatic reconnect.
 * - Frames are not acknowledged (the server then sends at most two and ends a silent
 *   viewer after 15 s); a hidden tab keeps receiving frames or does not resume.
 * - H.264 frames are not decoded onto the canvas (blank or wrong picture), or a new frame
 *   size is not followed.
 * - A browser without WebCodecs H.264, or a plain-HTTP page, starts a session, shows a blank
 *   canvas or falls back to JPEG instead of its message (live view is H.264 only).
 * - Collapsing controls stops health polling or hides recording/errors.
 * - Small screens overflow, touch controls shrink, or keyboard focus is lost.
 * - An expired access token makes status polls and live-view start fail with 401 forever
 *   instead of renewing the sign-in once (a lab screen left open overnight).
 * - Playout buffer (useLiveViewSocket.ts): frames that arrive in bursts are still shown in bursts
 *   instead of evenly by capture time; a frame past its slot waits anyway, or any frame waits
 *   longer than the 300 ms clamp; a VideoFrame is never closed, closed twice, or more than 8 are
 *   held; hiding the tab leaves held frames queued; held frames pin a hardware decoder's output
 *   pool (it stalls: live view freezes on GPUs the checks never see), so decoding must be software. Turned off (PLAYOUT_BUFFER), the same case
 *   fails on evenness with the numbers from before the buffer (frames shown as decoded).
 * Fixture contract: POST /__e2e/camera configures dimensions, send_frames,
 * disconnect, generation, interval (seconds between captured frames) and burst (frames sent
 * together); only the isolated fixture handles these requests. Its frames are
 * real H.264 from the bundled ffmpeg (red, lime, yellow, magenta corner squares on blue).
 */
test.beforeEach(async ({ page, request }) => {
  await request.post('/__e2e/camera', { data: { width: 640, height: 480, send_frames: true, disconnect: false, generation: 'g1',
    interval: .2, burst: 1 } });
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
});

const liveImage = (page: Page) => page.getByRole('img', { name: 'Live camera stream', exact: true });
const frameWidth = (page: Page) => liveImage(page).evaluate((canvas: HTMLCanvasElement) => canvas.width);

/** Decoded colours at the frame's corners: proves H.264 reached the canvas, not just an element. */
const cornerColours = (page: Page) => liveImage(page).evaluate((canvas: HTMLCanvasElement) => {
  const context = canvas.getContext('2d')!;
  const name = ([r, g, b]: Uint8ClampedArray) => r > 180 && g < 90 && b < 90 ? 'red' : r < 90 && g > 180 && b < 90 ? 'lime'
    : r > 180 && g > 180 && b < 90 ? 'yellow' : r > 180 && g < 90 && b > 180 ? 'magenta' : `rgb(${r},${g},${b})`;
  return [[20, 20], [canvas.width - 20, 20], [20, canvas.height - 20], [canvas.width - 20, canvas.height - 20]]
    .map(([x, y]) => name(context.getImageData(x, y, 1, 1).data));
});

/** Pixels of the image hidden by its stage, and the stage width. */
const wholeFrame = (page: Page) => liveImage(page).evaluate((image: HTMLCanvasElement) => {
  const r = image.getBoundingClientRect(), s = image.closest('[data-testid="camera-stage"]')!.getBoundingClientRect();
  return { clipped: Math.round(Math.max(0, s.top - r.top) + Math.max(0, r.bottom - s.bottom) + Math.max(0, s.left - r.left) + Math.max(0, r.right - s.right)),
    width: Math.round(s.width) };
});

async function openLiveView(page: Page) {
  await page.goto('/camera?section=live');
  await page.getByRole('button', { name: 'Start my live view', exact: true }).click();
  await expect(liveImage(page)).toBeVisible();
  await expect.poll(() => cornerColours(page)).toEqual(['red', 'lime', 'yellow', 'magenta']);
  await expect(page.getByText('Live view receiving frames', { exact: true })).toBeVisible();
}

for (const viewport of [{ width: 1920, height: 1080 }, { width: 320, height: 568 }]) {
  for (const frame of [{ width: 640, height: 480 }, { width: 480, height: 800 }]) {
    test(`Fit preserves ${frame.width}x${frame.height} at ${viewport.width}px`, async ({ page, request }, testInfo) => {
      await page.setViewportSize(viewport);
      await request.post('/__e2e/camera', { data: frame });
      await openLiveView(page);
      const geometry = await liveImage(page).evaluate((image: HTMLCanvasElement) => {
        const rect = image.getBoundingClientRect();
        const surface = image.closest('[data-testid="camera-stage"]')!.getBoundingClientRect();
        return { width: rect.width, height: rect.height, naturalWidth: image.width, naturalHeight: image.height,
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
  await expect(liveImage(page)).toHaveCount(1);
  // Fit width shows the whole frame at the dialog's width and scrolls; only zoom crops.
  await page.getByRole('button', { name: 'Fit width', exact: true }).click();
  await expect(page.getByText('Cropped view', { exact: true })).toHaveCount(0);
  expect(await wholeFrame(page)).toEqual({ clipped: 0, width: page.viewportSize()!.width });
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await expect(page.getByText('Cropped view', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Reset view', exact: true }).click();
  // A different frame size (another camera) restarts decoding at its keyframe and keeps the viewer's choice.
  await request.post('/__e2e/camera', { data: { width: 320, height: 240 } });
  await expect.poll(() => frameWidth(page)).toBe(320);
  await expect.poll(() => cornerColours(page)).toEqual(['red', 'lime', 'yellow', 'magenta']);
  await expect(page.getByRole('button', { name: 'Fit width', exact: true })).toHaveAttribute('aria-pressed', 'true');
  expect(await wholeFrame(page)).toEqual({ clipped: 0, width: page.viewportSize()!.width });
  await request.post('/__e2e/camera', { data: { width: 640, height: 480 } });
  await expect.poll(() => frameWidth(page)).toBe(640);
  await page.getByRole('button', { name: 'Fit entire frame', exact: true }).click();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.getByRole('button', { name: 'Pan up', exact: true }).click();
  await page.getByTestId('camera-stage').focus();
  await page.keyboard.press('ArrowDown');
  await page.getByRole('button', { name: 'Reset view', exact: true }).click();
  await expect(page.getByText('1×', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await request.post('/__e2e/camera', { data: { width: 480, height: 800 } });
  await expect.poll(() => frameWidth(page)).toBe(480);
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

const fixture = async (request: APIRequestContext) => (await request.post('/__e2e/camera', { data: {} })).json();

test('a dropped live view keeps the last image as stale, reconnects by itself and resumes', async ({ page, request }, testInfo) => {
  await openLiveView(page);
  await page.getByRole('button', { name: 'Expand live view', exact: true }).click();
  const sessions = (await fixture(request)).sessions;
  await request.post('/__e2e/camera', { data: { send_frames: false } });
  await expect(page.getByText(/Stale image/)).toBeVisible({ timeout: 15000 });
  await request.post('/__e2e/camera', { data: { disconnect: true } });
  await expect(page.getByRole('dialog', { name: 'Live camera inspection' })).toBeVisible();
  // The last image stays (marked stale) and a new session is created without a click.
  await expect(liveImage(page)).toBeVisible();
  expect(await cornerColours(page)).toEqual(['red', 'lime', 'yellow', 'magenta']);
  await expect.poll(async () => (await fixture(request)).sessions, { timeout: 10_000 }).toBeGreaterThan(sessions);
  await expect(page.getByText('My view: connected', { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('reconnected-stale.png'), fullPage: true });
  await request.post('/__e2e/camera', { data: { send_frames: true } });
  await expect(page.getByText('Live view receiving frames', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reconnect live view', exact: true })).toBeEnabled();
  // After Stop, a closed stream is not reconnected.
  await page.getByRole('button', { name: 'Stop my live view', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Start my live view', exact: true })).toBeVisible();
  const stopped = (await fixture(request)).sessions;
  await page.waitForTimeout(3000);
  expect((await fixture(request)).sessions).toBe(stopped);
});

test('frames are acknowledged and a hidden tab pauses the stream', async ({ page, request }) => {
  await request.post('/__e2e/camera', { data: { controls: [] } });
  await openLiveView(page);
  const controls = async () => (await fixture(request)).controls as string[];
  await expect.poll(async () => (await controls()).filter(type => type === 'ack').length).toBeGreaterThan(1);
  const setVisibility = (state: string) => page.evaluate(value => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => value });
    document.dispatchEvent(new Event('visibilitychange'));
  }, state);
  await setVisibility('hidden');
  await expect.poll(controls).toContain('pause');
  await setVisibility('visible');
  await expect.poll(controls).toContain('resume');
  // Decoding resumes at the next keyframe: new frames are acknowledged again.
  const acknowledged = (await controls()).filter(type => type === 'ack').length;
  await expect.poll(async () => (await controls()).filter(type => type === 'ack').length).toBeGreaterThan(acknowledged);
  await expect(page.getByText('Live view receiving frames', { exact: true })).toBeVisible();
});

/** Through platform APIs only: when each sequence arrived (chunk created), was decoded and was
 * drawn, decoder outputs, and first and repeated VideoFrame closes (open = outputs − first closes). */
const instrumentFrames = () => {
  const target = window as unknown as Record<string, unknown>;
  const log = { received: {} as Record<number, number>, decoded: {} as Record<number, number>, draws: [] as [number, number][],
    opened: 0, closed: 0, closedTwice: 0, acceleration: [] as string[] };
  target.__liveView = log;
  const Chunk = EncodedVideoChunk;
  target.EncodedVideoChunk = class extends Chunk {
    constructor(init: EncodedVideoChunkInit) { super(init); log.received[init.timestamp] = performance.now(); }
  };
  const Decoder = VideoDecoder;
  target.VideoDecoder = class extends Decoder {
    constructor(init: VideoDecoderInit) { super({ ...init, output: frame => { log.opened++; log.decoded[frame.timestamp] = performance.now(); init.output(frame); } }); }
    configure(config: VideoDecoderConfig) { log.acceleration.push(config.hardwareAcceleration ?? 'no-preference'); super.configure(config); }
  };
  const closed = new WeakSet<VideoFrame>();
  const close = VideoFrame.prototype.close;
  VideoFrame.prototype.close = function (this: VideoFrame) {
    if (closed.has(this)) log.closedTwice++;
    else { closed.add(this); log.closed++; }
    close.call(this);
  };
  const draw = CanvasRenderingContext2D.prototype.drawImage as (...args: unknown[]) => void;
  CanvasRenderingContext2D.prototype.drawImage = function (this: CanvasRenderingContext2D, ...args: unknown[]) {
    if (args[0] instanceof VideoFrame) log.draws.push([args[0].timestamp, performance.now()]);
    draw.apply(this, args);
  } as typeof CanvasRenderingContext2D.prototype.drawImage;
};
type FrameLog = { received: Record<number, number>; decoded: Record<number, number>; draws: [number, number][]; opened: number; closed: number; closedTwice: number; acceleration: string[] };
const frameLog = (page: Page) => page.evaluate(() => (window as unknown as { __liveView: FrameLog }).__liveView);
const percentile = (values: number[], share: number) => [...values].sort((a, b) => a - b)[Math.min(values.length - 1, Math.floor(share * values.length))];

/** Draws during `ms`: gaps between them and how long each frame waited from arrival to drawing. */
async function playout(page: Page, ms: number) {
  await page.evaluate(() => { (window as unknown as { __liveView: FrameLog }).__liveView.draws = []; });
  await page.waitForTimeout(ms);
  const { draws, received, decoded, opened, closed, closedTwice } = await frameLog(page);
  const gaps = draws.slice(1).map(([, at], index) => at - draws[index][1]);
  const waits = draws.map(([sequence, at]) => at - received[sequence]);
  const decoding = draws.map(([sequence]) => decoded[sequence] - received[sequence]);
  const round = (value: number) => Math.round(value);
  return { shown: draws.length, gap_ms_p50: round(percentile(gaps, .5)), gap_ms_p95: round(percentile(gaps, .95)),
    gap_ms_max: round(Math.max(...gaps)), wait_ms_median: round(percentile(waits, .5)), wait_ms_max: round(Math.max(...waits)),
    decode_ms_median: round(percentile(decoding, .5)), decode_ms_p95: round(percentile(decoding, .95)),
    open: opened - closed, closedTwice, draws, received };
}

test('frames delivered in bursts are shown evenly, late frames at once, within the delay clamp', async ({ page, request }, testInfo) => {
  // The owner's tunnel: 15 fps, acknowledgements p95 280 ms apart. Here 4 frames (267 ms) arrive together.
  await page.addInitScript(instrumentFrames);
  await request.post('/__e2e/camera', { data: { interval: 1 / 15, burst: 4 } });
  await openLiveView(page);
  await page.waitForTimeout(3000); // the jitter estimate fills and the delay settles
  const { draws: _bursts, received: _r1, ...bursts } = await playout(page, 8000);
  // 10 frames (667 ms) together: the oldest are later than the 300 ms clamp allows.
  await request.post('/__e2e/camera', { data: { burst: 10 } });
  await page.waitForTimeout(3000);
  const { draws, received, ...late } = await playout(page, 8000);
  const report = { burst4: bursts, burst10: late };
  writeFileSync(testInfo.outputPath('playout.json'), JSON.stringify(report, null, 2));
  await testInfo.attach('playout', { path: testInfo.outputPath('playout.json'), contentType: 'application/json' });

  // Even: drawn about one capture interval (67 ms) apart, not three at once and then a 267 ms pause.
  expect(bursts.gap_ms_p95).toBeLessThanOrEqual(100);
  expect(bursts.shown).toBeGreaterThan(100);
  // No frame waits longer than the 300 ms clamp, plus one display frame and decoding.
  expect(bursts.wait_ms_max).toBeLessThanOrEqual(350);
  expect(late.wait_ms_max).toBeLessThanOrEqual(350);
  // The oldest frame of each burst is past its slot: drawn as soon as it is decoded.
  const arrivals = Object.entries(received).map(([sequence, at]) => [Number(sequence), at]).sort((a, b) => a[0] - b[0]);
  const firsts = arrivals.filter(([, at], index) => index > 0 && at - arrivals[index - 1][1] > 300).map(([sequence]) => sequence);
  const drawnAt = new Map(draws);
  const firstWaits = firsts.filter(sequence => drawnAt.has(sequence)).map(sequence => drawnAt.get(sequence)! - received[sequence]);
  expect(firstWaits.length).toBeGreaterThan(5);
  expect(Math.max(...firstWaits)).toBeLessThanOrEqual(50);
  // Held frames must not pin a hardware decoder's small output pool (it would stall): software decoding.
  expect(new Set((await frameLog(page)).acceleration)).toEqual(new Set(['prefer-software']));
  // Bounded and released: at most 8 held plus the one shown; nothing closed twice.
  for (const result of [bursts, late]) {
    expect(result.open).toBeLessThanOrEqual(9);
    expect(result.closedTwice).toBe(0);
  }

  // Hiding the tab releases the held frames at once (resume starts again from a keyframe).
  await page.waitForFunction(() => {
    const log = (window as unknown as { __liveView: FrameLog }).__liveView;
    return log.opened - log.closed >= 3;
  });
  const afterHide = await page.evaluate(() => {
    const log = (window as unknown as { __liveView: FrameLog }).__liveView;
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
    return log.opened - log.closed;
  });
  expect(afterHide).toBe(1);
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const shownBefore = (await frameLog(page)).draws.length;
  await expect.poll(async () => (await frameLog(page)).draws.length).toBeGreaterThan(shownBefore);
  // Stop releases every frame exactly once.
  await page.getByRole('button', { name: 'Stop my live view', exact: true }).click();
  await expect.poll(async () => { const log = await frameLog(page); return log.opened - log.closed; }).toBe(0);
  expect((await frameLog(page)).closedTwice).toBe(0);
});

for (const [name, setup, message] of [
  ['a browser without H.264 decoding', () => { delete (window as { VideoDecoder?: unknown }).VideoDecoder; },
    "This browser can't show live view; use Chrome/Edge 94+, Safari 16.4+ or Firefox 130+."],
  ['a plain-HTTP page', () => { Object.defineProperty(window, 'isSecureContext', { get: () => false }); },
    'Live view needs a secure connection. Open RobotControl through its https:// address, or on the RobotControl computer.'],
] as const) {
  test(`${name} shows why live view is unavailable and starts no session`, async ({ page }, testInfo) => {
    const sessions: string[] = [];
    page.on('request', req => { if (req.url().includes('/api/camera/streaming/session')) sessions.push(req.method()); });
    await page.addInitScript(setup);
    await page.goto('/camera?section=live');
    await expect(page.getByText(message, { exact: true })).toBeVisible();
    await expect(page.getByText('Live view is not available here', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start my live view', exact: true })).toBeDisabled();
    await expect(liveImage(page)).toHaveCount(0);
    expect(sessions).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath('unavailable.png'), fullPage: true });
  });
}

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
  await expect(liveImage(page)).toBeVisible();
  await expect(page.getByText(/\(401\)|Failed to create streaming session/)).toHaveCount(0);
  expect(refreshes).toBe(1);
  await page.screenshot({ path: testInfo.outputPath('renewed-sign-in.png') });
});
