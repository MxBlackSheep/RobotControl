# Camera frontend maintenance

## Active components

The active page is `frontend/src/pages/CameraPage.tsx`. `CameraControls.tsx` owns the camera control panel. `CameraViewport.tsx` owns image sizing, zoom, pan and expanded viewing. `LiveFrame.tsx` owns the current-frame store, the canvas that draws it and freshness status. `components/camera/VideoArchiveTab.tsx` handles archive browsing.

## Reading the live image

Live view is the first section (`?section=live` is the default; opening it never starts a session) and Video archive the second. Below the image, Recent recordings lists the four newest folders from the same archive read and links to the archive. Beside the image (1200px and wider) the controls are two cards, Recording and Camera, each with its state; on phones they share one collapsible panel.

The image and a compact camera/recording status appear before the settings. **Start my live view**, **Stop my live view** and **Reconnect live view** affect this user's viewing session. Recording and source controls remain under **Camera and recording settings**. Collapsing settings only hides their contents: the polling owner stays mounted and errors remain visible above the image.

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
ffmpeg; `camera.spec.ts` reads decoded corner colours from the canvas. Physical disconnect/reconnect and long recordings are hardware acceptance tasks
on an isolated package and data folder.
