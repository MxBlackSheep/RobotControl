# Camera frontend maintenance

## Active components

The active page is `frontend/src/pages/CameraPage.tsx`. `CameraControls.tsx` owns the camera control panel. `LiveFrame.tsx` owns the current image store and freshness overlay. `components/camera/VideoArchiveTab.tsx` handles archive browsing. Older CameraViewer/LiveCamerasTab components are not the main live page; do not implement recovery only in those legacy components.

## Controls and status

CameraControls uses one serial polling owner: cached health every five seconds, or every second during an operation. Hidden browser pages continue polling. Refresh cameras is an explicit admin action; status refresh never reconnects hardware. Device dropdown drafts survive polling and errors. Save selection is separate from Connect. An existing selected camera cannot be changed while recording is requested; Stop recording explains and unlocks the change. A first selection after camera-less startup preserves waiting intent.

Show camera capture and recording separately from Streaming Session's browser connection. Device changes, connect/reconnect and recording controls are admin-only; ordinary users retain live viewing permissions. Errors are persistent inline messages. Operation IDs/revisions prevent a status response from an earlier request prematurely replacing operation progress.

Reconnect camera affects the shared source and can interrupt all viewers. Reconnect live view closes/replaces only that user's streaming session. It never changes recording intent or starts another camera. Stop My Stream remains independent of recording.

## Frames and performance

The page stores only image availability and dimensions. Actual JPEG data lives in one current-frame store shared by inline and fullscreen LiveFrame components. Never move per-frame images into page state or add per-frame console logs.

FrameFreshness samples monotonic receive time once per second and visibly marks an image stale after ten seconds without a frame. Identical image bytes still refresh receive time: this is not a motion detector. The overlay exists in inline and fullscreen views. Source generation changes clear obsolete images. Socket close/unmount detaches handlers and releases the local frame reference.

## Archive behavior and checks

Retain existing folder browsing, video preview and resumable downloads. Camera recovery does not change archive metadata or execute Hamilton methods.

Run frontend Vitest tests, including CameraControls and LiveFrame. Check admin/user permissions, first selection, recording locks, failed operations, refresh focus, identical-image freshness, and timer cleanup. Review narrow/desktop layouts and keyboard selection. Use a fixture server for UI mutations, and an isolated package/data directory for actual camera checks. Physical disconnect/reconnect and long-duration recording remain hardware acceptance tasks.
