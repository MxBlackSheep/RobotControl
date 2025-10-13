"""
PyRobot Database Backup/Restore Service

Provides secure database backup and restore functionality for authorized users.
Implements SQL Server backup operations with metadata management and file validation.

Features:
- SQL Server BACKUP/RESTORE operations
- Metadata management with JSON files  
- File path validation and security
- Admin-only access control
- Comprehensive error handling
- Connection resilience during restore operations
"""

import os
import sys
import json
import logging
import logging.handlers
import subprocess
import threading
import time
import traceback
import pyodbc
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
from contextlib import contextmanager

from backend.utils.data_paths import get_path_manager, get_backups_path

# Import configuration from project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

try:
    import config
except ImportError:
    # Create minimal config if none exists
    class Config:
        pass
    config = Config()

# Enhanced Logging Configuration
def setup_backup_logging():
    """
    Setup comprehensive logging for backup operations.
    Creates dedicated backup log file with detailed formatting and rotation.
    """
    backup_logger = logging.getLogger(__name__)
    
    # Prevent duplicate handlers
    if backup_logger.handlers:
        return backup_logger
    
    backup_logger.setLevel(logging.DEBUG)
    
    # Use data path manager for logs directory
    try:
        from backend.utils.data_paths import get_logs_path
        log_file = get_logs_path() / "backup_service.log"
    except ImportError:
        # Fallback to traditional approach
        log_dir = os.path.join(project_root, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "backup_service.log")
    
    # File handler with rotation (10MB max, keep 5 files)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler for immediate feedback
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Detailed formatter with operation context
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Simple formatter for console
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - Backup: %(message)s',
        datefmt='%H:%M:%S'
    )
    
    file_handler.setFormatter(detailed_formatter)
    console_handler.setFormatter(simple_formatter)
    
    backup_logger.addHandler(file_handler)
    backup_logger.addHandler(console_handler)
    
    return backup_logger

# Initialize enhanced logger
logger = setup_backup_logging()

# Performance and Operation Tracking
@dataclass
class OperationMetrics:
    """Track detailed metrics for backup operations"""
    operation_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None
    success: bool = False
    file_size_bytes: Optional[int] = None
    error_message: Optional[str] = None
    recovery_suggestions: List[str] = None
    
    def __post_init__(self):
        if self.recovery_suggestions is None:
            self.recovery_suggestions = []
    
    def complete(self, success: bool = True, error_message: Optional[str] = None):
        """Mark operation as complete and calculate duration"""
        self.end_time = datetime.now()
        self.duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        self.success = success
        self.error_message = error_message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        return {
            'operation_type': self.operation_type,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_ms': self.duration_ms,
            'success': self.success,
            'file_size_bytes': self.file_size_bytes,
            'file_size_mb': round(self.file_size_bytes / (1024*1024), 2) if self.file_size_bytes else None,
            'error_message': self.error_message,
            'recovery_suggestions': self.recovery_suggestions
        }

@contextmanager
def operation_tracker(operation_type: str, context: Dict[str, Any] = None):
    """
    Context manager for tracking backup operations with comprehensive logging
    
    Usage:
        with operation_tracker('backup_create', {'filename': 'backup.bak'}) as metrics:
            # perform operation
            metrics.file_size_bytes = file_size
    """
    metrics = OperationMetrics(operation_type, datetime.now())
    operation_id = f"{operation_type}_{int(time.time())}"
    
    try:
        logger.info(f"Starting {operation_type} operation", 
                   extra={'operation_id': operation_id, 'context': context or {}})
        yield metrics
        
        # Success path
        metrics.complete(success=True)
        logger.info(f"{operation_type} completed successfully in {metrics.duration_ms}ms",
                   extra={'operation_id': operation_id, 'metrics': metrics.to_dict()})
        
    except Exception as e:
        # Error path with recovery suggestions
        error_msg = str(e)
        recovery_suggestions = _get_recovery_suggestions(operation_type, e)
        
        metrics.complete(success=False, error_message=error_msg)
        metrics.recovery_suggestions = recovery_suggestions
        
        logger.error(f"{operation_type} failed after {metrics.duration_ms}ms: {error_msg}",
                    extra={
                        'operation_id': operation_id, 
                        'metrics': metrics.to_dict(),
                        'traceback': traceback.format_exc()
                    })
        
        # Log recovery suggestions
        if recovery_suggestions:
            logger.info(f"Recovery suggestions for {operation_type}:",
                       extra={'recovery_suggestions': recovery_suggestions})
        
        raise

