"""
Browser auto-launch functionality for single-exe mode.
Handles server readiness checking and automatic browser opening.
"""

import webbrowser
import time
import requests
import logging
import threading
from typing import Optional, Callable
import socket

logger = logging.getLogger(__name__)

class BrowserLauncher:
    """Handles automatic browser launching for the PyRobot application."""
    
    def __init__(self, host: str = "localhost", port: int = 8005, auto_launch: bool = True):
        self.host = host
        self.port = port
        self.auto_launch = auto_launch
        self.url = f"http://{host}:{port}"
        self._launch_thread: Optional[threading.Thread] = None
    
    def wait_for_server(self, timeout: int = 30, check_interval: float = 0.5) -> bool:
        """
        Wait for server to become ready.
        
        Args:
            timeout: Maximum time to wait in seconds
            check_interval: Time between checks in seconds
            
        Returns:
            True if server is ready, False if timeout
        """
        start_time = time.time()
        logger.info(f"Waiting for server at {self.url} to become ready...")
        
        while time.time() - start_time < timeout:
            try:
                # Try to connect to server
                response = requests.get(f"{self.url}/health", timeout=2)
                if response.status_code == 200:
                    logger.info(f"Server is ready at {self.url}")
                    return True
            except (requests.exceptions.RequestException, requests.exceptions.ConnectionError):
                # Server not ready yet
                pass
            
            time.sleep(check_interval)
        
        logger.warning(f"Server at {self.url} did not become ready within {timeout} seconds")
        return False
    
    def launch_browser(self, url: Optional[str] = None) -> bool:
        """
        Launch the default browser to the application URL.
        
        Args:
            url: Optional specific URL to open (defaults to self.url)
            
        Returns:
            True if browser launched successfully, False otherwise
        """
        if not url:
            url = self.url
        
        try:
            logger.info(f"Launching browser to {url}")
            webbrowser.open(url)
            return True
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            return False
    
    def launch_when_ready(self, on_ready: Optional[Callable] = None):
        """
        Launch browser automatically when server is ready.
        Runs in a separate thread to avoid blocking startup.
        
        Args:
            on_ready: Optional callback function to call when server is ready
        """
        def _launch_thread():
            if self.wait_for_server():
                if on_ready:
                    try:
                        on_ready()
                    except Exception as e:
                        logger.error(f"Error in on_ready callback: {e}")
                
                if self.auto_launch:
                    if not self.launch_browser():
                        self._show_manual_instructions()
                else:
                    self._show_manual_instructions()
            else:
                logger.error("Server failed to start - cannot launch browser")
                self._show_manual_instructions()
        
        self._launch_thread = threading.Thread(target=_launch_thread, daemon=True)
        self._launch_thread.start()
    
    def _show_manual_instructions(self):
        """Show manual instructions if browser launch fails."""
        logger.info("=" * 60)
        logger.info("MANUAL ACCESS REQUIRED")
        logger.info("=" * 60)
        logger.info(f"Open your browser and navigate to: {self.url}")
        logger.info("=" * 60)
    
    def set_port(self, port: int):
        """Update the port and URL."""
        self.port = port
        self.url = f"http://{self.host}:{port}"
        logger.info(f"Browser launcher updated to use port {port}")
    
    def stop(self):
        """Stop the browser launcher."""
        if self._launch_thread and self._launch_thread.is_alive():
            logger.info("Browser launcher stopping...")
            # Note: Thread will finish naturally when server check completes

def is_port_available(port: int, host: str = "localhost") -> bool:
    """
    Check if a port is available for binding.
    
    Args:
        port: Port number to check
        host: Host to check (default localhost)
        
    Returns:
        True if port is available, False otherwise
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result != 0  # Port is available if connection failed
    except Exception:
        return False

def find_available_port(start_port: int = 8005, end_port: int = 8099, host: str = "localhost") -> Optional[int]:
    """
    Find an available port in the given range.
    
    Args:
        start_port: First port to try
        end_port: Last port to try
        host: Host to check
        
    Returns:
        Available port number or None if none found
    """
    for port in range(start_port, end_port + 1):
        if is_port_available(port, host):
            return port
    return None

# Global launcher instance
_browser_launcher: Optional[BrowserLauncher] = None

def get_browser_launcher(host: str = "localhost", port: int = 8005, auto_launch: bool = True) -> BrowserLauncher:
    """Get or create the global browser launcher instance."""
    global _browser_launcher
    if _browser_launcher is None:
        _browser_launcher = BrowserLauncher(host, port, auto_launch)
    return _browser_launcher

def launch_browser_when_ready(host: str = "localhost", port: int = 8005, auto_launch: bool = True):
    """Convenience function to launch browser when server is ready."""
    launcher = get_browser_launcher(host, port, auto_launch)
    launcher.launch_when_ready()

def update_launcher_port(port: int):
    """Update the global launcher's port."""
    if _browser_launcher:
        _browser_launcher.set_port(port)