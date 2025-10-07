"""
Comprehensive resource management for PyRobot backend.

Monitors and optimizes memory usage, file handles, and system resources
with automatic cleanup and garbage collection strategies.
"""

import asyncio
import gc
import logging
import psutil
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from contextlib import contextmanager, asynccontextmanager
import weakref
import os

logger = logging.getLogger(__name__)

@dataclass
class ResourceUsage:
    """System resource usage snapshot"""
    timestamp: datetime
    memory_usage_mb: float
    memory_percentage: float
    cpu_percentage: float
    disk_usage_percentage: float
    open_files_count: int
    thread_count: int
    
@dataclass
class MemoryPool:
    """Memory pool for reusing objects"""
    name: str
    max_size: int
    current_size: int = 0
    objects: List[Any] = field(default_factory=list)
    created_count: int = 0
    reused_count: int = 0

class ResourceManager:
    """
    Comprehensive resource manager for memory, file handles, and system resources.
    
    Features:
    - Real-time memory monitoring and alerting
    - Automatic garbage collection triggers
    - File handle leak detection
    - Memory pool management for frequent allocations
    - Resource usage analytics and optimization
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
        
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        # Resource monitoring configuration
        self.memory_warning_threshold = 80.0  # 80% memory usage
        self.memory_critical_threshold = 90.0  # 90% memory usage
        self.monitoring_interval = 30  # seconds
        
        # Resource tracking
        self.resource_history: List[ResourceUsage] = []
        self.max_history_size = 1440  # 24 hours at 1-minute intervals
        
        # Memory pools for frequent allocations
        self.memory_pools: Dict[str, MemoryPool] = {
            'video_frames': MemoryPool('video_frames', max_size=50),
            'image_buffers': MemoryPool('image_buffers', max_size=20),
            'query_results': MemoryPool('query_results', max_size=100)
        }
        
        # Weak reference tracking for automatic cleanup
        self.tracked_objects = weakref.WeakSet()
        
        # Cleanup callbacks
        self.cleanup_callbacks: List[Callable] = []
        
        # Monitoring state
        self._monitoring_active = False
        self._monitoring_task = None
        
        # Alert handlers
        self.alert_handlers: List[Callable[[str, Dict[str, Any]], None]] = []
        
        self._initialized = True
        logger.info("ResourceManager initialized")
        
    async def start_monitoring(self):
        """Start resource monitoring"""
        if self._monitoring_active:
            return
            
        self._monitoring_active = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Resource monitoring started")
        
    async def stop_monitoring(self):
        """Stop resource monitoring"""
        self._monitoring_active = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Resource monitoring stopped")
        
    async def _monitoring_loop(self):
        """Main resource monitoring loop"""
        while self._monitoring_active:
            try:
                # Collect resource usage
                usage = self.get_current_resource_usage()
                self.resource_history.append(usage)
                
                # Trim history if needed
                if len(self.resource_history) > self.max_history_size:
                    self.resource_history = self.resource_history[-self.max_history_size:]
                
                # Check for resource warnings
                await self._check_resource_alerts(usage)
                
                # Trigger cleanup if needed
                await self._auto_cleanup(usage)
                
                await asyncio.sleep(self.monitoring_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                await asyncio.sleep(30)
                
    def get_current_resource_usage(self) -> ResourceUsage:
        """Get current system resource usage"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            # System-wide stats
            system_memory = psutil.virtual_memory()
            system_disk = psutil.disk_usage('/')
            
            return ResourceUsage(
                timestamp=datetime.now(),
                memory_usage_mb=memory_info.rss / 1024 / 1024,
                memory_percentage=memory_percent,
                cpu_percentage=process.cpu_percent(),
                disk_usage_percentage=system_disk.percent,
                open_files_count=len(process.open_files()),
                thread_count=process.num_threads()
            )
        except Exception as e:
            logger.error(f"Error getting resource usage: {e}")
            return ResourceUsage(
                timestamp=datetime.now(),
                memory_usage_mb=0,
                memory_percentage=0,
                cpu_percentage=0,
                disk_usage_percentage=0,
                open_files_count=0,
                thread_count=0
            )
            
    async def _check_resource_alerts(self, usage: ResourceUsage):
        """Check for resource usage alerts"""
        alerts = []
        
        if usage.memory_percentage > self.memory_critical_threshold:
            alerts.append({
                'level': 'critical',
                'type': 'memory',
                'message': f'Memory usage critical: {usage.memory_percentage:.1f}%',
                'usage': usage
            })
        elif usage.memory_percentage > self.memory_warning_threshold:
            alerts.append({
                'level': 'warning', 
                'type': 'memory',
                'message': f'Memory usage high: {usage.memory_percentage:.1f}%',
                'usage': usage
            })
            
        if usage.disk_usage_percentage > 90:
            alerts.append({
                'level': 'warning',
                'type': 'disk',
                'message': f'Disk usage high: {usage.disk_usage_percentage:.1f}%',
                'usage': usage
            })
            
        if usage.open_files_count > 500:
            alerts.append({
                'level': 'warning',
                'type': 'file_handles',
                'message': f'High file handle count: {usage.open_files_count}',
                'usage': usage
            })
            
        # Send alerts
        for alert in alerts:
            for handler in self.alert_handlers:
                try:
                    handler(alert['level'], alert)
                except Exception as e:
                    logger.error(f"Alert handler error: {e}")
                    
    async def _auto_cleanup(self, usage: ResourceUsage):
        """Perform automatic cleanup based on resource usage"""
        cleanup_triggered = False
        
        # Trigger cleanup if memory usage is high
        if usage.memory_percentage > self.memory_warning_threshold:
            logger.info("Memory usage high, triggering cleanup")
            await self.cleanup_resources()
            cleanup_triggered = True
            
        # Force garbage collection if memory is critical
        if usage.memory_percentage > self.memory_critical_threshold:
            logger.warning("Memory usage critical, forcing garbage collection")
            gc.collect()
            cleanup_triggered = True
            
        if cleanup_triggered:
            # Log cleanup results
            new_usage = self.get_current_resource_usage()
            memory_freed = usage.memory_usage_mb - new_usage.memory_usage_mb
            logger.info(f"Cleanup completed: {memory_freed:.1f}MB freed")
            
    def register_cleanup_callback(self, callback: Callable):
        """Register a cleanup callback"""
        self.cleanup_callbacks.append(callback)
        
    def register_alert_handler(self, handler: Callable[[str, Dict[str, Any]], None]):
        """Register an alert handler"""
        self.alert_handlers.append(handler)
        
    async def cleanup_resources(self):
        """Perform comprehensive resource cleanup"""
        logger.info("Starting resource cleanup")
        
        # Call registered cleanup callbacks
        for callback in self.cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Cleanup callback error: {e}")
                
        # Clean up memory pools
        for pool_name, pool in self.memory_pools.items():
            if pool.current_size > pool.max_size // 2:  # If more than half full
                objects_to_remove = pool.current_size - (pool.max_size // 4)
                for _ in range(objects_to_remove):
                    if pool.objects:
                        pool.objects.pop(0)
                        pool.current_size -= 1
                logger.debug(f"Cleaned up {objects_to_remove} objects from {pool_name} pool")
                
        # Force garbage collection
        collected = gc.collect()
        logger.info(f"Resource cleanup completed: {collected} objects collected")
        
    @contextmanager
    def get_from_pool(self, pool_name: str, factory_func: Callable = None):
        """Context manager for getting objects from memory pool"""
        pool = self.memory_pools.get(pool_name)
        if not pool:
            raise ValueError(f"Unknown memory pool: {pool_name}")
            
        obj = None
        if pool.objects:
            obj = pool.objects.pop()
            pool.current_size -= 1
            pool.reused_count += 1
        elif factory_func:
            obj = factory_func()
            pool.created_count += 1
            
        try:
            yield obj
        finally:
            # Return object to pool if there's space
            if obj and pool.current_size < pool.max_size:
                # Reset object state if it has a reset method
                if hasattr(obj, 'reset'):
                    obj.reset()
                pool.objects.append(obj)
                pool.current_size += 1
                
    def track_object(self, obj: Any):
        """Track object for automatic cleanup"""
        self.tracked_objects.add(obj)
        
    def get_memory_pool_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get memory pool statistics"""
        stats = {}
        for name, pool in self.memory_pools.items():
            stats[name] = {
                'max_size': pool.max_size,
                'current_size': pool.current_size,
                'created_count': pool.created_count,
                'reused_count': pool.reused_count,
                'reuse_ratio': pool.reused_count / max(pool.created_count, 1)
            }
        return stats
        
    def get_resource_analytics(self, hours: int = 1) -> Dict[str, Any]:
        """Get resource usage analytics for specified time period"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_usage = [u for u in self.resource_history if u.timestamp > cutoff_time]
        
        if not recent_usage:
            return {"error": "No recent usage data"}
            
        return {
            'period_hours': hours,
            'samples_count': len(recent_usage),
            'memory': {
                'avg_usage_mb': sum(u.memory_usage_mb for u in recent_usage) / len(recent_usage),
                'max_usage_mb': max(u.memory_usage_mb for u in recent_usage),
                'avg_percentage': sum(u.memory_percentage for u in recent_usage) / len(recent_usage),
                'max_percentage': max(u.memory_percentage for u in recent_usage)
            },
            'cpu': {
                'avg_percentage': sum(u.cpu_percentage for u in recent_usage) / len(recent_usage),
                'max_percentage': max(u.cpu_percentage for u in recent_usage)
            },
            'files': {
                'avg_open_files': sum(u.open_files_count for u in recent_usage) / len(recent_usage),
                'max_open_files': max(u.open_files_count for u in recent_usage)
            }
        }
        
    @asynccontextmanager
    async def memory_monitoring_context(self, operation_name: str):
        """Context manager for monitoring memory usage during operations"""
        start_usage = self.get_current_resource_usage()
        start_time = time.time()
        
        try:
            yield
        finally:
            end_usage = self.get_current_resource_usage()
            end_time = time.time()
            
            memory_delta = end_usage.memory_usage_mb - start_usage.memory_usage_mb
            duration = end_time - start_time
            
            logger.info(
                f"Operation '{operation_name}' completed: "
                f"Duration: {duration:.2f}s, "
                f"Memory change: {memory_delta:+.2f}MB"
            )
            
            # Log warning if operation used excessive memory
            if memory_delta > 100:  # More than 100MB
                logger.warning(
                    f"Operation '{operation_name}' used {memory_delta:.1f}MB memory"
                )

# Global resource manager instance
resource_manager = ResourceManager()

# Utility functions for common resource management patterns
def cleanup_video_resources():
    """Cleanup video processing resources"""
    import cv2
    # Force OpenCV to release all resources
    cv2.destroyAllWindows()
    gc.collect()

def cleanup_database_resources():
    """Cleanup database connection resources"""
    # This would be called by the connection manager
    pass

# Register default cleanup callbacks
resource_manager.register_cleanup_callback(cleanup_video_resources)
resource_manager.register_cleanup_callback(cleanup_database_resources)

# Default alert handler that logs to the standard logger
def default_alert_handler(level: str, alert: Dict[str, Any]):
    """Default handler for resource alerts"""
    message = alert['message']
    if level == 'critical':
        logger.critical(f"RESOURCE ALERT: {message}")
    elif level == 'warning':
        logger.warning(f"RESOURCE ALERT: {message}")
    else:
        logger.info(f"RESOURCE ALERT: {message}")

resource_manager.register_alert_handler(default_alert_handler)