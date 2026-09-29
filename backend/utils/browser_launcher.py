"""
Browser auto-launch functionality for single-exe mode.
Handles server readiness checking and automatic browser opening.
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

class BrowserLauncher:
    """Handles automatic browser launching for the RobotControl application."""
    
    def __init__(self, host: str = "localhost", port: int = 8005, auto_launch: bool = True):
        self.host = host
        self.port = port
        self.auto_launch = auto_launch
        self.url = f"http://{host}:{port}"
        self._launch_thread: Optional[threading.Thread] = None
    
    def stop(self):
        """Stop the browser launcher."""
        if self._launch_thread and self._launch_thread.is_alive():
            logger.info("Browser launcher stopping...")
            # Note: Thread will finish naturally when server check completes

# Global launcher instance
_browser_launcher: Optional[BrowserLauncher] = None

