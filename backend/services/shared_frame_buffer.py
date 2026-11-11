"""
Shared frame buffer for zero-copy frame sharing between recording and streaming.
Implements priority access to ensure recording is never blocked.
"""

import threading
import time
from collections import deque
from datetime import datetime
from typing import Optional
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
        self.frames_read_streaming = 0
        self.frames_dropped_streaming = 0
        
        self._async_readers = {}
        
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
            
            self._notify_async_readers()
            
            return True
            
        except Exception as e:
            logger.error(f"Error putting frame in buffer: {e}")
            return False
    
    def subscribe_frames(self, loop, event):
        """One coalesced wake-up per reader; no frame payloads queued on the loop."""
        with self.streaming_lock:
            self._async_readers[event] = [loop, False]
        self._notify_async_readers()

    def unsubscribe_frames(self, event):
        with self.streaming_lock:
            self._async_readers.pop(event, None)

    def _notify_async_readers(self):
        with self.streaming_lock:
            for event, reader in list(self._async_readers.items()):
                if reader[1]:
                    continue
                reader[1] = True
                try:
                    reader[0].call_soon_threadsafe(self._wake_reader, event)
                except RuntimeError:  # Event loop already closed.
                    self._async_readers.pop(event, None)

    def _wake_reader(self, event):
        with self.streaming_lock:
            reader = self._async_readers.get(event)
            if reader is None:
                return
            reader[1] = False
        event.set()
    
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


    def clear(self) -> None:
        """
        Clear the buffer and reset statistics.
        Used during shutdown or reset.
        """
        with self.recording_lock:
            self.latest_frame = None
            
        with self.streaming_lock:
            self.buffer.clear()
            self.frame_counter = 0
            self.frames_written = 0
            self.frames_read_streaming = 0
            self.frames_dropped_streaming = 0
            
        logger.info("SharedFrameBuffer cleared")


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
