"""
Comprehensive tests for the simplified camera service

Tests cover:
- Camera detection and initialization
- Recording functionality with mocked hardware
- Live streaming capabilities
- Archive management
- Error handling and edge cases
- Thread safety and resource cleanup
"""

import pytest
import asyncio
import threading
import time
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
from datetime import datetime, timedelta
from collections import deque

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.services.camera import CameraService
from shared.config import CAMERA_CONFIG


class TestCameraService:
    """Test suite for CameraService"""
    
    @pytest.fixture
    def temp_video_path(self):
        """Create temporary directory for video storage during tests"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def camera_service(self, temp_video_path):
        """Create camera service instance with mocked video path"""
        with patch('backend.services.camera.VIDEO_PATH', str(temp_video_path)):
            # Reset singleton
            CameraService._instance = None
            service = CameraService()
            service.video_path = temp_video_path
            service.rolling_clips_path = temp_video_path / "rolling_clips"
            service.experiments_path = temp_video_path / "experiments"
            service._create_directories()
            yield service
            # Cleanup
            service.shutdown()
            CameraService._instance = None
    
    @pytest.fixture
    def mock_cv2(self):
        """Mock OpenCV for testing without hardware"""
        with patch('cv2.VideoCapture') as mock_cap_class:
            mock_cap = Mock()
            mock_cap_class.return_value = mock_cap
            
            # Configure mock camera to simulate working camera
            mock_cap.isOpened.return_value = True
            mock_cap.get.side_effect = lambda prop: {
                'cv2.CAP_PROP_FRAME_WIDTH': 640,
                'cv2.CAP_PROP_FRAME_HEIGHT': 480,
                'cv2.CAP_PROP_FPS': 30
            }.get(str(prop), 30)
            
            # Mock successful frame reading
            import numpy as np
            fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            mock_cap.read.return_value = (True, fake_frame)
            
            yield mock_cap_class, mock_cap


class TestCameraDetection(TestCameraService):
    """Tests for camera detection functionality"""
    
    def test_detect_cameras_with_working_cameras(self, camera_service, mock_cv2):
        """Test detection of working cameras"""
        mock_cap_class, mock_cap = mock_cv2
        
        # Test detection
        cameras = camera_service.detect_cameras()
        
        # Verify results
        assert len(cameras) == CAMERA_CONFIG["max_cameras"]
        for i, camera in enumerate(cameras):
            assert camera["id"] == i
            assert camera["name"] == f"Camera {i}"
            assert camera["width"] == 640
            assert camera["height"] == 480
            assert camera["fps"] == 30
            assert camera["status"] == "available"
        
        # Verify cameras are stored in service
        assert len(camera_service.cameras) == CAMERA_CONFIG["max_cameras"]
    
    def test_detect_cameras_with_no_cameras(self, camera_service):
        """Test detection when no cameras are available"""
        with patch('cv2.VideoCapture') as mock_cap_class:
            mock_cap = Mock()
            mock_cap_class.return_value = mock_cap
            mock_cap.isOpened.return_value = False
            
            cameras = camera_service.detect_cameras()
            
            assert len(cameras) == 0
            assert len(camera_service.cameras) == 0
    
    def test_detect_cameras_with_partial_failure(self, camera_service):
        """Test detection with some cameras failing"""
        with patch('cv2.VideoCapture') as mock_cap_class:
            def mock_camera_open(camera_id, backend=None):
                mock_cap = Mock()
                # Only camera 0 works
                mock_cap.isOpened.return_value = (camera_id == 0)
                if camera_id == 0:
                    mock_cap.get.side_effect = lambda prop: 640 if 'WIDTH' in str(prop) else 480 if 'HEIGHT' in str(prop) else 30
                return mock_cap
            
            mock_cap_class.side_effect = mock_camera_open
            
            cameras = camera_service.detect_cameras()
            
            assert len(cameras) == 1
            assert cameras[0]["id"] == 0


class TestCameraRecording(TestCameraService):
    """Tests for camera recording functionality"""
    
    def test_start_recording_success(self, camera_service, mock_cv2):
        """Test successful recording start"""
        mock_cap_class, mock_cap = mock_cv2
        
        # Setup cameras
        camera_service.detect_cameras()
        
        # Start recording
        success = camera_service.start_recording(0)
        
        assert success is True
        assert 0 in camera_service.recording_threads
        assert 0 in camera_service.stop_events
        assert 0 in camera_service.frame_locks
        assert camera_service.recording_threads[0].is_alive()
    
    def test_start_recording_camera_not_found(self, camera_service):
        """Test recording start with invalid camera"""
        success = camera_service.start_recording(999)
        assert success is False
    
    def test_start_recording_already_recording(self, camera_service, mock_cv2):
        """Test starting recording on already recording camera"""
        mock_cap_class, mock_cap = mock_cv2
        camera_service.detect_cameras()
        
        # Start recording first time
        success1 = camera_service.start_recording(0)
        assert success1 is True
        
        # Try to start again
        success2 = camera_service.start_recording(0)
        assert success2 is False
    
    def test_stop_recording_success(self, camera_service, mock_cv2):
        """Test successful recording stop"""
        mock_cap_class, mock_cap = mock_cv2
        camera_service.detect_cameras()
        
        # Start then stop recording
        camera_service.start_recording(0)
        success = camera_service.stop_recording(0)
        
        assert success is True
        assert 0 not in camera_service.recording_threads
        assert 0 not in camera_service.stop_events
        assert 0 not in camera_service.frame_locks
    
    def test_stop_recording_not_recording(self, camera_service, mock_cv2):
        """Test stopping recording on camera that's not recording"""
        mock_cap_class, mock_cap = mock_cv2
        camera_service.detect_cameras()
        
        success = camera_service.stop_recording(0)
        assert success is False
    
    def test_stop_recording_camera_not_found(self, camera_service):
        """Test stopping recording on invalid camera"""
        success = camera_service.stop_recording(999)
        assert success is False


