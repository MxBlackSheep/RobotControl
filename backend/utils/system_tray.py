"""
System tray icon for RobotControl server status indication.
Shows server running status and provides convenient management options.
"""

import os
import webbrowser
import threading
import logging
from typing import Optional, Callable
import subprocess

# Only import pystray when actually needed (not available in all environments)
try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    pystray = None
    Item = None
    Image = None
    ImageDraw = None

logger = logging.getLogger(__name__)


class RobotControlSystemTray:
    """System tray icon for RobotControl server management"""

    def __init__(self, port: int = 8005):
        self.port = port
        self.icon: Optional['pystray.Icon'] = None
        self.running = False
        self.server_status = "starting"  # starting, running, stopped, error
        self.stop_callback: Optional[Callable] = None

        if not TRAY_AVAILABLE:
            logger.warning("System tray not available - pystray/PIL not installed")
            return

        # Create tray icon
        self._create_icon()

    def _create_icon(self):
        """Create the system tray icon"""
        if not TRAY_AVAILABLE:
            return

        try:
            # Create menu with the requested minimal actions
            menu = pystray.Menu(
                Item("Open in Browser", self._open_browser, default=True),
                Item("Show Data", self._open_data_dir),
                Item("Terminate", self._terminate),
            )

            # Create icon with initial status
            image = self._create_status_image("starting")

            self.icon = pystray.Icon(
                "RobotControl",
                image,
                "RobotControl Server - Starting",
                menu
            )

            logger.info("System tray icon created successfully")

        except Exception as e:
            logger.error(f"Failed to create system tray icon: {e}")
            self.icon = None

    def _create_status_image(self, status: str) -> Optional['Image.Image']:
        """Create status indicator image"""
        if not TRAY_AVAILABLE:
            return None

        try:
            # Create a 16x16 image with appropriate color
            image = Image.new('RGB', (16, 16), color='white')
            draw = ImageDraw.Draw(image)

            # Status colors
            colors = {
                'starting': '#FFA500',  # Orange
                'running': '#00FF00',   # Green
                'stopped': '#FF0000',   # Red
                'error': '#FF0000'      # Red
            }

            color = colors.get(status, '#808080')  # Gray fallback

            # Draw a filled circle as status indicator
            draw.ellipse([2, 2, 14, 14], fill=color, outline='black')

            # Add a small "P" for RobotControl
            draw.text((6, 4), "P", fill='black')

            return image

        except Exception as e:
            logger.error(f"Failed to create status image: {e}")
            return None

    def update_status(self, status: str, message: str = None):
        """Update the server status and tray icon"""
        self.server_status = status

        if not self.icon:
            return

        try:
            # Update icon image
            image = self._create_status_image(status)
            if image:
                self.icon.icon = image

            # Update tooltip
            status_messages = {
                'starting': 'RobotControl Server - Starting up...',
                'running': f'RobotControl Server - Running on port {self.port}',
                'stopped': 'RobotControl Server - Stopped',
                'error': f'RobotControl Server - Error: {message or "Unknown error"}'
            }

            tooltip = status_messages.get(status, f'RobotControl Server - {status}')
            self.icon.title = tooltip

            logger.debug(f"Tray icon updated: {status}")

        except Exception as e:
            logger.error(f"Failed to update tray icon: {e}")

    def start(self, stop_callback: Optional[Callable] = None):
        """Start the system tray icon"""
        if not TRAY_AVAILABLE or not self.icon:
            logger.info("System tray not available - server will run without tray icon")
            return

        self.stop_callback = stop_callback
        self.running = True

        try:
            # Run tray icon in separate thread
            tray_thread = threading.Thread(
                target=self._run_tray,
                name="RobotControlTray",
                daemon=True
            )
            tray_thread.start()

            logger.info("System tray icon started")

        except Exception as e:
            logger.error(f"Failed to start system tray: {e}")

    def _run_tray(self):
        """Run the tray icon (blocking)"""
        try:
            self.icon.run()
        except Exception as e:
            logger.error(f"Tray icon runtime error: {e}")

    def stop(self):
        """Stop the system tray icon"""
        self.running = False

        if self.icon:
            try:
                self.icon.stop()
                logger.info("System tray icon stopped")
            except Exception as e:
                logger.error(f"Error stopping tray icon: {e}")

    # Menu item handlers
    def _open_browser(self, icon, item):
        """Open RobotControl in default browser"""
        try:
            url = f"http://localhost:{self.port}"
            webbrowser.open(url)
            logger.info(f"Opened browser to {url}")
        except Exception as e:
            logger.error(f"Failed to open browser: {e}")

    def _open_data_dir(self, icon, item):
        """Open data directory"""
        try:
            from backend.utils.data_paths import get_data_path
            data_path = get_data_path()
            subprocess.run(['explorer', str(data_path)], shell=True)
            logger.info(f"Opened data directory: {data_path}")
        except Exception as e:
            logger.error(f"Failed to open data directory: {e}")

    def _terminate(self, icon, item):
        """Terminate the RobotControl process from the system tray"""
        logger.info("Terminate requested from system tray")
        try:
            self.stop()
            if self.stop_callback:
                self.stop_callback()
        except Exception as e:
            logger.error(f"Failed to terminate gracefully: {e}")
        finally:
            # Ensure the process exits even if callbacks hang
            threading.Timer(1.0, lambda: os._exit(0)).start()


# Global tray instance
_tray_instance: Optional[RobotControlSystemTray] = None


def get_system_tray(port: int = 8005) -> RobotControlSystemTray:
    """Get the global system tray instance"""
    global _tray_instance
    if _tray_instance is None:
        _tray_instance = RobotControlSystemTray(port)
    return _tray_instance


def start_system_tray(port: int = 8005, stop_callback: Optional[Callable] = None) -> RobotControlSystemTray:
    """Start system tray icon and return instance"""
    tray = get_system_tray(port)
    tray.start(stop_callback)
    return tray


def update_tray_status(status: str, message: str = None):
    """Update system tray status"""
    global _tray_instance
    if _tray_instance:
        _tray_instance.update_status(status, message)


def stop_system_tray():
    """Stop system tray icon"""
    global _tray_instance
    if _tray_instance:
        _tray_instance.stop()
        _tray_instance = None


def is_tray_available() -> bool:
    """Check if system tray is available"""
    return TRAY_AVAILABLE
