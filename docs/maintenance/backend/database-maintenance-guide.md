# Database Maintenance Guide

This guide explains how the database utilities (backup, restore, metadata management, and basic data viewing) fit together. It targets maintainers who prefer explicit instructions and may not remember all the moving parts.

---

## 1. High-Level Architecture

- `backend/services/backup.py`  
  Contains `BackupService` plus two helpers: `SqlCommandExecutor` (runs sqlcmd commands) and `BackupMetadataStore` (writes/reads `.json` metadata). This is the core logic behind backup/restore features.

- `backend/services/database.py`  
  Houses utility functions for running ad-hoc SQL queries and listing tables (used by the “Database” admin page). It sits in front of the shared database connection manager.

- `backend/api/backup.py`  
  FastAPI routes for listing backups, creating/deleting them, restoring, and fetching health metrics. Calls into `BackupService` and emits audit logs.

- `backend/api/database.py`  
  Exposes endpoints for listing important tables, running queries, and checking database health. Uses `backend/services/database.py` helpers.

- `frontend/src/pages/BackupPage.tsx` & related components (`DatabaseRestore`, `BackupListComponent`, `BackupActions`)  
  UI surfaces for the backup workflow. Show progress to operators, trigger REST API calls, and display maintenance mode warnings.

- `frontend/src/pages/DatabasePage.tsx` & related components (`DatabaseTable`, `StoredProcedures`, etc.)  
  Read-only view into schema/table data for quick inspection; calls the database API route.

**Rule of thumb:** All backup and restore operations should flow through `BackupService`. Do not call `SqlCommandExecutor` directly from API routes or new modules; let the service manage locking, validation, and logging.

---

## 2. Backup Lifecycle Cheat Sheet

1. **Request arrives** (`POST /api/backup/create`).  
   The API validates the description, emits an audit log, and calls `BackupService.create_backup`.

2. **Path validation** (`BackupService.create_backup`).  
   Generates a filename, ensures the backup directory and metadata path live under `BACKUP_DIR`, and checks available disk space.

3. **SQL command execution** (`SqlCommandExecutor.perform_backup`).  
   Writes a temp `.sql` file containing `BACKUP DATABASE ...`, runs it via `sqlcmd -S server -i temp.sql`, and deletes the temp file. If `sqlcmd` fails, the operation aborts (there is no longer a pyodbc fallback).

4. **File verification & metadata** (`BackupService`).  
   Confirm the `.bak` file exists, record its size, and save a companion `.json` file via `BackupMetadataStore.save` (stores description, timestamp, server, size, etc.).

5. **Response** (`BackupResult`).  
   The service returns success, file size, and duration. The API wraps it in the standard response format. The frontend displays a success toast and updates the list.

6. **Listing backups** (`GET /api/backup/list`).  
   `BackupMetadataStore.list_backups` walks the `BACKUP_DIR`, pairs `.bak` files with `.json` metadata, and returns `BackupInfo` objects (or marks orphaned files as invalid).

7. **Restore** (`POST /api/backup/restore`).  
   Validates the filename, builds a multi-statement `RESTORE` script, and passes it to `SqlCommandExecutor.execute`. On failure it attempts to set the database back to multi-user mode before returning an error.

8. **Delete** (`DELETE /api/backup/{filename}`).
   Removes the `.bak` file, asks `BackupMetadataStore.delete_metadata_file` to remove the `.json`, and reports which files were deleted.

9. **Health metrics** (`GET /api/backup/health`).  
   Combines performance stats, directory checks, and disk space info so the frontend can display a health summary.

---

## 3. Key Data Structures & Configuration

- `BACKUP_DIR`, `SQL_BACKUP_DIR` (`backend/services/backup.py`)  
  Paths resolved from `LOCAL_BACKUP_PATH` / `SQL_BACKUP_PATH`. `BACKUP_DIR` is where `.bak` and `.json` files live on the host. `SQL_BACKUP_DIR` is the path SQL Server writes to (often the same as `BACKUP_DIR`, but may be a network share). Make sure SQL Server has permission to write to this location.

- `BackupInfo`, `BackupDetails`, `BackupResult`, `RestoreResult` (`backend/services/backup.py`)  
  Dataclasses used to serialise backup metadata/results. Frontend types map closely to these shapes.

