# API Response Format Standardization Guide

This guide explains how to migrate existing RobotControl API endpoints to use the standardized response format, addressing the frontend Axios data wrapping issue.

## Problem Statement

**Frontend Issue**: Axios automatically wraps responses in a `.data` property, causing confusion between:
- `response.data` (Axios wrapper)
- `response.data.data` (actual API payload)

**Current Inconsistency**: Some endpoints return raw objects, others use different wrapper formats.

## Standard Response Format

All API endpoints now use this consistent format:

```typescript
{
    success: boolean;           // Always present - indicates success/failure
    data: any;                 // The actual response payload (null on error)
    metadata?: {               // Optional metadata
        timestamp: string;           // ISO timestamp
        execution_time_ms: number;   // Response time
        cache_used: boolean;         // Cache usage indicator
        total_count?: number;        // For paginated responses
        page?: number;               // Current page (1-indexed)
        limit?: number;              // Items per page
        // ... additional metadata
    };
    error?: {                  // Only present when success=false
        message: string;             // Human-readable error
        code: string;                // Machine-readable error code
        details?: any;               // Additional error details
    };
}
```

## Frontend Benefits

With standardized responses, frontend code becomes predictable:

```javascript
// Always works the same way
const response = await api.getDatabaseStatus();

if (response.data.success) {
    const statusData = response.data.data;  // Actual payload
    const metadata = response.data.metadata; // Optional metadata
} else {
    const error = response.data.error;      // Error information
}
```

## Migration Examples

### Before: Raw Object Response

```python
@router.get("/status")
async def get_database_status():
    try:
        status = get_status()
        return {
            "is_connected": status.is_connected,
            "mode": status.mode,
            "database": status.database
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### After: Standardized Response

```python
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata

@router.get("/status")
async def get_database_status():
    start_time = time.time()
    
    try:
        status = get_status()
        
        data = {
            "is_connected": status.is_connected,
            "mode": status.mode,
            "database": status.database
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("status_source", "database_service")
        
        return ResponseFormatter.success(data, metadata)
        
    except Exception as e:
        return ResponseFormatter.server_error(
            message="Failed to get database status",
            details=str(e)
        )
```

### Before: Inconsistent Success/Error Format

```python
@router.get("/tables")
async def get_tables():
    try:
        tables = get_tables()
        return {
            "success": True,
            "data": {"tables": tables},
            "metadata": {"count": len(tables)}
        }
    except Exception as e:
        return {"error": str(e), "success": False}
```

### After: Consistent Format

```python
@router.get("/tables")
async def get_tables():
    start_time = time.time()
    
    try:
        tables = get_tables()
        
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.set_pagination(len(tables))
        
        return ResponseFormatter.success(
            data={"tables": tables},
            metadata=metadata
        )
        
    except Exception as e:
        return ResponseFormatter.server_error(
            message="Failed to retrieve tables",
            details=str(e)
        )
```

## ResponseFormatter Methods

### Success Responses

```python
# Basic success
ResponseFormatter.success(data={"result": "ok"})

# With metadata
metadata = ResponseMetadata()
metadata.set_execution_time(start_time)
ResponseFormatter.success(data, metadata)

# Paginated response
ResponseFormatter.paginated_response(
    data=items,
    total_count=1000,
    page=1,
    limit=50,
    execution_start_time=start_time,
    cache_used=True
)
```

### Error Responses

```python
# Generic error
ResponseFormatter.error(
    message="Operation failed",
    error_code="OPERATION_FAILED",
    status_code=500
)

# Validation error
ResponseFormatter.validation_error(
    message="Invalid input data",
    details={"field": "username", "issue": "required"}
)

# Not found
ResponseFormatter.not_found(
    message="User not found",
    details={"user_id": 123}
)

# From exception
ResponseFormatter.from_exception(exception)
```

## Convenience Functions

For simple cases, use the convenience functions:

```python
from backend.api.response_formatter import format_success, format_error

# Quick success with timing
return format_success(data, start_time, cache_used=True)

# Quick error
return format_error("Something went wrong", status_code=400)
```

## Migration Checklist

For each API endpoint:

1. **Import response formatter**:
   ```python
   from backend.api.response_formatter import ResponseFormatter, ResponseMetadata
   ```

2. **Add timing for metadata**:
   ```python
   start_time = time.time()
   ```

3. **Replace success returns**:
   ```python
   # Old: return {"data": result}
   # New: return ResponseFormatter.success(result, metadata)
   ```

4. **Replace error handling**:
   ```python
   # Old: raise HTTPException(status_code=500, detail=str(e))
   # New: return ResponseFormatter.server_error(message, details=str(e))
   ```

5. **Add metadata where helpful**:
   ```python
   metadata = ResponseMetadata()
   metadata.set_execution_time(start_time)
   metadata.add_metadata("cache_used", cache_hit)
   ```

6. **Test frontend compatibility**:
   - Verify `response.data.success` is boolean
   - Verify `response.data.data` contains payload
   - Verify `response.data.error` contains error info on failures

## Error Handler Decorator

For automatic exception handling:

```python
from backend.api.response_formatter import handle_api_exceptions

@handle_api_exceptions
@router.get("/example")
async def example_endpoint():
    # Any unhandled exception automatically becomes standardized error response
    return ResponseFormatter.success({"message": "ok"})
```

## Benefits

1. **Frontend Consistency**: Predictable response structure
2. **Better Error Handling**: Structured error information
3. **Rich Metadata**: Execution timing, caching info, pagination
4. **Development Experience**: Clear success/error distinction
5. **API Documentation**: Self-documenting response structure
6. **Monitoring**: Built-in performance metrics collection

## Migration Priority

**High Priority** (user-facing endpoints):
- `/api/auth/*`
- `/api/database/*`
- `/api/experiments/*`
- `/api/scheduling/*`

**Medium Priority** (admin endpoints):
- `/api/admin/*`
- `/api/system/*`
- `/api/monitoring/*`

**Low Priority** (internal/utility endpoints):
- Health checks
- Status endpoints
- Development endpoints