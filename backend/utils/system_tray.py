"""
System tray icon for PyRobot server status indication.
Shows server running status and provides convenient management options.
"""

import sys
import webbrowser
import threading
import time
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

class PyRobotSystemTray:
    """System tray icon for PyRobot server management"""
    
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
            # Create menu
            menu = pystray.Menu(
                Item("PyRobot Server", self._show_info, default=True),
                Item("Status", self._show_status),
                pystray.Menu.SEPARATOR,
                Item("Open in Browser", self._open_browser),
                Item("API Documentation", self._open_docs),
                pystray.Menu.SEPARATOR,
                Item("View Logs", self._view_logs),
                Item("Data Directory", self._open_data_dir),
                pystray.Menu.SEPARATOR,
                Item("Stop Server", self._stop_server),
                Item("Exit", self._exit_app)
            )
            
            # Create icon with initial status
            image = self._create_status_image("starting")
            
            self.icon = pystray.Icon(
                "PyRobot",
                image,
                "PyRobot Server - Starting",
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
            
            # Add a small "P" for PyRobot
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
                'starting': 'PyRobot Server - Starting up...',
                'running': f'PyRobot Server - Running on port {self.port}',
                'stopped': 'PyRobot Server - Stopped',
                'error': f'PyRobot Server - Error: {message or "Unknown error"}'
            }
            
            tooltip = status_messages.get(status, f'PyRobot Server - {status}')
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
                name="PyRobotTray",
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
    def _show_info(self, icon, item):
        """Show PyRobot information"""
        try:
            # Try to use native Windows notification
            subprocess.run([
                'powershell', '-Command',
                f'''
                Add-Type -AssemblyName System.Windows.Forms
                $notification = New-Object System.Windows.Forms.NotifyIcon
                $notification.Icon = [System.Drawing.SystemIcons]::Information
                $notification.BalloonTipTitle = "PyRobot Server"
                $notification.BalloonTipText = "Hamilton VENUS Robot Management System\\nRunning on port {self.port}\\nClick to open in browser"
                $notification.Visible = $true
                $notification.ShowBalloonTip(5000)
                Start-Sleep -Seconds 6
                $notification.Dispose()
                '''
            ], shell=True, capture_output=True)
        except:
            # Fallback - just log
            logger.info(f"PyRobot Server running on port {self.port}")
    
    def _show_status(self, icon, item):
        """Show server status"""
        status_msg = f"Status: {self.server_status.title()}\\nPort: {self.port}"
        try:
            subprocess.run([
                'powershell', '-Command',
                f'''
                Add-Type -AssemblyName System.Windows.Forms
                [System.Windows.Forms.MessageBox]::Show("{status_msg}", "PyRobot Server Status", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
                '''
            ], shell=True, capture_output=True)
        except:
            logger.info(status_msg)
    
    def _open_browser(self, icon, item):
        """Open PyRobot in default browser"""
        try:
            url = f"http://localhost:{self.port}"
            webbrowser.open(url)
            logger.info(f"Opened browser to {url}")
        except Exception as e:
            logger.error(f"Failed to open browser: {e}")
    
    def _open_docs(self, icon, item):
        """Open API documentation"""
        try:
            url = f"http://localhost:{self.port}/docs"
            webbrowser.open(url)
            logger.info(f"Opened API docs at {url}")
        except Exception as e:
            logger.error(f"Failed to open docs: {e}")
    
    def _view_logs(self, icon, item):
        """Open logs directory"""
        try:
            from backend.utils.data_paths import get_logs_path
            logs_path = get_logs_path()
            subprocess.run(['explorer', str(logs_path)], shell=True)
            logger.info(f"Opened logs directory: {logs_path}")
        except Exception as e:
            logger.error(f"Failed to open logs directory: {e}")
    
    def _open_data_dir(self, icon, item):
        """Open data directory"""
        try:
            from backend.utils.data_paths import get_data_path
            data_path = get_data_path()
            subprocess.run(['explorer', str(data_path)], shell=True)
            logger.info(f"Opened data directory: {data_path}")
        except Exception as e:
            logger.error(f"Failed to open data directory: {e}")
    
    def _stop_server(self, icon, item):
        """Stop the PyRobot server"""
        try:
            if self.stop_callback:
                logger.info("Stopping PyRobot server via tray menu")
                self.stop_callback()
            else:
                logger.warning("No stop callback configured")
        except Exception as e:
            logger.error(f"Failed to stop server: {e}")
    
    def _exit_app(self, icon, item):
        """Exit the application"""
        try:
            logger.info("Exiting PyRobot via tray menu")
            self.stop()
            if self.stop_callback:
                self.stop_callback()
            # Force exit after a short delay
            threading.Timer(1.0, lambda: sys.exit(0)).start()
        except Exception as e:
            logger.error(f"Failed to exit application: {e}")
            sys.exit(1)

# Global tray instance
_tray_instance: Optional[PyRobotSystemTray] = None

def get_system_tray(port: int = 8005) -> PyRobotSystemTray:
    """Get the global system tray instance"""
    global _tray_instance
    if _tray_instance is None:
        _tray_instance = PyRobotSystemTray(port)
    return _tray_instance

def start_system_tray(port: int = 8005, stop_callback: Optional[Callable] = None) -> PyRobotSystemTray:
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