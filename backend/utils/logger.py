"""
Enhanced logging utility for PyRobot with performance monitoring capabilities.

Provides structured logging with:
- Performance-specific log levels and contexts
- Request ID tracking for distributed tracing
- Database query timing and monitoring
- Metrics collection and aggregation
- Memory and resource usage tracking
"""

import logging
import logging.handlers
import time
import uuid
import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from collections import defaultdict
import traceback

# Import project utilities
from ..utils.data_paths import get_logs_path


class PerformanceLevel:
    """Custom log levels for performance monitoring"""
    PERF_DEBUG = 25     # Between DEBUG and INFO
    PERF_INFO = 35      # Between INFO and WARNING
    PERF_WARNING = 45   # Between WARNING and ERROR


# Add custom levels to logging module
logging.addLevelName(PerformanceLevel.PERF_DEBUG, 'PERF_DEBUG')
logging.addLevelName(PerformanceLevel.PERF_INFO, 'PERF_INFO')
logging.addLevelName(PerformanceLevel.PERF_WARNING, 'PERF_WARNING')


@dataclass
class PerformanceMetric:
    """Data class for performance metrics"""
    name: str
    value: float
    unit: str
    timestamp: datetime
    context: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class RequestContext:
    """Context information for request tracking"""
    request_id: str
    endpoint: str
    method: str
    user_id: Optional[str] = None
    start_time: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        data = asdict(self)
        if self.start_time:
            data['start_time'] = self.start_time.isoformat()
        return data


class ThreadLocalContext:
    """Thread-local storage for request context"""
    def __init__(self):
        self._storage = threading.local()
    
    @property
    def request_context(self) -> Optional[RequestContext]:
        """Get current request context"""
        return getattr(self._storage, 'request_context', None)
    
    @request_context.setter
    def request_context(self, context: Optional[RequestContext]):
        """Set current request context"""
        self._storage.request_context = context
    
    def clear(self):
        """Clear current context"""
        if hasattr(self._storage, 'request_context'):
            delattr(self._storage, 'request_context')


# Global context storage
_context = ThreadLocalContext()


