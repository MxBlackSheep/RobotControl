# Camera Service Maintenance Guide

This guide demystifies the camera stack. It explains what each file does, how frames move from a physical camera to the UI, and what to touch when you need to add or change behaviour. Everything is written for cautious maintainers who prefer explicit, step-by-step instructions.

---

## 1. High-Level Architecture

- `backend/services/camera.py`  
  Singleton façade exposed to the rest of the backend. Handles camera discovery, starts/stops recording threads, pushes frames into the shared buffer, archives clips, and exposes health/status helpers.

- `backend/services/live_streaming.py`  
  Manages WebSocket sessions and distributes frames to viewers. Pulls frames from `SharedFrameBuffer`, applies quality throttling, and coordinates streaming sessions per user.

- `backend/services/shared_frame_buffer.py`  
  Thread-safe ring buffer that records use to publish frames and streaming use to read them. Guarantees recording always wins if there is contention.

- `backend/services/automatic_recording.py`  
  Higher-level orchestrator that decides when automatic recording starts/stops based on experiment state; it calls into `CameraService` to do actual work.

- `backend/services/storage_manager.py`  
  Filesystem helper used when archiving clips for experiments (copies files into experiment-specific folders, cleans up old folders).

- `frontend/src/components/CameraViewer.tsx`  
  React component that connects to the backend (MJPEG stream + WebSocket), displays status badges, and surfaces errors when streaming is unavailable.

- `frontend/src/components/camera/*Tab.tsx`  
  UI tabs for live view, streaming management, and archive browsing. They rely on `CameraViewer` for the actual stream widget.

**Rule of thumb:** Treat `CameraService` as the single entry point for backend camera operations. Other services/components should not open cameras themselves or bypass the shared frame buffer.

---

## 2. Frame Lifecycle Cheat Sheet

1. **Camera discovery** (`CameraService.detect_cameras`).  
   Opens each camera ID via OpenCV, probes resolution/FPS, and caches the info in `self.cameras`.

2. **Recording start** (`CameraService.start_recording`).  
   Creates a stop event, spawns a dedicated `_recording_worker` thread, and marks the camera as recording. If streaming integration is not enabled yet, it calls `enable_streaming_integration()` to wire up the shared buffer.

3. **Frame capture** (`_recording_worker`).  
   Reads frames from OpenCV. Each frame is written to the rolling clip writer *and* pushed into `SharedFrameBuffer.put_frame(frame)` so streaming clients can consume it.

4. **Clip rotation** (`_recording_worker`).  
   Every `recording_duration_minutes` minutes, releases the current video writer, records metadata (path, timestamp, frame count) in `self.rolling_clips`, and starts a new clip.

5. **Streaming distribution** (`LiveStreamingService._frame_distribution_loop`).  
   Grabs frames from `SharedFrameBuffer`, sends them to active WebSocket sessions, and keeps statistics about bandwidth/CPU usage.

6. **Frontend display** (`CameraViewer.tsx`).  
   Requests frames via WebSocket (`request_frame` messages) and updates an `<img>` element with base64 JPEG data. If the backend responds with `no_frame`, the component shows “Live streaming is not available…”, so users know to start recording first.

7. **Archive export** (`CameraService.archive_experiment_videos`).  
   Uses `StorageManager` to copy recent rolling clips into an experiment folder when experiments complete.

8. **Recording stop** (`CameraService.stop_recording`).  
   Sets the stop event, joins the recording thread, cleans up clip metadata, and marks the camera as idle.

---

## 3. Key Data Structures & Settings

- `CAMERA_CONFIG` (`backend/config.py`)  
  Dict controlling max cameras, clip length, rolling buffer size, default FPS/resolution. Alter this when you need to adjust recording behaviour.

- `CameraRecordingModel` (`backend/models.py`)  
  Captures metadata for single clips (camera ID, filename, timestamp, duration, file size, recording type). The archive/REST APIs serialise this model.

