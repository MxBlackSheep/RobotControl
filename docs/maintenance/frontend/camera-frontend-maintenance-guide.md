# Camera frontend maintenance

## Active components

The active page is `frontend/src/pages/CameraPage.tsx`. `CameraControls.tsx` owns the camera control panel. `CameraViewport.tsx` owns image sizing, zoom, pan and expanded viewing. `LiveFrame.tsx` owns the current-frame store, the canvas that draws it and freshness status. `components/camera/VideoArchiveTab.tsx` handles archive browsing.

## Reading the live image

Live view is the first section (`?section=live` is the default; opening it never starts a session) and Video archive the second. Below the image, Recent recordings lists the four newest folders from the same archive read and links to the archive. Beside the image (1200px and wider) the controls are two cards, Recording and Camera, each with its state; on phones they share one collapsible panel.

The image and a compact camera/recording status appear before the settings. On a phone (under 600px wide, or under 500px tall, i.e. on its side) the viewing controls (Start/Stop/Reconnect and the sizing toolbar) sit below the picture and its freshness line, within thumb reach, in the DOM too so tab order follows the screen; the inline picture may then fill one screen below the app's sticky header rather than only the height left under the controls (the page scrolls to it), so an upright phone shows a 4:3 frame at full width. Under 600px wide the viewer panel also runs edge to edge. **Start my live view**, **Stop my live view** and **Reconnect live view** affect this user's viewing session. Recording and source controls remain under **Camera and recording settings**. Collapsing settings only hides their contents: the polling owner stays mounted and errors remain visible above the image.

Live view is H.264 only, decoded by the browser (WebCodecs). On opening the page, `liveViewUnsupportedReason()` checks for a secure page (HTTPS or localhost) and H.264 support; if either is missing, **Start my live view** is disabled and the reason is shown above the picture ("This browser can't show live view; use Chrome/Edge 94+, Safari 16.4+ or Firefox 130+", or the secure-connection message). There is no image fallback.

**Fit** is the default and preserves the full image without distortion. Its inline surface follows the camera's actual aspect ratio and shrinks both dimensions when height is limited. **Width** ("Fit width") scales the full image to the available width; the surface grows to the image height and the page, or the expanded dialog, scrolls. Nothing is cropped. (Until October 2026 this was **Fill**, which kept the Fit height and cropped up to 40% of the frame.) Only zoom displays **Cropped view** and the pan arrows, because only zoom moves part of the image out of view. Zoom ranges from 1× to 4×. Use the plus/minus buttons, Reset, drag, or the pan arrows. The image accepts +/−, arrow keys and 0 when focused. The expanded image also supports pinch zoom; gesture handling is limited to the image, leaving browser zoom available elsewhere.

