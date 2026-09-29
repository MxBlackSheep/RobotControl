## September 2026 archive workspace

- `VideoArchiveTab` uses the shared inspection workspace: folder selector plus files on wide containers, folder-to-files navigation with Back on phones. Selection, search and page state stay mounted across width changes.
- File rows use natural height and local scrolling. Pagination (25/50/100 files) replaces fixed-height virtualization, bounding rendered rows while allowing long filenames and touch controls to wrap safely.
- Keep lazy folder-loading callbacks, the folder cache and the existing download lifecycle. Display changes do not call camera hardware or recording APIs.
- `CameraControls.active` pauses status polling when the live section is inactive. Collapsing camera settings does not pause polling. The shared document-visibility policy is unchanged.
- Verify archive behavior with `operations.spec.ts`; retain `camera.spec.ts` for Fit, Fill, zoom, source resets, Escape focus, disconnect and mutation checks. Evidence is written to `recovery/viewer-verification`.

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

Reconnect camera affects the shared source and can interrupt all viewers. Reconnect live view closes/replaces only that user's streaming session. It never changes recording intent or starts another camera. Stop My Stream remains independent of recording.

## Frames and performance

The page stores image availability; CameraViewport stores dimensions and viewing transforms. Actual JPEG data lives in one current-frame store, consumed by a single visible LiveFrame component. Never move per-frame images into page state or add per-frame console logs. Clear frames through the page's `setCurrentFrame` function so availability and image data cannot disagree.

FrameFreshness samples monotonic receive time once per second and visibly marks an image stale after ten seconds without a frame. Identical image bytes still refresh receive time: this is not a motion detector. The overlay exists in inline and fullscreen views. Source generation changes clear obsolete images. Socket close/unmount detaches handlers and releases the local frame reference.

## Archive behavior and checks

Retain existing folder browsing, video preview and resumable downloads. Camera recovery does not change archive metadata or execute Hamilton methods.

The browser failure scenarios are declared in `frontend/e2e/camera.spec.ts` before the viewer implementation. Run the Playwright camera suite against the isolated E2E fixture. It checks 4:3, widescreen and portrait frames on desktop/phone, Fit geometry, Fill warnings, zoom/reset, one visible frame, unchanged session requests, stale/disconnected expanded viewing, polling while settings are collapsed and touch target sizes. It saves screenshots and JSON geometry/request reports alongside the Playwright report. Also retain the existing CameraControls and LiveFrame regression checks; do not add unit tests after implementation. Use an isolated package/data directory for actual camera checks. Physical disconnect/reconnect and long-duration recording remain hardware acceptance tasks.
