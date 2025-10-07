"""
Shared frame buffer for zero-copy frame sharing between recording and streaming.
Implements priority access to ensure recording is never blocked.
"""

import threading
import time
from collections import deque
from datetime import datetime
from typing import Optional, Callable, List
import numpy as np
import logging

from backend.services.streaming_types import FrameData

logger = logging.getLogger(__name__)


class SharedFrameBuffer:
    """
    Thread-safe circular buffer for zero-copy frame sharing.
    Recording has priority access - always gets frames.
    Streaming gets non-blocking access - may miss frames under load.
    """
    
    def __init__(self, max_frames: int = 30):
        """
        Initialize the shared frame buffer.
        
        Args:
            max_frames: Maximum number of frames to buffer (~1 second at 30fps)
        """
        self.max_frames = max_frames
        self.buffer = deque(maxlen=max_frames)
        
        # Separate locks for recording and streaming to minimize contention
        self.recording_lock = threading.Lock()
        self.streaming_lock = threading.RLock()
        self.streaming_condition = threading.Condition(self.streaming_lock)
        
        # Latest frame for quick access
        self.latest_frame: Optional[FrameData] = None
        self.frame_counter = 0
        
        # Statistics
        self.frames_written = 0
        self.frames_read_recording = 0
        self.frames_read_streaming = 0
        self.frames_dropped_streaming = 0
        
        # Callbacks for frame distribution
        self.streaming_callbacks: List[Callable[[FrameData], None]] = []
        
        logger.info(f"SharedFrameBuffer initialized with max_frames={max_frames}")
    
    def put_frame(self, frame: np.ndarray, timestamp: Optional[datetime] = None) -> bool:
        """
        Add a frame from the camera.
        Called by CameraService capture thread.
        
        Args:
            frame: Raw frame data from camera (BGR format)
            timestamp: Frame timestamp (uses current time if not provided)
            
        Returns:
            True if frame was successfully added
        """
        if frame is None:
            return False
        
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            # Create frame data
            self.frame_counter += 1
            frame_data = FrameData(
                frame=frame,
                timestamp=timestamp,
                frame_number=self.frame_counter,
                is_keyframe=(self.frame_counter % 30 == 0),  # Keyframe every second
                size_bytes=frame.nbytes
            )
            
            # Update latest frame with minimal locking
            with self.recording_lock:
                self.latest_frame = frame_data
                self.frames_written += 1
            
            # Add to buffer for streaming
            with self.streaming_lock:
                self.buffer.append(frame_data)
                # Notify streaming threads
                self.streaming_condition.notify_all()
            
            # Distribute to streaming callbacks asynchronously
            if self.streaming_callbacks:
                self._distribute_to_callbacks(frame_data)
            
            return True
            
        except Exception as e:
            logger.error(f"Error putting frame in buffer: {e}")
            return False
    
    def get_frame_for_recording(self) -> Optional[FrameData]:
        """
        Priority access for recording service.
        Always returns the latest frame if available.
        Never blocks or waits.
        
        Returns:
            Latest frame data or None if no frames available
        """
        with self.recording_lock:
            if self.latest_frame:
                self.frames_read_recording += 1
            return self.latest_frame
    
    def get_frame_for_streaming(self, timeout: float = 0.033) -> Optional[FrameData]:
        """
        Non-priority access for streaming.
        May return None if recording has priority or timeout occurs.
        
        Args:
            timeout: Maximum time to wait for a frame (default ~30fps)
            
        Returns:
            Latest frame from buffer or None if timeout/unavailable
        """
        try:
            with self.streaming_condition:
                # Wait for a frame or timeout
                if not self.buffer:
                    if not self.streaming_condition.wait(timeout):
                        self.frames_dropped_streaming += 1
                        return None  # Timeout - recording has priority
                
                # Get the latest frame from buffer
                if self.buffer:
                    frame_data = self.buffer[-1]
                    self.frames_read_streaming += 1
                    return frame_data
                else:
                    self.frames_dropped_streaming += 1
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting frame for streaming: {e}")
            self.frames_dropped_streaming += 1
            return None
    
    def get_recent_frames(self, count: int = 5) -> List[FrameData]:
        """
        Get multiple recent frames for adaptive streaming.
        Non-blocking access for quality adjustment algorithms.
        
        Args:
            count: Number of recent frames to retrieve
            
        Returns:
            List of recent frames (may be less than requested)
        """
        with self.streaming_lock:
            # Return up to 'count' most recent frames
            if not self.buffer:
                return []
            
            frames_to_return = min(count, len(self.buffer))
            return list(self.buffer)[-frames_to_return:]
    
    def register_streaming_callback(self, callback: Callable[[FrameData], None]) -> None:
        """
        Register a callback for frame distribution.
        Used by streaming sessions for push-based frame delivery.
        
        Args:
            callback: Function to call with each new frame
        """
        with self.streaming_lock:
            if callback not in self.streaming_callbacks:
                self.streaming_callbacks.append(callback)
                logger.debug(f"Registered streaming callback, total: {len(self.streaming_callbacks)}")
    
    def unregister_streaming_callback(self, callback: Callable[[FrameData], None]) -> None:
        """
        Unregister a streaming callback.
        
        Args:
            callback: Function to remove from callbacks
        """
        with self.streaming_lock:
            if callback in self.streaming_callbacks:
                self.streaming_callbacks.remove(callback)
                logger.debug(f"Unregistered streaming callback, remaining: {len(self.streaming_callbacks)}")
    
    def _distribute_to_callbacks(self, frame_data: FrameData) -> None:
        """
        Distribute frame to all registered callbacks.
        Non-blocking - callbacks are called in separate threads.
        
        Args:
            frame_data: Frame to distribute
        """
        # Create a copy of callbacks to avoid holding lock during distribution
        with self.streaming_lock:
            callbacks = self.streaming_callbacks.copy()
        
        # Call each callback in a separate thread to avoid blocking
        for callback in callbacks:
            threading.Thread(
                target=self._safe_callback,
                args=(callback, frame_data),
                daemon=True
            ).start()
    
    def _safe_callback(self, callback: Callable[[FrameData], None], frame_data: FrameData) -> None:
        """
        Safely call a callback with error handling.
        
        Args:
            callback: Function to call
            frame_data: Frame data to pass
        """
        try:
            callback(frame_data)
        except Exception as e:
            logger.error(f"Error in streaming callback: {e}")
            # Remove failed callback
            self.unregister_streaming_callback(callback)
    
    def get_buffer_status(self) -> dict:
        """
        Get current buffer status and statistics.
        
        Returns:
            Dictionary with buffer metrics
        """
        with self.streaming_lock:
            buffer_size = len(self.buffer)
            buffer_usage = (buffer_size / self.max_frames * 100) if self.max_frames > 0 else 0
            
        return {
            "buffer_size": buffer_size,
            "buffer_capacity": self.max_frames,
            "buffer_usage_percent": round(buffer_usage, 1),
            "frames_written": self.frames_written,
            "frames_read_recording": self.frames_read_recording,
            "frames_read_streaming": self.frames_read_streaming,
            "frames_dropped_streaming": self.frames_dropped_streaming,
            "active_callbacks": len(self.streaming_callbacks),
            "latest_frame_number": self.frame_counter,
            "recording_efficiency": round(
                (self.frames_read_recording / self.frames_written * 100) 
                if self.frames_written > 0 else 0, 1
            ),
            "streaming_efficiency": round(
                (self.frames_read_streaming / (self.frames_read_streaming + self.frames_dropped_streaming) * 100)
                if (self.frames_read_streaming + self.frames_dropped_streaming) > 0 else 0, 1
            )
        }
    
    def clear(self) -> None:
        """
        Clear the buffer and reset statistics.
        Used during shutdown or reset.
        """
        with self.recording_lock:
            self.latest_frame = None
            
        with self.streaming_lock:
            self.buffer.clear()
            self.streaming_callbacks.clear()
            self.frame_counter = 0
            self.frames_written = 0
            self.frames_read_recording = 0
            self.frames_read_streaming = 0
            self.frames_dropped_streaming = 0
            
        logger.info("SharedFrameBuffer cleared")
    
    def is_healthy(self) -> bool:
        """
        Check if buffer is operating normally.
        
        Returns:
            True if buffer is healthy
        """
        # Check if we're receiving frames
        if self.frames_written == 0:
            return True  # Just started, no frames yet is OK
        
        # Check if recording is getting frames
        recording_ratio = self.frames_read_recording / self.frames_written
        if recording_ratio < 0.5:  # Recording getting less than 50% of frames
            logger.warning(f"Recording efficiency low: {recording_ratio:.1%}")
            return False
        
        # Check buffer overflow
        with self.streaming_lock:
            if len(self.buffer) >= self.max_frames:
                logger.warning("Buffer at maximum capacity")
                # This is OK - circular buffer handles overflow
        
        return True


# Global instance (singleton pattern)
_shared_buffer_instance: Optional[SharedFrameBuffer] = None
_shared_buffer_lock = threading.Lock()


def get_shared_frame_buffer(max_frames: int = 30) -> SharedFrameBuffer:
    """
    Get the global shared frame buffer instance.
    Creates it if it doesn't exist.
    
    Args:
        max_frames: Maximum frames to buffer (only used on first call)
        
    Returns:
        The global SharedFrameBuffer instance
    """
    global _shared_buffer_instance
    
    if _shared_buffer_instance is None:
        with _shared_buffer_lock:
            if _shared_buffer_instance is None:
                _shared_buffer_instance = SharedFrameBuffer(max_frames)
                logger.info("Created global SharedFrameBuffer instance")
    
    return _shared_buffer_instance


def clear_shared_frame_buffer() -> None:
    """
    Clear and reset the global shared frame buffer.
    Used during shutdown or reset.
    """
    global _shared_buffer_instance
    
    if _shared_buffer_instance is not None:
        _shared_buffer_instance.clear()
        logger.info("Cleared global SharedFrameBuffer")