- `SqlCommandExecutor`  
  Provides `perform_backup` and `execute(sql, timeout=...)`. It always uses `sqlcmd`; if `sqlcmd` is missing or the command fails, the calling service handles the error. There is no pyodbc fallback anymore.

- `BackupMetadataStore`  
  Handles writing `.json`, listing backups, loading details, and removing metadata files. Keeps metadata logic out of the core service.

- `get_path_manager()` / `settings.LOCAL_BACKUP_PATH` (`backend/config.py`)  
  Determine where backups live. Update these paths when deploying to new environments.

- Frontend components (`BackupListComponent`, `BackupActions`, `DatabaseRestore`)  
  Rely on the API responses above and surface success/error messages to operators. `DatabaseRestore` also triggers maintenance mode banners via `MaintenanceManager`.

---

## 4. How to Add or Modify Functionality

### 4.1 Add Metadata Fields
1. Update `create_backup_metadata` in `backup.py` to include the new field.
2. Adjust `BackupMetadataStore.save` so the field is persisted; update `BackupInfo`/`BackupDetails` dataclasses with the new attribute.
3. Thread the field through API responses (`backend/api/backup.py`) and frontend types/components (`frontend/src/types/backup.ts`, `BackupListComponent`, etc.).
4. Document the change and test listing/backups to ensure the JSON round-trip works.

### 4.2 Support Differential or Compressed Backups
1. Add configuration options to `settings` (e.g., `LOCAL_BACKUP_TYPE`).
2. Update `SqlCommandExecutor.perform_backup` to build the correct `BACKUP DATABASE` command (WITH DIFFERENTIAL, WITH COMPRESSION, etc.). Keep a single code path—do not fork the function.
3. Include the chosen mode in metadata so operators can tell what kind of backup was produced.
4. Ensure restore scripts (`RESTORE ... WITH REPLACE`) still work for the new backup type.

### 4.3 Modify Restore Validation
1. Update `BackupService.restore_backup` to include your new checks (e.g., verify database compatibility level from metadata).
2. If you need extra details, load them via `BackupMetadataStore.load_details` before running the restore.
3. Surface warnings in the `warnings` list so the frontend can display them.
4. Test both success and failure paths—always confirm the database returns to multi-user mode when errors occur.

---

## 5. Common Maintenance Tasks

| Task | Where | Tips |
|------|-------|------|
| Create backup programmatically | `BackupService.create_backup("Description")` | Always provide a human-readable description; it shows up in the UI. |
| List backups | `BackupMetadataStore.list_backups()` or `BackupService.list_backups()` | Returns newest-first. Invalid entries are marked so the UI can warn operators. |
| Restore backup | `BackupService.restore_backup(filename)` | Takes exclusive control of the database; warn users first. |
| Delete backup | `BackupService.delete_backup(filename)` | Removes `.bak` and `.json`; returns partial success if one file couldn’t be deleted. |
| Health check | `BackupService.get_performance_metrics()` | Includes disk space, backup count, and average durations—feed this into monitoring dashboards. |
| Run ad-hoc query | `backend/services/database.py` helpers (via `/api/database/query`) | UI is read-only; hammering production with heavy queries is discouraged. |

---

## 6. Extension Points & Gotchas

- **sqlcmd required**: The service no longer falls back to pyodbc. Ensure `sqlcmd` is installed and in PATH on the machine running RobotControl.
- **Permissions**: SQL Server must have permission to write to `SQL_BACKUP_DIR`. Likewise, the RobotControl process must have permission to delete files there.
- **Disk space**: Backups can be large. `create_backup` warns when disk checks fail but does not prevent the OS from running out of space. Monitor `get_performance_metrics()["health_info"]["available_disk_space_mb"]`.
- **Metadata consistency**: Always use `BackupMetadataStore` to manipulate metadata. Writing JSON manually bypasses validation and breaks the UI.
- **Maintenance mode**: The frontend sets a maintenance window when a restore starts. Keep this behaviour; cutting the restore short can leave the database in single-user mode.
- **Network paths**: UNC paths (e.g., `\\server\share`) are supported, but validation uses string comparisons. Ensure the paths are normalised and accessible.
- **Query API**: `/api/database/query` is powerful—enforce authentication and avoid exposing it in insecure environments.

