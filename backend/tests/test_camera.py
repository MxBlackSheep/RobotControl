"""Camera tests use isolated storage and never enumerate or open physical devices."""
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from backend.services.camera import CameraService
from backend.services.camera_runtime import CameraRuntime
from backend.services.camera_devices import resolve_device

DEVICES = [{"id": 0, "name": "USB camera", "device_identity": "usb:a", "status": "available"},
           {"id": 3, "name": "USB camera", "device_identity": "usb:b", "status": "available"}]

class TestCameraService:
    @pytest.fixture
    def temp_video_path(self, tmp_path):
        return tmp_path / "videos"

    @pytest.fixture
    def camera_service(self, temp_video_path):
        with patch("backend.services.camera.VIDEO_PATH", str(temp_video_path)), patch(
                "backend.services.camera_runtime.enumerate_devices", return_value=DEVICES):
            CameraService._instance = None
            service = CameraService()
            from backend.services.storage_manager import StorageManager
            with patch("backend.services.storage_manager.VIDEO_PATH", str(temp_video_path)):
                service._storage_manager = StorageManager()
            yield service
            service.shutdown()
            CameraService._instance = None

class TestExperimentArchiving(TestCameraService):
    """Tests for experiment video archiving"""
    
    def test_archive_experiment_videos_success(self, camera_service, temp_video_path):
        """Test successful experiment video archiving"""
        # Create some mock clips
        now = datetime.now()
        for i in range(3):
            clip_path = camera_service.rolling_clips_path / f"clip_{i}.mp4"
            clip_path.touch()
            
            camera_service.rolling_clips.append({
                "path": str(clip_path),
                "timestamp": now - timedelta(minutes=i),
                "camera_id": 0,
                "frame_count": 100
            })
        
        # Archive experiment
        archive_path = camera_service.archive_experiment_videos(123, "TestMethod")
        
        # Verify archive directory was created
        archive_dir = Path(archive_path)
        assert archive_dir.exists()
        assert archive_dir.is_dir()
        assert "TestMethod" in archive_dir.name
    
    def test_archive_experiment_videos_with_old_clips(self, camera_service, temp_video_path):
        """Test archiving when some clips are too old"""
        # Create clips with varying timestamps
        now = datetime.now()
        for i in range(5):
            clip_path = camera_service.rolling_clips_path / f"clip_{i}.mp4"
            clip_path.touch()
            
            # Make some clips older than archive duration
            timestamp = now - timedelta(minutes=i * 10)
            
            camera_service.rolling_clips.append({
                "path": str(clip_path),
                "timestamp": timestamp,
                "camera_id": 0,
                "frame_count": 100
            })
        
        archive_path = camera_service.archive_experiment_videos(123, "TestMethod")
        
        # Verify only recent clips were archived
        archive_dir = Path(archive_path)
        archived_files = list(archive_dir.glob("*.mp4"))
        
        # Should have fewer files than total clips due to age filtering
        assert len(archived_files) < 5



