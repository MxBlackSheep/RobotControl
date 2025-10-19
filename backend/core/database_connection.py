"""
Centralized Database Connection Manager

High-performance connection pooling with async support and comprehensive monitoring.
Implements connection lifecycle management, health monitoring, and automatic recovery.
"""

import asyncio
import pyodbc
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
from backend.config import settings
from backend.utils.odbc_driver import choose_driver, format_driver_for_connection

logger = logging.getLogger(__name__)

@dataclass
class ConnectionHealth:
    """Connection health monitoring data"""
    connection_id: str
    created_at: datetime
    last_used: datetime
    query_count: int
    error_count: int
    is_healthy: bool

@dataclass
class PoolStats:
    """Connection pool statistics"""
    total_connections: int
    active_connections: int
    idle_connections: int
    failed_connections: int
    avg_query_time: float
    total_queries: int

class AsyncDatabaseConnectionManager:
    """
    High-performance async database connection manager with comprehensive monitoring.
    
    Features:
    - Thread-safe connection pooling with automatic cleanup
    - Connection health monitoring and automatic recovery
    - Query performance tracking and optimization
    - Circuit breaker pattern for fault tolerance
    - Async context managers for proper resource management
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
            
        # Connection pool configuration
        self.min_connections = 2
        self.max_connections = 10
        self.connection_timeout = 5
        self.pool_timeout = 3
        self.health_check_interval = 60
        
        # Connection pools (separate for production and development)
        self._production_pool = Queue(maxsize=self.max_connections)
        self._development_pool = Queue(maxsize=self.max_connections)
        self._pool_lock = threading.RLock()
        
        # Connection tracking
        self._connection_health: Dict[str, ConnectionHealth] = {}
        self._pool_stats = PoolStats(0, 0, 0, 0, 0.0, 0)
        
        # Thread pool for async operations
        self._executor = ThreadPoolExecutor(max_workers=5)
        
        # Circuit breaker state
        self._circuit_breaker_state = "closed"  # closed, open, half-open
        self._failure_count = 0
        self._failure_threshold = 5
        self._recovery_timeout = 60
        self._last_failure_time = None
        
        # Health monitoring
        self._health_monitor_task = None
        self._monitoring_active = False

        # Resolve SQL Server ODBC driver once on initialization
        try:
            configured_driver = settings.DB_CONFIG_PRIMARY.get('driver')  # type: ignore[attr-defined]
        except AttributeError:
            configured_driver = None

        self._driver_name = choose_driver(configured_driver)
        self._driver_clause = format_driver_for_connection(self._driver_name)

        if self._driver_clause:
            logger.info("Using SQL Server ODBC driver '%s'", self._driver_name)
        else:
            logger.error("No SQL Server ODBC driver detected; database connections will fail until a driver is installed")
        
        self._initialized = True
        logger.info("AsyncDatabaseConnectionManager initialized")
        
    async def start_monitoring(self):
        """Start connection health monitoring"""
        if self._monitoring_active:
            return
            
        self._monitoring_active = True
        self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Database connection health monitoring started")
        
    async def stop_monitoring(self):
        """Stop connection health monitoring"""
        self._monitoring_active = False
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Database connection health monitoring stopped")

    async def get_connection_async(self, timeout: int = 30) -> Optional[pyodbc.Connection]:
        """
        Get database connection asynchronously with circuit breaker protection.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            Database connection or None if unavailable
        """
        # Check circuit breaker
        if not await self._check_circuit_breaker():
            logger.warning("Circuit breaker is open - refusing connection request")
            return None
            
        try:
            # Run connection creation in thread pool to avoid blocking
            connection = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                self._get_connection_sync,
                timeout
            )
            
            if connection:
                await self._record_successful_connection()
                return connection
            else:
                await self._record_connection_failure()
                return None
                
        except Exception as e:
            logger.error(f"Async connection error: {e}")
            await self._record_connection_failure()
            return None

    def _get_connection_sync(self, timeout: int) -> Optional[pyodbc.Connection]:
        """Synchronous connection creation (runs in thread pool)"""
        # Try to get existing connection from pool
        connection = self._get_pooled_connection()
        if connection and self._test_connection(connection):
            return connection
        
        # Create new connection with fallback logic
        connection = self._create_new_connection(timeout)
        if connection:
            self._track_connection(connection)
        
        return connection

    def _get_pooled_connection(self) -> Optional[pyodbc.Connection]:
        """Get connection from pool if available"""
        try:
            # Try production pool first
            return self._production_pool.get_nowait()
        except Empty:
            try:
                # Fallback to development pool
                return self._development_pool.get_nowait()
            except Empty:
                return None

    def _get_driver_clause(self) -> Optional[str]:
        """Lazily resolve the SQL Server ODBC driver clause."""
        if self._driver_clause:
            return self._driver_clause

        try:
            configured_driver = settings.DB_CONFIG_PRIMARY.get('driver')  # type: ignore[attr-defined]
        except AttributeError:
            configured_driver = None

        previous_name = getattr(self, '_driver_name', None)
        self._driver_name = choose_driver(configured_driver)
        self._driver_clause = format_driver_for_connection(self._driver_name)

        if self._driver_clause:
            if self._driver_name and self._driver_name != previous_name:
                logger.info("Using SQL Server ODBC driver '%s'", self._driver_name)
        else:
            logger.error("No SQL Server ODBC driver detected; database connections will fail until a driver is installed")

        return self._driver_clause

    def _create_new_connection(self, timeout: int) -> Optional[pyodbc.Connection]:
        """Create new database connection with fallback"""
        driver_clause = self._get_driver_clause()
        if not driver_clause:
            return None

        # Try production first (integrated auth)
        try:
            conn_string = (
                f"DRIVER={driver_clause};"
                "SERVER=LOCALHOST\\HAMILTON;"
                "DATABASE=EvoYeast;"
                "Trusted_Connection=yes;"
            )
            conn = pyodbc.connect(conn_string, timeout=2)
            conn.timeout = timeout
            conn.autocommit = True  # Better performance for read operations
            logger.debug("Connected using integrated authentication (production)")
            return conn
        except Exception as prod_error:
            logger.debug(f"Production connection failed: {prod_error}")
        
        # Try development VM
        try:
            conn_string = (
                f"DRIVER={driver_clause};"
                f"SERVER={settings.VM_SQL_SERVER};"
                "DATABASE=EvoYeast;"
                f"UID={settings.VM_SQL_USER};"
                f"PWD={settings.VM_SQL_PASSWORD};"
                "Encrypt=no;TrustServerCertificate=yes;"
            )
            conn = pyodbc.connect(conn_string, timeout=2)
            conn.timeout = timeout
            conn.autocommit = True
            logger.debug(f"Connected to VM SQL Server: {settings.VM_SQL_SERVER}")
            return conn
        except Exception as dev_error:
            logger.debug(f"Development connection failed: {dev_error}")
        
        logger.error("All database connection methods failed")
        return None

    def _test_connection(self, connection: pyodbc.Connection) -> bool:
        """Test if connection is still healthy"""
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False

    def _track_connection(self, connection: pyodbc.Connection):
        """Track connection for health monitoring"""
        conn_id = str(id(connection))
        self._connection_health[conn_id] = ConnectionHealth(
            connection_id=conn_id,
            created_at=datetime.now(),
            last_used=datetime.now(),
            query_count=0,
            error_count=0,
            is_healthy=True
        )

    async def _check_circuit_breaker(self) -> bool:
        """Check circuit breaker state"""
        if self._circuit_breaker_state == "closed":
            return True
        elif self._circuit_breaker_state == "open":
            # Check if we should transition to half-open
            if (self._last_failure_time and 
                datetime.now() - self._last_failure_time > timedelta(seconds=self._recovery_timeout)):
                self._circuit_breaker_state = "half-open"
                logger.info("Circuit breaker transitioning to half-open")
                return True
            return False
        else:  # half-open
            return True

    async def _record_successful_connection(self):
        """Record successful connection for circuit breaker"""
        if self._circuit_breaker_state == "half-open":
            self._circuit_breaker_state = "closed"
            self._failure_count = 0
            logger.info("Circuit breaker closed after successful connection")

    async def _record_connection_failure(self):
        """Record connection failure for circuit breaker"""
        self._failure_count += 1
        self._last_failure_time = datetime.now()
        
        if self._failure_count >= self._failure_threshold:
            self._circuit_breaker_state = "open"
            logger.warning(f"Circuit breaker opened after {self._failure_count} failures")

    @asynccontextmanager
    async def get_async_connection(self, timeout: int = 30):
        """Async context manager for database connections"""
        connection = await self.get_connection_async(timeout)
        if connection is None:
            raise ConnectionError("Unable to establish database connection")
        
        try:
            yield connection
        finally:
            await self.return_connection_async(connection)

    async def return_connection_async(self, connection: pyodbc.Connection):
        """Return connection to pool asynchronously"""
        if connection and self._test_connection(connection):
            # Return to appropriate pool
            try:
                # Determine which pool based on connection string
                if "LOCALHOST" in str(connection):
                    self._production_pool.put_nowait(connection)
                else:
                    self._development_pool.put_nowait(connection)
            except:
                # Pool is full, close connection
                connection.close()
        else:
            # Close unhealthy connection
            if connection:
                try:
                    connection.close()
                except:
                    pass

    async def _health_monitor_loop(self):
        """Periodic health monitoring of connections"""
        while self._monitoring_active:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(30)  # Wait before retrying

    async def _perform_health_check(self):
        """Perform health check on all tracked connections"""
        current_time = datetime.now()
        unhealthy_connections = []
        
        for conn_id, health in self._connection_health.items():
            # Check if connection is too old (> 1 hour)
            if current_time - health.created_at > timedelta(hours=1):
                unhealthy_connections.append(conn_id)
            # Check error rate
            elif health.query_count > 0 and (health.error_count / health.query_count) > 0.1:
                unhealthy_connections.append(conn_id)
        
        # Remove unhealthy connections
        for conn_id in unhealthy_connections:
            del self._connection_health[conn_id]
            
        logger.debug(f"Health check complete: {len(unhealthy_connections)} connections removed")

    def get_pool_stats(self) -> PoolStats:
        """Get current connection pool statistics"""
        production_size = self._production_pool.qsize()
        development_size = self._development_pool.qsize()
        
        return PoolStats(
            total_connections=production_size + development_size,
            active_connections=len(self._connection_health),
            idle_connections=production_size + development_size,
            failed_connections=self._failure_count,
            avg_query_time=self._pool_stats.avg_query_time,
            total_queries=self._pool_stats.total_queries
        )

    def reset_pools(self):
        """Close and clear pooled connections after disruptive operations."""
        with self._pool_lock:
            for pool in (self._production_pool, self._development_pool):
                while True:
                    try:
                        connection = pool.get_nowait()
                    except Empty:
                        break
                    try:
                        connection.close()
                    except Exception:
                        pass

            self._connection_health.clear()
            self._pool_stats = PoolStats(0, 0, 0, 0, 0.0, 0)
            self._failure_count = 0
            self._circuit_breaker_state = "closed"
            self._last_failure_time = None

# Global async connection manager instance
async_db_manager = AsyncDatabaseConnectionManager()

# Legacy compatibility - synchronous connection method
class DatabaseConnectionManager:
    """Legacy synchronous database connection manager"""
    
    @staticmethod
    def get_connection(timeout: int = 30) -> Optional[pyodbc.Connection]:
        """Legacy synchronous connection method"""
        return async_db_manager._get_connection_sync(timeout)

    @staticmethod
    def reset_pools():
        """Expose pool reset for callers that need to drop stale connections."""
        async_db_manager.reset_pools()

# Global instance for backward compatibility
db_connection_manager = DatabaseConnectionManager()