def _get_recovery_suggestions(operation_type: str, error: Exception) -> List[str]:
    """Generate contextual recovery suggestions based on operation type and error"""
    suggestions = []
    error_msg = str(error).lower()
    
    # Common suggestions based on error patterns
    if "timeout" in error_msg:
        suggestions.extend([
            "Increase operation timeout in configuration",
            "Check for database locks or long-running queries",
            "Verify SQL Server performance and resource availability",
            "Consider running operation during low-activity periods"
        ])
    
    if "permission" in error_msg or "access" in error_msg:
        suggestions.extend([
            "Verify SQL Server service account has backup privileges",
            "Check file system permissions on backup directory",
            "Ensure backup directory exists and is writable",
            "Verify SQL Server can access backup file path"
        ])
    
    if "connection" in error_msg or "network" in error_msg:
        suggestions.extend([
            "Verify SQL Server instance is running and accessible",
            "Check network connectivity to database server",
            "Verify connection string and authentication credentials",
            "Check firewall settings for SQL Server port (1433)"
        ])
    
    if "space" in error_msg or "disk" in error_msg:
        suggestions.extend([
            "Free up disk space on backup destination drive",
            "Clean up old backup files to make room",
            "Check available disk space before starting operations",
            "Consider using compression for backup files"
        ])
    
    # Operation-specific suggestions
    if operation_type == 'backup_create':
        suggestions.extend([
            "Verify database is online and accessible",
            "Check for exclusive database locks",
            "Ensure backup directory has sufficient space",
            "Consider differential backup for large databases"
        ])
    
    elif operation_type == 'backup_restore':
        suggestions.extend([
            "Verify backup file integrity before restore",
            "Ensure exclusive access to target database",
            "Check database compatibility between backup and target",
            "Verify sufficient space in database data directory"
        ])
    
    elif operation_type == 'backup_delete':
        suggestions.extend([
            "Check if backup file is in use by another process",
            "Verify file permissions allow deletion",
            "Ensure backup file exists at expected location"
        ])
    
    return suggestions

