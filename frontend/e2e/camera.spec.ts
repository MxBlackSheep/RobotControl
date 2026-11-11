import { readFileSync, writeFileSync } from 'node:fs';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { signIn } from './sign-in';

/** Failure scenarios written before the camera implementation:
 * - The picture (it always fits) crops or distorts 4:3, widescreen or portrait images on
 *   desktop/phone, or a new frame size is not shown whole.
 * - Expanding renders two frame subscribers or reconnects capture/recording.
 * - The line under the picture says "Waiting for frames" before live view is started.
 * - Disconnect closes the inspection surface; stale images look live; a dropped stream
 *   clears the image or stays stopped instead of reconnecting by itself; Stop is undone
 *   by an automatic reconnect. Reconnect live view does not replace the session or frames do
 *   not resume after it.
 * - Choose and connect: an administrator cannot stop recording, pick another camera, save it
 *   and connect; the Camera chip does not go from Disconnected to Connected; Connect and
 *   Reconnect camera are offered at once (they are one backend action).
 * - Download (useRecordingDownload.ts): a response cut mid-file is not resumed from the received
 *   byte with Range, the progress line does not show "x / y" then "Reconnecting...", or the
 *   saved file differs from the server's bytes; the browser cache resumes instead of the page.
 *   Cancel saves a file, sends another request or leaves the Download buttons disabled. A 404 is
 *   retried, shown more than once, or opens a dialog whose button does something else.
 * - Frames are not acknowledged (the server then sends at most two and ends a silent
 *   viewer after 15 s); a hidden tab keeps receiving frames or does not resume.
 * - H.264 frames are not decoded onto the canvas (blank or wrong picture), or a new frame
 *   size is not followed.
 * - A browser without WebCodecs H.264, or a plain-HTTP page, starts a session, shows a blank
 *   canvas or falls back to JPEG instead of its message (live view is H.264 only).
 * - Collapsing controls (or closing the phone settings sheet) stops health polling or hides recording/errors.
 * - Small screens overflow, touch controls shrink, or keyboard focus is lost. On an upright phone
 *   the picture is narrower than the screen, or the viewing controls sit above it (out of thumb
 *   reach) instead of below.
 * - An expired access token makes status polls and live-view start fail with 401 forever
 *   instead of renewing the sign-in once (a lab screen left open overnight).
 * - Playout buffer (useLiveViewSocket.ts): frames that arrive in bursts are still shown in bursts
 *   instead of evenly by capture time; a frame past its slot waits anyway, or any frame waits
 *   longer than the 300 ms clamp; a VideoFrame is never closed, closed twice, or more than 8 are
 *   held; hiding the tab leaves held frames queued; held frames pin a hardware decoder's output
 *   pool (it stalls: live view freezes on GPUs the checks never see), so decoding must be software. Turned off (PLAYOUT_BUFFER), the same case
 *   fails on evenness with the numbers from before the buffer (frames shown as decoded).
 * Fixture contract: POST /__e2e/camera configures dimensions, send_frames,
 * disconnect, generation, interval (seconds between captured frames), burst (frames sent
 * together), the camera controls' device, capture and recording, and cut_after (drop the next
 * download after that many bytes); it returns sessions, controls and each download's Range in
 * ranges. Only the isolated fixture handles these requests. Its frames are
 * real H.264 from the bundled ffmpeg (red, lime, yellow, magenta corner squares on blue).
 */