class TestRecordingWorker(TestCameraService):
    """Tests for the recording worker thread"""
    
    @patch('cv2.VideoWriter')
    @patch('cv2.imencode')
    def test_recording_worker_frame_processing(self, mock_imencode, mock_writer_class, camera_service, mock_cv2):
        """Test that recording worker processes frames correctly"""
        mock_cap_class, mock_cap = mock_cv2
        
        # Setup video writer mock
        mock_writer = Mock()
        mock_writer_class.return_value = mock_writer
        mock_writer.isOpened.return_value = True
        
        # Setup frame encoding mock
        import numpy as np
        mock_imencode.return_value = (True, np.array([1, 2, 3]))
        
        camera_service.detect_cameras()
        
        # Start recording for short duration
        camera_service.start_recording(0)
        
        # Wait a bit for frames to be processed
        time.sleep(0.5)
        
        # Stop recording
        camera_service.stop_recording(0)
        
        # Verify video writer was called
        assert mock_writer.write.called
        assert mock_writer.release.called
    
    def test_recording_worker_cleanup_old_clips(self, camera_service, mock_cv2):
        """Test that old clips are cleaned up properly"""
        mock_cap_class, mock_cap = mock_cv2
        
        # Reduce rolling clips count for testing
        camera_service.rolling_clips_count = 3
        camera_service.rolling_clips = deque(maxlen=3)
        
        # Add some mock clips
        for i in range(5):
            clip_path = camera_service.rolling_clips_path / f"test_clip_{i}.mp4"
            clip_path.touch()  # Create empty file
            
            camera_service.rolling_clips.append({
                "path": str(clip_path),
                "timestamp": datetime.now(),
                "camera_id": 0,
                "frame_count": 100
            })
        
        # Trigger cleanup
        camera_service._cleanup_old_clips()
        
        # Check that clips were limited
        assert len(camera_service.rolling_clips) <= camera_service.rolling_clips_count


