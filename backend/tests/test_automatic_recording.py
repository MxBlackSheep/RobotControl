"""
Automatic Recording Service Tests

Tests for automatic recording service initialization, configuration loading,
manual override scenarios, and error handling. Ensures service reliability
and proper integration with camera service and monitoring components.
"""

import pytest
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

from backend.services.automatic_recording import AutomaticRecordingService, get_automatic_recording_service
from backend.services.automatic_recording_types import (
    AutomationStatus, AutomationState, ExperimentState, ExperimentStateType, ArchiveResult
)


class TestAutomaticRecordingService:
    """Test suite for AutomaticRecordingService initialization and core functionality"""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton instance before each test"""
        AutomaticRecordingService._instance = None
        yield
        # Cleanup after test
        if AutomaticRecordingService._instance:
            try:
                AutomaticRecordingService._instance.stop_automatic_recording()
            except:
                pass
            AutomaticRecordingService._instance = None

    @pytest.fixture
    def mock_config(self):
        """Mock AUTO_RECORDING_CONFIG for testing"""
        config = {
            "enabled": True,
            "startup_delay_seconds": 2,  # Reduced for testing
            "primary_camera_id": 0,
            "rolling_clips_limit": 10,
            "experiment_folders_limit": 5,
            "archive_duration_minutes": 15,
            "experiment_check_interval": 5,
            "storage_cleanup_interval": 60
        }
        with patch('backend.services.automatic_recording.AUTO_RECORDING_CONFIG', config):
            yield config

    @pytest.fixture
    def mock_camera_service(self):
        """Mock camera service for testing"""
        mock_service = Mock()
        
        # Mock camera detection
        mock_service.detect_cameras.return_value = [
            {"id": 0, "name": "Camera 0", "width": 640, "height": 480, "fps": 30, "status": "available"},
            {"id": 1, "name": "Camera 1", "width": 640, "height": 480, "fps": 30, "status": "available"}
        ]
        
        # Mock recording control
        mock_service.start_recording.return_value = True
        mock_service.stop_recording.return_value = True
        
        # Mock rolling clips
        mock_service.rolling_clips = deque(maxlen=10)
        mock_service.clips_lock = threading.Lock()
        
        return mock_service

    @pytest.fixture
    def mock_storage_manager(self):
        """Mock storage manager for testing"""
        mock_manager = Mock()
        
        # Mock storage statistics
        mock_manager.get_storage_statistics.return_value = {
            "rolling_clips_count": 5,
            "experiment_folders_count": 3
        }
        
        # Mock archive operation
        mock_archive_result = ArchiveResult(
            success=True,
            archive_path="/test/archive/path",
            clips_archived=5,
            archive_size_bytes=1024 * 1024  # 1MB
        )
        mock_manager.archive_experiment_videos.return_value = mock_archive_result
        
        return mock_manager

    @pytest.fixture
    def mock_experiment_monitor(self):
        """Mock experiment monitor for testing"""
        mock_monitor = Mock()
        
        mock_monitor.is_monitoring_active.return_value = False
        mock_monitor.start_monitoring.return_value = True
        mock_monitor.stop_monitoring.return_value = True
        mock_monitor.add_completion_callback = Mock()
        
        # Mock monitor stats
        mock_stats = Mock()
        mock_stats.last_check_time = datetime.now()
        mock_monitor.get_monitor_stats.return_value = mock_stats
        
        return mock_monitor


class TestServiceInitialization(TestAutomaticRecordingService):
    """Tests for service initialization and configuration loading"""

    def test_service_initialization_with_valid_config(self, mock_config):
        """Test service initializes correctly with valid configuration"""
        service = AutomaticRecordingService()
        
        # Verify configuration is loaded correctly
        assert service.startup_delay_seconds == 2
        assert service.primary_camera_id == 0
        assert service.enabled is True
        
        # Verify initial state
        assert service.current_state == AutomationState.STOPPED
        assert service.recording_camera_id is None
        assert service.automation_start_time is None
        assert service.manual_override_active is False
        assert service.error_message is None
        assert service.error_count == 0

    def test_service_singleton_pattern(self, mock_config):
        """Test that service follows singleton pattern correctly"""
        service1 = AutomaticRecordingService()
        service2 = AutomaticRecordingService()
        
        # Should be the same instance
        assert service1 is service2
        
        # Get service function should also return same instance
        service3 = get_automatic_recording_service()
        assert service1 is service3

    def test_service_initialization_thread_safety(self, mock_config):
        """Test that singleton initialization is thread-safe"""
        results = []
        
        def create_service():
            service = AutomaticRecordingService()
            results.append(service)
        
        # Create multiple threads that create service instances
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=create_service)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5)
        
        # All instances should be the same
        first_instance = results[0]
        for instance in results[1:]:
            assert instance is first_instance

    @patch('backend.services.automatic_recording.AUTO_RECORDING_CONFIG', {
        "enabled": False,
        "startup_delay_seconds": 10,
        "primary_camera_id": 1
    })
    def test_service_initialization_with_disabled_config(self):
        """Test service initialization when automatic recording is disabled"""
        service = AutomaticRecordingService()
        
        assert service.enabled is False
        assert service.startup_delay_seconds == 10
        assert service.primary_camera_id == 1
        assert service.current_state == AutomationState.STOPPED

    def test_service_lazy_loading_dependencies(self, mock_config):
        """Test that service dependencies are lazy-loaded correctly"""
        service = AutomaticRecordingService()
        
        # Dependencies should be None initially
        assert service._camera_service is None
        assert service._storage_manager is None
        assert service._experiment_monitor is None
        
        # Mock the get functions for lazy loading
        with patch('backend.services.automatic_recording.get_camera_service') as mock_get_camera:
            with patch('backend.services.automatic_recording.get_storage_manager') as mock_get_storage:
                with patch('backend.services.automatic_recording.get_experiment_monitor') as mock_get_experiment:
                    
                    mock_camera = Mock()
                    mock_storage = Mock()
                    mock_experiment = Mock()
                    
                    mock_get_camera.return_value = mock_camera
                    mock_get_storage.return_value = mock_storage
                    mock_get_experiment.return_value = mock_experiment
                    
                    # Access properties to trigger lazy loading
                    camera_service = service.camera_service
                    storage_manager = service.storage_manager  
                    experiment_monitor = service.experiment_monitor
                    
                    # Verify services were loaded
                    assert camera_service is mock_camera
                    assert storage_manager is mock_storage
                    assert experiment_monitor is mock_experiment
                    
                    # Verify get functions were called
                    mock_get_camera.assert_called_once()
                    mock_get_storage.assert_called_once()
                    mock_get_experiment.assert_called_once()

    def test_service_initialization_with_camera_service_error(self, mock_config):
        """Test service handles camera service loading errors gracefully"""
        service = AutomaticRecordingService()
        
        with patch('backend.services.automatic_recording.get_camera_service') as mock_get_camera:
            mock_get_camera.side_effect = ImportError("Camera service not available")
            
            # Should return None and not raise exception
            camera_service = service.camera_service
            assert camera_service is None


class TestAutomaticRecordingStartup(TestAutomaticRecordingService):
    """Tests for automatic recording startup with delay"""

    def test_start_automatic_recording_success(self, mock_config, mock_camera_service):
        """Test successful automatic recording startup"""
        service = AutomaticRecordingService()
        
        with patch.object(service, 'camera_service', mock_camera_service):
            success = service.start_automatic_recording()
            
            assert success is True
            assert service.current_state == AutomationState.STARTING
            assert service.automation_start_time is not None
            assert service.startup_thread is not None
            assert service.startup_thread.is_alive()

    def test_start_automatic_recording_when_disabled(self):
        """Test starting automatic recording when disabled in config"""
        with patch('backend.services.automatic_recording.AUTO_RECORDING_CONFIG', {"enabled": False}):
            service = AutomaticRecordingService()
            
            success = service.start_automatic_recording()
            
            assert success is False
            assert service.current_state == AutomationState.STOPPED

    def test_start_automatic_recording_already_active(self, mock_config, mock_camera_service):
        """Test starting automatic recording when already active"""
        service = AutomaticRecordingService()
        service.current_state = AutomationState.ACTIVE
        
        success = service.start_automatic_recording()
        
        assert success is False
        assert service.startup_thread is None

    def test_startup_delay_timing(self, mock_config, mock_camera_service, mock_storage_manager, mock_experiment_monitor):
        """Test that startup delay is respected"""
        service = AutomaticRecordingService()
        
        # Mock all dependencies
        with patch.object(service, 'camera_service', mock_camera_service):
            with patch.object(service, 'storage_manager', mock_storage_manager):
                with patch.object(service, 'experiment_monitor', mock_experiment_monitor):
                    
                    start_time = time.time()
                    service.start_automatic_recording()
                    
                    # Wait for startup to complete (should take at least startup_delay_seconds)
                    service.startup_thread.join(timeout=10)
                    end_time = time.time()
                    
                    # Verify timing (with some tolerance for test execution)
                    assert end_time - start_time >= mock_config["startup_delay_seconds"] - 0.1
                    assert service.current_state == AutomationState.ACTIVE

    def test_startup_cancellation_during_delay(self, mock_config):
        """Test that startup can be cancelled during delay period"""
        service = AutomaticRecordingService()
        
        # Start automatic recording
        success = service.start_automatic_recording()
        assert success is True
        assert service.current_state == AutomationState.STARTING
        
        # Cancel during delay
        service.stop_automatic_recording()
        
        # Wait for startup thread to finish
        service.startup_thread.join(timeout=5)
        
        # Should be stopped, not active
        assert service.current_state == AutomationState.STOPPED

    def test_startup_with_manual_override_during_delay(self, mock_config):
        """Test startup cancellation when manual override occurs during delay"""
        service = AutomaticRecordingService()
        
        # Start automatic recording
        service.start_automatic_recording()
        assert service.current_state == AutomationState.STARTING
        
        # Set manual override flag during delay
        service.manual_override_active = True
        
        # Wait for startup to complete
        service.startup_thread.join(timeout=5)
        
        # Should be stopped due to manual override
        assert service.current_state == AutomationState.STOPPED


class TestCameraRecordingIntegration(TestAutomaticRecordingService):
    """Tests for camera service integration and recording control"""

    def test_camera_recording_start_success(self, mock_config, mock_camera_service, mock_storage_manager, mock_experiment_monitor):
        """Test successful camera recording start"""
        service = AutomaticRecordingService()
        
        # Mock all dependencies
        with patch.object(service, 'camera_service', mock_camera_service):
            with patch.object(service, 'storage_manager', mock_storage_manager):
                with patch.object(service, 'experiment_monitor', mock_experiment_monitor):
                    
                    success = service._start_camera_recording(0)
                    
                    assert success is True
                    assert service.recording_camera_id == 0
                    
                    # Verify camera service interactions
                    mock_camera_service.detect_cameras.assert_called_once()
                    mock_camera_service.start_recording.assert_called_once_with(0)

    def test_camera_recording_start_no_cameras(self, mock_config, mock_camera_service):
        """Test camera recording start when no cameras detected"""
        service = AutomaticRecordingService()
        mock_camera_service.detect_cameras.return_value = []
        
        with patch.object(service, 'camera_service', mock_camera_service):
            success = service._start_camera_recording(0)
            
            assert success is False
            assert service.recording_camera_id is None

    def test_camera_recording_start_camera_not_found(self, mock_config, mock_camera_service):
        """Test camera recording start when requested camera not found"""
        service = AutomaticRecordingService()
        
        with patch.object(service, 'camera_service', mock_camera_service):
            success = service._start_camera_recording(5)  # Camera ID 5 doesn't exist
            
            assert success is False
            assert service.recording_camera_id is None

    def test_camera_recording_start_service_failure(self, mock_config, mock_camera_service):
        """Test camera recording start when camera service fails"""
        service = AutomaticRecordingService()
        mock_camera_service.start_recording.return_value = False
        
        with patch.object(service, 'camera_service', mock_camera_service):
            success = service._start_camera_recording(0)
            
            assert success is False
            assert service.recording_camera_id is None

    def test_camera_recording_start_no_service(self, mock_config):
        """Test camera recording start when camera service not available"""
        service = AutomaticRecordingService()
        
        # No camera service available
        with patch.object(service, 'camera_service', None):
            success = service._start_camera_recording(0)
            
            assert success is False
            assert service.recording_camera_id is None


class TestManualOverrideScenarios(TestAutomaticRecordingService):
    """Tests for manual override functionality"""

    def test_manual_stop_override(self, mock_config, mock_camera_service):
        """Test manual stop override functionality"""
        service = AutomaticRecordingService()
        service.current_state = AutomationState.ACTIVE
        service.recording_camera_id = 0
        
        with patch.object(service, 'camera_service', mock_camera_service):
            result = service.handle_manual_override("stop")
            
            assert result["success"] is True
            assert result["manual_override"] is True
            assert result["action"] == "stop"
            assert service.manual_override_active is True
            assert service.current_state == AutomationState.STOPPED

    def test_manual_start_override(self, mock_config, mock_camera_service, mock_experiment_monitor):
        """Test manual start override functionality"""
        service = AutomaticRecordingService()
        service.current_state = AutomationState.STOPPED
        
        with patch.object(service, 'camera_service', mock_camera_service):
            with patch.object(service, 'experiment_monitor', mock_experiment_monitor):
                result = service.handle_manual_override("start", camera_id=1)
                
                assert result["success"] is True
                assert result["camera_id"] == 1
                assert result["action"] == "start"
                assert service.current_state == AutomationState.ACTIVE
                assert service.recording_camera_id == 1

    def test_manual_start_when_already_active(self, mock_config):
        """Test manual start when automatic recording already active"""
        service = AutomaticRecordingService()
        service.current_state = AutomationState.ACTIVE
        service.recording_camera_id = 0
        
        result = service.handle_manual_override("start")
        
        assert result["success"] is False
        assert "already active" in result["message"]

    def test_manual_override_unknown_action(self, mock_config):
        """Test manual override with unknown action"""
        service = AutomaticRecordingService()
        
        result = service.handle_manual_override("unknown_action")
        
        assert result["success"] is False
        assert "Unknown manual override action" in result["message"]

    def test_manual_override_error_handling(self, mock_config, mock_camera_service):
        """Test manual override error handling"""
        service = AutomaticRecordingService()
        mock_camera_service.start_recording.side_effect = Exception("Camera error")
        
        with patch.object(service, 'camera_service', mock_camera_service):
            result = service.handle_manual_override("start")
            
            assert result["success"] is False
            assert "Manual override error" in result["message"]
            assert service.error_count == 1
            assert service.error_message is not None


class TestErrorHandling(TestAutomaticRecordingService):
    """Tests for error handling and recovery scenarios"""

    def test_startup_error_handling(self, mock_config, mock_camera_service):
        """Test error handling during startup process"""
        service = AutomaticRecordingService()
        mock_camera_service.detect_cameras.side_effect = Exception("Camera detection failed")
        
        with patch.object(service, 'camera_service', mock_camera_service):
            service.start_automatic_recording()
            
            # Wait for startup thread to complete
            service.startup_thread.join(timeout=5)
            
            # Should be in error state
            assert service.current_state == AutomationState.ERROR
            assert service.error_count == 1
            assert "Camera detection failed" in service.error_message

    def test_error_state_tracking(self, mock_config):
        """Test error state tracking and statistics"""
        service = AutomaticRecordingService()
        
        # Trigger error
        service._handle_error("Test error message")
        
        assert service.error_message == "Test error message"
        assert service.error_count == 1
        assert service.last_error_time is not None
        assert service.current_state == AutomationState.ERROR
        
        # Trigger another error
        service._handle_error("Second error")
        
        assert service.error_count == 2
        assert service.error_message == "Second error"

    def test_error_during_stopping_state(self, mock_config):
        """Test that errors during stopping don't change state to ERROR"""
        service = AutomaticRecordingService()
        service.current_state = AutomationState.STOPPING
        
        service._handle_error("Error during stop")
        
        # State should remain STOPPING, not ERROR
        assert service.current_state == AutomationState.STOPPING
        assert service.error_count == 1


