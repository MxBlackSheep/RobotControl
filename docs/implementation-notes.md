## 2025-10-14 Camera Page Streamlining

- Camera page now focuses on two tabs (Archive + Live Streaming); dropped the inline system-status modal and live camera grid so health info stays on the dedicated System Status screen (`frontend/src/pages/CameraPage.tsx:392-760`).
- Streaming panel shows only session ID and connection state while keeping fullscreen playback support; removed quality/bandwidth/FPS details per UX request (`frontend/src/pages/CameraPage.tsx:660-750`).
- Video archive folders/files wrap cleanly on mobile and always expose action buttons thanks to responsive tweaks and loading spinners (`frontend/src/components/camera/VideoArchiveTab.tsx:200-464`).

## 2025-10-14 Scheduling Recovery Reference & Camera Notes

- Interval miss grace is half the configured interval hours; see `backend/services/scheduling/scheduler_engine.py:575-599` where `_find_due_jobs` computes `grace_period_minutes = (experiment.interval_hours * 60) / 2`.
- Missed runs log `start_time` plus the current timestamp as `end_time`, so execution history shows a long `calculated_duration_minutes`; originates in `_find_due_jobs` (`backend/services/scheduling/scheduler_engine.py:583-599`) and the formatter `get_execution_history` (`backend/services/scheduling/sqlite_database.py:1399-1424`).
- New pre-execution steps register via `_register_builtin_steps` (`backend/services/scheduling/pre_execution.py:103-160`); implement handlers with cleanup similar to `_scheduled_to_run_step`.
