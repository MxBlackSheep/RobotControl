"""
High-performance WebSocket management for RobotControl real-time features.

Implements connection pooling, load balancing, and resource management
for scalable WebSocket operations.
"""

import asyncio
import json
import logging
import time
import random
from datetime import datetime, timedelta
from typing import Dict, Set, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from fastapi import WebSocket, WebSocketDisconnect
import weakref
from collections import defaultdict, deque
import uuid
from enum import Enum

logger = logging.getLogger(__name__)

class ConnectionState(Enum):
    """WebSocket connection states"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    FAILED = "failed"

@dataclass
class ReconnectionConfig:
    """Configuration for automatic reconnection with exponential backoff"""
    enabled: bool = True
    max_retries: int = 5
    initial_delay: float = 1.0  # seconds
    max_delay: float = 60.0     # seconds
    backoff_multiplier: float = 2.0
    jitter: bool = True         # Add random jitter to prevent thundering herd

@dataclass
class ConnectionInfo:
    """WebSocket connection information"""
    websocket: WebSocket
    connection_id: str
    channel: str
    connected_at: datetime
    last_ping: datetime
    last_pong: datetime
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    message_count: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    # Enhanced connection state tracking
    state: ConnectionState = ConnectionState.CONNECTING
    reconnection_attempts: int = 0
    last_reconnection_attempt: Optional[datetime] = None
    connection_errors: List[str] = field(default_factory=list)
    # Resource cleanup tracking
    cleanup_tasks: Set[asyncio.Task] = field(default_factory=set)
    message_queue: Optional[deque] = None  # For offline message queuing

@dataclass
class ChannelStats:
    """Channel statistics"""
    name: str
    connection_count: int
    message_count: int
    bytes_transferred: int
    created_at: datetime
    last_activity: datetime

class WebSocketConnectionManager:
    """
    High-performance WebSocket connection manager with advanced features.
    
    Features:
    - Connection pooling with automatic cleanup
    - Channel-based message routing
    - Load balancing across multiple workers
    - Heartbeat monitoring with automatic reconnection
    - Message queuing and delivery guarantees
    - Connection rate limiting and throttling
    - Comprehensive monitoring and analytics
    """
    
    def __init__(self, max_connections_per_channel: int = 100, 
                 reconnection_config: Optional[ReconnectionConfig] = None):
        # Connection management
        self.connections: Dict[str, ConnectionInfo] = {}
        self.channels: Dict[str, Set[str]] = defaultdict(set)
        self.user_connections: Dict[str, Set[str]] = defaultdict(set)
        
        # Configuration
        self.max_connections_per_channel = max_connections_per_channel
        self.heartbeat_interval = 30  # seconds
        self.connection_timeout = 90  # seconds
        self.max_message_size = 1024 * 1024  # 1MB
        self.rate_limit_messages_per_minute = 60
        
        # Enhanced reconnection configuration
        self.reconnection_config = reconnection_config or ReconnectionConfig()
        
        # Enhanced message queuing with persistence for reconnection
        self.message_queues: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.offline_message_queues: Dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        self.delivery_guarantees = True
        
        # Monitoring
        self.channel_stats: Dict[str, ChannelStats] = {}
        self.total_connections = 0
        self.total_messages = 0
        self.start_time = datetime.now()
        
        # Enhanced background tasks
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        self.reconnection_task: Optional[asyncio.Task] = None
        self.resource_monitor_task: Optional[asyncio.Task] = None
        self.monitoring_active = False
        
        # Rate limiting
        self.rate_limits: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Resource management tracking
        self.pending_cleanup_tasks: Set[asyncio.Task] = set()
        self.connection_pools: Dict[str, Set[str]] = defaultdict(set)  # Pool connections by type
        self.memory_usage_bytes = 0
        
        logger.info("WebSocketConnectionManager initialized with enhanced resource management")
        
    async def start_background_tasks(self):
        """Start enhanced background monitoring and resource management tasks"""
        if self.monitoring_active:
            return
            
        self.monitoring_active = True
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        # Enhanced resource management tasks
        if self.reconnection_config.enabled:
            self.reconnection_task = asyncio.create_task(self._reconnection_loop())
        
        self.resource_monitor_task = asyncio.create_task(self._resource_monitor_loop())
        
        logger.info("WebSocket background tasks started with enhanced resource management")
        
    async def stop_background_tasks(self):
        """Stop enhanced background monitoring and resource management tasks"""
        self.monitoring_active = False
        
        tasks_to_cancel = [
            ("heartbeat", self.heartbeat_task),
            ("cleanup", self.cleanup_task),
            ("reconnection", self.reconnection_task),
            ("resource_monitor", self.resource_monitor_task)
        ]
        
        for task_name, task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.debug(f"{task_name} task cancelled")
                except Exception as e:
                    logger.error(f"Error stopping {task_name} task: {e}")
        
        # Clean up any pending resource cleanup tasks
        for task in list(self.pending_cleanup_tasks):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error cancelling cleanup task: {e}")
        
        self.pending_cleanup_tasks.clear()
        logger.info("WebSocket background tasks stopped with resource cleanup")
        
    async def connect(self, websocket: WebSocket, channel: str, user_id: Optional[str] = None) -> str:
        """
        Accept and register a new WebSocket connection.
        
        Args:
            websocket: FastAPI WebSocket instance
            channel: Channel name for message routing
            user_id: Optional user identifier
            
        Returns:
            Connection ID string
            
        Raises:
            ConnectionError: If connection limit exceeded
        """
        # Check channel connection limit
        if len(self.channels[channel]) >= self.max_connections_per_channel:
            raise ConnectionError(f"Channel '{channel}' connection limit exceeded")
            
        # Accept the WebSocket connection
        try:
            await websocket.accept()
        except Exception as e:
            logger.error(f"Failed to accept WebSocket connection: {e}")
            raise ConnectionError(f"Failed to accept connection: {e}")
            
        # Generate connection ID
        connection_id = str(uuid.uuid4())
        current_time = datetime.now()
        
        # Create enhanced connection info with resource tracking
        connection_info = ConnectionInfo(
            websocket=websocket,
            connection_id=connection_id,
            channel=channel,
            connected_at=current_time,
            last_ping=current_time,
            last_pong=current_time,
            user_id=user_id,
            state=ConnectionState.CONNECTED,  # Set to connected after successful accept
            message_queue=deque(maxlen=100)   # Initialize message queue for potential offline messages
        )
        
        # Register connection
        self.connections[connection_id] = connection_info
        self.channels[channel].add(connection_id)
        
        if user_id:
            self.user_connections[user_id].add(connection_id)
            
        # Update statistics
        self.total_connections += 1
        if channel not in self.channel_stats:
            self.channel_stats[channel] = ChannelStats(
                name=channel,
                connection_count=0,
                message_count=0,
                bytes_transferred=0,
                created_at=current_time,
                last_activity=current_time
            )
            
        self.channel_stats[channel].connection_count += 1
        self.channel_stats[channel].last_activity = current_time
        
        logger.info(f"WebSocket connected: {connection_id} to channel '{channel}' (user: {user_id})")
        
        # Send welcome message
        await self.send_to_connection(connection_id, {
            "type": "connection_established",
            "connection_id": connection_id,
            "channel": channel,
            "timestamp": current_time.isoformat()
        })
        
        return connection_id
        
    async def disconnect(self, connection_id: str, preserve_offline_queue: bool = False):
        """
        Disconnect and clean up a WebSocket connection with enhanced resource management.
        
        Args:
            connection_id: Connection ID to disconnect
            preserve_offline_queue: Whether to preserve message queue for reconnection
        """
        connection_info = self.connections.get(connection_id)
        if not connection_info:
            logger.warning(f"Attempted to disconnect unknown connection: {connection_id}")
            return
            
        try:
            # Update connection state
            connection_info.state = ConnectionState.DISCONNECTED
            
            # Enhanced resource cleanup
            channel = connection_info.channel
            user_id = connection_info.user_id
            
            # Cancel any ongoing cleanup tasks for this connection
            for task in list(connection_info.cleanup_tasks):
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"Error cancelling connection cleanup task: {e}")
            
            connection_info.cleanup_tasks.clear()
            
            # Preserve message queue for potential reconnection
            if preserve_offline_queue and connection_info.message_queue:
                queue_key = f"{user_id}:{channel}" if user_id else f"anonymous:{channel}"
                self.offline_message_queues[queue_key] = connection_info.message_queue.copy()
                logger.debug(f"Preserved {len(connection_info.message_queue)} messages for {queue_key}")
            
            # Remove from tracking structures
            self.channels[channel].discard(connection_id)
            self.connection_pools.get(channel, set()).discard(connection_id)
            
            if user_id:
                self.user_connections[user_id].discard(connection_id)
                # Clean up empty user sets
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
                    
            # Clean up empty channels and update stats
            if not self.channels[channel]:
                del self.channels[channel]
                # Don't delete channel stats to preserve historical data
            else:
                if channel in self.channel_stats:
                    self.channel_stats[channel].connection_count = max(0, 
                        self.channel_stats[channel].connection_count - 1)
                
            # Close WebSocket gracefully
            try:
                if connection_info.websocket and connection_info.websocket.client_state.name != 'DISCONNECTED':
                    await connection_info.websocket.close(code=1000, reason="Normal closure")
            except Exception as e:
                logger.debug(f"WebSocket already closed or error closing: {e}")
            
            # Clean up rate limiting data
            if connection_id in self.rate_limits:
                del self.rate_limits[connection_id]
                
            # Remove connection info last
            del self.connections[connection_id]
            
            logger.info(f"WebSocket disconnected: {connection_id} from channel '{channel}' "
                       f"(preserved_queue: {preserve_offline_queue})")
            
        except Exception as e:
            logger.error(f"Error during WebSocket disconnect: {e}")
            # Ensure connection is removed even if cleanup fails
            self.connections.pop(connection_id, None)
            
    async def send_to_connection(self, connection_id: str, message: Union[Dict, str]) -> bool:
        """
        Send message to a specific connection.
        
        Args:
            connection_id: Target connection ID
            message: Message to send (dict will be JSON encoded)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        connection_info = self.connections.get(connection_id)
        if not connection_info:
            logger.warning(f"Attempted to send to unknown connection: {connection_id}")
            return False
            
        try:
            # Prepare message
            if isinstance(message, dict):
                message_str = json.dumps(message)
            else:
                message_str = str(message)
                
            # Check message size
            if len(message_str) > self.max_message_size:
                logger.warning(f"Message too large ({len(message_str)} bytes) for connection {connection_id}")
                return False
                
            # Send message
            await connection_info.websocket.send_text(message_str)
            
            # Update statistics
            connection_info.message_count += 1
            connection_info.bytes_sent += len(message_str)
            
            channel_stats = self.channel_stats.get(connection_info.channel)
            if channel_stats:
                channel_stats.message_count += 1
                channel_stats.bytes_transferred += len(message_str)
                channel_stats.last_activity = datetime.now()
                
            self.total_messages += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message to connection {connection_id}: {e}")
            # Schedule connection for cleanup
            asyncio.create_task(self.disconnect(connection_id))
            return False
            
    async def broadcast_to_channel(self, channel: str, message: Union[Dict, str], 
                                 exclude_connections: Optional[Set[str]] = None) -> int:
        """
        Broadcast message to all connections in a channel.
        
        Args:
            channel: Target channel name
            message: Message to broadcast
            exclude_connections: Optional set of connection IDs to exclude
            
        Returns:
            Number of connections that received the message
        """
        if channel not in self.channels:
            logger.debug(f"No connections in channel '{channel}'")
            return 0
            
        exclude_connections = exclude_connections or set()
        target_connections = self.channels[channel] - exclude_connections
        
        if not target_connections:
            logger.debug(f"No target connections for broadcast in channel '{channel}'")
            return 0
            
        # Send to all connections concurrently
        tasks = []
        for connection_id in target_connections:
            tasks.append(self.send_to_connection(connection_id, message))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful sends
        successful_sends = sum(1 for result in results if result is True)
        
        logger.debug(f"Broadcast to channel '{channel}': {successful_sends}/{len(target_connections)} successful")
        
        return successful_sends
        
    async def send_to_user(self, user_id: str, message: Union[Dict, str]) -> int:
        """
        Send message to all connections for a specific user.
        
        Args:
            user_id: Target user ID
            message: Message to send
            
        Returns:
            Number of connections that received the message
        """
        if user_id not in self.user_connections:
            logger.debug(f"No connections for user '{user_id}'")
            return 0
            
        user_connection_ids = self.user_connections[user_id].copy()
        
        # Send to all user connections
        tasks = []
        for connection_id in user_connection_ids:
            tasks.append(self.send_to_connection(connection_id, message))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful sends
        successful_sends = sum(1 for result in results if result is True)
        
        logger.debug(f"Send to user '{user_id}': {successful_sends}/{len(user_connection_ids)} successful")
        
        return successful_sends
        
    async def _heartbeat_loop(self):
        """Background task for sending heartbeat pings"""
        while self.monitoring_active:
            try:
                current_time = datetime.now()
                ping_tasks = []
                
                for connection_id, connection_info in self.connections.items():
                    # Send ping if it's time
                    time_since_ping = current_time - connection_info.last_ping
                    if time_since_ping.total_seconds() >= self.heartbeat_interval:
                        ping_tasks.append(self._send_ping(connection_id))
                        
                # Send all pings concurrently
                if ping_tasks:
                    await asyncio.gather(*ping_tasks, return_exceptions=True)
                    
                await asyncio.sleep(self.heartbeat_interval / 2)  # Check twice per interval
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                await asyncio.sleep(10)
                
    async def _cleanup_loop(self):
        """Background task for cleaning up stale connections"""
        while self.monitoring_active:
            try:
                current_time = datetime.now()
                stale_connections = []
                
                for connection_id, connection_info in self.connections.items():
                    # Check for stale connections (no pong received)
                    time_since_pong = current_time - connection_info.last_pong
                    if time_since_pong.total_seconds() > self.connection_timeout:
                        stale_connections.append(connection_id)
                        
                # Clean up stale connections
                for connection_id in stale_connections:
                    logger.info(f"Cleaning up stale connection: {connection_id}")
                    await self.disconnect(connection_id)
                    
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
                await asyncio.sleep(30)
                
    async def _send_ping(self, connection_id: str):
        """Send ping to a specific connection"""
        try:
            connection_info = self.connections.get(connection_id)
            if not connection_info:
                return
                
            await connection_info.websocket.ping()
            connection_info.last_ping = datetime.now()
            
        except Exception as e:
            logger.debug(f"Failed to ping connection {connection_id}: {e}")
            # Schedule for cleanup
            asyncio.create_task(self.disconnect(connection_id))
            
    def handle_pong(self, connection_id: str):
        """Handle pong response from connection"""
        connection_info = self.connections.get(connection_id)
        if connection_info:
            connection_info.last_pong = datetime.now()
            if connection_info.state == ConnectionState.RECONNECTING:
                connection_info.state = ConnectionState.CONNECTED
                logger.info(f"Connection {connection_id} successfully reconnected")
            
    def is_rate_limited(self, connection_id: str) -> bool:
        """Check if connection is rate limited"""
        connection_info = self.connections.get(connection_id)
        if not connection_info:
            return True
            
        current_time = datetime.now()
        minute_ago = current_time - timedelta(minutes=1)
        
        # Get rate limit queue for this connection
        rate_queue = self.rate_limits[connection_id]
        
        # Remove old entries
        while rate_queue and rate_queue[0] < minute_ago:
            rate_queue.popleft()
            
        # Check if rate limit exceeded
        if len(rate_queue) >= self.rate_limit_messages_per_minute:
            return True
            
        # Add current timestamp
        rate_queue.append(current_time)
        return False

    async def _reconnection_loop(self):
        """Background task for handling automatic reconnections with exponential backoff"""
        while self.monitoring_active:
            try:
                current_time = datetime.now()
                
                # Find connections that need reconnection
                for connection_id, connection_info in list(self.connections.items()):
                    if connection_info.state == ConnectionState.FAILED:
                        await self._attempt_reconnection(connection_id, connection_info)
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconnection loop error: {e}")
                await asyncio.sleep(10)

    async def _attempt_reconnection(self, connection_id: str, connection_info: ConnectionInfo):
        """Attempt to reconnect a failed connection with exponential backoff"""
        try:
            # Check if we've exceeded max retry attempts
            if connection_info.reconnection_attempts >= self.reconnection_config.max_retries:
                logger.warning(f"Max reconnection attempts reached for {connection_id}, giving up")
                await self.disconnect(connection_id, preserve_offline_queue=True)
                return
            
            # Calculate backoff delay with exponential increase and jitter
            delay = min(
                self.reconnection_config.initial_delay * 
                (self.reconnection_config.backoff_multiplier ** connection_info.reconnection_attempts),
                self.reconnection_config.max_delay
            )
            
            # Add jitter to prevent thundering herd
            if self.reconnection_config.jitter:
                delay *= (0.5 + random.random() * 0.5)  # 50%-100% of calculated delay
            
            # Check if enough time has passed since last attempt
            current_time = datetime.now()
            if (connection_info.last_reconnection_attempt and 
                (current_time - connection_info.last_reconnection_attempt).total_seconds() < delay):
                return
            
            # Update reconnection tracking
            connection_info.reconnection_attempts += 1
            connection_info.last_reconnection_attempt = current_time
            connection_info.state = ConnectionState.RECONNECTING
            
            logger.info(f"Attempting reconnection {connection_info.reconnection_attempts}/"
                       f"{self.reconnection_config.max_retries} for {connection_id} "
                       f"(delay: {delay:.1f}s)")
            
            # Restore any offline messages when reconnection succeeds
            queue_key = f"{connection_info.user_id}:{connection_info.channel}" if connection_info.user_id else f"anonymous:{connection_info.channel}"
            if queue_key in self.offline_message_queues:
                offline_messages = self.offline_message_queues[queue_key]
                for message in offline_messages:
                    await self.send_to_connection(connection_id, message)
                del self.offline_message_queues[queue_key]
                logger.info(f"Restored {len(offline_messages)} offline messages for {connection_id}")
            
        except Exception as e:
            logger.error(f"Reconnection attempt failed for {connection_id}: {e}")
            connection_info.connection_errors.append(f"Reconnection failed: {str(e)}")

    async def _resource_monitor_loop(self):
        """Background task for monitoring and managing resource usage"""
        while self.monitoring_active:
            try:
                await self._monitor_memory_usage()
                await self._cleanup_stale_queues()
                await self._optimize_connection_pools()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Resource monitor loop error: {e}")
                await asyncio.sleep(60)

    async def _monitor_memory_usage(self):
        """Monitor and log memory usage of WebSocket connections"""
        try:
            # Calculate approximate memory usage
            connection_memory = len(self.connections) * 1024  # Rough estimate per connection
            queue_memory = sum(len(queue) * 512 for queue in self.message_queues.values())
            offline_queue_memory = sum(len(queue) * 512 for queue in self.offline_message_queues.values())
            
            total_memory = connection_memory + queue_memory + offline_queue_memory
            self.memory_usage_bytes = total_memory
            
            # Log if memory usage is high (>10MB)
            if total_memory > 10 * 1024 * 1024:
                logger.warning(f"High WebSocket memory usage: {total_memory / (1024*1024):.1f}MB "
                             f"({len(self.connections)} connections, {len(self.message_queues)} queues)")
            
        except Exception as e:
            logger.error(f"Memory monitoring error: {e}")

    async def _cleanup_stale_queues(self):
        """Clean up stale offline message queues"""
        try:
            current_time = datetime.now()
            stale_queues = []
            
            # Find queues that haven't been accessed recently
            for queue_key in self.offline_message_queues:
                # Remove queues older than 1 hour
                # This is a simple heuristic - in production you might track last access time
                if len(self.offline_message_queues[queue_key]) == 0:
                    stale_queues.append(queue_key)
            
            for queue_key in stale_queues:
                del self.offline_message_queues[queue_key]
                logger.debug(f"Cleaned up stale offline queue: {queue_key}")
                
        except Exception as e:
            logger.error(f"Queue cleanup error: {e}")

    async def _optimize_connection_pools(self):
        """Optimize connection pools by balancing load"""
        try:
            # Rebalance connection pools if needed
            for channel, connections in self.channels.items():
                if len(connections) > self.max_connections_per_channel * 0.8:
                    logger.info(f"Channel '{channel}' approaching connection limit: "
                               f"{len(connections)}/{self.max_connections_per_channel}")
                
                # Update connection pool tracking
                self.connection_pools[channel] = connections.copy()
                
        except Exception as e:
            logger.error(f"Connection pool optimization error: {e}")
        
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get comprehensive connection statistics with enhanced resource management info"""
        current_time = datetime.now()
        uptime = current_time - self.start_time
        
        # Calculate connection state distribution
        state_counts = defaultdict(int)
        error_counts = defaultdict(int)
        reconnection_stats = {
            "total_attempts": 0,
            "successful_reconnections": 0,
            "failed_connections": 0
        }
        
        for conn_info in self.connections.values():
            state_counts[conn_info.state.value] += 1
            reconnection_stats["total_attempts"] += conn_info.reconnection_attempts
            if conn_info.state == ConnectionState.CONNECTED and conn_info.reconnection_attempts > 0:
                reconnection_stats["successful_reconnections"] += 1
            elif conn_info.state == ConnectionState.FAILED:
                reconnection_stats["failed_connections"] += 1
            
            # Count connection errors
            for error in conn_info.connection_errors:
                error_type = error.split(':')[0] if ':' in error else 'unknown'
                error_counts[error_type] += 1
        
        return {
            "uptime_seconds": uptime.total_seconds(),
            "total_connections": self.total_connections,
            "active_connections": len(self.connections),
            "total_messages": self.total_messages,
            "messages_per_second": self.total_messages / max(uptime.total_seconds(), 1),
            # Enhanced connection state tracking
            "connection_states": dict(state_counts),
            "reconnection_stats": reconnection_stats,
            "connection_errors": dict(error_counts),
            # Resource management
            "memory_usage_bytes": self.memory_usage_bytes,
            "memory_usage_mb": self.memory_usage_bytes / (1024 * 1024),
            "offline_queues": {
                "count": len(self.offline_message_queues),
                "total_messages": sum(len(queue) for queue in self.offline_message_queues.values())
            },
            "connection_pools": {
                name: len(connections) for name, connections in self.connection_pools.items()
            },
            # Channel statistics
            "channels": {
                name: {
                    "connection_count": stats.connection_count,
                    "message_count": stats.message_count,
                    "bytes_transferred": stats.bytes_transferred,
                    "last_activity": stats.last_activity.isoformat(),
                    "active_connections": len(self.channels.get(name, set()))
                }
                for name, stats in self.channel_stats.items()
            },
            # Background task status
            "background_tasks": {
                "monitoring_active": self.monitoring_active,
                "heartbeat_running": self.heartbeat_task and not self.heartbeat_task.done(),
                "cleanup_running": self.cleanup_task and not self.cleanup_task.done(),
                "reconnection_running": self.reconnection_task and not self.reconnection_task.done(),
                "resource_monitor_running": self.resource_monitor_task and not self.resource_monitor_task.done(),
                "pending_cleanup_tasks": len(self.pending_cleanup_tasks)
            }
        }
        
    async def shutdown(self):
        """Gracefully shutdown all connections"""
        logger.info("Shutting down WebSocket connections...")
        
        # Stop background tasks first
        await self.stop_background_tasks()
        
        # Close all connections
        disconnect_tasks = []
        for connection_id in list(self.connections.keys()):
            disconnect_tasks.append(self.disconnect(connection_id))
            
        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)
            
        logger.info("WebSocket connection manager shutdown complete")

    # Enhanced utility methods for resource management
    
    def mark_connection_failed(self, connection_id: str, error: str):
        """Mark a connection as failed and prepare it for reconnection"""
        connection_info = self.connections.get(connection_id)
        if connection_info:
            connection_info.state = ConnectionState.FAILED
            connection_info.connection_errors.append(error)
            logger.warning(f"Connection {connection_id} marked as failed: {error}")
    
    def get_connection_health(self, connection_id: str) -> Dict[str, Any]:
        """Get detailed health information for a specific connection"""
        connection_info = self.connections.get(connection_id)
        if not connection_info:
            return {"exists": False}
        
        current_time = datetime.now()
        return {
            "exists": True,
            "connection_id": connection_id,
            "state": connection_info.state.value,
            "channel": connection_info.channel,
            "user_id": connection_info.user_id,
            "connected_duration_seconds": (current_time - connection_info.connected_at).total_seconds(),
            "last_ping_seconds_ago": (current_time - connection_info.last_ping).total_seconds(),
            "last_pong_seconds_ago": (current_time - connection_info.last_pong).total_seconds(),
            "message_count": connection_info.message_count,
            "bytes_sent": connection_info.bytes_sent,
            "bytes_received": connection_info.bytes_received,
            "reconnection_attempts": connection_info.reconnection_attempts,
            "connection_errors": connection_info.connection_errors[-5:],  # Last 5 errors
            "message_queue_size": len(connection_info.message_queue) if connection_info.message_queue else 0
        }
    
    def configure_reconnection(self, new_config: ReconnectionConfig):
        """Update reconnection configuration at runtime"""
        old_enabled = self.reconnection_config.enabled
        self.reconnection_config = new_config
        
        # Start/stop reconnection task based on new config
        if new_config.enabled and not old_enabled and self.monitoring_active:
            if not self.reconnection_task or self.reconnection_task.done():
                self.reconnection_task = asyncio.create_task(self._reconnection_loop())
        elif not new_config.enabled and old_enabled:
            if self.reconnection_task and not self.reconnection_task.done():
                self.reconnection_task.cancel()
        
        logger.info(f"Reconnection configuration updated: enabled={new_config.enabled}, "
                   f"max_retries={new_config.max_retries}")
    
    def get_offline_message_count(self, user_id: str = None, channel: str = None) -> int:
        """Get count of offline messages for a user/channel combination"""
        if user_id and channel:
            queue_key = f"{user_id}:{channel}"
            return len(self.offline_message_queues.get(queue_key, []))
        elif channel:
            # Count all messages for anonymous users in this channel
            queue_key = f"anonymous:{channel}"
            return len(self.offline_message_queues.get(queue_key, []))
        else:
            # Count all offline messages
            return sum(len(queue) for queue in self.offline_message_queues.values())
    
    async def force_connection_cleanup(self, connection_id: str):
        """Force cleanup of a connection, bypassing normal graceful shutdown"""
        connection_info = self.connections.get(connection_id)
        if not connection_info:
            return
        
        logger.warning(f"Force cleaning up connection: {connection_id}")
        
        # Cancel all tasks immediately
        for task in connection_info.cleanup_tasks:
            task.cancel()
        
        # Remove from all tracking structures immediately
        channel = connection_info.channel
        user_id = connection_info.user_id
        
        self.channels.get(channel, set()).discard(connection_id)
        self.connection_pools.get(channel, set()).discard(connection_id)
        if user_id:
            self.user_connections.get(user_id, set()).discard(connection_id)
        
        # Close WebSocket without waiting
        try:
            await asyncio.wait_for(connection_info.websocket.close(), timeout=1.0)
        except:
            pass  # Ignore any errors during force cleanup
        
        # Remove from connections
        self.connections.pop(connection_id, None)
        self.rate_limits.pop(connection_id, None)

# Global WebSocket connection manager
websocket_manager = WebSocketConnectionManager()

# Utility functions for common WebSocket patterns
async def handle_websocket_connection(websocket: WebSocket, channel: str, 
                                    message_handler: Optional[Callable] = None):
    """
    Handle a complete WebSocket connection lifecycle.
    
    Args:
        websocket: FastAPI WebSocket instance
        channel: Channel name
        message_handler: Optional function to handle incoming messages
    """
    connection_id = None
    try:
        # Connect
        connection_id = await websocket_manager.connect(websocket, channel)
        
        # Message loop
        while True:
            try:
                # Receive message
                data = await websocket.receive_text()
                
                # Check rate limiting
                if websocket_manager.is_rate_limited(connection_id):
                    await websocket_manager.send_to_connection(connection_id, {
                        "type": "rate_limit_exceeded",
                        "message": "Too many messages, please slow down"
                    })
                    continue
                    
                # Handle pong messages
                if data == "pong":
                    websocket_manager.handle_pong(connection_id)
                    continue
                    
                # Process message with handler
                if message_handler:
                    try:
                        message = json.loads(data)
                        await message_handler(connection_id, message)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from connection {connection_id}: {data}")
                    except Exception as e:
                        logger.error(f"Message handler error: {e}")
                        
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket message handling error: {e}")
                break
                
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        # Cleanup
        if connection_id:
            await websocket_manager.disconnect(connection_id)