class TestStatusReporting(TestAutomaticRecordingService):
    """Tests for service status reporting and monitoring"""

    def test_get_automation_status_stopped(self, mock_config):
        """Test automation status when service is stopped"""
        service = AutomaticRecordingService()
        
        with patch.object(service, 'storage_manager', Mock()) as mock_storage:
            mock_storage.get_storage_statistics.return_value = {
                "rolling_clips_count": 5,
                "experiment_folders_count": 2
            }
            
            status = service.get_automation_status()
            
            assert isinstance(status, AutomationStatus)
            assert status.is_active is False
            assert status.state == AutomationState.STOPPED
            assert status.recording_camera_id is None
            assert status.rolling_clips_count == 5
            assert status.experiment_folders_count == 2

    def test_get_automation_status_active(self, mock_config, mock_storage_manager, mock_experiment_monitor):
        """Test automation status when service is active"""
        service = AutomaticRecordingService()
        service.current_state = AutomationState.ACTIVE
        service.recording_camera_id = 0
        service.total_experiments_archived = 3
        
        # Mock monitor stats
        mock_stats = Mock()
        mock_stats.last_check_time = datetime.now()
        mock_experiment_monitor.get_monitor_stats.return_value = mock_stats
        
        with patch.object(service, 'storage_manager', mock_storage_manager):
            with patch.object(service, 'experiment_monitor', mock_experiment_monitor):
                status = service.get_automation_status()
                
                assert status.is_active is True
                assert status.state == AutomationState.ACTIVE
                assert status.recording_camera_id == 0
                assert status.total_experiments_archived == 3
                assert status.last_experiment_check is not None

    def test_get_automation_status_with_errors(self, mock_config, mock_storage_manager):
        """Test automation status includes error information"""
        service = AutomaticRecordingService()
        service._handle_error("Test error")
        
        with patch.object(service, 'storage_manager', mock_storage_manager):
            status = service.get_automation_status()
            
            assert status.error_message == "Test error"
            assert status.error_count == 1
            assert status.last_error_time is not None

    def test_status_helper_methods(self, mock_config):
        """Test status helper methods"""
        service = AutomaticRecordingService()
        
        # Test when stopped
        assert service.is_active() is False
        assert service.is_enabled() is True  # Based on mock_config
        
        # Test when active
        service.current_state = AutomationState.ACTIVE
        assert service.is_active() is True

    def test_get_current_experiment(self, mock_config, mock_experiment_monitor):
        """Test getting current experiment information"""
        service = AutomaticRecordingService()
        
        mock_experiment = ExperimentState(
            run_guid="test-guid",
            method_name="TestMethod",
            run_state=ExperimentStateType.RUNNING
        )
        mock_experiment_monitor.get_current_experiment.return_value = mock_experiment
        
        with patch.object(service, 'experiment_monitor', mock_experiment_monitor):
            current_exp = service.get_current_experiment()
            
            assert current_exp is mock_experiment
            assert current_exp.run_guid == "test-guid"

    def test_get_current_experiment_no_monitor(self, mock_config):
        """Test getting current experiment when monitor not available"""
        service = AutomaticRecordingService()
        
        with patch.object(service, 'experiment_monitor', None):
            current_exp = service.get_current_experiment()
            assert current_exp is None


