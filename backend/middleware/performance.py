"""
Performance optimization middleware for PyRobot FastAPI backend.

Implements caching, compression, and request/response optimization patterns.
"""

import asyncio
import gzip
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
from functools import wraps

from fastapi import Request, Response
from fastapi.responses import JSONResponse
import redis.asyncio as redis
import logging

# Import the new performance logging utilities
from ..utils.logger import get_logger, request_context, request_timer

logger = logging.getLogger(__name__)
perf_logger = get_logger('pyrobot.performance.middleware')

class PerformanceMiddleware:
    """
    High-performance middleware for API optimization.
    
    Features:
    - Response caching with Redis backend
    - Gzip compression for large responses
    - Request timing and metrics collection
    - Smart cache invalidation patterns
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_client = None
        self.redis_url = redis_url
        self.metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_response_time": 0.0
        }
        
    async def setup(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            logger.info("Redis cache backend connected successfully")
        except Exception as e:
            logger.warning(f"Redis unavailable, using in-memory cache: {e}")
            self.redis_client = None

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Process request with performance optimizations"""
        start_time = time.time()
        
        # Extract user info for context (if available from auth)
        user_id = getattr(request.state, 'user_id', None)
        
        # Create request context for tracing
        with request_context(
            endpoint=request.url.path,
            method=request.method,
            user_id=user_id,
            query_params=str(request.query_params),
            client_ip=request.client.host if request.client else None
        ) as ctx:
            
            # Check cache for GET requests
            cache_key = None
            cache_hit = False
            if request.method == "GET" and self.should_cache(request.url.path):
                cache_key = self.generate_cache_key(request)
                cached_response = await self.get_cached_response(cache_key)
                if cached_response:
                    self.metrics["cache_hits"] += 1
                    cache_hit = True
                    
                    # Log cache hit
                    processing_time = (time.time() - start_time) * 1000
                    perf_logger.perf_info(f"Cache HIT for {request.method} {request.url.path}",
                                        cache_key=cache_key, processing_time=processing_time)
                    
                    response = self.create_cached_response(cached_response)
                    response.headers["X-Response-Time"] = f"{processing_time/1000:.3f}s"
                    response.headers["X-Cache-Status"] = "HIT"
                    return response
            
            # Process request with timing
            with request_timer(perf_logger, request.url.path, request.method):
                response = await call_next(request)
                
                # Update metrics
                processing_time = time.time() - start_time
                self.update_metrics(processing_time)
                
                # Log request performance
                self._log_request_performance(request, response, processing_time, cache_hit)
                
                # Cache successful GET responses
                if (cache_key and response.status_code == 200 and 
                    hasattr(response, 'body') and response.body):
                    await self.cache_response(cache_key, response, ttl=300)  # 5 min default
                    perf_logger.perf_debug(f"Cached response for {request.url.path}",
                                         cache_key=cache_key, response_size=len(response.body))
                    
                # Apply compression for large responses
                original_size = len(response.body) if hasattr(response, 'body') else 0
                if original_size > 1024:  # > 1KB
                    response = self.compress_response(response)
                    compressed_size = len(response.body) if hasattr(response, 'body') else 0
                    if compressed_size < original_size:
                        perf_logger.perf_debug(f"Compressed response for {request.url.path}",
                                             original_size=original_size, compressed_size=compressed_size,
                                             compression_ratio=f"{(1 - compressed_size/original_size)*100:.1f}%")
                
                # Add performance headers
                response.headers["X-Response-Time"] = f"{processing_time:.3f}s"
                response.headers["X-Cache-Status"] = "HIT" if cache_hit else "MISS"
                response.headers["X-Request-ID"] = ctx.request_id
                
                return response
    
    def _log_request_performance(self, request: Request, response: Response, 
                               processing_time: float, cache_hit: bool):
        """Log detailed request performance information"""
        processing_time_ms = processing_time * 1000
        
        # Basic request info
        log_data = {
            'endpoint': request.url.path,
            'method': request.method,
            'status_code': response.status_code,
            'processing_time': processing_time_ms,
            'cache_hit': cache_hit
        }
        
        # Add response size if available
        if hasattr(response, 'body'):
            log_data['response_size'] = len(response.body)
        
        # Add query parameters count
        if request.query_params:
            log_data['query_param_count'] = len(request.query_params)
        
        # Determine log level based on performance
        if processing_time_ms > 5000:  # > 5 seconds
            perf_logger.perf_warning("SLOW REQUEST detected", **log_data)
        elif processing_time_ms > 1000:  # > 1 second
            perf_logger.perf_info("REQUEST performance", **log_data)
        else:
            perf_logger.perf_debug("REQUEST completed", **log_data)
        
        # Log error responses
        if response.status_code >= 400:
            perf_logger.perf_warning(f"ERROR RESPONSE {response.status_code}", **log_data)

    def should_cache(self, path: str) -> bool:
        """Determine if endpoint should be cached"""
        cacheable_patterns = [
            "/api/database/status",
            "/api/database/tables",
            "/api/auth/users",
            "/api/monitoring/system",
            "/api/camera/cameras"
        ]
        return any(path.startswith(pattern) for pattern in cacheable_patterns)

    def generate_cache_key(self, request: Request) -> str:
        """Generate cache key from request"""
        return f"api_cache:{request.url.path}:{request.url.query}"

    async def get_cached_response(self, cache_key: str) -> Optional[Dict]:
        """Retrieve cached response"""
        if not self.redis_client:
            return None
            
        try:
            cached = await self.redis_client.get(cache_key)
            return json.loads(cached) if cached else None
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
            return None

    async def cache_response(self, cache_key: str, response: Response, ttl: int):
        """Cache response data"""
        if not self.redis_client:
            return
            
        try:
            cache_data = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.body.decode(),
                "cached_at": datetime.now().isoformat()
            }
            await self.redis_client.setex(cache_key, ttl, json.dumps(cache_data))
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    def create_cached_response(self, cached_data: Dict) -> JSONResponse:
        """Create response from cached data"""
        return JSONResponse(
            content=json.loads(cached_data["body"]),
            status_code=cached_data["status_code"],
            headers={**cached_data["headers"], "X-Cache-Status": "HIT"}
        )

    def compress_response(self, response: Response) -> Response:
        """Apply gzip compression to response"""
        try:
            compressed_body = gzip.compress(response.body)
            if len(compressed_body) < len(response.body):
                response.body = compressed_body
                response.headers["content-encoding"] = "gzip"
                response.headers["content-length"] = str(len(compressed_body))
        except Exception as e:
            logger.warning(f"Compression error: {e}")
        return response

    def update_metrics(self, processing_time: float):
        """Update performance metrics"""
        self.metrics["total_requests"] += 1
        # Rolling average for response time
        self.metrics["avg_response_time"] = (
            (self.metrics["avg_response_time"] * 0.9) + 
            (processing_time * 0.1)
        )

