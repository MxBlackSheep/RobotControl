# Frontend Camera Maintenance Guide

If you need to change anything about live video, streaming, or the archive UI, read this first. It walks through every React piece involved so you don’t guess how frames reach the page. Follow the steps in order—skipping one usually breaks the viewer.

---

## 1. High-Level Architecture

- `frontend/src/pages/CameraPage.tsx`  
  Container page. Manages the two tab views (Archive vs Streaming), loads experiment folders, downloads clips, and tracks streaming sessions.

- `frontend/src/components/CameraViewer.tsx`  
  Core live viewer. Handles MJPEG `<img>` feed, optional WebSocket streaming, fullscreen toggles, and state chips.

- `frontend/src/components/camera/LiveCamerasTab.tsx`  
  Shows the list of detected cameras with status badges. Calls back into the page when the user wants to refresh camera info or open settings.

- `frontend/src/components/camera/LiveStreamingTab.tsx`  
  UI for creating/stopping streaming sessions. Displays service stats and allows new session creation.

- `frontend/src/components/camera/VideoArchiveTab.tsx`  
  Virtualised archive browser. Lists experiment folders, lazily loads video lists, and triggers downloads/deletes.

- Supporting utilities:  
  - `frontend/src/utils/apiBase.ts` (`buildApiUrl`, `buildWsUrl`) – builds REST and WS URLs with the correct host.  
  - `frontend/src/components/LoadingSpinner.tsx` – shared spinner component for loading states.

**Rule of thumb:** Keep network calls inside `CameraPage` (or the specific tab) and pass data down via props. `CameraViewer` itself should only care about rendering frames, not fetching metadata.

---

## 2. How the Camera UI Works (Step-by-Step)

1. **Page mounts** → `CameraPage` sets `currentTab=0` (Archive) and calls `loadRecordings()`.  
   - Fetches `/api/camera/recordings?recording_type=experiment&limit=100` with the access token.  
   - Stores `experimentFolders` and clears old errors.

2. **Switch to Streaming tab** → `loadStreamingStatus()` calls `/api/camera/streaming/status`.  
   - Response populates `streamingStatus` and the “My Session” badge if available.

3. **Starting a streaming session** (LiveStreamingTab):  
   - User picks a camera ID, clicks “Start New Session”.  
   - Tab calls `onStartSession(cameraId)` provided by `CameraPage`, which POSTs to `/api/camera/streaming/session`.  
   - After success the tab refreshes status.

4. **Watching live video** (CameraViewer):  
   - `startMJPEGStream()` sets `<img src>` to `/api/camera/stream/{cameraId}` so the browser displays MJPEG frames.  
   - `startWebSocketStream()` (for high-frequency updates) opens `ws://.../api/camera/ws/{cameraId}`. Incoming messages of type `"frame"` update the `<img>` element to `data:image/jpeg;base64,...`.

5. **Archive browsing** (VideoArchiveTab):  
   - When the user expands a folder, the tab calls `onLoadFolderVideos(folder_name)` which should return video metadata.  
   - Downloads call `onDownloadVideo(filename)` that performs a signed fetch and builds a temporary `<a>` tag to save the file.

6. **Cleanup**  
   - `CameraViewer` cleans WebSockets and revokes blob URLs in `cleanup()`, invoked on unmount and tab change.  
   - `CameraPage` closes its own WebSocket (`wsRef`) on unmount.

---

## 3. Key State & Props to Watch

- `CameraPage` state:
  - `experimentFolders` – data rendered by `VideoArchiveTab`.  
  - `streamingStatus` – top-level stats provided to `LiveStreamingTab`.  
  - `mySession` – shows the viewer’s session details (used to gate fullscreen).  
  - `currentTab`, `error`, `archiveError`, `streamingLoading` – control UI feedback.

- `CameraViewer` state:
  - `isStreaming`, `connectionStatus`, `error` – control status chips.  
  - `isRecording` – initialised from `cameraInfo.is_recording`.  
  - `lastFrameTime`, `frameCount`, `streamQuality` – shown in UI to help debugging.

- Props to pass correctly:
  - `CameraViewer` needs `cameraId` and optionally `cameraInfo` so it can show resolution/FPS and toggles.  
  - `VideoArchiveTab` requires `onLoadFolderVideos`; otherwise expanding a folder does nothing.

---

## 4. Working With API Calls

1. **Always attach the bearer token** when using `fetch`. `CameraPage` reads `localStorage.getItem('access_token')` before hitting any camera endpoint.
2. **Use `buildApiUrl` / `buildWsUrl`.** They adapt to different hosts (localhost vs packaged exe). Hardcoding `/api/...` only works in dev.
3. **Handle error states explicitly.** When a fetch fails, set both `error` and `archiveError`/`streamingLoading` so the correct view shows the inline warning card (the tabs now render in-panel callouts instead of modal alerts).
4. **Remember to `URL.revokeObjectURL`.** When you create download links, revoke them once `click()` completes to avoid memory leaks.

