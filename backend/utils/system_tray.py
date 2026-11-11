"""
System tray icon for RobotControl server status indication.
Shows server running status and provides convenient management options.
"""

import ctypes
import functools
import os
import sys
import webbrowser
import threading
import logging
from pathlib import Path
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

# Bundled by build_scripts/pyinstaller_build.py at the same relative path.
APP_ICON = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])) / 'build_scripts' / 'icon' / 'RobotControl.ico'

STATUS_COLOR = '#00FF00'
STATUS_DOT_RING = '#0b1f3a'


def _tray_icon_sizes() -> tuple[int, int]:
    """(drawn, handle): the size the notification area draws icons at, and the size of the
    icon handle pystray makes (LoadImage with LR_DEFAULTSIZE: SM_CXICON for this thread)."""
    try:
        user32 = ctypes.windll.user32
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        handle = user32.GetSystemMetrics(11)  # SM_CXICON
        # The shell is per-monitor DPI aware; ask in that context for its real small-icon size.
        previous = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
        try:
            drawn = user32.GetSystemMetrics(49)  # SM_CXSMICON
        finally:
            if previous:
                user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(previous))
        if drawn > 0 and handle > 0:
            return drawn, handle
    except (AttributeError, OSError):
        pass
    return 16, 32


@functools.cache
def _app_icon_frames() -> Optional[dict]:
    """RobotControl.ico's frames by pixel size, or None (logged once) when it cannot be read."""
    try:
        frames = {}
        with Image.open(APP_ICON) as ico:
            for size in sorted(ico.info['sizes']):
                ico.size = size
                frames[size[0]] = ico.convert('RGBA')
        return frames
    except Exception:
        logger.warning("Tray: app icon %s could not be read; showing the plain status icon", APP_ICON, exc_info=True)
        return None


def _app_status_image(color: str) -> Optional['Image.Image']:
    """The app icon frame for the tray's size with a status dot in the bottom-right corner."""
    frames = _app_icon_frames()
    if not frames:
        return None
    drawn, handle = _tray_icon_sizes()
    # LoadImage smooths any stretch, which blurs the hand-tuned 16/24 px frames. When the handle
    # is a whole multiple of the drawn size, design at the drawn size and enlarge it by pixel
    # doubling: the handle then needs no stretch and the shell's reduction restores the frame.
    size = drawn if handle % drawn == 0 else handle
    best = min((s for s in frames if s >= size), default=max(frames))
    image = frames[best].copy() if best == size else frames[best].resize((size, size), Image.Resampling.LANCZOS)
    # A crisp dot 7/16 of the icon with a dark ring stays distinct from the white gripper and
    # the blue art at 16 px; anti-aliasing blurred it into both.
    dot, ring = round(size * 7 / 16), max(1, size // 16)
    draw = ImageDraw.Draw(image)
    outer = [size - dot, size - dot, size - 1, size - 1]
    draw.ellipse(outer, fill=STATUS_DOT_RING)
    draw.ellipse([outer[0] + ring, outer[1] + ring, outer[2] - ring, outer[3] - ring], fill=color)
    if size != handle:
        image = image.resize((handle, handle), Image.Resampling.NEAREST)
    return image


class RobotControlSystemTray:
    """System tray icon for RobotControl server management"""

    def __init__(self, port: int = 8005, shutdown_complete=None):
        self.port = port
        self.shutdown_complete = shutdown_complete or threading.Event()
        self.icon: Optional['pystray.Icon'] = None
        self.running = False
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
            image = _app_status_image(STATUS_COLOR)

            self.icon = pystray.Icon(
                "RobotControl",
                image,
                f"RobotControl Server - port {self.port}",
                menu
            )

            logger.info("System tray icon created successfully")

        except Exception as e:
            logger.error(f"Failed to create system tray icon: {e}")
            self.icon = None

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
        """Request cleanup, allow ten seconds, then enforce the operator's exit request."""
        logger.info("Terminate requested from system tray")
        def terminate():
            if self.stop_callback:
                self.stop_callback()
            self.shutdown_complete.wait(10)
            os._exit(0)
        threading.Thread(target=terminate, name="RobotControlTerminate", daemon=True).start()
