# Camera maintenance

## Ownership and recovery

`CameraService` is the public coordinator. `camera_runtime.py` serializes device selection, connection, recording and stop requests. `camera_worker.py` is the only code that opens the selected camera or its recording writer. The helper is a Windows spawned process, so a blocked native driver call can be recovered without restarting RobotControl.

Recovery is manual. Stop requests allow 15 seconds for clip finalization, then may terminate only the helper. Its exit must be verified before replacement. Every helper owns fresh IPC resources and a generation ID. Old frames/events cannot enter a replacement connection. The main application retains scheduling, SQL monitoring, archive coordination and viewer sessions.

The preview transport has one fixed 640x480 colour frame slot. Recording remains in the helper and does not depend on a browser. Clip events use acknowledgements; completed clips also have durable JSON sidecars so they can be recovered after a parent interruption. Do not introduce frame queues or open devices from API handlers.

## Selecting and connecting a device

DirectShow enumeration reads friendly names and device paths without opening cameras. Numeric indexes are temporary. The selection is saved in `data/config/camera_selection.json` (swapped in with `utils/filesystem.replace_file`, so a scanner reading it cannot fail a reselection), then resolved and checked around every camera open. Missing/ambiguous identities require explicit selection. Identical model names are distinguished in the UI by the current device number. Changing USB ports can change identity and require reselection.

On a new installation, automatic startup uses the configured primary index only when it can resolve a unique identity. A missing camera leaves automatic recording waiting. Refresh/select/connect after attaching it; there is no retry loop. First selection can retain waiting recording intent. Changing an existing selection requires stopping recording. Reconnect preserves recording intent; reconnect after an intentional stop supplies preview only.

## API and permissions

All paths below are beneath `/api/camera`:

- `GET /control-status`: authenticated, cached devices, health and operation state. No hardware probing.
- `POST /devices/refresh`: admin-only device enumeration.
- `PATCH /selection`: admin-only, JSON `{ "device_identity": "..." }`.
- `POST /connect`, `/reconnect`, `/recording/start`, `/recording/stop`: admin-only operations.

Operations return HTTP 202 with `data.operation.id`. Poll control-status for pending/succeeded/failed and errors. Overlapping operations return 409. The operation revision distinguishes a newer operation initiated by another administrator. Existing numeric recording APIs remain adapters and run blocking operations off the API event loop. The legacy public health endpoint retains limited fields; detailed identities require authentication.

Capture state, recording state, automation state and viewer connection are separate. A live process is not proof of recording. `CAMERA_CONFIG.no_frame_seconds` defaults to 10; `startup_seconds` defaults to 20. Both use monotonic time. Repeated images count as frames and are not analyzed for scene changes. No camera failure changes Hamilton execution status or triggers completion callbacks.

## Clips and storage

Keep the existing 640x480 capture request, 30 FPS camera setting, MJPEG AVI format, measured rolling recording rate capped at 7.5 FPS, one-minute clips, 120-clip rolling limit and 15-minute archive window. Do not change quality as part of recovery work.

Active or interrupted files end in `.partial.avi`. They are excluded from normal cleanup, archive selection and finalized downloads. They remain available for operator investigation; do not label them complete or delete them automatically. Completed new clips have JSON sidecars containing actual frame counts, elapsed duration, device identity and generation. Legacy clips without sidecars keep unknown counts rather than invented values. Cleanup removes sidecars with expired finalized clips.

Archival still follows Hamilton completion, including existing run association and paused-state rules. Registering the same completion callback repeatedly must remain idempotent. A camera reconnect must not register duplicate archival callbacks.

Recording downloads support GET/HEAD and byte ranges for resumable remote downloads. Preserve archive directory naming and existing API envelopes. Runtime configuration is separate from SQLite; this change requires no database migration.

## Troubleshooting and validation

Check control-status capture state, frame age, last-write age, heartbeat age, read-failure count, generation and operation error. A fresh heartbeat with old frames can mean a blocked capture/writer call. A repeated still image alone is inconclusive. Opt-in resource diagnostics include these counters without recording image payloads.

Run `uv run --locked python -m pytest backend/tests/test_camera.py backend/tests/test_camera_worker.py backend/tests/test_camera_control_api.py backend/tests/test_automatic_recording.py backend/tests/test_camera_download_api.py`. Tests must mock device enumeration and use temporary storage. Never run hardware probes through a production CameraService instance.

Windows packaging must retain early `multiprocessing.freeze_support()` before application imports. Verify packaged recording and reconnect; source tests alone do not exercise frozen child startup. Preserve the previous package and runtime data. See `docs/camera-recovery-validation.md` for measured results and outstanding physical/endurance checks.
