"""
Performance monitoring API endpoints for PyRobot.

Provides endpoints to access performance metrics, query statistics,
and system monitoring data collected by the performance logging system.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

from ..utils.logger import setup_performance_logging, get_logger
from ..api.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)
perf_logger = get_logger('pyrobot.performance.api')
router = APIRouter()
formatter = ResponseFormatter()

# Store reference to performance loggers
_performance_loggers: Dict[str, Any] = {}


def initialize_performance_loggers():
    """Initialize performance loggers if not already done"""
    global _performance_loggers
    if not _performance_loggers:
        _performance_loggers = setup_performance_logging()


@router.get("/performance/metrics")
async def get_performance_metrics(
    since_hours: Optional[int] = Query(1, description="Hours to look back for metrics"),
    metric_name: Optional[str] = Query(None, description="Filter by specific metric name"),
    subsystem: Optional[str] = Query(None, description="Filter by subsystem (api, database, websocket, etc.)")
):
    """Get performance metrics collected over time"""
    try:
        initialize_performance_loggers()
        
        since_time = datetime.now() - timedelta(hours=since_hours)
        all_metrics = []
        
        # Collect metrics from relevant loggers
        if subsystem and subsystem in _performance_loggers:
            loggers_to_check = {subsystem: _performance_loggers[subsystem]}
        else:
            loggers_to_check = _performance_loggers
        
        for system_name, system_logger in loggers_to_check.items():
            metrics = system_logger.get_recent_metrics(since=since_time, metric_name=metric_name)
            for metric in metrics:
                metric_dict = metric.to_dict()
                metric_dict['subsystem'] = system_name
                all_metrics.append(metric_dict)
        
        # Sort by timestamp
        all_metrics.sort(key=lambda x: x['timestamp'])
        
        perf_logger.perf_debug(f"Retrieved {len(all_metrics)} performance metrics",
                             since_hours=since_hours, metric_name=metric_name, 
                             subsystem=subsystem)
        
        return formatter.format_success(
            data=all_metrics,
            metadata={
                "count": len(all_metrics),
                "since": since_time.isoformat(),
                "metric_name": metric_name,
                "subsystem": subsystem
            }
        )
    
    except Exception as e:
        logger.error(f"Error retrieving performance metrics: {e}")
        return formatter.format_error(
            message="Failed to retrieve performance metrics",
            details=str(e)
        )


@router.get("/performance/database/stats")
async def get_database_performance_stats():
    """Get database query performance statistics"""
    try:
        initialize_performance_loggers()
        
        db_logger = _performance_loggers.get('database')
        if not db_logger:
            raise HTTPException(status_code=404, detail="Database performance logger not found")
        
        # Get stats for different query types
        query_types = ['select', 'select_join', 'select_filtered', 'select_ordered', 'select_grouped']
        stats = {}
        
        for query_type in query_types:
            type_stats = db_logger.get_query_stats(query_type)
            if type_stats:
                stats[query_type] = type_stats
        
        perf_logger.perf_debug("Retrieved database performance statistics",
                             query_types_found=len(stats))
        
        return formatter.format_success(
            data=stats,
            metadata={
                "query_types": list(stats.keys()),
                "total_query_types": len(stats)
            }
        )
    
    except Exception as e:
        logger.error(f"Error retrieving database stats: {e}")
        return formatter.format_error(
            message="Failed to retrieve database performance statistics",
            details=str(e)
        )


@router.get("/performance/api/stats")
async def get_api_performance_stats(
    endpoint: Optional[str] = Query(None, description="Filter by specific endpoint")
):
    """Get API request performance statistics"""
    try:
        initialize_performance_loggers()
        
        api_logger = _performance_loggers.get('api')
        if not api_logger:
            # Try middleware logger as fallback
            middleware_logger = get_logger('pyrobot.performance.middleware')
            stats = middleware_logger.get_request_stats(endpoint)
        else:
            stats = api_logger.get_request_stats(endpoint)
        
        perf_logger.perf_debug("Retrieved API performance statistics",
                             endpoint=endpoint, stats_count=len(stats))
        
        return formatter.format_success(
            data=stats,
            metadata={
                "filtered_endpoint": endpoint,
                "endpoint_count": len([k for k in stats.keys() if not k.startswith('_')])
            }
        )
    
    except Exception as e:
        logger.error(f"Error retrieving API stats: {e}")
        return formatter.format_error(
            message="Failed to retrieve API performance statistics",
            details=str(e)
        )


@router.get("/performance/summary")
async def get_performance_summary():
    """Get overall performance summary across all subsystems"""
    try:
        initialize_performance_loggers()
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "subsystems": {},
            "overall_stats": {
                "total_metrics": 0,
                "active_loggers": len(_performance_loggers)
            }
        }
        
        # Collect summary from each subsystem
        for system_name, system_logger in _performance_loggers.items():
            # Get recent metrics (last hour)
            recent_metrics = system_logger.get_recent_metrics(
                since=datetime.now() - timedelta(hours=1)
            )
            
            subsystem_summary = {
                "recent_metrics_count": len(recent_metrics),
                "logger_active": True
            }
            
            # Add specific stats based on subsystem type
            if system_name == 'database':
                # Add query stats summary
                query_types = ['select', 'select_join', 'select_filtered']
                total_queries = 0
                avg_time = 0
                
                for query_type in query_types:
                    stats = system_logger.get_query_stats(query_type)
                    if stats:
                        total_queries += stats.get('count', 0)
                        avg_time += stats.get('avg', 0)
                
                subsystem_summary['total_queries'] = total_queries
                subsystem_summary['avg_query_time'] = avg_time / len(query_types) if query_types else 0
                
            elif system_name == 'api':
                # Add request stats summary
                request_stats = system_logger.get_request_stats()
                summary_stats = request_stats.get('_summary', {})
                subsystem_summary.update(summary_stats)
            
            summary['subsystems'][system_name] = subsystem_summary
            summary['overall_stats']['total_metrics'] += len(recent_metrics)
        
        perf_logger.perf_info("Generated performance summary",
                            active_loggers=len(_performance_loggers),
                            total_recent_metrics=summary['overall_stats']['total_metrics'])
        
        return formatter.format_success(
            data=summary,
            metadata={
                "generated_at": summary["timestamp"],
                "subsystem_count": len(summary['subsystems'])
            }
        )
    
    except Exception as e:
        logger.error(f"Error generating performance summary: {e}")
        return formatter.format_error(
            message="Failed to generate performance summary",
            details=str(e)
        )


@router.post("/performance/clear")
async def clear_performance_metrics():
    """Clear stored performance metrics (useful for testing or maintenance)"""
    try:
        initialize_performance_loggers()
        
        cleared_count = 0
        for system_name, system_logger in _performance_loggers.items():
            system_logger.clear_metrics()
            cleared_count += 1
        
        perf_logger.perf_info("Cleared performance metrics",
                            subsystems_cleared=cleared_count)
        
        return formatter.format_success(
            data={"cleared_subsystems": cleared_count},
            metadata={"operation": "clear_metrics", "timestamp": datetime.now().isoformat()}
        )
    
    except Exception as e:
        logger.error(f"Error clearing performance metrics: {e}")
        return formatter.format_error(
            message="Failed to clear performance metrics",
            details=str(e)
        )


@router.get("/performance/health")
async def get_performance_health():
    """Get health status of performance monitoring system"""
    try:
        initialize_performance_loggers()
        
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "loggers": {},
            "issues": []
        }
        
        # Check each logger's health
        for system_name, system_logger in _performance_loggers.items():
            logger_health = {
                "active": True,
                "recent_metrics_count": len(system_logger.get_recent_metrics(
                    since=datetime.now() - timedelta(minutes=5)
                )),
                "has_metrics": len(system_logger.metrics) > 0
            }
            
            health_status["loggers"][system_name] = logger_health
            
            # Check for issues
            if not logger_health["has_metrics"]:
                health_status["issues"].append(f"{system_name} logger has no metrics recorded")
        
        # Determine overall health
        if health_status["issues"]:
            health_status["status"] = "degraded"
        
        perf_logger.perf_debug("Performance system health check completed",
                             status=health_status["status"],
                             active_loggers=len(health_status["loggers"]),
                             issues_count=len(health_status["issues"]))
        
        return formatter.format_success(
            data=health_status,
            metadata={"check_type": "health", "timestamp": health_status["timestamp"]}
        )
    
    except Exception as e:
        logger.error(f"Error checking performance health: {e}")
        return formatter.format_error(
            message="Failed to check performance monitoring health",
            details=str(e)
        )