class PerformanceLogger:
    """Enhanced logger with performance monitoring capabilities"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.metrics: List[PerformanceMetric] = []
        self.query_times: Dict[str, List[float]] = defaultdict(list)
        self.request_times: Dict[str, List[float]] = defaultdict(list)
        self.query_counts: Dict[str, int] = defaultdict(int)
        self.query_sample_rate: int = 20
        self.query_log_threshold_ms: float = 500.0
        self._lock = threading.Lock()
        
        # Add custom level methods
        self.logger.perf_debug = lambda msg, *args, **kwargs: self.logger.log(PerformanceLevel.PERF_DEBUG, msg, *args, **kwargs)
        self.logger.perf_info = lambda msg, *args, **kwargs: self.logger.log(PerformanceLevel.PERF_INFO, msg, *args, **kwargs)
        self.logger.perf_warning = lambda msg, *args, **kwargs: self.logger.log(PerformanceLevel.PERF_WARNING, msg, *args, **kwargs)
    
    def set_level(self, level):
        """Set logging level"""
        self.logger.setLevel(level)
    
    def debug(self, msg: str, **kwargs):
        """Debug level logging with context"""
        self._log_with_context(logging.DEBUG, msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        """Info level logging with context"""
        self._log_with_context(logging.INFO, msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        """Warning level logging with context"""
        self._log_with_context(logging.WARNING, msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        """Error level logging with context"""
        self._log_with_context(logging.ERROR, msg, **kwargs)
    
    def critical(self, msg: str, **kwargs):
        """Critical level logging with context"""
        self._log_with_context(logging.CRITICAL, msg, **kwargs)
    
    def perf_debug(self, msg: str, **kwargs):
        """Performance debug logging"""
        self._log_with_context(PerformanceLevel.PERF_DEBUG, msg, **kwargs)
    
    def perf_info(self, msg: str, **kwargs):
        """Performance info logging"""
        self._log_with_context(PerformanceLevel.PERF_INFO, msg, **kwargs)
    
    def perf_warning(self, msg: str, **kwargs):
        """Performance warning logging"""
        self._log_with_context(PerformanceLevel.PERF_WARNING, msg, **kwargs)
    
    def _log_with_context(self, level: int, msg: str, **kwargs):
        """Log message with request context"""
        extra = kwargs.copy()
        
        # Add request context if available
        context = _context.request_context
        if context:
            extra.update({
                'request_id': context.request_id,
                'endpoint': context.endpoint,
                'method': context.method,
                'user_id': context.user_id
            })
            if context.metadata:
                extra.update(context.metadata)
        
        # Add timestamp
        extra['timestamp'] = datetime.now().isoformat()
        
        self.logger.log(level, msg, extra=extra)
    
    def log_metric(self, name: str, value: float, unit: str = "ms", 
                   tags: Optional[List[str]] = None, context: Optional[Dict[str, Any]] = None):
        """Log a performance metric"""
        metric = PerformanceMetric(
            name=name,
            value=value,
            unit=unit,
            timestamp=datetime.now(),
            context=context,
            tags=tags or []
        )
        
        with self._lock:
            self.metrics.append(metric)
        
        # Log the metric
        self.perf_info(f"METRIC: {name} = {value} {unit}", 
                      metric_name=name, metric_value=value, metric_unit=unit, 
                      metric_tags=tags, metric_context=context)
    
    def log_query_time(self, query_type: str, duration: float, query: Optional[str] = None):
        """Log database query timing"""
        with self._lock:
            self.query_times[query_type].append(duration)
            self.query_counts[query_type] += 1
            count = self.query_counts[query_type]
        
        context = {}
        if query:
            context['query'] = query[:200] + '...' if len(query) > 200 else query
        
        should_log_metric = duration >= self.query_log_threshold_ms or count % self.query_sample_rate == 1
        
        if should_log_metric:
            self.log_metric(f"db_query_{query_type}", duration, "ms",
                           tags=['database', 'query'], context=context)
        
        # Log slow queries as warnings
        if duration > 1000:  # > 1 second
            self.perf_warning(f"SLOW QUERY: {query_type} took {duration:.2f}ms",
                            query_type=query_type, duration=duration)
    
    def log_request_time(self, endpoint: str, method: str, duration: float, 
                        status_code: Optional[int] = None):
        """Log API request timing"""
        key = f"{method}:{endpoint}"
        with self._lock:
            self.request_times[key].append(duration)
        
        context = {
            'endpoint': endpoint,
            'method': method,
            'status_code': status_code
        }
        
        self.log_metric(f"api_request", duration, "ms", 
                       tags=['api', 'request', method.lower()], context=context)
        
        # Log slow requests as warnings
        if duration > 5000:  # > 5 seconds
            self.perf_warning(f"SLOW REQUEST: {method} {endpoint} took {duration:.2f}ms", 
                            endpoint=endpoint, method=method, duration=duration, 
                            status_code=status_code)
    
    def get_query_stats(self, query_type: str) -> Dict[str, float]:
        """Get statistics for a specific query type"""
        with self._lock:
            times = self.query_times.get(query_type, [])
        
        if not times:
            return {}
        
        return {
            'count': len(times),
            'avg': sum(times) / len(times),
            'min': min(times),
            'max': max(times),
            'total': sum(times)
        }
    
    def get_request_stats(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for API requests"""
        with self._lock:
            if endpoint:
                times_dict = {k: v for k, v in self.request_times.items() if endpoint in k}
            else:
                times_dict = dict(self.request_times)
        
        stats = {}
        total_requests = 0
        total_time = 0.0
        
        for key, times in times_dict.items():
            if not times:
                continue
            
            method, ep = key.split(':', 1)
            stats[key] = {
                'count': len(times),
                'avg': sum(times) / len(times),
                'min': min(times),
                'max': max(times),
                'total': sum(times)
            }
            total_requests += len(times)
            total_time += sum(times)
        
        if total_requests > 0:
            stats['_summary'] = {
                'total_requests': total_requests,
                'avg_response_time': total_time / total_requests,
                'total_time': total_time
            }
        
        return stats
    
    def get_recent_metrics(self, since: Optional[datetime] = None, 
                          metric_name: Optional[str] = None) -> List[PerformanceMetric]:
        """Get recent performance metrics"""
        if since is None:
            since = datetime.now() - timedelta(hours=1)
        
        with self._lock:
            metrics = [m for m in self.metrics if m.timestamp >= since]
            if metric_name:
                metrics = [m for m in metrics if m.name == metric_name]
        
        return metrics
    
    def clear_metrics(self):
        """Clear stored metrics"""
        with self._lock:
            self.metrics.clear()
            self.query_times.clear()
            self.request_times.clear()