class TestCameraLifecycle(TestCameraService):
    def test_discovery_replaces_stale_entries_without_capture(self, camera_service):
        with patch("cv2.VideoCapture") as capture:
            assert len(camera_service.detect_cameras()) == 2
            with patch("backend.services.camera_runtime.enumerate_devices", return_value=[]):
                assert camera_service.detect_cameras() == []
            assert camera_service.cameras == {}
            capture.assert_not_called()

    def test_selected_identity_survives_index_changes(self, camera_service):
        runtime = camera_service.runtime
        runtime.run("select", identity="usb:b")
        assert runtime.identity == "usb:b"
        assert resolve_device([{**DEVICES[1], "id": 0}], runtime.identity)["id"] == 0
        restored = CameraRuntime(runtime.folder, 60, Mock(), Mock())
        assert restored.identity == "usb:b"

    @pytest.mark.parametrize("devices", [[], [DEVICES[0], DEVICES[0]]])
    def test_missing_or_ambiguous_identity_rejected(self, devices):
        with pytest.raises(ValueError, match="missing or ambiguous"):
            resolve_device(devices, "usb:a")

    def test_selection_cannot_change_recording(self, camera_service):
        runtime = camera_service.runtime
        runtime.identity = "usb:a"
        runtime.recording_requested = True
        with pytest.raises(ValueError, match="Stop recording"):
            runtime.run("select", identity="usb:b")

    def test_first_selection_preserves_waiting_recording_intent(self, camera_service):
        runtime = camera_service.runtime
        runtime.recording_requested = True
        runtime.run("select", identity="usb:a")
        assert runtime.identity == "usb:a"
        assert runtime.recording_requested

    def test_concurrent_operations_rejected(self, camera_service):
        runtime = camera_service.runtime
        runtime.operation_lock.acquire()
        try:
            with pytest.raises(ValueError, match="in progress"):
                runtime.submit("reconnect")
            with pytest.raises(ValueError, match="in progress"):
                runtime.run("start", camera_id=0)
        finally:
            runtime.operation_lock.release()

    def test_failed_start_never_reports_recording(self, camera_service):
        with patch.object(camera_service.runtime, "connect", side_effect=RuntimeError("open failed")):
            assert not camera_service.start_recording(0)
        assert camera_service.get_camera_status()["cameras_recording"] == 0

    def test_second_camera_rejected_without_changing_intent(self, camera_service):
        runtime = camera_service.runtime
        runtime.process = Mock()
        runtime.camera_id = 0
        runtime.recording_requested = True
        try:
            with pytest.raises(ValueError, match="Only one"):
                runtime.connect(True, camera_id=3)
            assert runtime.recording_requested
        finally:
            runtime.process = None

    @pytest.mark.parametrize("age,state", [(0, "connected"), (9.99, "connected"), (10, "no_frames"), (80, "no_frames")])
    def test_freshness_boundary_not_pixel_content(self, camera_service, age, state):
        runtime = camera_service.runtime
        runtime.process = Mock()
        runtime.process.is_alive.return_value = True
        runtime.ready = runtime.recording_requested = True
        runtime.counters[1] = 100
        try:
            with patch("backend.services.camera_runtime.time.monotonic", return_value=100+age):
                assert runtime.status()["capture_state"] == state
                assert (runtime.status()["recording_state"] == "recording") == (state == "connected")
        finally:
            runtime.process = None

    def test_force_stop_verifies_exit_before_forgetting_worker(self, camera_service):
        runtime = camera_service.runtime
        process = runtime.process = Mock()
        runtime.stop_event, runtime.monitor, runtime.events = Mock(), Mock(), Mock()
        runtime.monitor.is_alive.return_value = False
        process.is_alive.side_effect = [True, True]
        with pytest.raises(RuntimeError, match="could not be stopped"):
            runtime._stop()
        assert runtime.process is process
        process.close.assert_not_called()
        process.is_alive.side_effect = [True, False]
        runtime._stop()
        assert runtime.process is None
        process.close.assert_called_once()

    def test_manual_stop_clears_recording_intent(self, camera_service):
        runtime = camera_service.runtime
        runtime.recording_requested = True
        with patch.object(runtime, "_stop"):
            runtime.run("stop")
        with patch.object(runtime, "connect") as connect:
            runtime.run("reconnect")
            connect.assert_called_once_with(camera_id=None)
        assert not runtime.recording_requested

    def test_blocked_helper_is_terminated_and_reaped(self, camera_service):
        import multiprocessing
        import time
        runtime = camera_service.runtime
        context = multiprocessing.get_context("spawn")
        process = context.Process(target=time.sleep, args=(60,))
        process.start()
        runtime.process = process
        runtime.stop_event = context.Event()
        runtime.events = Mock()
        runtime.graceful_stop_seconds = .1
        runtime._stop()
        assert runtime.process is None
        assert process not in multiprocessing.active_children()

    def test_reconcile_preserves_metadata_excludes_partial(self, camera_service):
        import json
        folder = camera_service.rolling_clips_path
        final = folder / "clip_new.avi"
        final.write_bytes(b"video")
        final.with_suffix(".json").write_text(json.dumps({"timestamp": datetime.now().isoformat(),
            "camera_id": 3, "frame_count": 42, "actual_duration": 7, "device_identity": "usb:b"}))
        partial = folder / "clip_failed.partial.avi"
        partial.write_bytes(b"partial")
        camera_service._sync_memory_with_filesystem()
        assert len(camera_service.rolling_clips) == 1
        assert camera_service.rolling_clips[0]["frame_count"] == 42
        assert camera_service.rolling_clips[0]["camera_id"] == 3
        camera_service._cleanup_orphaned_files()
        assert partial.exists()

    def test_legacy_metadata_is_unknown(self, camera_service):
        (camera_service.rolling_clips_path / "clip_20260101_120000.avi").touch()
        camera_service._sync_memory_with_filesystem()
        assert camera_service.rolling_clips[0]["frame_count"] is None

    def test_health_when_disconnected_is_not_healthy(self, camera_service):
        assert not camera_service.health_check()["healthy"]