- `LIVE_STREAMING_CONFIG` (`backend/config.py`)  
  Streaming-specific knobs: enable flag, frame buffer size, quality presets, CPU thresholds, bandwidth limits.

- `SharedFrameBuffer.FrameData` (`backend/services/shared_frame_buffer.py`)  
  Wrapper storing raw frame, timestamp, frame number, and size. Streaming callbacks receive this structure.

- Frontend state (`CameraViewer.tsx`)  
  `isStreaming`, `connectionStatus`, `error`, `frameCount`, `lastFrameTime`, and `streamQuality`. These fields drive the status chips and error banners.

---

## 4. How to Add or Modify Functionality

### 4.1 Add a New Camera Setting
1. Define the setting in `CAMERA_CONFIG` (or `LIVE_STREAMING_CONFIG`). Give it a sensible default.
2. Thread the value into `CameraService.__init__` (or `LiveStreamingService.__init__`) and store it as an attribute.
3. If the setting is user-configurable, expose it via `backend/api/camera.py` and update the frontend forms/types (`frontend/src/types/camera.ts` if you introduce one, otherwise extend existing props).
4. Document the behaviour in the appropriate maintenance guide and test manually.

### 4.2 Support a New Frame Consumer
1. If it needs live frames, register a callback with `SharedFrameBuffer.register_streaming_callback` **or** expose a dedicated method on `LiveStreamingService`. Avoid reading the buffer directly from elsewhere.
2. Ensure the callback is resilient (non-blocking, catches exceptions). Long-running processing should happen in a background task, not in the callback.
3. If the consumer requires configuration, update `LIVE_STREAMING_CONFIG` and pass the values through `LiveStreamingService`.
4. Update documentation and add logging so operators know the new consumer is active.

### 4.3 Extend Archiving Logic
1. Modify `CameraService.archive_experiment_videos`. Always use `StorageManager` helpers instead of raw `shutil` calls, so folder structure stays consistent.
2. If you need extra metadata in the archive directories, extend `StorageManager.archive_experiment_videos` to include it (e.g., JSON manifest).
3. Update frontend archive tabs to display the new information.
4. Make sure the cleanup routines (`_cleanup_old_clips`, `StorageManager` cleanup) are still correct.

---

## 5. Common Maintenance Tasks

| Task | Where | Tips |
|------|-------|------|
| Detect cameras again | `CameraService.detect_cameras()` | Run this at startup. Re-running will refresh `self.cameras`, but make sure no recordings are active. |
| Start/stop recording | `CameraService.start_recording(camera_id)` / `stop_recording(camera_id)` | Always call `stop_recording` in `finally` blocks to release the OpenCV handle. |
| Update stream quality defaults | `CameraViewer.tsx` (`getFps`, stream quality state), `LIVE_STREAMING_CONFIG` | Keep backend and frontend quality options in sync. |
| Archive clips manually | `CameraService.archive_experiment_videos(experiment_id, method_name)` | Works even if automatic recording is disabled, provided rolling clips exist. |
| Clean orphaned clips | `_cleanup_old_clips()` | Called automatically, but you can run it after changing clip limits. |
| Check health | `CameraService.health_check()` | Returns storage availability, active threads, and a timestamp – use this for monitoring dashboards. |

---

## 6. Extension Points & Gotchas

