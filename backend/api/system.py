"""
System API endpoints for file browsing and system operations
"""

import logging
import time
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pathlib import Path
from backend.utils.filesystem import restricted_directory, visible_children

from backend.services.auth import get_current_user

# Import standardized response formatter
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

@router.get("/browse")
async def browse_directory(
    path: str = Query(..., description="Directory path to browse"),
    filter: str = Query(None, description="File extension filter (e.g., '.bck')"),
    current_user: dict = Depends(get_current_user)
):
    """
    Browse file system directory with optional filtering
    
    Args:
        path: Directory path to browse
        filter: Optional file extension filter
        current_user: Current authenticated user
    
    Returns:
        Dictionary containing directory items
    """
    start_time = time.time()
    
    try:
        # Validate and sanitize path
        browse_path = Path(path).resolve()
        
        # Security check - prevent browsing outside of reasonable bounds
        # Allow browsing most Windows directories but prevent system-critical areas
        
        if restricted_directory(browse_path):
            return ResponseFormatter.forbidden(
                message="Access to this directory is restricted",
                details="Cannot access system-critical directories"
            )
        
        if not browse_path.exists():
            return ResponseFormatter.not_found(
                message="Directory not found",
                details=f"The directory '{path}' does not exist"
            )
        
        if not browse_path.is_dir():
            return ResponseFormatter.bad_request(
                message="Path is not a directory",
                details=f"The path '{path}' exists but is not a directory"
            )
        
        items = []
        
        try:
            # List directory contents
            for item in visible_children(browse_path):
                try:
                    is_directory = item.is_dir()
                    item_name = item.name
                    
                    
                    item_info = {
                        'name': item_name,
                        'path': str(item),
                        'is_directory': is_directory
                    }
                    
                    if not is_directory:
                        # Check filter if specified
                        if filter and not item_name.lower().endswith(filter.lower()):
                            continue
                        
                        # Get file details
                        stat = item.stat()
                        item_info.update({
                            'size': stat.st_size,
                            'size_formatted': format_file_size(stat.st_size),
                            'modified_date': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            'is_backup_file': item_name.lower().endswith('.bck') or item_name.lower().endswith('.bak')
                        })
                    
                    items.append(item_info)
                    
                except (OSError, PermissionError) as e:
                    # Skip items we can't access
                    logger.debug(f"Skipping inaccessible item {item}: {e}")
                    continue
            
            # Sort: directories first, then files
            items.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))
            
            browse_data = {
                "current_path": str(browse_path),
                "items": items,
                "total_items": len(items)
            }
            
            # Create metadata
            metadata = ResponseMetadata()
            metadata.set_execution_time(start_time)
            metadata.add_metadata("operation", "browse_directory")
            metadata.add_metadata("user_id", current_user.get("user_id"))
            metadata.add_metadata("path", str(browse_path))
            metadata.add_metadata("filter", filter)
            metadata.add_metadata("item_count", len(items))
            
            return ResponseFormatter.success(
                data=browse_data,
                metadata=metadata,
                message=f"Successfully browsed directory with {len(items)} items"
            )
            
        except PermissionError:
            return ResponseFormatter.forbidden(
                message="Permission denied to access this directory",
                details="You do not have sufficient permissions to access this directory"
            )
        
    except Exception as e:
        logger.error(f"Error browsing directory {path}: {e}")
        return ResponseFormatter.server_error(
            message="Failed to browse directory",
            details=str(e)
        )