class TestServiceShutdown(TestAutomaticRecordingService):
    """Tests for service shutdown and cleanup"""

    def test_stop_automatic_recording_success(self, mock_config, mock_camera_service, mock_experiment_monitor):
        """Test successful automatic recording stop"""
        service = AutomaticRecordingService()
        service.current_state = AutomationState.ACTIVE
        service.recording_camera_id = 0
        
        with patch.object(service, 'camera_service', mock_camera_service):
            with patch.object(service, 'experiment_monitor', mock_experiment_monitor):
                mock_experiment_monitor.is_monitoring_active.return_value = True
                
                success = service.stop_automatic_recording()
                
                assert success is True
                assert service.current_state == AutomationState.STOPPED
                assert service.recording_camera_id is None
                
                # Verify cleanup calls
                mock_camera_service.stop_recording.assert_called_once_with(0)
                mock_experiment_monitor.stop_monitoring.assert_called_once()

    def test_stop_when_already_stopped(self, mock_config):
        """Test stopping when already stopped"""
        service = AutomaticRecordingService()
        service.current_state = AutomationState.STOPPED
        
        success = service.stop_automatic_recording()
        
        assert success is True
        assert service.current_state == AutomationState.STOPPED

    def test_stop_with_startup_thread_running(self, mock_config):
        """Test stopping while startup thread is running"""
        service = AutomaticRecordingService()
        
        # Start automatic recording to create startup thread
        service.start_automatic_recording()
        assert service.startup_thread is not None
        assert service.startup_thread.is_alive()
        
        # Stop should wait for startup thread
        success = service.stop_automatic_recording()
        
        assert success is True
        assert service.current_state == AutomationState.STOPPED
        assert not service.startup_thread.is_alive()

    def test_stop_error_handling(self, mock_config, mock_camera_service):
        """Test error handling during stop operation"""
        service = AutomaticRecordingService()
        service.current_state = AutomationState.ACTIVE
        service.recording_camera_id = 0
        
        mock_camera_service.stop_recording.side_effect = Exception("Stop error")
        
        with patch.object(service, 'camera_service', mock_camera_service):
            success = service.stop_automatic_recording()
            
            # Should still succeed even with camera stop error
            assert success is True
            assert service.current_state == AutomationState.STOPPED