test.beforeEach(async ({ page, request }) => {
  await request.post('/__e2e/camera', { data: { width: 640, height: 480, send_frames: true, disconnect: false, generation: 'g1',
    interval: .2, burst: 1, device: 'fixture-camera', capture: 'connected', recording: true, operation: null, ranges: [], cut_after: null } });
  await signIn(page);
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
  const start = page.getByRole('button', { name: 'Start my live view', exact: true });
  await expect(start).toBeEnabled();
  // The line under the picture stays empty until live view starts.
  await expect(page.getByText('Waiting for frames', { exact: true })).toHaveCount(0);
  await start.click();
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

test('Expand keeps one picture and the session, and follows a new frame size whole', async ({ page, request }, testInfo) => {
  const writes: string[] = [];
  page.on('request', req => { if (req.method() !== 'GET' && req.url().includes('/api/camera/')) writes.push(`${req.method()} ${new URL(req.url()).pathname}`); });
  await openLiveView(page);
  await page.getByRole('button', { name: 'Expand live view', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Live camera inspection' })).toBeVisible();
  await expect(liveImage(page)).toHaveCount(1);
  // A different frame size (another camera) restarts decoding at its keyframe and still fits whole.
  for (const [width, height] of [[320, 240], [480, 800], [640, 480]]) {
    await request.post('/__e2e/camera', { data: { width, height } });
    await expect.poll(() => frameWidth(page)).toBe(width);
    await expect.poll(() => cornerColours(page)).toEqual(['red', 'lime', 'yellow', 'magenta']);
    expect((await wholeFrame(page)).clipped).toBe(0);
  }
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
  // Connected again: the view-state chip only appears while connecting or dropped.
  await expect(page.getByText(/^My view: /)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Stop my live view', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('reconnected-stale.png'), fullPage: true });
  await request.post('/__e2e/camera', { data: { send_frames: true } });
  await expect(page.getByText('Live view receiving frames', { exact: true })).toBeVisible();
  // Reconnect replaces the session and frames resume on the new socket.
  const replaced = (await fixture(request)).sessions;
  const acks = async () => (((await fixture(request)).controls ?? []) as string[]).filter(type => type === 'ack').length;
  await page.getByRole('button', { name: 'Reconnect live view', exact: true }).click();
  await expect.poll(async () => (await fixture(request)).sessions).toBe(replaced + 1);
  const acknowledged = await acks();
  await expect.poll(acks).toBeGreaterThan(acknowledged);
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
    await expect(page.getByRole('button', { name: 'Start my live view', exact: true })).toBeDisabled();
    await expect(liveImage(page)).toHaveCount(0);
    expect(sessions).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath('unavailable.png'), fullPage: true });
  });
}

test('phone settings sheet: polling continues while closed, controls open from the button and stay touchable', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let healthRequests = 0;
  page.on('request', req => { if (req.url().includes('/api/camera/control-status')) healthRequests++; });
  await openLiveView(page);
  await expect(page.getByText('Camera connected · Recording', { exact: true })).toBeVisible();
  const before = healthRequests;
  await expect.poll(() => healthRequests, { timeout: 8000 }).toBeGreaterThan(before);
  // The sheet's button carries the recording state, and the controls live in the sheet.
  const opener = page.getByRole('button', { name: /^Camera and recording/ });
  await expect(opener).toContainText('On');
  await expect(page.getByRole('combobox', { name: 'Selected camera' })).not.toBeVisible();
  await opener.click();
  const sheet = page.getByRole('dialog', { name: 'Camera and recording' });
  await expect(sheet.getByRole('combobox', { name: 'Selected camera' })).toBeVisible();
  await sheet.getByRole('button', { name: 'Done', exact: true }).click();
  await expect(sheet).toBeHidden();
  await expect(opener).toBeFocused();
  const targets = await page.getByTestId('camera-toolbar').getByRole('button').evaluateAll(buttons => buttons.map(button => ({ label: button.getAttribute('aria-label') ?? button.textContent, height: button.getBoundingClientRect().height })));
  for (const target of targets) expect(target.height, target.label ?? 'camera control').toBeGreaterThanOrEqual(44);
  expect(await wholeFrame(page)).toEqual({ clipped: 0, width: 390 });
  const stage = (await page.getByTestId('camera-stage').boundingBox())!;
  expect((await page.getByTestId('camera-toolbar').boundingBox())!.y).toBeGreaterThan(stage.y + stage.height);
  await testInfo.attach('touch-targets', { body: JSON.stringify(targets, null, 2), contentType: 'application/json' });
  await page.screenshot({ path: testInfo.outputPath('phone-controls.png'), fullPage: true });
});

test('an expired sign-in is renewed and live view still starts', async ({ page }, testInfo) => {
  let expired = false, refreshes = 0;
  const rejected: string[] = [];
  await page.route('**/api/auth/refresh', async route => {
    refreshes++;
    await signIn(page, 'e2e-admin');
    return route.fulfill({ json: { success: true, data: {} } });
  });
  await page.route('**/api/camera/**', async route => {
    if (expired && (await route.request().headerValue('cookie'))?.includes('rc_access=viewer-admin')) {
      rejected.push(new URL(route.request().url()).pathname);
      return route.fulfill({ status: 401, json: { detail: 'Expired' } });
    }
    return route.fallback();
  });
  await page.goto('/camera?section=live');
  await expect(page.getByRole('region', { name: 'Camera', exact: true }).getByText('Connected', { exact: true })).toBeVisible();
  expired = true;
  await expect.poll(() => rejected.length, { timeout: 15_000 }).toBeGreaterThan(0);
  await expect.poll(async () => (await page.context().cookies()).find(c => c.name === 'rc_access')?.value).toBe('e2e-admin');
  await page.getByRole('button', { name: 'Start my live view', exact: true }).click();
  await expect(liveImage(page)).toBeVisible();
  await expect(page.getByText(/\(401\)|Failed to create streaming session/)).toHaveCount(0);
  expect(refreshes).toBe(1);
  await page.screenshot({ path: testInfo.outputPath('renewed-sign-in.png') });
});

test('an administrator stops recording, chooses another camera and connects it', async ({ page, request }) => {
  const writes: string[] = [];
  page.on('request', req => { if (req.method() !== 'GET' && req.url().includes('/api/camera/') && !req.url().includes('/streaming/')) writes.push(`${req.method()} ${new URL(req.url()).pathname}`); });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto('/camera?section=live');
  const cameraPanel = page.getByRole('region', { name: 'Camera', exact: true });
  const recordingPanel = page.getByRole('region', { name: 'Recording', exact: true });
  const choice = page.getByRole('combobox', { name: 'Selected camera' });
  await expect(cameraPanel.getByText('Connected', { exact: true })).toBeVisible();
  // One button for one backend action: a connected camera offers Reconnect only.
  await expect(cameraPanel.getByRole('button', { name: 'Connect', exact: true })).toHaveCount(0);
  await expect(choice).toHaveAttribute('aria-disabled', 'true');
  await recordingPanel.getByRole('button', { name: 'Stop recording', exact: true }).click();
  await expect(recordingPanel.getByText('Off', { exact: true })).toBeVisible();
  await expect(cameraPanel.getByText('Disconnected', { exact: true })).toBeVisible();
  await cameraPanel.getByRole('button', { name: 'Refresh cameras', exact: true }).click();
  await expect(choice).not.toHaveAttribute('aria-disabled', 'true');
  await choice.click();
  await page.getByRole('option', { name: 'Second camera · Device 2', exact: true }).click();
  await cameraPanel.getByRole('button', { name: 'Save selection', exact: true }).click();
  await expect(cameraPanel.getByRole('button', { name: 'Save selection', exact: true })).toBeDisabled();
  await expect(cameraPanel.getByRole('button', { name: 'Reconnect camera', exact: true })).toHaveCount(0);
  await cameraPanel.getByRole('button', { name: 'Connect', exact: true }).click();
  await expect(cameraPanel.getByText('Connected', { exact: true })).toBeVisible();
  await expect(cameraPanel.getByRole('button', { name: 'Reconnect camera', exact: true })).toBeEnabled();
  await expect(cameraPanel.getByRole('button', { name: 'Connect', exact: true })).toHaveCount(0);
  await expect(choice).toContainText('Second camera');
  expect(writes).toEqual(['POST /api/camera/recording/stop', 'POST /api/camera/devices/refresh', 'PATCH /api/camera/selection', 'POST /api/camera/connect']);
  expect((await fixture(request)).device).toBe('second-camera');
});

const clip = 'fixture-clip.mp4';
const downloadButton = (page: Page, name: string) => page.getByRole('button', { name: `Download ${name}`, exact: true });
async function openArchive(page: Page) {
  await page.goto('/camera?section=archive');
  await page.getByRole('button', { name: /Open folder Fixture run/ }).click();
}

test('a download cut mid-file resumes from the received byte and saves the whole file', async ({ page, request }) => {
  await request.post('/__e2e/camera', { data: { cut_after: 100_000 } });
  await openArchive(page);
  const saved = page.waitForEvent('download');
  await downloadButton(page, clip).click();
  await expect(page.getByText('97.7 KB / 300.0 KB · Reconnecting...', { exact: true })).toBeVisible();
  const file = await (await saved).path();
  expect((await fixture(request)).ranges).toEqual([null, 'bytes=100000-']);
  const served = await request.get(`/api/camera/recording/${clip}`, { headers: { Authorization: 'Bearer viewer-admin' } });
  expect(readFileSync(file).equals(await served.body())).toBe(true);
  await expect(page.getByText(/^Downloading /)).toHaveCount(0);
  await expect(page.getByRole('dialog', { name: 'Download failed' })).toHaveCount(0);
});

test('Cancel during a download saves no file and frees the Download buttons', async ({ page, request }) => {
  await request.post('/__e2e/camera', { data: { cut_after: 100_000 } });
  const downloads: string[] = [];
  page.on('download', download => downloads.push(download.suggestedFilename()));
  await openArchive(page);
  await downloadButton(page, clip).click();
  await expect(page.getByText(/· Reconnecting\.\.\.$/)).toBeVisible();
  await expect(downloadButton(page, clip)).toBeDisabled();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByText(/^Downloading /)).toHaveCount(0);
  await expect(downloadButton(page, clip)).toBeEnabled();
  await page.waitForTimeout(2500); // longer than the first retry wait (1.2 s)
  expect(downloads).toEqual([]);
  expect((await fixture(request)).ranges).toEqual([null]);
  await expect(page.getByRole('dialog', { name: 'Download failed' })).toHaveCount(0);
  // The buttons work again: the next download completes.
  const saved = page.waitForEvent('download');
  await downloadButton(page, clip).click();
  expect((await saved).suggestedFilename()).toBe(clip);
});

test('a missing recording shows its reason once and is not retried', async ({ page, request }) => {
  await openArchive(page);
  await downloadButton(page, 'missing-clip.mp4').click();
  const dialog = page.getByRole('dialog', { name: 'Download failed' });
  await expect(dialog).toContainText('Recording not found on server. It may have been moved or deleted.');
  await page.waitForTimeout(2500); // longer than the first retry wait (1.2 s)
  expect((await fixture(request)).ranges).toEqual([null]);
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText(/Recording not found/)).toHaveCount(0);
  await expect(downloadButton(page, 'missing-clip.mp4')).toBeEnabled();
});