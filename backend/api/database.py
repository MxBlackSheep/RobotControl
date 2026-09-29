"""
RobotControl Database API

Clean and simple REST API endpoints for database operations.
Consolidates functionality from web_app/api/v1/database.py into a simplified interface.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from starlette.concurrency import run_in_threadpool
from typing import Optional, List
import logging
import time
import json

# Import our simplified database service
from backend.services.auth import get_current_user
from backend.services.database import DatabaseService
from backend.services.database_tools import get_database_tools

# Import standardized response formatter
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/database", tags=["database"])

def get_viewer_service(source_id: str | None = Query(None, max_length=64),
                       user=Depends(get_current_user), service=Depends(get_database_tools)):
    from backend.services.workspace_database import WorkspaceDatabase
    from backend.services.database_packages import PackageError
    try:
        source = service.sources.viewer()
        if not source:
            raise PackageError('Ask an administrator to choose the viewer database in Database settings.', 409)
        if source_id and source_id != source['id']:
            raise PackageError('The viewer database changed. Refresh this page.', 409)
        return WorkspaceDatabase(service.sources, source)
    except PackageError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.get("/tables")
async def get_tables(
    use_cache: bool = Query(True, description="Use cached results if available"),
    important_only: bool = Query(False, description="Show only important tables"),
    db_service: DatabaseService = Depends(get_viewer_service)
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
        all_tables = await run_in_threadpool(db_service.get_tables, use_cache=use_cache)
        
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
    search: Optional[str] = Query(None, max_length=200, description="Literal search across supported scalar columns"),
    sort_direction: str = Query("asc", pattern="^(asc|desc)$"),
    filters: Optional[str] = Query(None, description="JSON string of column filters"),
    use_cache: bool = Query(True, description="Use cached results if available"),
    db_service: DatabaseService = Depends(get_viewer_service)
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
        result = await run_in_threadpool(db_service.get_table_data,
            table_name=table_name,
            limit=limit,
            offset=offset,
            order_by=order_by,
            filters=parsed_filters,
            use_cache=use_cache, search=search, sort_direction=sort_direction
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
            "filters_applied": parsed_filters,
            "search": search, "sort_direction": sort_direction
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
        
    except ValueError as e:
        return ResponseFormatter.validation_error(message=str(e))
    except Exception as e:
        logger.error(f"Error getting data from table '{table_name}': {e}")
        return ResponseFormatter.server_error(
            message=f"Failed to retrieve data from table '{table_name}'",
            details=str(e)
        )


@router.post("/query")
@router.post("/execute-procedure")
def retired_execution_route(current_user=Depends(get_current_user)):
    raise HTTPException(status_code=410, detail="Use an installed database operation or report.")


@router.get("/stored-procedures")
async def get_stored_procedures(
    use_cache: bool = Query(True, description="Use cached results if available"),
    db_service: DatabaseService = Depends(get_viewer_service)
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
        result = await run_in_threadpool(db_service.get_stored_procedures, use_cache=use_cache)
        
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


if __name__ == "__main__":
    # For testing purposes
    import uvicorn
    from fastapi import FastAPI
    
    app = FastAPI(title="RobotControl Database API", version="1.0.0")
    app.include_router(router)
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
