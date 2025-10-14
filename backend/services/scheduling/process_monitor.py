"""
Hamilton Process Monitoring Service

Monitors Hamilton HxRun.exe process status for scheduling system.
Replicates VBS script functionality for process detection and availability checking.

Features:
- Windows WMI integration for process monitoring
- Mock mode for development environments without HxRun.exe
- Process availability detection and waiting
- Hamilton robot status monitoring
"""

import logging
import time
import threading
import subprocess
import platform
import os
from typing import Dict, Any, List, Optional, Tuple, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Development mode detection - if HxRun.exe is not available
# Process monitor for Hamilton HxRun.exe processes


@dataclass
class ProcessInfo:
    """Information about a running process"""
    process_id: int
    process_name: str
    command_line: Optional[str]
    start_time: datetime
    cpu_percent: float = 0.0
    memory_mb: float = 0.0


@dataclass
class HamiltonStatus:
    """Hamilton robot status information"""
    is_running: bool
    process_count: int
    processes: List[ProcessInfo]
    last_check: datetime
    availability: str  # 'available', 'busy', 'error', 'unknown'


class HamiltonProcessMonitor:
    """Process monitoring service for Hamilton HxRun.exe"""
    
    def __init__(self):
        """
        Initialize the Hamilton process monitor
        """
        self._monitoring = False
        self._monitor_thread = None
        self._status_callbacks = []
        self._last_status = HamiltonStatus(
            is_running=False,
            process_count=0,
            processes=[],
            last_check=datetime.now(),
            availability='unknown'
        )
        self._status_lock = threading.Lock()
        
        # Windows-specific WMI initialization
        self._wmi = None
        if platform.system() == "Windows":
            try:
                import wmi
                self._wmi = wmi.WMI()
                logger.info("WMI initialized for Hamilton process monitoring")
            except ImportError:
                logger.warning("WMI module not available - process monitoring will be limited")
            except Exception as e:
                logger.warning(f"WMI initialization failed: {e} - process monitoring will be limited")
        
        logger.info("Hamilton process monitor initialized")
    
    def start_monitoring(self, check_interval: float = 5.0) -> bool:
        """
        Start process monitoring in background thread
        
        Args:
            check_interval: Seconds between process checks
            
        Returns:
            bool: True if monitoring started successfully
        """
        try:
            if self._monitoring:
                logger.warning("Process monitoring already running")
                return True
            
            self._monitoring = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                args=(check_interval,),
                daemon=True,
                name="HamiltonProcessMonitor"
            )
            self._monitor_thread.start()
            
            logger.info("Hamilton process monitoring started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start process monitoring: {e}")
            self._monitoring = False
            return False
    
    def stop_monitoring(self):
        """Stop process monitoring"""
        self._monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        logger.info("Hamilton process monitoring stopped")
    
    def is_hamilton_running(self) -> bool:
        """
        Check if Hamilton HxRun.exe is currently running
        Replicates VBS isProcessRunning functionality
        
        Returns:
            bool: True if HxRun.exe is running, False otherwise
        """
        try:
            # Use WMI to check for HxRun.exe processes if available
            if self._wmi:
                processes = self._wmi.Win32_Process(name="HxRun.exe")
                is_running = len(processes) > 0
            else:
                # Fallback method using tasklist command (Windows-specific)
                if platform.system() == "Windows":
                    try:
                        # Suppress tasklist window flashes in packaged apps
                        startupinfo = None
                        creationflags = 0
                        if os.name == "nt":
                            startupinfo = subprocess.STARTUPINFO()
                            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                            creationflags = subprocess.CREATE_NO_WINDOW

                        result = subprocess.run(
                            ['tasklist', '/FI', 'IMAGENAME eq HxRun.exe'],
                            capture_output=True,
                            text=True,
                            timeout=5,
                            startupinfo=startupinfo,
                            creationflags=creationflags
                        )
                        is_running = "HxRun.exe" in result.stdout
                    except Exception as e:
                        logger.debug(f"Tasklist fallback failed: {e}")
                        is_running = False
                else:
                    # Non-Windows fallback
                    is_running = False
            
            if self._wmi:
                logger.debug(f"Hamilton running check: {is_running} ({len(processes)} processes)")
            else:
                logger.debug(f"Hamilton running check: {is_running} (using tasklist fallback)")
            return is_running
            
        except Exception as e:
            logger.error(f"Error checking Hamilton process: {e}")
            return False
    
    def get_hamilton_processes(self) -> List[ProcessInfo]:
        """
        Get information about running Hamilton processes
        
        Returns:
            List of ProcessInfo objects for Hamilton processes
        """
        try:
            if not self._wmi:
                return []
            
            processes = []
            for proc in self._wmi.Win32_Process(name="HxRun.exe"):
                try:
                    # Get process creation time
                    start_time = datetime.now()  # Fallback
                    if hasattr(proc, 'CreationDate') and proc.CreationDate:
                        try:
                            # WMI date format conversion
                            import datetime as dt
                            start_time = dt.datetime.strptime(proc.CreationDate[:14], '%Y%m%d%H%M%S')
                        except:
                            pass
                    
                    process_info = ProcessInfo(
                        process_id=proc.ProcessId,
                        process_name=proc.Name,
                        command_line=proc.CommandLine,
                        start_time=start_time,
                        cpu_percent=0.0,  # Would need additional WMI queries
                        memory_mb=0.0
                    )
                    processes.append(process_info)
                    
                except Exception as e:
                    logger.warning(f"Error getting process info for PID {proc.ProcessId}: {e}")
            
            return processes
            
        except Exception as e:
            logger.error(f"Error getting Hamilton processes: {e}")
            return []
    
    def wait_for_hamilton_available(self, timeout_minutes: int = 10) -> bool:
        """
        Wait for Hamilton to become available (not running)
        
        Args:
            timeout_minutes: Maximum time to wait
            
        Returns:
            bool: True if Hamilton becomes available, False if timeout
        """
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        logger.info(f"Waiting for Hamilton to become available (timeout: {timeout_minutes} minutes)")
        
        while time.time() - start_time < timeout_seconds:
            if not self.is_hamilton_running():
                logger.info("Hamilton is now available")
                return True
            
            time.sleep(5)  # Check every 5 seconds
        
        logger.warning(f"Timeout waiting for Hamilton availability ({timeout_minutes} minutes)")
        return False
    
    def get_status(self) -> HamiltonStatus:
        """
        Get current Hamilton status
        
        Returns:
            HamiltonStatus object with current status information
        """
        with self._status_lock:
            return HamiltonStatus(
                is_running=self._last_status.is_running,
                process_count=self._last_status.process_count,
                processes=self._last_status.processes.copy(),
                last_check=self._last_status.last_check,
                availability=self._last_status.availability
            )
    
    def add_status_callback(self, callback: Callable[[HamiltonStatus], None]):
        """
        Add a callback function to be called when status changes
        
        Args:
            callback: Function to call with HamiltonStatus when status changes
        """
        self._status_callbacks.append(callback)
    
    def remove_status_callback(self, callback: Callable[[HamiltonStatus], None]):
        """
        Remove a status callback function
        
        Args:
            callback: Function to remove from callbacks
        """
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
    
    
    def _monitor_loop(self, check_interval: float):
        """
        Main monitoring loop running in background thread
        
        Args:
            check_interval: Seconds between checks
        """
        logger.info("Process monitoring loop started")
        
        while self._monitoring:
            try:
                # Get current process information
                is_running = self.is_hamilton_running()
                processes = self.get_hamilton_processes()
                process_count = len(processes)
                
                # Determine availability
                availability = 'available'
                if is_running:
                    availability = 'busy'
                elif process_count == 0:
                    availability = 'available'
                else:
                    availability = 'unknown'
                
                # Create new status
                new_status = HamiltonStatus(
                    is_running=is_running,
                    process_count=process_count,
                    processes=processes,
                    last_check=datetime.now(),
                    availability=availability
                )
                
                # Check if status changed
                status_changed = False
                with self._status_lock:
                    if (self._last_status.is_running != new_status.is_running or
                        self._last_status.process_count != new_status.process_count or
                        self._last_status.availability != new_status.availability):
                        status_changed = True
                    
                    self._last_status = new_status
                
                # Notify callbacks if status changed
                if status_changed:
                    logger.info(f"Hamilton status changed: {availability} ({process_count} processes)")
                    for callback in self._status_callbacks:
                        try:
                            callback(new_status)
                        except Exception as e:
                            logger.error(f"Status callback error: {e}")
                
                time.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Error in process monitoring loop: {e}")
                time.sleep(check_interval)
        
        logger.info("Process monitoring loop stopped")


# Singleton instance management
_process_monitor_instance = None
_process_monitor_lock = threading.Lock()


def get_hamilton_process_monitor() -> HamiltonProcessMonitor:
    """
    Get the singleton HamiltonProcessMonitor instance
    
    Returns:
        HamiltonProcessMonitor: The process monitor instance
    """
    global _process_monitor_instance
    
    with _process_monitor_lock:
        if _process_monitor_instance is None:
            _process_monitor_instance = HamiltonProcessMonitor()
            
    return _process_monitor_instance


def is_hamilton_available() -> bool:
    """
    Quick check if Hamilton is available (not running)
    Convenience function replicating VBS functionality
    
    Returns:
        bool: True if Hamilton is available, False if busy
    """
    monitor = get_hamilton_process_monitor()
    return not monitor.is_hamilton_running()