---

## 5. Common Maintenance Tasks

| Task | Where | Step-by-step instructions |
|------|-------|---------------------------|
| Add a new camera action button | `LiveCamerasTab.tsx` | Extend the card footer; pass a callback from `CameraPage` via props so the page performs the API call. |
| Change the archive limit | `loadRecordings()` in `CameraPage.tsx` | Tweak the query parameter (`limit=100`). Update backend defaults if you want parity. |
| Display more streaming stats | `LiveStreamingTab.tsx` | Add fields to the status card. Make sure the backend returns the fields and update the `StreamingStatus` interface. |
| Customise fullscreen viewer | `CameraViewer.tsx` | Adjust the `fullscreenDialogOpen` logic and the `<Dialog>` contents. Keep the cleanup logic so the WebSocket closes. |
| Fix letterboxed live feed | `CameraPage.tsx` (streaming card) | The card now stores `frameDimensions` from the `<img>` load event and sets the container `aspectRatio` dynamically—if you tweak the layout, keep that state update and avoid reintroducing fixed heights, while still leaving the placeholder `minHeight` for the spinner and only showing the fullscreen button once a frame is visible. |
| Delete recordings | Add `onDeleteVideo` to `VideoArchiveTab` | Provide a handler in `CameraPage` that calls `DELETE /api/camera/recording/{filename}` and then refreshes the folder. |

---

## 6. Passive vs Active Messaging

- **Passive (dashboard) surfaces** – `LiveCamerasTab`, `LiveStreamingTab`, `VideoArchiveTab`, and `CameraViewer` now render inline warning cards for errors. If you introduce new read-only panels, follow the same pattern: stick the message in the card, include a retry button, and avoid opening modals.
- **Active operations** – Destructive or state-changing flows (e.g., deleting recordings, starting/stopping sessions) should continue to use modal confirmations. Place the modal in the page-level component so the rest of the UI remains responsive.
- **Keep titles short** – Inline cards use `Typography` with succinct headings (“Streaming service unavailable”). Reserve long technical details for expandable sections or logs.

---

## 7. Extending or Modifying Behaviour

### 6.1 Supporting multiple simultaneous camera feeds
1. Store an array of selected cameras in `CameraPage` instead of a single `currentFrame`.  
2. Render multiple `CameraViewer` instances, each with its own `cameraId`.  
3. Ensure each viewer calls `cleanup()` in `useEffect` so websockets close when a camera is removed.

### 6.2 Integrating thumbnails for archive videos
1. Extend `VideoFile` with `thumbnail_url`.  
2. Update `VideoArchiveTab` to render `<img>` inside each row using the new URL.  
3. Cache-bust thumbnails when a video is deleted (e.g., append `?t=${Date.now()}`).

### 6.3 Allowing users to rename experiment folders
1. Add a rename button in `VideoArchiveTab`.  
2. Call a new backend endpoint (`PATCH /api/camera/recordings/{folder}`) from the handler.  
3. After success, call `onRefresh()` so the latest names re-render.

---

## 8. Quick Reference

| Component / Function | Purpose | Notes |
|----------------------|---------|-------|
| `CameraPage` | Coordinates tabs, fetches data | Central hub—keep API calls here. |
| `CameraViewer` | Displays live feed | Works with both MJPEG and WebSocket sources. |
| `LiveCamerasTab` | Shows camera list + status | Relies on parent to provide `onRefresh`, `onCameraSettings`. |
| `LiveStreamingTab` | Manage streaming sessions | Needs `streamingStatus` and handlers for start/stop. |
| `VideoArchiveTab` | Browse recordings | Virtualised list for performance. Requires `onLoadFolderVideos`. |
| `buildApiUrl`, `buildWsUrl` | Build endpoints | Always use these helpers; they respect Vite env vars. |

---

## 9. When Something Goes Wrong

1. **Viewer stuck on “connecting”**  
   - Check browser dev tools for blocked WebSocket or MJPEG request. Usually the backend isn’t streaming or the token expired. Attempt logout/login to refresh tokens.

2. **Black screen with “Live streaming is not available”**  
   - `CameraViewer` sets this when the backend responds with an error. Confirm recording is running—otherwise the streaming endpoints send `no_frame`.

3. **Tabs show stale data after actions**  
   - Make sure you call `handleRefresh()` (which picks the right loader depending on the active tab) once an API action completes.

4. **Fullscreen dialog never closes**  
   - `CameraPage` automatically closes it if `mySession.websocket_state !== 'connected'`. Ensure you update `mySession` when the session stops.

5. **Archive folders blank after refresh**  
   - `VideoArchiveTab` keeps per-folder state. If your API returns a different structure, clear `folderState` in `useEffect` or normalise the payload before setting state.

Follow these guardrails and the camera UI will stay reliable while you extend it.