**Expand live view** uses an application fullscreen dialog with safe-area padding. Only one image component subscribes to the frame store at a time. Opening/closing it does not start a new stream or change recording. A disconnected view stays open with its reconnect action. The expanded surface has a definite viewport height, and short windows can scroll to reach its controls. Resizing, a source change or a frame-size change keeps the selected mode and resets zoom and pan to 1×. The measured area is a state ref: the dialog mounts its content through a portal one render later, so measuring starts when the element attaches (before, the expanded view kept the page's size). Stale/crop labels sit outside the transformed image.

When a source change temporarily removes frames, focused zoom/pan controls may become disabled. The viewport moves that focus to the stable image region so Escape still closes the expanded view immediately; closing restores focus to Expand. Keep this behavior when changing toolbar controls.

## Controls and status

CameraControls uses one serial polling owner: cached health every five seconds, or every second during an operation. Hidden browser pages continue polling. Refresh cameras is an explicit admin action; status refresh never reconnects hardware. Device dropdown drafts survive polling and errors. Save selection is separate from Connect. An existing selected camera cannot be changed while recording is requested; Stop recording explains and unlocks the change. A first selection after camera-less startup preserves waiting intent.

Show camera capture and recording separately from Streaming Session's browser connection. Device changes, connect/reconnect and recording controls are admin-only; ordinary users retain live viewing permissions. Errors are persistent inline messages. Operation IDs/revisions prevent a status response from an earlier request prematurely replacing operation progress.

`CameraControls.active` pauses status polling while the live section is not shown; collapsing the settings does not.

All camera JSON requests use the shared `api` client, so an expired access token is renewed once instead of failing with 401 on a screen left open. Polling and in-flight actions reset when the signed-in user changes, not when the token is renewed. Recording downloads stay on `fetch` (ranged, resumable, with progress) and call `attemptTokenRefresh` once on a 401. Each error has one owner: `archiveError` for the recordings list, `error` for downloads (archive dialog), `liveError` for the viewing session (shown in the viewer), and a failed live-view status read clears the old status and shows **Live view status unavailable** with Retry.

Reconnect camera affects the shared source and can interrupt all viewers. Reconnect live view closes/replaces only that user's streaming session. `hooks/useLiveViewSocket.ts` owns the socket: one `VideoDecoder` per socket and frame size; it starts at a keyframe and skips delta frames until one arrives (after an error or a size change), shows only newer sequences from the current socket, acknowledges each frame once decoded or skipped (cumulatively, also after a decoder error, so the server keeps sending), pauses while the tab is hidden, and after an unexpected close keeps the last image (stale after 10 s) and reconnects automatically with jittered back-off (1 s to 30 s; waits for `online`; never after Stop or unmount). The page owns the session requests it reconnects with. It never changes recording intent or starts another camera. Stop My Stream remains independent of recording.

### Playout buffer

Over a long link (the Cloudflare tunnel) frames reach the browser in bursts, so showing each one as it is decoded looks like a freeze followed by a quick catch-up. The hook therefore holds decoded frames briefly and shows them evenly spaced by their capture times (`createPlayout` in `useLiveViewSocket.ts`):

- **When a frame is shown:** at capture time (the frame header's Unix time) + offset + delay. The offset is the smallest (arrival − capture) over the last 90 frames (6 s at 15 fps), so a difference between the server's and the browser's clocks cancels out. The delay follows the p95 of the arrival jitter above that minimum, clamped to 0–300 ms; it rises within about a second and falls over several (`DELAY_RISE`, `DELAY_FALL`), so it does not swing.
- **Never later than needed:** a frame already past its time is shown at once, so no frame waits more than the current delay. On each animation frame only the newest due frame is shown; older due frames are closed unshown. At most 8 frames are held (the oldest is closed beyond that).
- **Buffered frames must not pin decoder output.** A decoded `VideoFrame` holds one of the decoder's output buffers until it is closed; hardware decoders (e.g. D3D11 in Chrome/Edge on Windows) have small fixed pools and stall when they run out, which would freeze live view on GPUs the checks never see. So with the buffer on, `liveViewUnsupportedReason()` picks `hardwareAcceleration: 'prefer-software'` when the browser supports it (otherwise the default, so Safari and Firefox keep working) and every decoder uses that choice. Software decoding of 640×480 at 15 fps measured 1 ms a frame (median; p95 2 ms) in the check. Do not raise `MAX_HELD` or hold frames elsewhere without keeping them off the decoder's pool.
- **Acknowledgements stay at decode time**, before the buffer, so the server's window and the delivery log still measure the link, not the buffer.
- **Reset:** hiding or showing the tab, a new socket (reconnect), a new decoder (a frame size change, or a decoder error after which decoding restarts at a keyframe) and Stop close the held frames and restart the estimates.
- **Cost:** the picture lags by about the link's recent jitter: in the burst check below, frames waited 124 ms (median) and 225 ms at most, about +100–250 ms on the owner's tunnel. Beyond the 300 ms clamp a burst is still partly visible, by design: the lag stays bounded.
- **Off switch:** set `PLAYOUT_BUFFER = false` in `useLiveViewSocket.ts` and rebuild; every frame is then shown as soon as it is decoded, by the browser's default decoder, exactly as before October 2026. A frontend constant was chosen because a `LIVE_STREAMING_CONFIG` field would also need a rebuild of the packaged app, plus an API field and a state path to the hook.

If the owner still sees freezes, read the delivery log: `ack_gap_ms_max` well above 300 ms means bursts longer than the clamp, which still show as a pause by design; a `rtt_ms_median` that rose by about the delay would mean the browser's decoder slowed while frames were held.

## Frames and performance

The page stores image availability; CameraViewport stores dimensions and viewing transforms. The decoded `VideoFrame` lives in one current-frame store, drawn by a single visible LiveFrame canvas from a store subscription (no React render per frame). The store owns frames: replacing or clearing one closes the previous (a decoder stalls when frames are not released). Never move per-frame images into page state or add per-frame console logs. Clear frames through the page's `setCurrentFrame` function so availability and image data cannot disagree.

FrameFreshness samples monotonic receive time once per second and visibly marks an image stale after ten seconds without a frame. Identical image bytes still refresh receive time: this is not a motion detector. The overlay exists in inline and fullscreen views. Source generation changes clear obsolete images. Socket close/unmount detaches handlers and releases the local frame reference.

## Archive

`VideoArchiveTab` uses the shared inspection workspace: folders beside files on wide
containers, folder then files with Back on phones. Selection, search and page stay
mounted across width changes. Rows have natural height and scroll locally; pagination
(25/50/100 files) bounds the rendered rows so long names and touch controls can wrap.
Keep the lazy folder loading, folder cache, video preview and resumable downloads.
Archive display never calls camera hardware or recording APIs, changes archive metadata
or runs Hamilton methods.

## Checks

Failure cases are in the headers of `camera.spec.ts` (viewer: 4:3, widescreen and
portrait frames, Fit/Fit width/zoom, one visible frame, stale and disconnected expanded view,
polling with settings collapsed, touch targets) and `operations.spec.ts` (archive). Both
run against the isolated fixture and save screenshots and JSON reports to
`test-output/viewer-verification`; `CameraControls.test.tsx` remains. The fixture streams real H.264 from the bundled
ffmpeg; `camera.spec.ts` reads decoded corner colours from the canvas. Its burst case sends 15 fps in groups of 4 and 10 frames (fixture `interval` and `burst`) and measures, through the platform APIs only, the gaps between drawn frames, each frame's wait and open `VideoFrame`s; the numbers are attached as `playout.json`. Physical disconnect/reconnect and long recordings are hardware acceptance tasks
on an isolated package and data folder.