class ContextualFormatter(logging.Formatter):
    """Custom formatter that includes request context"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Add context information to record
        if hasattr(record, 'request_id'):
            record.request_context = f"[{record.request_id}]"
        else:
            record.request_context = ""
        
        # Format the message
        formatted = super().format(record)
        
        # Add structured data for performance logs
        if record.levelno >= PerformanceLevel.PERF_DEBUG:
            extra_data = {}
            for key, value in record.__dict__.items():
                if key.startswith(('metric_', 'query_', 'endpoint', 'method', 'duration', 'status_code')):
                    extra_data[key] = value
            
            if extra_data:
                formatted += f" | DATA: {json.dumps(extra_data, default=str)}"
        
        return formatted


@contextmanager
def request_context(request_id: Optional[str] = None, endpoint: str = "", 
                   method: str = "", user_id: Optional[str] = None, 
                   **metadata):
    """Context manager for request tracking"""
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]
    
    context = RequestContext(
        request_id=request_id,
        endpoint=endpoint,
        method=method,
        user_id=user_id,
        start_time=datetime.now(),
        metadata=metadata
    )
    
    _context.request_context = context
    try:
        yield context
    finally:
        _context.clear()


@contextmanager
def query_timer(logger: PerformanceLogger, query_type: str, query: Optional[str] = None):
    """Context manager for timing database queries"""
    start_time = time.time()
    try:
        yield
    finally:
        duration = (time.time() - start_time) * 1000  # Convert to milliseconds
        logger.log_query_time(query_type, duration, query)


@contextmanager
def request_timer(logger: PerformanceLogger, endpoint: str, method: str):
    """Context manager for timing API requests"""
    start_time = time.time()
    status_code = None
    try:
        yield lambda code: setattr(request_timer, 'status_code', code)
    finally:
        duration = (time.time() - start_time) * 1000  # Convert to milliseconds
        logger.log_request_time(endpoint, method, duration, 
                               getattr(request_timer, 'status_code', None))


def setup_performance_logging(log_dir: Optional[Path] = None) -> Dict[str, PerformanceLogger]:
    """Set up performance logging infrastructure"""
    if log_dir is None:
        log_dir = get_logs_path()
    
    # Create performance log file
    perf_log_file = log_dir / f"performance_{datetime.now().strftime('%Y%m%d')}.log"
    
    # Configure performance file handler
    perf_handler = logging.handlers.RotatingFileHandler(
        str(perf_log_file),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    perf_handler.setLevel(PerformanceLevel.PERF_DEBUG)
    
    # Use contextual formatter
    formatter = ContextualFormatter(
        '%(asctime)s - %(name)s - %(levelname)s %(request_context)s - %(message)s'
    )
    perf_handler.setFormatter(formatter)
    
    # Create loggers for different subsystems
    loggers = {}
    subsystems = ['api', 'database', 'websocket', 'camera', 'scheduler', 'auth']
    
    for subsystem in subsystems:
        logger_name = f"pyrobot.performance.{subsystem}"
        logger = PerformanceLogger(logger_name)
        logger.logger.addHandler(perf_handler)
        logger.set_level(PerformanceLevel.PERF_DEBUG)
        loggers[subsystem] = logger
    
    return loggers


def get_logger(name: str) -> PerformanceLogger:
    """Get or create a performance logger"""
    return PerformanceLogger(name)


# Convenience functions for common use cases
def log_db_query(query_type: str, duration: float, query: Optional[str] = None):
    """Log database query performance"""
    logger = get_logger('pyrobot.performance.database')
    logger.log_query_time(query_type, duration, query)


def log_api_request(endpoint: str, method: str, duration: float, status_code: Optional[int] = None):
    """Log API request performance"""
    logger = get_logger('pyrobot.performance.api')
    logger.log_request_time(endpoint, method, duration, status_code)


def log_metric(name: str, value: float, unit: str = "ms", logger_name: str = 'pyrobot.performance'):
    """Log a performance metric"""
    logger = get_logger(logger_name)
    logger.log_metric(name, value, unit)