- **OpenCV handles**: Each camera ID maps to a single OpenCV capture. Never open the same ID twice without releasing the old handle; otherwise, you’ll get black frames.
- **Thread safety**: Stick to the provided locks (`camera_lock`, `clips_lock`, `SharedFrameBuffer` locks). Do not manipulate `rolling_clips` without holding `clips_lock`.
- **Streaming availability**: If streaming is disabled (`LIVE_STREAMING_CONFIG["enabled"] = False`), `CameraService.get_live_frame` returns `None`. The frontend already shows a banner, so backend APIs should propagate the `no_frame` message rather than fabricating data.
- **Disk space**: Rolling clips and archives live under `VIDEO_PATH`. Ensure there’s enough space (check `CameraService.health_check()["free_disk_space_gb"]`) before enabling long recordings.
- **MJPEG vs WebSocket**: The MJPEG endpoint is a basic fallback. Prefer the WebSocket for modern features (quality switches, error notifications). Keep both in sync when changing frame handling.
- **Automatic recording**: `AutomaticRecordingService` will start recording the primary camera on startup if enabled. When debugging manual behaviour, disable auto recording in `AUTO_RECORDING_CONFIG` to avoid unexpected threads.

---

## 7. Quick Reference

| Function / Method | Purpose | Notes |
|-------------------|---------|-------|
| `CameraService.detect_cameras()` | Probe available cameras | Should be called once during startup. |
| `CameraService.start_recording(camera_id)` | Spawn recording thread | Returns `False` if already recording or camera missing. |
| `CameraService.stop_recording(camera_id)` | Stop recording | Joins the worker thread and cleans metadata. |
| `CameraService.get_live_frame(camera_id)` | Fetch JPEG bytes for UI | Uses `LiveStreamingService`; returns `None` if streaming unavailable. |
| `CameraService.archive_experiment_videos(experiment_id, method)` | Copy clips for an experiment | Utilises `StorageManager`; returns archive path string. |
| `LiveStreamingService.create_session(user_id, ...)` | Register a new WebSocket session | Handles capacity checks and returns session metadata. |
| `SharedFrameBuffer.put_frame(frame)` | Publish frame from recording worker | Should be called for every captured frame. |
| `SharedFrameBuffer.get_frame_for_streaming()` | Non-blocking frame read | Streaming loops use this to grab the latest frame. |

---

## 8. When Something Goes Wrong

1. **Black screen or “stream unavailable” banner**  
   - Check if the camera is recording (`CameraService.recording_threads`).  
   - Confirm `LiveStreamingService.enabled` is `True`.  
   - Ensure the frontend received frames (look for `frame` messages in dev tools).

2. **High CPU usage**  
   - Inspect `LiveStreamingService` logs for resource limit warnings.  
   - Reduce `frame_buffer_size` or lower quality defaults.  
   - Check that no other process is holding camera handles (e.g., Windows camera app).

3. **Clips not archiving**  
   - Confirm rolling clips exist (`rolling_clips` deque has entries).  
  - Make sure `StorageManager` paths (`VIDEO_PATH/experiments`) are writable.  
   - Check logs for “Archive warning” messages to see why copies failed.

4. **Disk fills up quickly**  
   - Lower `CAMERA_CONFIG["rolling_clips_count"]` or `recording_duration_minutes`.  
   - Run `_cleanup_old_clips()` manually.  
   - Schedule a cron job to move archives to long-term storage if needed.

5. **WebSocket disconnects frequently**  
   - Inspect browser console for `no_frame` events (means recording stopped).  
   - Check server logs for bandwidth warnings (may need to reduce quality).  
   - Verify the client’s network (mobile networks are prone to timeouts).

---

## 9. Adding or Replacing Modules

1. **Starting point**: if you create new camera-related logic, place it under `backend/services/` and expose a clean method on `CameraService` rather than creating ad-hoc global functions.
2. **Integrate with streaming**: all live viewers should ultimately read from `SharedFrameBuffer`. If your module needs raw frames, register a callback or retrieve frames via the existing buffer interface.
3. **Document changes**: update this guide, `docs/implementation-notes.md`, and any relevant README sections so future maintainers know how to use the new module.
4. **Test manually**: because camera/streaming interactions depend on hardware, run at least one end-to-end test (start recording, view stream, archive clips) after major changes.

Keep this guide handy whenever you need to touch the camera stack. Following the stages above will help you avoid race conditions, blank streams, and mysterious file leaks.