---

## 7. Quick Reference

| Function / Method | Purpose | Notes |
|-------------------|---------|-------|
| `BackupService.create_backup(description)` | Create `.bak` + `.json` | Validates description, disk space, and logs duration. |
| `BackupService.list_backups()` | Get `BackupInfo` list | Delegates to metadata store; output is sorted newest-first. |
| `BackupService.get_backup_details(filename)` | Read metadata | Returns `BackupDetails` or `None` if files missing. |
| `BackupService.restore_backup(filename)` | Restore from `.bak` | Executes multi-step SQL script, handles warnings. |
| `BackupService.restore_backup_from_path(path)` | Restore from arbitrary file | Use for manual `.bck` files; perform validation yourself. |
| `BackupService.delete_backup(filename)` | Remove files | Returns dict with `files_deleted` and optional errors. |
| `SqlCommandExecutor.perform_backup(path)` | Run `BACKUP DATABASE` | Wraps sqlcmd call; returns `(success, message)`. |
| `SqlCommandExecutor.execute(sql, timeout)` | Run arbitrary SQL via sqlcmd | Used for restore scripts and recovery commands. |
| `BackupMetadataStore.save(...)` | Persist metadata | Always call this after a successful backup. |
| `BackupMetadataStore.delete_metadata_file(filename)` | Remove `.json` file | Returns `(deleted, name, error_message_or_None)`. |
| `database_service.execute_query(sql)` | Run read-only query | Leveraged by `/api/database/query`; use for dashboards. |

---

## 8. When Something Goes Wrong

1. **`sqlcmd` not found**  
   - Ensure `sqlcmd` is installed (usually via Microsoft ODBC driver package).  
   - Check PATH and service account permissions.  
   - The error message will mention “sqlcmd failed … not recognized”. Install the tool and rerun.

2. **Backup file missing after success**  
   - Confirm `SQL_BACKUP_DIR` points to a writable location.  
   - Check antivirus or security software (they can quarantine `.bak` files).  
   - Make sure UNC paths are accessible under the service account.

3. **Restore hangs or times out**  
   - The script forces SINGLE_USER mode. If it times out, verify no other processes are connected.  
   - After failure, an additional `ALTER DATABASE ... SET MULTI_USER` is attempted; if that fails, manually run it via sqlcmd.

4. **Metadata mismatch**  
   - If a `.json` is missing, the UI shows “[Orphaned backup]”. Either delete the orphan or recreate the metadata file using `BackupMetadataStore.save`.  
   - When copying backup files manually, copy the metadata too.

5. **Disk exhaustion**  
   - Set up external monitoring for `available_disk_space_mb`.  
   - Consider offloading old backups to long-term storage (e.g., another share) on a schedule.  
   - Remember that restores may require additional space for transaction logs.

6. **Ad-hoc query errors**  
   - The query API is intentionally minimalist. Avoid running multi-statement scripts; stick to `SELECT`, `EXEC` read-only procedures.  
   - Enforce role-based access to these endpoints; never expose them to unauthenticated users.

---

## 9. Adding New Modules or Integrations

1. **Keep backup logic inside `BackupService`**. If you need new operations (compression, cloud upload), add helper classes but expose them through `BackupService` so locking/logging stays centralised.
2. **Document config changes**. Whenever you adjust `LOCAL_BACKUP_PATH` or introduce new environment variables, update `.env.example` and the README.
3. **Re-use helpers**. For any new backup-related features (e.g., scheduled backups), call `BackupService.create_backup` instead of implementing raw sqlcmd calls.
4. **Test end-to-end**. After changing backup/restore logic, run: create backup → restore backup → list backups → delete backup. Confirm metadata and UI all work.
5. **Mind security**. Backups contain sensitive data. Ensure file permissions and network shares are locked down, and never write backups to public locations.

Follow this guide whenever you need to touch the database utilities. Being cautious about sqlcmd usage, metadata consistency, and permissions will keep the backup/restore pipeline predictable and safe.
