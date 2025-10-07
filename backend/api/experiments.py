"""
Experiments API endpoints
Provides access to experiment data from Hamilton Vector database
"""

from fastapi import APIRouter, HTTPException, Depends
from backend.services.database import get_database_service
from backend.services.auth import get_current_user
import logging
import time

# Import standardized response formatter
from backend.api.response_formatter import (
    ResponseFormatter, 
    ResponseMetadata, 
    format_success, 
    format_error
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

@router.get("/latest")
async def get_latest_experiment(current_user: dict = Depends(get_current_user)):
    """
    Get the latest experiment from HamiltonVectorDB.dbo.HxRun
    Safe lazy-loaded endpoint that fails gracefully if database is unavailable
    """
    start_time = time.time()
    
    try:
        db = get_database_service()  # Lazy-loaded database service
        
        query = """
            SELECT TOP 1 RunGUID, MethodName, StartTime, EndTime, RunState
            FROM HamiltonVectorDB.dbo.HxRun
            ORDER BY StartTime DESC
        """
        
        logger.info("Fetching latest experiment from HamiltonVectorDB")
        result = db.execute_query(query)
        
        if result.get("error"):
            # Database connection failed - return graceful fallback
            logger.warning(f"Database query failed: {result['error']}")
            return ResponseFormatter.service_unavailable(
                message="Database unavailable",
                details=result['error']
            )
        
        if result.get("rows") and len(result["rows"]) > 0:
            # Extract the first (latest) experiment
            row = result["rows"][0]
            experiment_data = {
                "run_guid": row.get("RunGUID"),
                "method_name": row.get("MethodName"),
                "start_time": row.get("StartTime"),  # Already converted to ISO string by execute_query
                "end_time": row.get("EndTime"),
                "run_state": row.get("RunState")
            }
            
            # Create metadata
            metadata = ResponseMetadata()
            metadata.set_execution_time(start_time)
            metadata.add_metadata("operation", "get_latest_experiment")
            metadata.add_metadata("user_id", current_user.get("user_id"))
            metadata.add_metadata("experiment_found", True)
            metadata.add_metadata("method_name", experiment_data["method_name"])
            metadata.add_metadata("run_state", experiment_data["run_state"])
            
            logger.info(f"Latest experiment: {experiment_data['method_name']} ({experiment_data['run_state']})")
            return ResponseFormatter.success(
                data=experiment_data,
                metadata=metadata,
                message="Latest experiment retrieved successfully"
            )
        else:
            # Create metadata for no results
            metadata = ResponseMetadata()
            metadata.set_execution_time(start_time)
            metadata.add_metadata("operation", "get_latest_experiment")
            metadata.add_metadata("user_id", current_user.get("user_id"))
            metadata.add_metadata("experiment_found", False)
            
            logger.info("No experiments found in HamiltonVectorDB")
            return ResponseFormatter.success(
                data=None,
                metadata=metadata,
                message="No experiments found"
            )
            
    except Exception as e:
        # Log error but don't break dashboard - return graceful failure
        logger.warning(f"Failed to fetch latest experiment: {str(e)}")
        return ResponseFormatter.server_error(
            message="Experiment data unavailable",
            details=str(e) if logger.level <= logging.DEBUG else None
        )

@router.get("/health")
async def experiments_health():
    """
    Health check endpoint for experiments service
    """
    start_time = time.time()
    
    try:
        db = get_database_service()
        # Simple query to test connection
        result = db.execute_query("SELECT 1 as test")
        
        if result.get("error"):
            health_data = {
                "status": "degraded", 
                "database_accessible": False,
                "service": "experiments"
            }
            
            # Create metadata for degraded state
            metadata = ResponseMetadata()
            metadata.set_execution_time(start_time)
            metadata.add_metadata("operation", "experiments_health")
            metadata.add_metadata("health_status", "degraded")
            metadata.add_metadata("database_accessible", False)
            
            return ResponseFormatter.service_unavailable(
                message="Experiments service degraded",
                details=result["error"],
                data=health_data,
                metadata=metadata
            )
        
        health_data = {
            "status": "healthy", 
            "database_accessible": True,
            "service": "experiments"
        }
        
        # Create metadata for healthy state
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "experiments_health")
        metadata.add_metadata("health_status", "healthy")
        metadata.add_metadata("database_accessible", True)
        
        return ResponseFormatter.success(
            data=health_data,
            metadata=metadata,
            message="Experiments service is healthy"
        )
        
    except Exception as e:
        health_data = {
            "status": "degraded", 
            "database_accessible": False,
            "service": "experiments"
        }
        
        return ResponseFormatter.server_error(
            message="Experiments service health check failed",
            details=str(e),
            data=health_data
        )