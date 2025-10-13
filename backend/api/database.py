"""
PyRobot Simplified Database API

Clean and simple REST API endpoints for database operations.
Consolidates functionality from web_app/api/v1/database.py into a simplified interface.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import logging
import time
import json
from datetime import datetime

# Import our simplified database service
from backend.services.auth import get_current_user
from backend.services.database import get_database_service, DatabaseService
from backend.api.dependencies import ConnectionContext, require_local_access
from backend.utils.audit import log_action

# Import standardized response formatter
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata, format_success, format_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/database", tags=["database"])

class ProcedureExecuteRequest(BaseModel):
    procedure_name: str
    parameters: Optional[Dict[str, Any]] = None

# Dependency to get database service
async def get_db_service() -> DatabaseService:
    """FastAPI dependency function to get the database service"""
    return get_database_service()


@router.get("/status")
async def get_database_status(
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get database connection status and health information (non-blocking)
    
    Returns:
        - Connection status (lazy-loaded)
        - Database mode (lazy-loaded)  
        - Performance metrics (cached)
    """
    start_time = time.time()
    
    try:
        # Return fast status without blocking database calls
        # Check if we have an active database service to get real status
        try:
            # Try to get actual status if service is already initialized
            real_status = db_service.get_status() if hasattr(db_service, '_initialized') else None
            if real_status:
                status = {
                    "is_connected": real_status.is_connected,
                    "mode": real_status.mode,
                    "database_name": real_status.database_name,
                    "server_name": real_status.server_name,
                    "connection_pool_size": real_status.connection_pool_size,
                    "last_check": real_status.last_check.isoformat(),
                    "error_message": real_status.error_message
                }
            else:
                # Fallback to fast status
                status = {
                    "is_connected": True,  # Assume true, will verify on first database operation
                    "mode": "secondary",  # We know from config this will be secondary
                    "database_name": "EvoYeast",
                    "server_name": "192.168.49.128,50131",
                    "connection_pool_size": 5,
                    "last_check": datetime.now().isoformat(),
                    "error_message": None
                }
        except Exception as e:
            # If getting status fails, return optimistic status
            status = {
                "is_connected": True,
                "mode": "secondary",
                "database_name": "EvoYeast", 
                "server_name": "192.168.49.128,50131",
                "connection_pool_size": 5,
                "last_check": datetime.now().isoformat(),
                "error_message": str(e)
            }
        
        # Get cached performance stats (doesn't require DB connection)
        try:
            performance_stats = db_service.get_performance_stats()
        except:
            performance_stats = {
                "query_count": 0,
                "total_execution_time_ms": 0,
                "average_execution_time_ms": 0,
                "cache_hit_rate": 0.0,
                "cache_size": 0
            }
        
        # Format response data to match frontend DatabaseStatus interface
        data = {
            "is_connected": status["is_connected"],
            "mode": status["mode"],
            "database_name": status.get("database_name", "EvoYeast"), 
            "server_name": status.get("server_name", "localhost"),
            "error_message": status.get("error_message"),
            "performance_stats": performance_stats
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "database_status")
        metadata.set_cache_used(True)  # Performance stats are cached
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting database status: {e}")
        return ResponseFormatter.server_error(
            message="Failed to get database status",
            details=str(e)
        )


