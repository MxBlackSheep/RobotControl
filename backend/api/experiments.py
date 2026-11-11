from starlette.concurrency import run_in_threadpool
"""
Experiments API endpoints
Provides access to experiment data from Hamilton Vector database
"""

from fastapi import APIRouter, Depends
from backend.services.database import get_database_service
from backend.services.experiment_monitor import query_latest_experiment
from backend.services.pyhsl_monitor import experiment_runner
from backend.services.auth import get_current_user
import logging
import time

# Import standardized response formatter
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata

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
        
        result = await run_in_threadpool(query_latest_experiment, db)

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
                **experiment_runner(row.get("MethodName")),
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
