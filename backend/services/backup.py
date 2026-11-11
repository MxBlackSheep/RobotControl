"""
RobotControl Database Backup/Restore Service

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
import json
import logging
import subprocess
import threading
import time
import shutil
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

from backend.utils.data_paths import get_path_manager, get_backups_path

logger = logging.getLogger(__name__)

from backend.config import settings
configured_backup_path = Path(settings.LOCAL_BACKUP_PATH)
BACKUP_DIR = str((get_path_manager().base_path / configured_backup_path).resolve())

# Operation timeouts (in seconds)
BACKUP_TIMEOUT = 300  # 5 minutes
RESTORE_TIMEOUT = 600  # 10 minutes

# File validation patterns
ALLOWED_EXTENSIONS = {'.bak'}
MAX_DESCRIPTION_LENGTH = 1000
MAX_FILENAME_LENGTH = 255

# SQL Commands
SQL_RESTORE_TEMPLATE = """
USE master;
ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; 
RESTORE DATABASE [{database}] 
FROM DISK = N'{backup_path}' 
WITH REPLACE; 
ALTER DATABASE [{database}] SET MULTI_USER;
"""

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
    duration_ms: Optional[int] = None
    warnings: Optional[List[str]] = None
    error_details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return asdict(self)


class SqlCommandExecutor:
    """Helper responsible for running SQL commands against the target server."""

    def __init__(self, server: str, database: str) -> None:
        self.server = server
        self.database = database

    def execute(
        self,
        sql_command: str,
        *,
        timeout: int = BACKUP_TIMEOUT,
    ) -> Tuple[bool, str]:
        """Execute the provided SQL command using sqlcmd."""
        temp_sql_file: Optional[str] = None
        try:
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as handle:
                handle.write(sql_command)
                temp_sql_file = handle.name

            try:
                command = f'sqlcmd -S "{self.server}" -i "{temp_sql_file}" -E'
                logger.debug("Executing SQL via sqlcmd: %s...", sql_command[:100])
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                output_text = (result.stdout or "") + (result.stderr or "")
                has_sql_errors = "Msg " in output_text and (
                    "Level 15" in output_text or "Level 16" in output_text
                )

                if result.returncode == 0 and not has_sql_errors:
                    if result.stdout:
                        logger.debug("SQL Server output: %s", result.stdout.strip())
                    return True, result.stdout.strip()

                if has_sql_errors:
                    sqlcmd_error = f"SQL Server error: {output_text.strip()}"
                else:
                    sqlcmd_error = (
                        f"sqlcmd failed (exit code {result.returncode}): {result.stderr.strip()}"
                    )

                logger.debug("sqlcmd execution failed: %s", sqlcmd_error)
                return False, sqlcmd_error
            finally:
                if temp_sql_file:
                    try:
                        os.unlink(temp_sql_file)
                    except OSError:
                        pass
        except subprocess.TimeoutExpired:
            return False, f"SQL command timed out after {timeout} seconds"
        except Exception as exc:  # pragma: no cover - defensive
            sqlcmd_error = f"sqlcmd execution error: {exc}"
            logger.debug(sqlcmd_error)
            return False, sqlcmd_error

    def perform_backup(self, backup_file_path: str) -> Tuple[bool, str]:
        """Execute a BACKUP DATABASE command using sqlcmd."""
        sql = (
            f"BACKUP DATABASE [{self.database}] "
            f"TO DISK = N'{escape_sql_path(backup_file_path)}' "
            "WITH FORMAT, INIT, NAME = 'Full Backup';"
        )
        success, message = self.execute(sql, timeout=BACKUP_TIMEOUT)
        if not success:
            return False, message
        try:
            if os.path.exists(backup_file_path):
                file_size = os.path.getsize(backup_file_path)
                return True, f"Backup created successfully ({format_file_size(file_size)})"
            return False, "Backup file was not created"
        except OSError as exc:
            return False, f"Could not verify backup file: {exc}"


def metadata_path(backup_path):
    return Path(backup_path).with_suffix(".json")


def read_metadata(backup_path):
    path = metadata_path(backup_path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class BackupValidationError(Exception):
    """Exception for backup security violations"""
    pass


class BackupError(Exception):
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
        BackupValidationError: If filename poses security risk
    """
    if not filename:
        raise BackupValidationError("Filename cannot be empty")
    
    if len(filename) > MAX_FILENAME_LENGTH:
        raise BackupValidationError(f"Filename too long (max {MAX_FILENAME_LENGTH} characters)")
    
    # Security check: prevent directory traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        raise BackupValidationError("Invalid characters in filename")
    
    # Check for allowed extensions
    file_ext = Path(filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise BackupValidationError(f"Invalid file extension. Allowed: {ALLOWED_EXTENSIONS}")
    
    # Additional security validation
    forbidden_chars = ['<', '>', ':', '"', '|', '?', '*']
    if any(char in filename for char in forbidden_chars):
        raise BackupValidationError("Filename contains forbidden characters")
    
    return filename


def validate_file_path(file_path: str) -> str:
    """
    Validate file path is within backup directory (supports network paths)
    
    Args:
        file_path: File path to validate
        
    Returns:
        Validated path
        
    Raises:
        BackupValidationError: If path is outside backup directory
    """
    try:
        # Handle network paths and local paths
        if BACKUP_DIR.startswith(r"\\"):
            # Network path - use direct string comparison
            backup_dir_norm = os.path.normpath(BACKUP_DIR).lower()
            file_path_norm = os.path.normpath(file_path).lower()
            
            if not file_path_norm.startswith(backup_dir_norm):
                raise BackupValidationError("File path outside backup directory")
            
            return file_path
        else:
            # Local path - use absolute path resolution
            abs_path = os.path.abspath(file_path)
            backup_dir_abs = os.path.abspath(BACKUP_DIR)
            
            if not abs_path.startswith(backup_dir_abs):
                raise BackupValidationError("File path outside backup directory")
            
            return abs_path
    
    except Exception as e:
        logger.error(f"Path validation error: {e}")
        raise BackupValidationError(f"Invalid file path: {e}")


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


class BackupService:
    """
    Database backup and restore service
    
    Provides secure backup operations with comprehensive validation and error handling.
    Maintains isolation from other application components to prevent cascading failures.
    """
    
    def __init__(self):
        """Initialize backup service"""
        self.backup_dir = BACKUP_DIR
        self.sql_server = settings.DB_CONFIG_PRIMARY["server"]
        self.database_name = settings.DB_CONFIG_PRIMARY["database"]
        self._operation_lock = threading.Lock()
        self._sql_executor = SqlCommandExecutor(self.sql_server, self.database_name)
        
        # Ensure backup directory exists (skip if network path not accessible locally)  
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create backup directory in service init (network path expected): {e}")
        
        logger.info(f"BackupService initialized - Database: {self.database_name}, Server: {self.sql_server}")
    
    def _recover_database_connections(self, timeout_seconds: int = 30) -> Optional[str]:
        deadline = time.monotonic() + timeout_seconds
        last_error = None
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                success, last_error = self._sql_executor.execute(
                    f"USE [{self.database_name.replace(']', ']]')}]; SELECT 1;", timeout=min(5, remaining))
                if success:
                    return None
            except Exception as exc:
                last_error = str(exc)
            time.sleep(min(2, max(0, deadline - time.monotonic())))
        return (f"Database connectivity check after restore failed: {last_error}" if last_error
                else "Database connectivity check after restore timed out")

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
        
        backup_file_path = None

        start_time = time.perf_counter()
        logger.info("Starting backup creation for %s", self.database_name)
        try:
            with self._operation_lock:
                # Chosen under the lock, when the backup starts: overlapping creates must not share a name.
                backup_filename = self._unused_backup_filename()
                backup_file_path = validate_file_path(os.path.join(self.backup_dir, backup_filename))
                validate_file_path(str(metadata_path(backup_file_path)))
                logger.debug(f"Backup paths validated - File: {backup_file_path}")

                # Check available disk space
                try:
                    available_space = shutil.disk_usage(self.backup_dir).free
                    logger.info(f"Available disk space: {format_file_size(available_space)}")
                    
                except Exception as e:
                    logger.warning(f"WARNING: Could not check disk space: {e}")

                # SQL Server writes to the same path RobotControl reads, so it must
                # run on this machine or see BACKUP_DIR under the same name.
                success, message = self._sql_executor.perform_backup(backup_file_path)
                if not success:
                    raise BackupError(f"SQL Server backup failed: {message}")

                logger.debug("Backup command executed successfully via sqlcmd: %s", message)

                # Verify backup file was created and get size
                if not os.path.exists(backup_file_path):
                    raise BackupError("Backup file was not created by SQL Server")

                # Get the completed backup size
                file_size = os.path.getsize(backup_file_path)

                logger.info("Backup file created: %s (%s)", backup_filename, format_file_size(file_size))

                # Save metadata alongside the backup, still under the lock so a delete cannot
                # run between the .bak and its .json.
                self._save_metadata(
                    backup_filename,
                    description.strip(),
                    self.database_name,
                    self.sql_server,
                    file_size
                )

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info("Backup created in %sms", duration_ms)
            return BackupResult(
                success=True,
                message="Backup created successfully",
                filename=backup_filename,
                file_size=file_size,
                duration_ms=duration_ms
            )

        except BackupValidationError as e:
            logger.exception("Backup creation failed after %sms", int((time.perf_counter() - start_time) * 1000))
            raise BackupError(str(e))

        except BackupError:
            logger.exception("Backup creation failed")
            raise

        except Exception as e:
            logger.exception("Backup creation failed after %sms", int((time.perf_counter() - start_time) * 1000))
            # Log additional context for unexpected errors
            logger.debug(f"Backup operation context - File: {backup_file_path}, Description length: {len(description)}")
            raise BackupError(f"Unexpected error during backup: {str(e)}")

    def _unused_backup_filename(self) -> str:
        """Call under _operation_lock. Names are per second and BACKUP ... WITH INIT overwrites,
        so a name already on disk gets a _2, _3, ... suffix instead."""
        base = generate_backup_filename(self.database_name)
        name, attempt = base, 1
        while any(os.path.exists(os.path.join(self.backup_dir, candidate))
                  for candidate in (name, str(Path(name).with_suffix(".json")))):
            attempt += 1
            name = base.replace('.bak', f'_{attempt}.bak')
        return name

    def _save_metadata(self, filename, description, database_name, sql_server, file_size):
        timestamp = datetime.now()
        metadata = dict(file=filename, description=description, timestamp=timestamp.strftime("%Y%m%d_%H%M%S"),
            created_date=timestamp.isoformat(), database_name=database_name, sql_server=sql_server,
            file_size=file_size, file_size_formatted=format_file_size(file_size),
            created_by="RobotControl Backup Service", version="1.0")
        path = metadata_path(Path(self.backup_dir) / filename)
        path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug("Metadata file created: %s", path)

    def list_backups(self) -> List[BackupInfo]:
        backups = []
        try:
            for path in Path(self.backup_dir).glob("*.bak"):
                try:
                    metadata = read_metadata(path)
                    stat = path.stat()
                    created = datetime.fromtimestamp(stat.st_ctime)
                    values = metadata or dict(description="[Orphaned backup - no metadata]",
                        timestamp=created.strftime("%Y%m%d_%H%M%S"), created_date=created.isoformat())
                    backups.append(BackupInfo(filename=path.name, description=values.get("description", "No description"),
                        timestamp=values.get("timestamp", ""), created_date=values.get("created_date", ""),
                        file_size=stat.st_size, file_size_formatted=format_file_size(stat.st_size),
                        is_valid=metadata is not None, database_name=values.get("database_name"), sql_server=values.get("sql_server")))
                except Exception as exc:
                    logger.warning("Error processing backup file %s: %s", path.name, exc)
            backups.sort(key=lambda item: item.created_date, reverse=True)
            logger.info("Found %s backup files", len(backups))
        except Exception as exc:
            logger.error("Error listing backups: %s", exc)
        return backups

    def _restore_database(self, backup_path: str, warnings: List[str]) -> Tuple[bool, str]:
        """Run under the caller's operation lock; recover MULTI_USER on SQL failure or timeout."""
        command = SQL_RESTORE_TEMPLATE.format(
            database=self.database_name, backup_path=escape_sql_path(backup_path)
        )
        success, message = self._sql_executor.execute(command, timeout=RESTORE_TIMEOUT)
        if not success:
            logger.error("SQL Server restore of %s failed: %s", backup_path, message)
            try:
                recovered, detail = self._sql_executor.execute(
                    f"USE master; ALTER DATABASE [{self.database_name}] SET MULTI_USER;"
                )
            except Exception as exc:
                recovered, detail = False, str(exc)
            if not recovered:
                recovery_warning = f"Database may still be in single-user mode: {detail}"
                logger.error(recovery_warning)
                warnings.append(recovery_warning)
        return success, message

    def restore_backup(self, filename: str) -> RestoreResult:
        """Resolve a managed backup before entering the shared restore operation."""
        try:
            filename = validate_filename(filename)
            path = validate_file_path(os.path.join(self.backup_dir, filename))
            sidecar = validate_file_path(str(Path(path).with_suffix('.json')))
            if not os.path.exists(path):
                return RestoreResult(False, filename, f"Backup file not found: {filename}")
            warnings = [] if os.path.exists(sidecar) else ["No metadata file found - proceeding with caution"]
            return self.restore_backup_from_path(path, warnings)
        except BackupValidationError as exc:
            logger.error("Validation error during restore: %s", exc)
            return RestoreResult(False, filename, str(exc))
        except Exception as exc:
            logger.error("Unexpected error during restore: %s", exc)
            return RestoreResult(False, filename, "An unexpected error occurred during restore", error_details=str(exc))

    def restore_backup_from_path(self, file_path: str, warnings=None) -> RestoreResult:
        """
        Restore database from backup file using full file path (for .bck files without metadata)
        
        Args:
            file_path: Full path to backup file to restore from
            
        Returns:
            RestoreResult with operation status and details
        """
        start_time = datetime.now()
        warnings = list(warnings or [])
        
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
            
            logger.info(f"Starting database restore from path: {backup_path}")
            
            with self._operation_lock:
                success, message = self._restore_database(str(backup_path), warnings)
                if not success:
                    raise BackupError(f"Database restore failed: {message}")

                logger.info("Database restore completed in %sms", int((datetime.now() - start_time).total_seconds() * 1000))

                recovery_warning = self._recover_database_connections()
                if recovery_warning:
                    warnings.append(recovery_warning)
            
            return RestoreResult(
                success=True,
                message="Database restored successfully",
                backup_filename=backup_path.name,
                warnings=warnings if warnings else None
            )
            
        except Exception as e:
            logger.exception("Restore from path failed after %sms: %s", int((datetime.now() - start_time).total_seconds() * 1000), e)
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return RestoreResult(
                success=False,
                message="Database restore failed",
                backup_filename=Path(file_path).name if file_path else 'unknown',
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
            
            backup_path = validate_file_path(os.path.join(self.backup_dir, filename))
            metadata = validate_file_path(str(metadata_path(backup_path)))
            files_deleted, errors = [], []
            with self._operation_lock:
                for label, path in (("backup", backup_path), ("metadata", metadata)):
                    name = Path(path).name
                    if not os.path.exists(path):
                        logger.warning("%s file not found: %s", label.capitalize(), name)
                        continue
                    try:
                        os.remove(path)
                        files_deleted.append(name)
                        logger.info("Deleted %s file: %s", label, name)
                    except Exception as exc:
                        error = f"Failed to delete {label} file: {exc}"
                        errors.append(error)
                        logger.error(error)

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
                
        except BackupValidationError as e:
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
    
    with _service_lock:
        if _backup_service_instance is None:
            _backup_service_instance = BackupService()
            logger.info("BackupService singleton instance created")
    return _backup_service_instance