class TestLiveStreaming(TestCameraService):
    """Tests for live streaming functionality"""
    
    def test_get_live_frame_success(self, camera_service, mock_cv2):
        """Test getting live frame when camera is recording"""
        mock_cap_class, mock_cap = mock_cv2
        camera_service.detect_cameras()
        
        # Setup frame data
        test_frame_data = b"fake_jpeg_data"
        camera_service.frame_locks[0] = threading.Lock()
        camera_service.shared_frames[0] = test_frame_data
        
        frame = camera_service.get_live_frame(0)
        assert frame == test_frame_data
    
    def test_get_live_frame_no_camera(self, camera_service):
        """Test getting live frame from non-existent camera"""
        frame = camera_service.get_live_frame(999)
        assert frame is None
    
    def test_get_live_frame_not_recording(self, camera_service, mock_cv2):
        """Test getting live frame when camera is not recording"""
        mock_cap_class, mock_cap = mock_cv2
        camera_service.detect_cameras()
        
        frame = camera_service.get_live_frame(0)
        assert frame is None


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


class TestCameraStatus(TestCameraService):
    """Tests for camera status and health monitoring"""
    
    def test_get_camera_status(self, camera_service, mock_cv2):
        """Test getting comprehensive camera status"""
        mock_cap_class, mock_cap = mock_cv2
        camera_service.detect_cameras()
        camera_service.start_recording(0)
        
        status = camera_service.get_camera_status()
        
        assert "cameras_detected" in status
        assert "cameras_recording" in status
        assert "rolling_clips_count" in status
        assert "cameras" in status
        assert status["cameras_detected"] == CAMERA_CONFIG["max_cameras"]
        assert status["cameras_recording"] == 1
        
        # Check individual camera status
        camera_status = status["cameras"][0]
        assert camera_status["recording"] is True
        assert camera_status["has_live_stream"] is False  # No shared frame yet
    
    def test_get_recent_clips(self, camera_service, temp_video_path):
        """Test getting recent clips list"""
        # Add some mock clips
        for i in range(5):
            clip_path = camera_service.rolling_clips_path / f"clip_{i}.mp4"
            clip_path.write_bytes(b"fake video data")
            
            camera_service.rolling_clips.append({
                "path": str(clip_path),
                "timestamp": datetime.now(),
                "camera_id": 0,
                "frame_count": 100 + i
            })
        
        clips = camera_service.get_recent_clips(limit=3)
        
        assert len(clips) == 3
        for clip in clips:
            assert "filename" in clip
            assert "timestamp" in clip
            assert "camera_id" in clip
            assert "frame_count" in clip
            assert "size_bytes" in clip
    
    def test_health_check_healthy(self, camera_service, mock_cv2):
        """Test health check when system is healthy"""
        mock_cap_class, mock_cap = mock_cv2
        camera_service.detect_cameras()
        camera_service.start_recording(0)
        
        health = camera_service.health_check()
        
        assert "healthy" in health
        assert "storage_accessible" in health
        assert "active_recording_threads" in health
        assert "total_cameras" in health
        assert "free_disk_space_gb" in health
        assert "rolling_clips_count" in health
    
    def test_health_check_unhealthy_storage(self, camera_service):
        """Test health check with storage issues"""
        # Make video path inaccessible
        camera_service.video_path = Path("/nonexistent/path")
        
        health = camera_service.health_check()
        
        assert health["healthy"] is False
        assert health["storage_accessible"] is False