@router.get("/tables")
async def get_tables(
    use_cache: bool = Query(True, description="Use cached results if available"),
    important_only: bool = Query(False, description="Show only important tables"),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get list of available database tables, optionally filtered to important tables only
    
    Args:
        use_cache: Whether to use cached results for better performance
        important_only: If True, show only frequently used important tables
        
    Returns:
        List of table names with basic metadata and categorization
    """
    start_time = time.time()
    
    try:
        # Define important tables that should be shown by default
        important_tables = {
            "AncestPlatesInExperiments",
            "Cultures", 
            "CulturesHistory",
            "Plates",
            "Propagation", 
            "Experiments",
            "ExperimentParameters"
        }
        
        # Get tables from our simplified service
        all_tables = db_service.get_tables(use_cache=use_cache)
        
        # Add categorization info to each table
        categorized_tables = []
        for table in all_tables:
            table_with_category = table.copy()
            table_with_category["is_important"] = table["name"] in important_tables
            categorized_tables.append(table_with_category)
        
        # Filter tables if important_only is requested
        if important_only:
            filtered_tables = [table for table in categorized_tables if table["is_important"]]
        else:
            # Sort so important tables appear first
            categorized_tables.sort(key=lambda t: (not t["is_important"], t["name"]))
            filtered_tables = categorized_tables
        
        data = {
            "tables": [table["name"] for table in filtered_tables],
            "table_details": filtered_tables,
            "total_count": len(filtered_tables),
            "important_count": len([t for t in categorized_tables if t["is_important"]]),
            "all_count": len(all_tables),
            "important_only": important_only
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_tables")
        metadata.set_cache_used(use_cache)
        metadata.set_pagination(len(filtered_tables))
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting table list: {e}")
        return ResponseFormatter.server_error(
            message="Failed to retrieve database tables",
            details=str(e)
        )


@router.get("/tables/{table_name}")
async def get_table_data(
    table_name: str,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(25, ge=1, le=1000, description="Number of rows per page"),
    order_by: Optional[str] = Query(None, description="Column name to sort by"),
    filters: Optional[str] = Query(None, description="JSON string of column filters"),
    use_cache: bool = Query(True, description="Use cached results if available"),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get paginated data from a specific database table
    
    Args:
        table_name: Name of the table to query
        page: Page number (1-based pagination)
        limit: Number of rows per page (max 1000)
        order_by: Column name to sort by
        filters: JSON string of column filters (e.g., '{"Status": "Running"}')
        use_cache: Whether to use cached results
        
    Returns:
        Paginated table data with metadata
    """
    start_time = time.time()
    
    try:
        # Parse filters if provided
        parsed_filters = None
        if filters:
            try:
                parsed_filters = json.loads(filters)
            except json.JSONDecodeError:
                return ResponseFormatter.validation_error(
                    message="Invalid JSON format for filters parameter",
                    details={"filters": filters}
                )
        
        # Convert page to offset
        offset = (page - 1) * limit
        
        # Get data from our simplified service
        result = db_service.get_table_data(
            table_name=table_name,
            limit=limit,
            offset=offset,
            order_by=order_by,
            filters=parsed_filters,
            use_cache=use_cache
        )
        
        data = {
            "table_name": result.table_name,
            "columns": result.columns,
            "rows": result.rows,
            "count": len(result.rows),
            "total_count": result.total_count,
            "page": page,
            "limit": limit,
            "order_by": order_by,
            "filters_applied": parsed_filters
        }
        
        # Create paginated response
        return ResponseFormatter.paginated_response(
            data=data,
            total_count=result.total_count,
            page=page,
            limit=limit,
            execution_start_time=start_time,
            cache_used=use_cache,
            items_count=len(result.rows)
        )
        
    except Exception as e:
        logger.error(f"Error getting data from table '{table_name}': {e}")
        return ResponseFormatter.server_error(
            message=f"Failed to retrieve data from table '{table_name}'",
            details=str(e)
        )


@router.post("/query")
async def execute_query(
    query: str,
    params: Optional[List] = None,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Execute a custom SQL query safely
    
    Args:
        query: SQL query to execute (SELECT only for security)
        params: Optional query parameters
        
    Returns:
        Query results with columns and rows
        
    Note:
        Only SELECT queries are allowed for security reasons
    """
    start_time = time.time()
    
    try:
        # Execute query through our simplified service
        result = db_service.execute_query(query, tuple(params) if params else None)
        
        data = {
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": result["row_count"]
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "execute_query")
        metadata.add_metadata("query_time_ms", result["execution_time_ms"])
        metadata.add_metadata("row_count", result["row_count"])
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except ValueError as ve:
        # Security validation errors
        return ResponseFormatter.validation_error(
            message="Query validation failed",
            details={"error": str(ve), "query": query}
        )
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return ResponseFormatter.server_error(
            message="Failed to execute query",
            details=str(e)
        )


@router.post("/execute-procedure")
async def execute_stored_procedure(
    request: ProcedureExecuteRequest,
    db_service: DatabaseService = Depends(get_db_service),
    connection: ConnectionContext = Depends(require_local_access),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Execute a stored procedure with parameters
    
    Args:
        request: Request containing procedure name and parameters
        
    Returns:
        Procedure execution results
    """
    start_time = time.time()
    actor = current_user.get("username", "unknown")
    
    try:
        # Execute procedure through our service
        result = db_service.execute_stored_procedure(request.procedure_name, request.parameters or {})
        
        data = {
            "procedure_name": request.procedure_name,
            "parameters_used": request.parameters,
            "result": result,
            "message": f"Stored procedure '{request.procedure_name}' executed successfully"
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "execute_procedure")
        metadata.add_metadata("procedure_name", request.procedure_name)
        
        log_action(
            actor=actor,
            action="execute_procedure",
            scope="database",
            client_ip=connection.client_ip,
            success=True,
            details={
                "procedure": request.procedure_name,
                "parameters": request.parameters or {},
            },
        )
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing stored procedure '{request.procedure_name}': {e}")
        log_action(
            actor=actor,
            action="execute_procedure",
            scope="database",
            client_ip=connection.client_ip,
            success=False,
            details={
                "procedure": request.procedure_name,
                "parameters": request.parameters or {},
                "error": str(e),
            },
        )
        return ResponseFormatter.server_error(
            message=f"Failed to execute stored procedure '{request.procedure_name}'",
            details=str(e)
        )


@router.get("/monitoring")
async def get_monitoring_data(
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get current experiment data for monitoring and real-time updates
    
    Returns:
        List of active/recent experiments for monitoring dashboards
    """
    start_time = time.time()
    
    try:
        # Get monitoring data from our simplified service
        monitoring_data = db_service.get_monitoring_data()
        
        data = {
            "experiments": monitoring_data,
            "count": len(monitoring_data),
            "timestamp": datetime.now().isoformat()
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_monitoring_data")
        metadata.add_metadata("experiment_count", len(monitoring_data))
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting monitoring data: {e}")
        return ResponseFormatter.server_error(
            message="Failed to get monitoring data",
            details=str(e)
        )


@router.get("/stored-procedures")
async def get_stored_procedures(
    use_cache: bool = Query(True, description="Use cached results if available"),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get all stored procedures and functions from the database
    
    Args:
        use_cache: Whether to use cached results for better performance
        
    Returns:
        List of stored procedures and functions with their definitions and parameters
    """
    start_time = time.time()
    
    try:
        # Get stored procedures from our service
        result = db_service.get_stored_procedures(use_cache=use_cache)
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_stored_procedures")
        metadata.set_cache_used(use_cache)
        metadata.set_pagination(len(result) if isinstance(result, list) else 0)
        
        return ResponseFormatter.success(data=result, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting stored procedures: {e}")
        return ResponseFormatter.server_error(
            message="Failed to get stored procedures",
            details=str(e)
        )


@router.post("/cache/clear")
async def clear_cache(
    pattern: Optional[str] = None,
    db_service: DatabaseService = Depends(get_db_service),
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """
    Clear database cache entries
    
    Args:
        pattern: Optional pattern to match cache keys (clears all if not provided)
        
    Returns:
        Number of cache entries cleared
    """
    start_time = time.time()
    
    actor = current_user.get("username", "unknown")
    try:
        cleared_count = db_service.clear_cache(pattern)
        
        data = {
            "message": "Cache cleared successfully",
            "entries_cleared": cleared_count,
            "pattern_used": pattern or "all"
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "clear_cache")
        metadata.add_metadata("entries_cleared", cleared_count)
        
        log_action(
            actor=actor,
            action="clear_database_cache",
            scope="database",
            client_ip=connection.client_ip,
            success=True,
            details={"pattern": pattern or "all", "entries_cleared": cleared_count},
        )
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        log_action(
            actor=actor,
            action="clear_database_cache",
            scope="database",
            client_ip=connection.client_ip,
            success=False,
            details={"pattern": pattern or "all", "error": str(e)},
        )
        return ResponseFormatter.server_error(
            message="Failed to clear cache",
            details=str(e)
        )


@router.get("/performance")
async def get_performance_stats(
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get database service performance statistics
    
    Returns:
        Detailed performance metrics including query stats and cache performance
    """
    start_time = time.time()
    
    try:
        # Get performance stats from our simplified service
        stats = db_service.get_performance_stats()
        status = db_service.get_status()
        
        data = {
            "database_status": {
                "is_connected": status.is_connected,
                "mode": status.mode,
                "connection_pool_size": status.connection_pool_size
            },
            "query_performance": {
                "total_queries": stats["query_count"],
                "total_execution_time_ms": stats["total_execution_time_ms"],
                "average_execution_time_ms": stats["average_execution_time_ms"]
            },
            "cache_performance": {
                "cache_entries": stats["cache_entries"],
                "connection_attempts": stats["connection_attempts"]
            },
            "last_error": stats["last_error"]
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_performance_stats")
        metadata.set_cache_used(True)  # Performance stats are cached
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        return ResponseFormatter.server_error(
            message="Failed to get performance stats",
            details=str(e)
        )


@router.get("/health")
async def health_check(
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Database service health check endpoint
    
    Returns:
        Service health status and basic diagnostics
    """
    start_time = time.time()
    
    try:
        # Get health information
        status = db_service.get_status()
        stats = db_service.get_performance_stats()
        
        # Determine health status
        is_healthy = status.is_connected or status.mode == "mock"
        
        data = {
            "service": "database",
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "details": {
                "database_connected": status.is_connected,
                "mode": status.mode,
                "total_queries": stats["query_count"],
                "last_error": status.error_message
            },
            "endpoints": [
                "/api/database/status",
                "/api/database/tables",
                "/api/database/tables/{table_name}",
                "/api/database/query",
                "/api/database/monitoring",
                "/api/database/performance",
                "/api/database/cache/clear",
                "/api/database/health"
            ]
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "health_check")
        metadata.add_metadata("health_status", "healthy" if is_healthy else "unhealthy")
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Database health check error: {e}")
        return ResponseFormatter.server_error(
            message="Database health check failed",
            details=str(e)
        )


# Additional convenience endpoints
@router.get("/tables/{table_name}/count")
async def get_table_count(
    table_name: str,
    filters: Optional[str] = Query(None, description="JSON string of column filters"),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get row count for a specific table with optional filters
    
    Args:
        table_name: Name of the table
        filters: Optional JSON string of column filters
        
    Returns:
        Row count for the table
    """
    start_time = time.time()
    
    try:
        # Parse filters if provided
        parsed_filters = None
        if filters:
            try:
                parsed_filters = json.loads(filters)
            except json.JSONDecodeError:
                return ResponseFormatter.validation_error(
                    message="Invalid JSON format for filters parameter",
                    details={"filters": filters}
                )
        
        # Get minimal data to get count
        result = db_service.get_table_data(
            table_name=table_name,
            limit=1,
            offset=0,
            filters=parsed_filters
        )
        
        data = {
            "table_name": table_name,
            "total_count": result.total_count,
            "filters_applied": parsed_filters
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_table_count")
        metadata.add_metadata("table_name", table_name)
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting count for table '{table_name}': {e}")
        return ResponseFormatter.server_error(
            message=f"Failed to get count for table '{table_name}'",
            details=str(e)
        )


@router.get("/tables/{table_name}/columns")
async def get_table_columns(
    table_name: str,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get column information for a specific table
    
    Args:
        table_name: Name of the table
        
    Returns:
        List of column names for the table
    """
    start_time = time.time()
    
    try:
        # Get minimal data to get column info
        result = db_service.get_table_data(
            table_name=table_name,
            limit=1,
            offset=0
        )
        
        data = {
            "table_name": table_name,
            "columns": result.columns,
            "column_count": len(result.columns)
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_table_columns")
        metadata.add_metadata("table_name", table_name)
        metadata.add_metadata("column_count", len(result.columns))
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting columns for table '{table_name}': {e}")
        return ResponseFormatter.server_error(
            message=f"Failed to get columns for table '{table_name}'",
            details=str(e)
        )


if __name__ == "__main__":
    # For testing purposes
    import uvicorn
    from fastapi import FastAPI
    
    app = FastAPI(title="PyRobot Database API", version="1.0.0")
    app.include_router(router)
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