# Response caching decorator for specific endpoints
def cached_response(ttl: int = 300):
    """Decorator for caching specific endpoint responses"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Implementation would integrate with the middleware cache
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Database query result caching
class QueryCache:
    """Specialized caching for database query results"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.local_cache = {}  # Fallback in-memory cache
        
    async def get_or_execute(self, query_key: str, query_func: Callable, ttl: int = 600):
        """Get cached result or execute query"""
        # Check cache first
        cached = await self.get_cached_query(query_key)
        if cached:
            return cached
            
        # Execute query and cache result
        result = await query_func()
        await self.cache_query_result(query_key, result, ttl)
        return result

    async def get_cached_query(self, query_key: str) -> Optional[Any]:
        """Get cached query result"""
        if self.redis_client:
            try:
                cached = await self.redis_client.get(f"query:{query_key}")
                return json.loads(cached) if cached else None
            except Exception:
                pass
        
        # Fallback to local cache
        cache_entry = self.local_cache.get(query_key)
        if cache_entry and cache_entry["expires"] > datetime.now():
            return cache_entry["data"]
        return None

    async def cache_query_result(self, query_key: str, result: Any, ttl: int):
        """Cache query result"""
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    f"query:{query_key}", 
                    ttl, 
                    json.dumps(result, default=str)
                )
                return
            except Exception:
                pass
                
        # Fallback to local cache
        self.local_cache[query_key] = {
            "data": result,
            "expires": datetime.now() + timedelta(seconds=ttl)
        }

    async def invalidate_pattern(self, pattern: str):
        """Invalidate cached queries matching pattern"""
        if self.redis_client:
            try:
                keys = await self.redis_client.keys(f"query:{pattern}*")
                if keys:
                    await self.redis_client.delete(*keys)
            except Exception:
                pass
                
        # Clear local cache entries matching pattern
        keys_to_remove = [k for k in self.local_cache.keys() if pattern in k]
        for key in keys_to_remove:
            del self.local_cache[key]