class TestThreadSafety(TestCameraService):
    """Tests for thread safety and concurrent operations"""
    
    def test_concurrent_camera_operations(self, camera_service, mock_cv2):
        """Test concurrent camera start/stop operations"""
        mock_cap_class, mock_cap = mock_cv2
        camera_service.detect_cameras()
        
        def start_stop_camera(camera_id):
            camera_service.start_recording(camera_id)
            time.sleep(0.1)
            camera_service.stop_recording(camera_id)
        
        # Start multiple threads doing camera operations
        threads = []
        for i in range(2):  # Use available cameras
            thread = threading.Thread(target=start_stop_camera, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5)
        
        # Verify clean state
        assert len(camera_service.recording_threads) == 0
        assert len(camera_service.stop_events) == 0
    
    def test_concurrent_clip_access(self, camera_service):
        """Test concurrent access to rolling clips"""
        def add_clips():
            for i in range(10):
                camera_service.rolling_clips.append({
                    "path": f"clip_{i}.mp4",
                    "timestamp": datetime.now(),
                    "camera_id": 0,
                    "frame_count": 100
                })
        
        def read_clips():
            for _ in range(10):
                camera_service.get_recent_clips(limit=5)
                time.sleep(0.01)
        
        # Start concurrent operations
        threads = [
            threading.Thread(target=add_clips),
            threading.Thread(target=read_clips),
            threading.Thread(target=read_clips)
        ]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join(timeout=5)
        
        # Verify no exceptions occurred and clips exist
        assert len(camera_service.rolling_clips) > 0


class TestErrorHandling(TestCameraService):
    """Tests for error handling and edge cases"""
    
    def test_recording_with_camera_failure(self, camera_service, mock_cv2):
        """Test recording behavior when camera fails during operation"""
        mock_cap_class, mock_cap = mock_cv2
        camera_service.detect_cameras()
        
        # Start recording
        camera_service.start_recording(0)
        
        # Simulate camera failure
        mock_cap.read.return_value = (False, None)
        
        # Wait for error handling
        time.sleep(0.5)
        
        # Recording should still be running (error tolerant)
        assert 0 in camera_service.recording_threads
    
    def test_cleanup_with_missing_files(self, camera_service):
        """Test cleanup when clip files are missing"""
        # Add clips with non-existent files
        for i in range(3):
            camera_service.rolling_clips.append({
                "path": f"/nonexistent/clip_{i}.mp4",
                "timestamp": datetime.now(),
                "camera_id": 0,
                "frame_count": 100
            })
        
        # Should not raise exception
        camera_service._cleanup_old_clips()
    
    def test_shutdown_with_active_recordings(self, camera_service, mock_cv2):
        """Test service shutdown with active recordings"""
        mock_cap_class, mock_cap = mock_cv2
        camera_service.detect_cameras()
        
        # Start recordings
        camera_service.start_recording(0)
        if len(camera_service.cameras) > 1:
            camera_service.start_recording(1)
        
        # Shutdown should stop all recordings
        camera_service.shutdown()
        
        assert len(camera_service.recording_threads) == 0
        assert len(camera_service.stop_events) == 0


class TestSingletonBehavior:
    """Tests for singleton pattern behavior"""
    
    def test_singleton_instance(self):
        """Test that CameraService follows singleton pattern"""
        # Reset singleton
        CameraService._instance = None
        
        # Create two instances
        service1 = CameraService()
        service2 = CameraService()
        
        # Should be the same instance
        assert service1 is service2
        
        # Cleanup
        service1.shutdown()
        CameraService._instance = None
    
    def test_get_camera_service_function(self):
        """Test the get_camera_service helper function"""
        from backend.services.camera import get_camera_service
        
        # Reset singleton
        CameraService._instance = None
        
        service1 = get_camera_service()
        service2 = get_camera_service()
        
        assert service1 is service2
        assert isinstance(service1, CameraService)
        
        # Cleanup
        service1.shutdown()
        CameraService._instance = None


# Pytest configuration and fixtures
@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment"""
    # Ensure test directories exist
    test_data_dir = Path(__file__).parent.parent.parent / "data"
    test_data_dir.mkdir(exist_ok=True)
    
    yield
    
    # Cleanup after all tests
    CameraService._instance = None


if __name__ == "__main__":
    # Run tests directly with pytest
    pytest.main([__file__, "-v", "--tb=short"])