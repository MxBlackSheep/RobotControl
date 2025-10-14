"""
RobotControl API Response Formatter

Standardizes API response formatting across all endpoints for consistency.
Addresses the frontend issue where Axios wraps responses in `.data`, causing
confusion between `response.data` vs `response.data.data`.

Standard Response Format:
{
    "success": boolean,
    "data": any,           # The actual response payload
    "metadata": {          # Optional metadata
        "timestamp": "ISO string",
        "execution_time_ms": number,
        "cache_used": boolean,
        "total_count": number,  # For paginated responses
        "page": number,         # For paginated responses
        "limit": number         # For paginated responses
    },
    "error": {             # Only present on errors
        "message": "string",
        "code": "string",
        "details": any
    }
}

This ensures consistent response handling in the frontend:
- Success responses: response.data.success === true, payload in response.data.data
- Error responses: response.data.success === false, error info in response.data.error
"""

from typing import Any, Dict, Optional, Union
from datetime import datetime
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
import time
import logging

logger = logging.getLogger(__name__)


class ResponseMetadata:
    """Metadata for API responses"""
    
    def __init__(self):
        self.timestamp = datetime.utcnow().isoformat() + 'Z'
        self.execution_time_ms: Optional[float] = None
        self.cache_used: bool = False
        self.total_count: Optional[int] = None
        self.page: Optional[int] = None
        self.limit: Optional[int] = None
        self.additional: Dict[str, Any] = {}
    
    def set_execution_time(self, start_time: float) -> None:
        """Set execution time from start timestamp"""
        self.execution_time_ms = round((time.time() - start_time) * 1000, 2)
    
    def set_pagination(self, total_count: int, page: int = None, limit: int = None) -> None:
        """Set pagination metadata"""
        self.total_count = total_count
        if page is not None:
            self.page = page
        if limit is not None:
            self.limit = limit
    
    def set_cache_used(self, cache_used: bool = True) -> None:
        """Mark that cache was used for this response"""
        self.cache_used = cache_used
    
    def add_metadata(self, key: str, value: Any) -> None:
        """Add additional metadata"""
        self.additional[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response"""
        result = {
            "timestamp": self.timestamp,
            "cache_used": self.cache_used
        }
        
        if self.execution_time_ms is not None:
            result["execution_time_ms"] = self.execution_time_ms
        
        if self.total_count is not None:
            result["total_count"] = self.total_count
        
        if self.page is not None:
            result["page"] = self.page
        
        if self.limit is not None:
            result["limit"] = self.limit
        
        # Add any additional metadata
        result.update(self.additional)
        
        return result


class ResponseFormatter:
    """
    Centralized API response formatter for consistent response structure.
    
    Provides methods for success and error responses with optional metadata.
    All responses follow the standard RobotControl API response format.
    """
    
    @staticmethod
    def success(
        data: Any = None,
        metadata: Optional[ResponseMetadata] = None,
        status_code: int = 200,
        message: Optional[str] = None
    ) -> JSONResponse:
        """
        Format a successful API response.

        Args:
            data: The response payload (will be nested under 'data' key)
            metadata: Optional response metadata or dictionary
            status_code: HTTP status code (default: 200)
            message: Optional human-readable success message

        Returns:
            JSONResponse with standard success format
        """
        resolved_message = message if message is not None else "Success"

        response = {
            "success": True,
            "message": resolved_message,
            "data": data
        }

        if metadata:
            metadata_payload = metadata.to_dict() if isinstance(metadata, ResponseMetadata) else metadata
            response["metadata"] = metadata_payload

        return JSONResponse(
            content=response,
            status_code=status_code
        )

    @staticmethod
    def error(
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        details: Any = None,
        status_code: int = 500,
        metadata: Optional[ResponseMetadata] = None
    ) -> JSONResponse:
        """
        Format an error API response.

        Args:
            message: Human-readable error message
            error_code: Machine-readable error code
            details: Additional error details
            status_code: HTTP status code (default: 500)
            metadata: Optional response metadata or dictionary

        Returns:
            JSONResponse with standard error format
        """
        response = {
            "success": False,
            "message": message,
            "data": None,
            "error": {
                "message": message,
                "code": error_code
            }
        }

        if details is not None:
            response["error"]["details"] = details

        if metadata:
            metadata_payload = metadata.to_dict() if isinstance(metadata, ResponseMetadata) else metadata
            response["metadata"] = metadata_payload

        return JSONResponse(
            content=response,
            status_code=status_code
        )

    @staticmethod
    def validation_error(
        message: str = "Validation failed",
        details: Any = None,
        metadata: Optional[ResponseMetadata] = None
    ) -> JSONResponse:
        """Format a validation error response (400)"""
        return ResponseFormatter.error(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details,
            status_code=400,
            metadata=metadata
        )

    @staticmethod
    def bad_request(
        message: str = "Bad request",
        details: Any = None,
        metadata: Optional[ResponseMetadata] = None
    ) -> JSONResponse:
        """Format a generic bad request response (400)."""
        return ResponseFormatter.error(
            message=message,
            error_code="BAD_REQUEST",
            details=details,
            status_code=400,
            metadata=metadata
        )
    
    @staticmethod
    def not_found(
        message: str = "Resource not found",
        details: Any = None,
        metadata: Optional[ResponseMetadata] = None
    ) -> JSONResponse:
        """Format a not found error response (404)"""
        return ResponseFormatter.error(
            message=message,
            error_code="NOT_FOUND",
            details=details,
            status_code=404,
            metadata=metadata
        )
    
    @staticmethod
    def unauthorized(
        message: str = "Authentication required",
        details: Any = None,
        metadata: Optional[ResponseMetadata] = None
    ) -> JSONResponse:
        """Format an unauthorized error response (401)"""
        return ResponseFormatter.error(
            message=message,
            error_code="UNAUTHORIZED",
            details=details,
            status_code=401,
            metadata=metadata
        )
    
    @staticmethod
    def forbidden(
        message: str = "Access denied",
        details: Any = None,
        metadata: Optional[ResponseMetadata] = None
    ) -> JSONResponse:
        """Format a forbidden error response (403)"""
        return ResponseFormatter.error(
            message=message,
            error_code="FORBIDDEN",
            details=details,
            status_code=403,
            metadata=metadata
        )
    
    @staticmethod
    def server_error(
        message: str = "Internal server error",
        details: Any = None,
        metadata: Optional[ResponseMetadata] = None
    ) -> JSONResponse:
        """Format a server error response (500)"""
        return ResponseFormatter.error(
            message=message,
            error_code="SERVER_ERROR",
            details=details,
            status_code=500,
            metadata=metadata
        )
    
    @staticmethod
    def paginated_response(
        data: Any,
        total_count: int,
        page: int = 1,
        limit: int = 50,
        execution_start_time: Optional[float] = None,
        cache_used: bool = False,
        items_count: Optional[int] = None
    ) -> JSONResponse:
        """
        Format a paginated response with metadata.
        
        Args:
            data: List of items for current page
            total_count: Total number of items available
            page: Current page number (1-indexed)
            limit: Items per page
            execution_start_time: Start time for execution timing
            cache_used: Whether cache was used
            
        Returns:
            JSONResponse with pagination metadata
        """
        metadata = ResponseMetadata()
        metadata.set_pagination(total_count, page, limit)
        metadata.set_cache_used(cache_used)
        
        if execution_start_time:
            metadata.set_execution_time(execution_start_time)
        
        # Calculate pagination info
        total_pages = (total_count + limit - 1) // limit  # Ceiling division
        has_next = page < total_pages
        has_prev = page > 1
        
        # Add pagination metadata
        metadata.add_metadata("total_pages", total_pages)
        metadata.add_metadata("has_next", has_next)
        metadata.add_metadata("has_prev", has_prev)

        count_value = items_count
        if count_value is None:
            if isinstance(data, list):
                count_value = len(data)
            else:
                try:
                    count_value = len(data)  # type: ignore[arg-type]
                except TypeError:
                    count_value = None
        if count_value is not None:
            metadata.add_metadata("items_count", count_value)

        
        return ResponseFormatter.success(
            data=data,
            metadata=metadata
        )
    
    @staticmethod
    def from_exception(exception: Exception, metadata: Optional[ResponseMetadata] = None) -> JSONResponse:
        """
        Convert an exception to a standardized error response.
        
        Args:
            exception: The exception to convert
            metadata: Optional response metadata
            
        Returns:
            JSONResponse with error format
        """
        if isinstance(exception, HTTPException):
            # FastAPI HTTPException
            return ResponseFormatter.error(
                message=exception.detail,
                error_code=f"HTTP_{exception.status_code}",
                status_code=exception.status_code,
                metadata=metadata
            )
        
        # Generic exception
        logger.error(f"Unhandled exception in API: {exception}", exc_info=True)
        
        return ResponseFormatter.server_error(
            message="An unexpected error occurred",
            details=str(exception),
            metadata=metadata
        )


# Convenience functions for common use cases
def format_success(data: Any = None, start_time: float = None, cache_used: bool = False, message: Optional[str] = None) -> JSONResponse:
    """Quick success response with optional timing metadata"""
    metadata = ResponseMetadata()
    if start_time:
        metadata.set_execution_time(start_time)
    if cache_used:
        metadata.set_cache_used(cache_used)

    return ResponseFormatter.success(data, metadata, message=message)


def format_error(message: str, status_code: int = 500, details: Any = None) -> JSONResponse:
    """Quick error response"""
    error_codes = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED", 
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        500: "SERVER_ERROR"
    }
    
    error_code = error_codes.get(status_code, "UNKNOWN_ERROR")
    
    return ResponseFormatter.error(
        message=message,
        error_code=error_code,
        details=details,
        status_code=status_code
    )


# Error handler decorator
def handle_api_exceptions(func):
    """Decorator to automatically handle exceptions and format responses"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return ResponseFormatter.from_exception(e)
    return wrapper