# Performance monitoring
class BackupPerformanceMonitor:
    """Monitor and track backup system performance metrics"""
    
    def __init__(self):
        self.operations_count = 0
        self.total_duration_ms = 0
        self.success_count = 0
        self.error_count = 0
        self.last_reset = datetime.now()
    
    def record_operation(self, metrics: OperationMetrics):
        """Record operation metrics for performance tracking"""
        self.operations_count += 1
        if metrics.duration_ms:
            self.total_duration_ms += metrics.duration_ms
        
        if metrics.success:
            self.success_count += 1
        else:
            self.error_count += 1
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary for monitoring dashboard"""
        avg_duration = (self.total_duration_ms / self.operations_count) if self.operations_count > 0 else 0
        success_rate = (self.success_count / self.operations_count * 100) if self.operations_count > 0 else 100
        
        return {
            'total_operations': self.operations_count,
            'success_count': self.success_count,
            'error_count': self.error_count,
            'success_rate_percent': round(success_rate, 1),
            'average_duration_ms': round(avg_duration, 2),
            'total_duration_seconds': round(self.total_duration_ms / 1000, 2),
            'monitoring_period_hours': (datetime.now() - self.last_reset).total_seconds() / 3600
        }
    
    def reset_metrics(self):
        """Reset performance metrics (useful for periodic reporting)"""
        self.operations_count = 0
        self.total_duration_ms = 0
        self.success_count = 0
        self.error_count = 0
        self.last_reset = datetime.now()
        logger.info("🔄 Performance metrics reset")

# Global performance monitor
performance_monitor = BackupPerformanceMonitor()

# Custom Exception Classes
class BackupOperationError(Exception):
    """Exception raised during backup operations with error code"""
    def __init__(self, message: str, error_code: str = "BACKUP_ERROR"):
        self.error_code = error_code
        super().__init__(message)

def get_available_disk_space(path: str) -> int:
    """Get available disk space for given path in bytes"""
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        return free
    except Exception:
        # Fallback for systems where shutil.disk_usage isn't available
        return 0

# Backup Configuration Constants
# Use relative path approach for both development and compiled modes
try:
    from backend.config import settings
    path_manager = get_path_manager()
    base_path = path_manager.base_path

    configured_backup_path = str(settings.LOCAL_BACKUP_PATH)

    # Resolve relative to executable/project root directory
    if os.path.isabs(configured_backup_path):
        # Already absolute path
        BACKUP_DIR = configured_backup_path
    else:
        # Relative path - resolve from compiled/dev base directory
        BACKUP_DIR = str((base_path / configured_backup_path).resolve())

    sql_backup_path = str(settings.SQL_BACKUP_PATH).strip()
    if not sql_backup_path:
        SQL_BACKUP_DIR = BACKUP_DIR
    elif os.path.isabs(sql_backup_path) or sql_backup_path.startswith(r"\\"):
        SQL_BACKUP_DIR = sql_backup_path
    else:
        SQL_BACKUP_DIR = str((base_path / sql_backup_path).resolve())
    logger.debug(f"Backup directory resolved to: {BACKUP_DIR}")
    logger.debug(f"SQL backup directory: {SQL_BACKUP_DIR}")

except ImportError:
    # Fallback to the managed data/backups directory
    BACKUP_DIR = str(get_backups_path())
    SQL_BACKUP_DIR = BACKUP_DIR
    logger.warning(f"Config import failed, using fallback directory: {BACKUP_DIR}")
SQL_SERVER = getattr(config, 'SQL_SERVER', "LOCALHOST\\HAMILTON")
DATABASE_NAME = getattr(config, 'DATABASE_NAME', "EvoYeast")

# Operation timeouts (in seconds)
BACKUP_TIMEOUT = 300  # 5 minutes
RESTORE_TIMEOUT = 600  # 10 minutes
FILE_OPERATION_TIMEOUT = 30  # 30 seconds

# File validation patterns
ALLOWED_EXTENSIONS = {'.bak', '.bck', '.json'}
MAX_DESCRIPTION_LENGTH = 1000
MAX_FILENAME_LENGTH = 255

# SQL Commands
SQL_RESTORE_TEMPLATE = """
ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; 
RESTORE DATABASE [{database}] 
FROM DISK = N'{backup_path}' 
WITH REPLACE; 
ALTER DATABASE [{database}] SET MULTI_USER;
"""

# Ensure backup directory exists (skip if network path not accessible locally)
try:
    os.makedirs(BACKUP_DIR, exist_ok=True)
except Exception as e:
    logger.warning(f"Could not create backup directory locally (network path expected): {e}")


@dataclass
class BackupInfo:
    """Information about a database backup"""
    filename: str
    description: str
    timestamp: str
    created_date: str
    file_size: int
    file_size_formatted: str
    is_valid: bool
    database_name: Optional[str] = None
    sql_server: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


@dataclass
class BackupResult:
    """Result of backup operation"""
    success: bool
    message: str
    filename: Optional[str] = None
    file_size: Optional[int] = None
    duration_ms: Optional[int] = None
    error_details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return asdict(self)


@dataclass
class RestoreResult:
    """Result of restore operation"""
    success: bool
    backup_filename: str
    message: str = ""
    file_path: Optional[str] = None
    execution_time_seconds: Optional[float] = None
    database_name: Optional[str] = None
    sql_server: Optional[str] = None
    duration_ms: Optional[int] = None
    warnings: Optional[List[str]] = None
    error_details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return asdict(self)


@dataclass
class BackupDetails:
    """Detailed backup information including metadata"""
    filename: str
    description: str
    timestamp: str
    created_date: str
    file_size: int
    file_size_formatted: str
    database_name: str
    sql_server: str
    metadata: Dict[str, Any]
    is_valid: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return asdict(self)


class BackupValidationError(Exception):
    """Exception for backup validation errors"""
    pass


class BackupSecurityError(Exception):
    """Exception for backup security violations"""
    pass


class BackupOperationError(Exception):
    """Exception for backup operation failures"""
    pass


def validate_filename(filename: str) -> str:
    """
    Validate and sanitize backup filename
    
    Args:
        filename: Input filename to validate
        
    Returns:
        Sanitized filename
        
    Raises:
        BackupValidationError: If filename is invalid
        BackupSecurityError: If filename poses security risk
    """
    if not filename:
        raise BackupValidationError("Filename cannot be empty")
    
    if len(filename) > MAX_FILENAME_LENGTH:
        raise BackupValidationError(f"Filename too long (max {MAX_FILENAME_LENGTH} characters)")
    
    # Security check: prevent directory traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        raise BackupSecurityError("Invalid characters in filename")
    
    # Check for allowed extensions
    file_ext = Path(filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise BackupSecurityError(f"Invalid file extension. Allowed: {ALLOWED_EXTENSIONS}")
    
    # Additional security validation
    forbidden_chars = ['<', '>', ':', '"', '|', '?', '*']
    if any(char in filename for char in forbidden_chars):
        raise BackupSecurityError("Filename contains forbidden characters")
    
    return filename


def validate_file_path(file_path: str) -> str:
    """
    Validate file path is within backup directory (supports network paths)
    
    Args:
        file_path: File path to validate
        
    Returns:
        Validated path
        
    Raises:
        BackupSecurityError: If path is outside backup directory
    """
    try:
        # Handle network paths and local paths
        if BACKUP_DIR.startswith(r"\\"):
            # Network path - use direct string comparison
            backup_dir_norm = os.path.normpath(BACKUP_DIR).lower()
            file_path_norm = os.path.normpath(file_path).lower()
            
            if not file_path_norm.startswith(backup_dir_norm):
                raise BackupSecurityError("File path outside backup directory")
            
            return file_path
        else:
            # Local path - use absolute path resolution
            abs_path = os.path.abspath(file_path)
            backup_dir_abs = os.path.abspath(BACKUP_DIR)
            
            if not abs_path.startswith(backup_dir_abs):
                raise BackupSecurityError("File path outside backup directory")
            
            return abs_path
    
    except Exception as e:
        logger.error(f"Path validation error: {e}")
        raise BackupSecurityError(f"Invalid file path: {e}")


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format
    
    Args:
        size_bytes: File size in bytes
        
    Returns:
        Formatted size string (e.g., "2.5 MB")
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    if i == 0:
        return f"{int(size)} {size_names[i]}"
    else:
        return f"{size:.1f} {size_names[i]}"


def escape_sql_path(path: str) -> str:
    """
    Escape SQL Server file path for safe command execution
    
    Args:
        path: File path to escape
        
    Returns:
        Escaped path safe for SQL commands
    """
    # For SQL Server with N'...' syntax, only escape single quotes
    # Backslashes are handled correctly by SQL Server for Windows paths
    return path.replace("'", "''")


def generate_backup_filename(database_name: str, timestamp: Optional[datetime] = None) -> str:
    """
    Generate standardized backup filename
    
    Args:
        database_name: Name of database being backed up
        timestamp: Optional timestamp (defaults to now)
        
    Returns:
        Generated filename (e.g., "EvoYeast_20250821_143022.bak")
    """
    if timestamp is None:
        timestamp = datetime.now()
    
    timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
    return f"{database_name}_{timestamp_str}.bak"


def create_backup_metadata(filename: str, description: str, database_name: str, 
                          sql_server: str, file_size: int) -> Dict[str, Any]:
    """
    Create backup metadata dictionary
    
    Args:
        filename: Backup filename
        description: User description
        database_name: Source database name
        sql_server: Source SQL Server instance
        file_size: Backup file size in bytes
        
    Returns:
        Metadata dictionary
    """
    timestamp = datetime.now()
    
    return {
        "file": filename,
        "description": description,
        "timestamp": timestamp.strftime("%Y%m%d_%H%M%S"),
        "created_date": timestamp.isoformat(),
        "database_name": database_name,
        "sql_server": sql_server,
        "file_size": file_size,
        "file_size_formatted": format_file_size(file_size),
        "created_by": "PyRobot Backup Service",
        "version": "1.0"
    }


class BackupService:
    """
    Database backup and restore service
    
    Provides secure backup operations with comprehensive validation and error handling.
    Maintains isolation from other application components to prevent cascading failures.
    """
    
    def __init__(self):
        """Initialize backup service"""
        self.backup_dir = BACKUP_DIR
        self.sql_server = SQL_SERVER
        self.database_name = DATABASE_NAME
        self._operation_lock = threading.Lock()
        
        # Ensure backup directory exists (skip if network path not accessible locally)  
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create backup directory in service init (network path expected): {e}")
        
        logger.info(f"BackupService initialized - Database: {self.database_name}, Server: {self.sql_server}")
    
    def _get_database_connection(self):
        """
        Get direct database connection using centralized connection manager.
        This is used as fallback when sqlcmd is not available.
        """
        try:
            from backend.core.database_connection import db_connection_manager
            return db_connection_manager.get_connection(timeout=30)
        except ImportError:
            logger.error("Could not import centralized database connection manager")
            return None
    
    def _execute_sql_command(self, sql_command: str, use_pyodbc_fallback: bool = True) -> Tuple[bool, str]:
        """
        Execute SQL command using sqlcmd first, with pyodbc fallback.
        
        Args:
            sql_command: SQL command to execute
            use_pyodbc_fallback: Whether to try pyodbc if sqlcmd fails
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        # First try sqlcmd using temp file (more reliable for complex SQL)
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
                f.write(sql_command)
                temp_sql_file = f.name
            
            try:
                cmd = f'sqlcmd -S "{self.sql_server}" -i "{temp_sql_file}" -E'
                logger.debug(f"Executing SQL command via sqlcmd temp file: {sql_command[:100]}...")
                
                result = subprocess.run(
                    cmd, 
                    shell=True, 
                    capture_output=True, 
                    text=True, 
                    timeout=BACKUP_TIMEOUT
                )
                
                # Check for SQL errors in output (even if returncode is 0)
                output_text = result.stdout + (result.stderr or "")
                has_sql_errors = "Msg " in output_text and ("Level 15" in output_text or "Level 16" in output_text)
                
                if result.returncode == 0 and not has_sql_errors:
                    logger.debug(f"SQL Server output: {result.stdout.strip()}")
                    return True, result.stdout.strip()
                else:
                    if has_sql_errors:
                        sqlcmd_error = f"SQL Server error: {output_text.strip()}"
                    else:
                        sqlcmd_error = f"sqlcmd failed (exit code {result.returncode}): {result.stderr.strip()}"
                    
                    logger.debug(f"sqlcmd execution failed: {sqlcmd_error}")
                    
                    # If sqlcmd not found and fallback enabled, try pyodbc
                    if use_pyodbc_fallback and ("not recognized" in result.stderr or "not found" in result.stderr):
                        logger.info("sqlcmd not available, trying direct database connection...")
                        return self._execute_sql_via_pyodbc(sql_command)
                    else:
                        return False, sqlcmd_error
                        
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_sql_file)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            return False, f"SQL command timed out after {BACKUP_TIMEOUT} seconds"
        except Exception as e:
            sqlcmd_error = f"sqlcmd execution error: {str(e)}"
            logger.debug(sqlcmd_error)
            
            # Try pyodbc fallback if enabled
            if use_pyodbc_fallback:
                logger.info("sqlcmd failed with exception, trying direct database connection...")
                return self._execute_sql_via_pyodbc(sql_command)
            else:
                return False, sqlcmd_error
    
    def _simple_backup_fallback(self, backup_file_path: str, description: str) -> Tuple[bool, str]:
        """
        Simple backup fallback using the exact PyQt5 approach.
        This method replicates the working backup_database() function from PyQt5.
        """
        try:
            # Use the exact same approach as PyQt5
            def escape_sql_path(path):
                return path.replace("\\", "\\\\").replace("'", "''")
            
            # Create SQL command exactly like PyQt5
            backup_sql_path = escape_sql_path(backup_file_path)
            sql = f"BACKUP DATABASE [{self.database_name}] TO DISK = N'{backup_sql_path}' WITH FORMAT, INIT, NAME = 'Full Backup';"
            
            # Execute using sqlcmd with temp file approach (more reliable than -Q for complex paths)
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
                f.write(sql)
                temp_sql_file = f.name
            
            try:
                cmd = f'sqlcmd -S "{self.sql_server}" -i "{temp_sql_file}" -E'
                logger.debug(f"Executing SQL command via sqlcmd temp file: {sql}")
                logger.info(f"Executing simple backup command: sqlcmd (path length: {len(backup_file_path)})")
                
                result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
                
                # Log output for debugging
                if result.stdout:
                    logger.debug(f"SQL Server output: {result.stdout.strip()}")
                if result.stderr:
                    logger.debug(f"SQL Server stderr: {result.stderr.strip()}")
                
                # Check for SQL errors in output
                output_text = result.stdout + (result.stderr or "")
                if "Msg " in output_text and ("Level 15" in output_text or "Level 16" in output_text):
                    logger.error(f"SQL Server reported errors: {output_text}")
                    return False, f"SQL Server error: {output_text}"
                    
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_sql_file)
                except:
                    pass
            
            # Verify file was created
            if os.path.exists(backup_file_path):
                file_size = os.path.getsize(backup_file_path)
                logger.info(f"Simple backup successful: {format_file_size(file_size)}")
                return True, f"Backup created successfully using simple method ({format_file_size(file_size)})"
            else:
                return False, "Backup file was not created (simple method)"
                
        except subprocess.CalledProcessError as e:
            error_msg = f"Simple backup failed: {e.stderr if e.stderr else str(e)}"
            logger.warning(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Simple backup error: {str(e)}"
            logger.warning(error_msg)
            return False, error_msg
    
    def _execute_sql_via_pyodbc(self, sql_command: str) -> Tuple[bool, str]:
        """
        Execute SQL command using direct pyodbc connection.
        Used as fallback when sqlcmd is not available.
        """
        try:
            conn = self._get_database_connection()
            if not conn:
                return False, "Could not establish database connection for direct SQL execution"
            
            # Execute without transaction context for BACKUP/RESTORE commands
            cursor = conn.cursor()
            conn.autocommit = True  # Enable autocommit to avoid transaction context
            
            cursor.execute(sql_command)
            
            # For backup/restore commands, we need to wait for completion
            while cursor.nextset():
                pass
            
            cursor.close()
            conn.close()
            
            logger.debug("SQL command executed successfully via direct connection")
            return True, "SQL command executed successfully via direct database connection"
                
        except Exception as e:
            error_msg = f"Direct database connection failed: {str(e)}"
            logger.debug(error_msg)
            return False, error_msg
    
    def _estimate_backup_size(self) -> Optional[int]:
        """
        Estimate backup size based on database size (rough approximation)
        Returns None if estimation fails
        """
        try:
            # This is a rough estimation - actual backup size varies based on compression
            # and database content. In practice, backups are often 10-50% of database size.
            # For safety, we'll assume 30% of database size
            
            # You could implement actual database size querying here:
            # sql_command = f"SELECT SUM(size) * 8 * 1024 FROM sys.master_files WHERE database_id = DB_ID('{self.database_name}')"
            
            # For now, return None to skip size estimation if it fails
            return None
        except Exception as e:
            logger.debug(f"Could not estimate backup size: {e}")
            return None
    
    def create_backup(self, description: str) -> BackupResult:
        """
        Create database backup with comprehensive logging and monitoring
        
        Args:
            description: User-provided backup description
            
        Returns:
            BackupResult with operation status and details
        """
        # Pre-validation logging
        logger.debug(f"Backup request received - Description: '{description[:100]}{'...' if len(description) > 100 else ''}'")
        
        # Validate description
        if not description or not description.strip():
            logger.warning("Backup creation rejected - Empty description")
            return BackupResult(
                success=False,
                message="Backup description cannot be empty"
            )
        
        if len(description) > MAX_DESCRIPTION_LENGTH:
            logger.warning(f"Backup creation rejected - Description too long ({len(description)} > {MAX_DESCRIPTION_LENGTH})")
            return BackupResult(
                success=False,
                message=f"Description too long (max {MAX_DESCRIPTION_LENGTH} characters)"
            )
        
        # Generate backup filename
        start_time = datetime.now()
        backup_filename = generate_backup_filename(self.database_name, start_time)
        
        # Use single path approach like PyQt5 (simpler and more reliable)
        backup_file_path = os.path.join(self.backup_dir, backup_filename)
        metadata_file_path = backup_file_path.replace('.bak', '.json')
        
        # For SQL Server command, use the same path (SQL Server can access local directories)
        sql_backup_path = backup_file_path
        
        # Use comprehensive operation tracking
        with operation_tracker('backup_create', {
            'filename': backup_filename,
            'database': self.database_name,
            'server': self.sql_server,
            'description_length': len(description)
        }) as metrics:
            
            try:
                # Validate paths
                backup_file_path = validate_file_path(backup_file_path)
                metadata_file_path = validate_file_path(metadata_file_path)
                
                logger.debug(f"Backup paths validated - File: {backup_file_path}")
                
                with self._operation_lock:
                    # Check available disk space
                    try:
                        available_space = get_available_disk_space(self.backup_dir)
                        logger.info(f"Available disk space: {format_file_size(available_space)}")
                        
                        # Estimate backup size (rough estimate: 10-30% of data size)
                        estimated_size = self._estimate_backup_size()
                        if estimated_size and available_space < (estimated_size * 1.5):  # 50% buffer
                            raise BackupOperationError(
                                "Insufficient disk space for backup operation",
                                "LOW_DISK_SPACE"
                            )
                            
                        logger.debug(f"Estimated backup size: {format_file_size(estimated_size) if estimated_size else 'unknown'}")
                    except Exception as e:
                        logger.warning(f"WARNING: Could not check disk space: {e}")
                    
                    # Execute backup using streamlined sqlcmd command (compatible with Express)
                    success, message = self._simple_backup_fallback(sql_backup_path, description)
                    if not success:
                        raise BackupOperationError(
                            f"SQL Server backup failed: {message}",
                            "SQL_BACKUP_FAILED"
                        )
                    
                    logger.debug(f"Backup command executed successfully via simple sqlcmd: {message}")
                    
                    # Verify backup file was created and get size
                    if not os.path.exists(backup_file_path):
                        raise BackupOperationError("Backup file was not created by SQL Server", "FILE_NOT_CREATED")
                
                # Get file size and update metrics
                file_size = os.path.getsize(backup_file_path)
                metrics.file_size_bytes = file_size
                
                logger.info(f"Backup file created: {format_file_size(file_size)}")
                
                # Create metadata
                metadata = create_backup_metadata(
                    backup_filename, 
                    description.strip(),
                    self.database_name,
                    self.sql_server,
                    file_size
                )
                
                # Save metadata file
                with open(metadata_file_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                logger.debug(f"Metadata file created: {metadata_file_path}")
                
                # Record performance metrics
                performance_monitor.record_operation(metrics)
                
                # operation_tracker will log success automatically
                return BackupResult(
                    success=True,
                    message="Backup created successfully",
                    filename=backup_filename,
                    file_size=file_size,
                    duration_ms=metrics.duration_ms
                )
                
            except subprocess.TimeoutExpired as e:
                raise BackupOperationError(f"Backup operation timed out after {BACKUP_TIMEOUT} seconds", "TIMEOUT")
            
            except (BackupValidationError, BackupSecurityError) as e:
                raise BackupOperationError(str(e), "VALIDATION_ERROR")
                
            except Exception as e:
                # Log additional context for unexpected errors
                logger.debug(f"Backup operation context - File: {backup_file_path}, Description length: {len(description)}")
                raise BackupOperationError(f"Unexpected error during backup: {str(e)}", "UNEXPECTED_ERROR")
    
    def list_backups(self) -> List[BackupInfo]:
        """
        List all available backups with metadata
        
        Returns:
            List of BackupInfo objects
        """
        backups = []
        
        try:
            # Get all .bak files in backup directory
            backup_files = [f for f in os.listdir(self.backup_dir) if f.endswith('.bak')]
            
            for backup_file in backup_files:
                try:
                    backup_path = os.path.join(self.backup_dir, backup_file)
                    metadata_path = backup_path.replace('.bak', '.json')
                    
                    # Check if both backup and metadata files exist
                    backup_exists = os.path.exists(backup_path)
                    metadata_exists = os.path.exists(metadata_path)
                    is_valid = backup_exists and metadata_exists
                    
                    if metadata_exists:
                        # Load metadata
                        with open(metadata_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                        
                        # Get current file size (may have changed)
                        current_file_size = os.path.getsize(backup_path) if backup_exists else 0
                        
                        backup_info = BackupInfo(
                            filename=backup_file,
                            description=metadata.get('description', 'No description'),
                            timestamp=metadata.get('timestamp', ''),
                            created_date=metadata.get('created_date', ''),
                            file_size=current_file_size,
                            file_size_formatted=format_file_size(current_file_size),
                            is_valid=is_valid,
                            database_name=metadata.get('database_name'),
                            sql_server=metadata.get('sql_server')
                        )
                    else:
                        # Backup file without metadata (orphaned)
                        file_size = os.path.getsize(backup_path) if backup_exists else 0
                        file_stats = os.stat(backup_path) if backup_exists else None
                        created_time = datetime.fromtimestamp(file_stats.st_ctime) if file_stats else datetime.now()
                        
                        backup_info = BackupInfo(
                            filename=backup_file,
                            description="[Orphaned backup - no metadata]",
                            timestamp=created_time.strftime("%Y%m%d_%H%M%S"),
                            created_date=created_time.isoformat(),
                            file_size=file_size,
                            file_size_formatted=format_file_size(file_size),
                            is_valid=False
                        )
                    
                    backups.append(backup_info)
                    
                except Exception as e:
                    logger.warning(f"Error processing backup file {backup_file}: {e}")
                    # Continue processing other files
                    continue
            
            # Sort by timestamp (most recent first)
            backups.sort(key=lambda b: b.created_date, reverse=True)
            
            logger.info(f"Found {len(backups)} backup files")
            return backups
            
        except Exception as e:
            logger.error(f"Error listing backups: {e}")
            return []
    
    def get_backup_details(self, filename: str) -> Optional[BackupDetails]:
        """
        Get detailed information about a specific backup
        
        Args:
            filename: Name of backup file
            
        Returns:
            BackupDetails object or None if not found
        """
        try:
            # Validate filename
            filename = validate_filename(filename)
            
            backup_path = os.path.join(self.backup_dir, filename)
            metadata_path = backup_path.replace('.bak', '.json')
            
            # Validate paths
            backup_path = validate_file_path(backup_path)
            metadata_path = validate_file_path(metadata_path)
            
            if not os.path.exists(backup_path):
                logger.warning(f"Backup file not found: {filename}")
                return None
            
            if not os.path.exists(metadata_path):
                logger.warning(f"Metadata file not found for backup: {filename}")
                return None
            
            # Load metadata
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # Get current file information
            file_size = os.path.getsize(backup_path)
            
            backup_details = BackupDetails(
                filename=filename,
                description=metadata.get('description', 'No description'),
                timestamp=metadata.get('timestamp', ''),
                created_date=metadata.get('created_date', ''),
                file_size=file_size,
                file_size_formatted=format_file_size(file_size),
                database_name=metadata.get('database_name', 'Unknown'),
                sql_server=metadata.get('sql_server', 'Unknown'),
                metadata=metadata,
                is_valid=True
            )
            
            return backup_details
            
        except (BackupValidationError, BackupSecurityError) as e:
            logger.error(f"Validation error getting backup details: {e}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting backup details for {filename}: {e}")
            return None
    
    def restore_backup(self, filename: str) -> RestoreResult:
        """
        Restore database from backup file
        
        Args:
            filename: Name of backup file to restore from
            
        Returns:
            RestoreResult with operation status and details
        """
        start_time = datetime.now()
        warnings = []
        
        try:
            # Validate filename
            filename = validate_filename(filename)
            
            backup_path = os.path.join(self.backup_dir, filename)
            metadata_path = backup_path.replace('.bak', '.json')
            
            # Validate paths
            backup_path = validate_file_path(backup_path)
            metadata_path = validate_file_path(metadata_path)
            
            # Check if backup file exists
            if not os.path.exists(backup_path):
                return RestoreResult(
                    success=False,
                    message=f"Backup file not found: {filename}",
                    backup_filename=filename
                )
            
            # Load metadata for validation (if exists)
            metadata = None
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                except Exception as e:
                    warnings.append(f"Could not load metadata: {e}")
            else:
                warnings.append("No metadata file found - proceeding with caution")
            
            with self._operation_lock:
                # Execute SQL Server restore command
                escaped_path = escape_sql_path(backup_path)
                sql_command = SQL_RESTORE_TEMPLATE.format(
                    database=self.database_name,
                    backup_path=escaped_path
                )
                
                # Execute restore with sqlcmd/pyodbc fallback
                logger.info(f"Starting restore from: {filename}")
                logger.warning("Database will be temporarily unavailable during restore")
                
                success, message = self._execute_sql_command(sql_command)
                
                if not success:
                    error_msg = f"SQL Server restore failed: {message}"
                    logger.error(error_msg)
                    
                    # Try to return database to multi-user mode if possible
                    try:
                        recovery_cmd = f"ALTER DATABASE [{self.database_name}] SET MULTI_USER;"
                        self._execute_sql_command(recovery_cmd)
                    except Exception as recovery_error:
                        logger.error(f"Failed to recover database to multi-user mode: {recovery_error}")
                        warnings.append("Database may still be in single-user mode")
                    
                    return RestoreResult(
                        success=False,
                        message="Database restore failed",
                        backup_filename=filename,
                        error_details=error_msg,
                        warnings=warnings if warnings else None
                    )
                
                # Calculate duration
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                logger.info(f"Restore completed successfully from: {filename}")
                
                return RestoreResult(
                    success=True,
                    message="Database restored successfully",
                    backup_filename=filename,
                    duration_ms=duration_ms,
                    warnings=warnings if warnings else None
                )
                
        except subprocess.TimeoutExpired:
            logger.error(f"Restore operation timed out after {RESTORE_TIMEOUT} seconds")
            
            # Try to recover database state
            try:
                recovery_cmd = f"ALTER DATABASE [{self.database_name}] SET MULTI_USER;"
                self._execute_sql_command(recovery_cmd)
            except Exception:
                warnings.append("Database may be in an inconsistent state")
            
            return RestoreResult(
                success=False,
                message=f"Restore operation timed out after {RESTORE_TIMEOUT} seconds",
                backup_filename=filename,
                warnings=warnings if warnings else None
            )
            
        except (BackupValidationError, BackupSecurityError) as e:
            logger.error(f"Validation error during restore: {e}")
            return RestoreResult(
                success=False,
                message=str(e),
                backup_filename=filename
            )
            
        except Exception as e:
            logger.error(f"Unexpected error during restore: {e}")
            return RestoreResult(
                success=False,
                message="An unexpected error occurred during restore",
                backup_filename=filename,
                error_details=str(e),
                warnings=warnings if warnings else None
            )
    
    def restore_backup_from_path(self, file_path: str) -> RestoreResult:
        """
        Restore database from backup file using full file path (for .bck files without metadata)
        
        Args:
            file_path: Full path to backup file to restore from
            
        Returns:
            RestoreResult with operation status and details
        """
        start_time = datetime.now()
        warnings = []
        
        try:
            from pathlib import Path
            backup_path = Path(file_path).resolve()
            
            # Validate file exists and is readable
            if not backup_path.exists():
                raise BackupError(f"Backup file not found: {file_path}")
            
            if not backup_path.is_file():
                raise BackupError(f"Path is not a file: {file_path}")
            
            # Validate file extension
            if not backup_path.suffix.lower() in ['.bck', '.bak']:
                raise BackupError(f"Invalid backup file extension. Expected .bck or .bak, got {backup_path.suffix}")
            
            # Security check - ensure it's a reasonable backup file
            file_size = backup_path.stat().st_size
            if file_size < 1024:  # Less than 1KB is suspicious for a database backup
                warnings.append(f"Warning: Backup file is very small ({file_size} bytes)")
            
            backup_logger.info(f"Starting database restore from path: {backup_path}")
            
            with operation_tracker('restore_from_path', {'file_path': str(backup_path)}) as metrics:
                # Execute restore operation
                with self.get_sql_connection() as conn:
                    if conn is None:
                        raise BackupError("Unable to connect to database for restore operation")
                    
                    try:
                        cursor = conn.cursor()
                        
                        # Use the absolute path for the SQL command
                        sql_restore = f"""
                        USE master;
                        ALTER DATABASE [{self.database_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
                        RESTORE DATABASE [{self.database_name}] 
                        FROM DISK = '{backup_path}'
                        WITH REPLACE;
                        ALTER DATABASE [{self.database_name}] SET MULTI_USER;
                        """
                        
                        backup_logger.info("Executing restore SQL command...")
                        
                        # Execute each statement separately
                        for statement in sql_restore.split(';'):
                            statement = statement.strip()
                            if statement:
                                cursor.execute(statement)
                        
                        backup_logger.info("Database restore completed successfully")
                        
                        # Update metrics
                        metrics.file_size_bytes = file_size
                        metrics.success = True
                        
                    except Exception as sql_error:
                        backup_logger.error(f"SQL restore operation failed: {sql_error}")
                        # Try to restore multi-user mode if possible
                        try:
                            cursor.execute(f"ALTER DATABASE [{self.database_name}] SET MULTI_USER;")
                        except:
                            pass
                        raise BackupError(f"Database restore failed: {sql_error}")
                    
                    finally:
                        try:
                            cursor.close()
                        except:
                            pass
            
            # Create successful result
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return RestoreResult(
                success=True,
                backup_filename=backup_path.name,
                file_path=str(backup_path),
                execution_time_seconds=execution_time,
                database_name=self.database_name,
                sql_server=self.server_name,
                warnings=warnings if warnings else None
            )
            
        except Exception as e:
            backup_logger.error(f"Restore from path failed: {e}")
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return RestoreResult(
                success=False,
                backup_filename=Path(file_path).name if file_path else 'unknown',
                file_path=file_path,
                execution_time_seconds=execution_time,
                error_details=str(e),
                warnings=warnings if warnings else None
            )

    def delete_backup(self, filename: str) -> Dict[str, Any]:
        """
        Delete backup file and associated metadata
        
        Args:
            filename: Name of backup file to delete
            
        Returns:
            Dictionary with operation status and details
        """
        try:
            # Validate filename
            filename = validate_filename(filename)
            
            backup_path = os.path.join(self.backup_dir, filename)
            metadata_path = backup_path.replace('.bak', '.json')
            
            # Validate paths
            backup_path = validate_file_path(backup_path)
            metadata_path = validate_file_path(metadata_path)
            
            files_deleted = []
            errors = []
            
            # Delete backup file
            if os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                    files_deleted.append(filename)
                    logger.info(f"Deleted backup file: {filename}")
                except Exception as e:
                    error_msg = f"Failed to delete backup file: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            else:
                logger.warning(f"Backup file not found: {filename}")
            
            # Delete metadata file
            metadata_filename = filename.replace('.bak', '.json')
            if os.path.exists(metadata_path):
                try:
                    os.remove(metadata_path)
                    files_deleted.append(metadata_filename)
                    logger.info(f"Deleted metadata file: {metadata_filename}")
                except Exception as e:
                    error_msg = f"Failed to delete metadata file: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            else:
                logger.warning(f"Metadata file not found: {metadata_filename}")
            
            # Determine overall success
            if files_deleted and not errors:
                return {
                    "success": True,
                    "message": f"Backup {filename} deleted successfully",
                    "files_deleted": files_deleted
                }
            elif files_deleted and errors:
                return {
                    "success": True,
                    "message": f"Backup partially deleted with some errors",
                    "files_deleted": files_deleted,
                    "errors": errors
                }
            elif not files_deleted and not errors:
                return {
                    "success": False,
                    "message": f"No files found to delete for backup: {filename}"
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to delete backup: {filename}",
                    "errors": errors
                }
                
        except (BackupValidationError, BackupSecurityError) as e:
            logger.error(f"Validation error during delete: {e}")
            return {
                "success": False,
                "message": str(e)
            }
            
        except Exception as e:
            logger.error(f"Unexpected error during delete: {e}")
            return {
                "success": False,
                "message": "An unexpected error occurred during delete",
                "error_details": str(e)
            }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics for backup operations
        
        Returns:
            Dictionary containing performance statistics and health information
        """
        with operation_tracker('performance_metrics_collection', {
            'request_type': 'performance_summary'
        }) as metrics:
            
            base_metrics = performance_monitor.get_performance_summary()
            
            # Add backup-specific health information
            health_info = {
                'backup_directory_exists': os.path.exists(self.backup_dir),
                'backup_directory_writable': os.access(self.backup_dir, os.W_OK),
                'available_disk_space_mb': round(get_available_disk_space(self.backup_dir) / (1024*1024), 2),
                'database_name': self.database_name,
                'sql_server': self.sql_server,
                'service_initialized': True
            }
            
            # Get backup count
            try:
                backup_count = len(self.list_backups())
            except Exception:
                backup_count = -1  # Error getting count
            
            # Combine all metrics
            comprehensive_metrics = {
                **base_metrics,
                'health_info': health_info,
                'backup_count': backup_count,
                'timestamp': datetime.now().isoformat(),
                'service_version': '1.0.0',
                'feature_status': {
                    'backup_creation': True,
                    'backup_restoration': True,
                    'backup_deletion': True,
                    'metadata_management': True,
                    'performance_monitoring': True,
                    'comprehensive_logging': True
                }
            }
            
            logger.debug(f"Performance metrics collected: {len(comprehensive_metrics)} metrics")
            return comprehensive_metrics
    


# Global service instance for dependency injection
_backup_service_instance = None
_service_lock = threading.Lock()


def get_backup_service() -> BackupService:
    """
    Get singleton backup service instance
    
    Returns:
        BackupService instance
    """
    global _backup_service_instance
    
    if _backup_service_instance is None:
        with _service_lock:
            if _backup_service_instance is None:
                _backup_service_instance = BackupService()
                logger.info("BackupService singleton instance created")
    
    return _backup_service_instance


