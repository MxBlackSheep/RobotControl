"""
Shared frame buffer for zero-copy frame sharing between recording and streaming.
Publishes the latest captured frame with coalesced async reader wakeups.
"""

import threading
from datetime import datetime
from typing import Optional
import numpy as np
import logging

from backend.services.streaming_types import FrameData

logger = logging.getLogger(__name__)


class SharedFrameBuffer:
    """
    One latest frame shared without queueing frame payloads.
    """
    
    def __init__(self):
        self.streaming_lock = threading.RLock()
        self.latest_frame: Optional[FrameData] = None
        self._async_readers = {}

    def put_frame(self, frame: np.ndarray, timestamp: Optional[datetime] = None) -> bool:
        if frame is None:
            return False
        with self.streaming_lock:
            self.latest_frame = FrameData(frame, timestamp or datetime.now())
        self._notify_async_readers()
        return True

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
    
    def get_frame_for_streaming(self) -> Optional[FrameData]:
        with self.streaming_lock:
            return self.latest_frame

    def clear(self) -> None:
        with self.streaming_lock:
            self.latest_frame = None


# Global instance (singleton pattern)
_shared_buffer_instance: Optional[SharedFrameBuffer] = None
_shared_buffer_lock = threading.Lock()


def get_shared_frame_buffer() -> SharedFrameBuffer:
    """
    Get the global shared frame buffer instance.
    Creates it if it doesn't exist.
    
    Returns:
        The global SharedFrameBuffer instance
    """
    global _shared_buffer_instance
    
    if _shared_buffer_instance is None:
        with _shared_buffer_lock:
            if _shared_buffer_instance is None:
                _shared_buffer_instance = SharedFrameBuffer()
                logger.info("Created global SharedFrameBuffer instance")
    
    return _shared_buffer_instance