# Integration test for complete initialization workflow
class TestCompleteInitializationWorkflow(TestAutomaticRecordingService):
    """Integration tests for complete service initialization workflow"""

    def test_complete_startup_workflow(self, mock_config, mock_camera_service, mock_storage_manager, mock_experiment_monitor):
        """Test complete startup workflow from initialization to active recording"""
        service = AutomaticRecordingService()
        
        # Mock all dependencies
        with patch.object(service, 'camera_service', mock_camera_service):
            with patch.object(service, 'storage_manager', mock_storage_manager):
                with patch.object(service, 'experiment_monitor', mock_experiment_monitor):
                    
                    # Start automatic recording
                    success = service.start_automatic_recording()
                    assert success is True
                    assert service.current_state == AutomationState.STARTING
                    
                    # Wait for startup to complete
                    service.startup_thread.join(timeout=10)
                    
                    # Verify final state
                    assert service.current_state == AutomationState.ACTIVE
                    assert service.recording_camera_id == 0
                    assert service.manual_override_active is False
                    
                    # Verify all services were called correctly
                    mock_camera_service.detect_cameras.assert_called()
                    mock_camera_service.start_recording.assert_called_with(0)
                    mock_experiment_monitor.add_completion_callback.assert_called()
                    mock_experiment_monitor.start_monitoring.assert_called()

    def test_complete_shutdown_workflow(self, mock_config, mock_camera_service, mock_storage_manager, mock_experiment_monitor):
        """Test complete shutdown workflow"""
        service = AutomaticRecordingService()
        
        # Setup active recording state
        service.current_state = AutomationState.ACTIVE
        service.recording_camera_id = 0
        
        mock_experiment_monitor.is_monitoring_active.return_value = True
        
        with patch.object(service, 'camera_service', mock_camera_service):
            with patch.object(service, 'experiment_monitor', mock_experiment_monitor):
                
                success = service.stop_automatic_recording(manual_stop=True)
                
                assert success is True
                assert service.current_state == AutomationState.STOPPED
                assert service.recording_camera_id is None
                assert service.manual_override_active is True
                
                # Verify cleanup
                mock_camera_service.stop_recording.assert_called_with(0)
                mock_experiment_monitor.stop_monitoring.assert_called()


# Pytest configuration
@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment for automatic recording tests"""
    # Ensure test directories exist
    test_data_dir = Path(__file__).parent.parent.parent / "data"
    test_data_dir.mkdir(exist_ok=True)
    
    yield
    
    # Cleanup after all tests
    AutomaticRecordingService._instance = None


if __name__ == "__main__":
    # Run tests directly with pytest
    pytest.main([__file__, "-v", "--tb=short"])