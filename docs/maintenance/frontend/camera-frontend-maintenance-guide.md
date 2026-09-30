# Camera frontend maintenance

## Active components

The active page is `frontend/src/pages/CameraPage.tsx`. `CameraControls.tsx` owns the camera control panel. `CameraViewport.tsx` owns image sizing, zoom, pan and expanded viewing. `LiveFrame.tsx` owns the current image store and freshness status. `components/camera/VideoArchiveTab.tsx` handles archive browsing.

## Reading the live image

The image and a compact camera/recording status appear before the settings. **Start my live view**, **Stop my live view** and **Reconnect live view** affect this user's viewing session. Recording and source controls remain under **Camera and recording settings**. Collapsing settings only hides their contents: the polling owner stays mounted and errors remain visible above the image.

**Fit** is the default and preserves the full image without distortion. Its inline surface follows the camera's actual aspect ratio and shrinks both dimensions when height is limited. **Fill** covers the available surface and explicitly displays **Cropped view**. Zoom also displays that label because some of the image can leave the viewing area. Zoom ranges from 1× to 4×. Use the plus/minus buttons, Reset, drag, or the pan arrows. The image accepts +/−, arrow keys and 0 when focused. The expanded image also supports pinch zoom; gesture handling is limited to the image, leaving browser zoom available elsewhere.

**Expand live view** uses an application fullscreen dialog with safe-area padding. Only one image component subscribes to the frame store at a time. Opening/closing it does not start a new stream or change recording. A disconnected view stays open with its reconnect action. The expanded surface has a definite viewport height, and short windows can scroll to reach its controls. Resizing preserves the selected viewing mode; a source or image-resolution change resets to Fit at 1×. Stale/crop labels sit outside the transformed image.

When a source change temporarily removes frames, focused zoom/pan controls may become disabled. The viewport moves that focus to the stable image region so Escape still closes the expanded view immediately; closing restores focus to Expand. Keep this behavior when changing toolbar controls.

## Controls and status

CameraControls uses one serial polling owner: cached health every five seconds, or every second during an operation. Hidden browser pages continue polling. Refresh cameras is an explicit admin action; status refresh never reconnects hardware. Device dropdown drafts survive polling and errors. Save selection is separate from Connect. An existing selected camera cannot be changed while recording is requested; Stop recording explains and unlocks the change. A first selection after camera-less startup preserves waiting intent.

Show camera capture and recording separately from Streaming Session's browser connection. Device changes, connect/reconnect and recording controls are admin-only; ordinary users retain live viewing permissions. Errors are persistent inline messages. Operation IDs/revisions prevent a status response from an earlier request prematurely replacing operation progress.

`CameraControls.active` pauses status polling while the live section is not shown; collapsing the settings does not.

All camera JSON requests use the shared `api` client, so an expired access token is renewed once instead of failing with 401 on a screen left open. Polling and in-flight actions reset when the signed-in user changes, not when the token is renewed. Recording downloads stay on `fetch` (ranged, resumable, with progress) and call `attemptTokenRefresh` once on a 401. Each error has one owner: `archiveError` for the recordings list, `error` for downloads (archive dialog), `liveError` for the viewing session (shown in the viewer), and a failed live-view status read clears the old status and shows **Live view status unavailable** with Retry.

Reconnect camera affects the shared source and can interrupt all viewers. Reconnect live view closes/replaces only that user's streaming session. It never changes recording intent or starts another camera. Stop My Stream remains independent of recording.

## Frames and performance

The page stores image availability; CameraViewport stores dimensions and viewing transforms. Actual JPEG data lives in one current-frame store, consumed by a single visible LiveFrame component. Never move per-frame images into page state or add per-frame console logs. Clear frames through the page's `setCurrentFrame` function so availability and image data cannot disagree.

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
portrait frames, Fit/Fill/zoom, one visible frame, stale and disconnected expanded view,
polling with settings collapsed, touch targets) and `operations.spec.ts` (archive). Both
run against the isolated fixture and save screenshots and JSON reports to
`test-output/viewer-verification`; `CameraControls.test.tsx` and `LiveFrame.test.tsx`
remain. Physical disconnect/reconnect and long recordings are hardware acceptance tasks
on an isolated package and data folder.
