# Database Maintenance Guide

## Package downloads and configuration (2026-09-28)

Local administrators can GET `/api/database/tools/packages/{id}/export`. New
installations retain the reviewed ZIP and verify its checksum on download; older
installations reconstruct the flat authored files. Exports contain neither local
source assignments nor app output/cache folders. Authored code may itself contain
secrets. Draft owners can GET `/drafts/{id}/editing-files` for original Python,
configured handler, input definitions and editing instructions; it is not an
installable package and downloading does not execute Python.

`LabSettings.change_source` rejects changes/removal of active or pending scheduling
sources. Create a separate profile and use the reviewed scheduling change instead.
See the scheduling maintenance guide for restart and recovery constraints.

## Configurable Database workspace (2026-09-28)

`workspace_database.py` uses an explicit snapshot from `report_sources.py` for
viewers. `/api/database/tables` (including count/columns) and `/stored-procedures`
require authenticated requests. `ReportSources.viewer()` resolves the admin's
`viewer_source` setting; a supplied stale/different `source_id` returns 409 and
cannot override it. On upgrade the first available reader is persisted once,
matching the former fresh-browser default. With none configured, return a setup error, not
fallback to the robot writer. Schema-qualified metadata names are validated against
SQL Server metadata; views and duplicate names in different schemas are supported.
The native `get_database_service()` singleton, scheduler SQL integration, scheduling
SQLite, Tip tracking, Cytomat, monitoring, backup and Restore remain unchanged.

PUT `/api/database/tools/viewer-source` is local-admin-only. The selected profile
cannot be removed until another is chosen. Browser-local connection preferences
do not affect server routing.

Connection settings stay in `data/database-tools/report-sources.json`. Existing
profiles default to read-only. `access=operation` profiles require a separate account;
report mappings and viewers reject them. Read-only effective permissions are checked
on every open. Operations store the target snapshot and configuration revision with
the preview, compare again under the configuration lock, then retain the existing
scheduler safety guard and transaction. Reconfiguration/remapping requires a new
preview. No native writer fallback remains for package operations.

Preview also takes the scheduler launch guard and rolls back its transaction.
Acquire that guard, then the catalogue lock, then `sources.lock`. Scheduling
settings also acquire the guard before source configuration. This avoids inversion
with package publication, which takes catalogue then sources.
Operation lookup inputs use separately mapped reading connections, validate values
before preview and again before execution, and retain the target transaction.
Trusted code must not commit inside preview, bypass connections or start independent
work. The host cannot enforce that contract against hostile Python.

Reports now run in disposable spawned processes (`report_worker.py`), with at most
two active reports and a five-minute limit. Shutdown/timeout terminates the child;
crash/error releases the slot. Only selected reading profiles are passed to the
child; no source catalogue or scheduler is initialized there. This is process
separation, not an OS sandbox: it has the application user's filesystem/network
permissions and there is no per-process memory cap. Package activation no longer
imports Python. Report imports happen in the child; operation imports occur during
explicit preview/execution under the guard.

POST `/reports/{id}/edit` captures the installed archive and its hash in an
owner-only draft. The generated update preserves sibling tools and authored files,
merges library declarations, retains IDs, and increments the suggested patch
version. Review/publish reject changed installed hashes or mappings. Both still
perform the normal activation running checks. Non-`run` entry functions use ZIP editing.

`database_access.py` creates a new reader only after the local admin reviews grants.
The review token is owner-bound, single-use and expires after ten minutes. SQL
provisioning credentials are never stored or audited. DDL runs in a transaction;
after commit, reader verification and encrypted persistence must succeed or the new
identity is removed. Cleanup failure gives explicit administrator instructions.
Existing logins are rejected, never altered. Grants are database-wide CONNECT,
SELECT and VIEW DEFINITION, with database-wide DENY EXECUTE for the new reader.
This overrides public execution grants such as SQL diagram procedures without
exempting them from permission verification. It also appears in downloaded setup
SQL and the access review. This includes future tables; use an existing narrowly
scoped account if the lab needs table-level restrictions. Windows setup authentication
uses the identity running RobotControl, not the browser user's Windows identity.

On post-creation verification failure, cleanup terminates pooled sessions belonging
only to the newly created login before dropping that user/login. SQL authority must
allow terminating those sessions; otherwise the error explicitly requests manual
cleanup. This does not repair identities left by an earlier release: a SQL
administrator must review/remove that failed new identity before reusing its name.

Setup errors identify duplicate login/user names, rejected sign-in, insufficient SQL
authority, inaccessible databases and missing ODBC drivers. Other failures show the
setup stage and SQLSTATE/native error numbers. Logs record only those diagnostics,
never raw driver messages that could contain SQL or credentials. Failed rollback or
cleanup explicitly asks the administrator to check the requested new account before
retrying. The original VM error was generic; its actual cause remains unconfirmed.

For manual setup, download the SQL, replace `<REPLACE_WITH_STRONG_PASSWORD>` and run
it on the selected server using an authorized SQL administrator. Then choose **Use
existing account** in RobotControl with that new login/password. The **Create account**
button instead generates its own password and saves the connection automatically.
Do not run the downloaded script and then use Create account for the same login.

Focused error checks and commands: `recovery/database-access-verification/index.html`.

`report_authoring.inspect_python` parses AST only. It detects nested imports,
explicit Excel engines, compatible synchronous entry-point signatures and common
connection/argument adaptations. Dynamic imports and local modules need manual
review. It neither runs Python nor certifies calculations or isolation. Contract 2
reports may explicitly use zero sources; their `context.connection` is None and
`context.connections` is empty. Contract 1 retains its required primary mapping.

Repeat commands and evidence: `frontend/e2e/README.md`, section Configurable
Database workspace; `recovery/database-workspace-verification`.


## uv setup and verification

Install pyodbc through `uv sync --locked`; install the Microsoft ODBC driver separately on the host. Run `uv run --locked python -m pytest backend/tests/test_database_service.py` for mocked primary connection, failure handling, pagination, query, and transaction tests. The current service has no secondary-server or mock-data fallback. The tests do not connect to SQL Server.

This guide explains how the database utilities (backup, restore, metadata management, and basic data viewing) fit together. It targets maintainers who prefer explicit instructions and may not remember all the moving parts.

---

## 1. High-Level Architecture

- `backend/services/backup.py`  
  Contains `BackupService` plus two helpers: `SqlCommandExecutor` (runs sqlcmd commands) and `BackupMetadataStore` (writes/reads `.json` metadata). This is the core logic behind backup/restore features.

- `backend/services/database.py`  
  Houses utility functions for running ad-hoc SQL queries and listing tables (used by the “Database” admin page). It now targets only the primary SQL Server instance and sits in front of the shared database connection manager.

- `backend/api/backup.py`  
  FastAPI routes for listing backups, creating/deleting them, restoring, and fetching health metrics. Calls into `BackupService` and emits audit logs.

- `backend/api/database.py`  
  Exposes authenticated external-database viewers plus native health/monitoring endpoints. Public SQL and procedure execution routes return 410; installed operations use the guarded tools API.

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
   Validates the filename, builds a multi-statement `RESTORE` script, and passes it to `SqlCommandExecutor.execute`. On failure it attempts to set the database back to multi-user mode before returning an error. On success the service immediately clears the connection pool, then pings the database until a fresh `SELECT 1` succeeds so the API is ready before the frontend resumes polling.

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

- `BackupService._recover_database_connections`  
  Runs right after a successful restore. It clears the pooled connections via `db_connection_manager.reset_pools()` and keeps trying `SELECT 1` until SQL Server responds, so the API does not hand control back while the database is still restarting.

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
| Run ad-hoc query | `backend/services/database.py` helpers (internal callers only) | UI is read-only; hammering production with heavy queries is discouraged. |

---

## 6. Extension Points & Gotchas

- **sqlcmd required**: The service no longer falls back to pyodbc. Ensure `sqlcmd` is installed and in PATH on the machine running RobotControl.
- **Permissions**: SQL Server must have permission to write to `SQL_BACKUP_DIR`. Likewise, the RobotControl process must have permission to delete files there.
- **Disk space**: Backups can be large. `create_backup` warns when disk checks fail but does not prevent the OS from running out of space. Monitor `get_performance_metrics()["health_info"]["available_disk_space_mb"]`.
- **Metadata consistency**: Always use `BackupMetadataStore` to manipulate metadata. Writing JSON manually bypasses validation and breaks the UI.
- **Maintenance mode**: The frontend sets a maintenance window when a restore starts. Keep this behaviour; cutting the restore short can leave the database in single-user mode.
- **Network paths**: UNC paths (e.g., `\\server\share`) are supported, but validation uses string comparisons. Ensure the paths are normalised and accessible.
- **Query API**: `/api/database/query` is retired (410); use registered tools.

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
| `database_service.execute_query(sql)` | Run read-only query | Internal monitoring/scheduling helper; no public raw-SQL route. |

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
   - The raw query API is retired. Use a registered operation/report or an internal helper.
   - Enforce role-based access to these endpoints; never expose them to unauthenticated users.

7. **Restore reports success but the API still errors**  
   - Check `backup_service.log` for the warning “Database connectivity check after restore …”. That means `_recover_database_connections()` could not reach SQL Server within 30 seconds. Verify SQL Server is fully online, then retry a manual `SELECT 1` via sqlcmd. Once the server responds, the next health poll will clear maintenance mode.

---

## 9. Adding New Modules or Integrations

1. **Keep backup logic inside `BackupService`**. If you need new operations (compression, cloud upload), add helper classes but expose them through `BackupService` so locking/logging stays centralised.
2. **Document config changes**. Whenever you adjust `LOCAL_BACKUP_PATH` or introduce new environment variables, update `.env.example` and the README.
3. **Re-use helpers**. For any new backup-related features (e.g., scheduled backups), call `BackupService.create_backup` instead of implementing raw sqlcmd calls.
4. **Test end-to-end**. After changing backup/restore logic, run: create backup → restore backup → list backups → delete backup. Confirm metadata and UI all work.
5. **Mind security**. Backups contain sensitive data. Ensure file permissions and network shares are locked down, and never write backups to public locations.

Follow this guide whenever you need to touch the database utilities. Being cautious about sqlcmd usage, metadata consistency, and permissions will keep the backup/restore pipeline predictable and safe.


### September 2026: table browsing and exports

The Tables section has a searchable catalogue, Important-only filter, and a separate selected-table workspace. Catalogue labels mean Has data/Empty, not row counts. On narrow screens Back to tables preserves the selected-table draft. Stored procedures also support name search.

`DatabaseTable` applies search/filter drafts only on Apply or Enter. Its single effect cancels/ignores superseded requests and keeps prior rows during refresh. `search` (maximum 200 characters) and `sort_direction=asc|desc` extend the existing table endpoint. SQL parameters carry values; column names are checked against metadata and identifiers are quoted. Scalar-type metadata excludes binary/complex columns from global search. SQL commands time out after 30 seconds. Primary keys break sorting ties; tables without a unique key cannot promise stable pagination during writes.

`databaseExport.ts` collects all matching rows in 1,000-row batches. Cancellation, count changes, incomplete batches and the 50 MB memory limit stop the download with an explanation. Exports use applied conditions and visible columns. They are not transaction snapshots. NULL is preserved in JSON and rendered as an empty CSV field. Do not replace this with a single unbounded page request. Restore retains its access rules; Operations now requires a local admin and uses package definitions.

## Portable operations and reports (2026-09-27)

### Report authoring and source permissions (2026-09-28)

`report_authoring.py` owns private, revisioned JSON drafts and generated archives.
`report_sources.py` owns named SQL Server profiles, encrypted credentials, package
source mappings, effective-permission checking and bounded dropdown queries.
`database_tools.py` owns trial/installed report workers and source snapshots.
No report falls back to the application's writer connection. After upgrading,
assign a read-only `primary` connection to each legacy report package. A connection
needs SELECT access and `VIEW ANY DATABASE` for the cross-database grant check.
See [the contract](../../../database_packages/CONTRACT.md) for accepted grants and
limits; do not work around a rejected identity by disabling permission checks.

The API adds local-admin `/sources`, `/drafts`, draft handler/package downloads,
trial/review/install actions and `/packages/{id}/sources`. Ordinary report clients
use registered `/reports/{id}/choices/{field}` lookups; catalogue responses omit
query text and source details. Dependency membership is checked again during runs.
SQL Server 2008-compatible ROW_NUMBER paging is intentional. No SQLite report
provider is implemented yet. Operations expose the equivalent local-admin choices
endpoint and preserve the same confirmation/transaction checks.

Focused real-SQL workflow: `.venv/Scripts/python.exe -m backend.e2e.report_wizard_check`.
It creates uniquely named disposable databases/login using local Windows-admin
authentication, then removes them. Never point this at a deployment server without
reviewing the fixture scope. Evidence: `recovery/report-wizard-verification`.

See [the package contract](../../../database_packages/README.md) for formats, limits
and authoring. The host owns installation, confirmations, receipts, SQL transactions
and private downloads. Public APIs are in `backend/api/database_tools.py`; raw SQL
and procedure execution routes now return 410. Internal monitoring helpers remain.

Deletion requires a local administrator and the existing scheduler safety checks.
Its transaction holds the same in-process locks as final scheduler launch. This
coordinates RobotControl dispatch; it cannot prevent an independent external launch
of robot software. The SQL procedure must respect the host transaction.

Repeated confirmation returns the saved result, never another execution. Unknown
means inspect the outcome before repeating. Report failures appear in Data retrieval.
Packages are trusted software, not sandboxed SQL definitions.


### Package inspection and authoring

`POST /api/database/tools/packages/inspect` reads and compiles the ZIP without
importing Python or writing an installation. It returns the manifest and current
installed version/hash. The install route accepts `expected_current` (the reviewed
hash, or `absent` for a new package) and `expected_package`; mismatches return 409.
All package routes retain local-admin checks and upload limits. Activation checks
syntax and entry-point definitions without importing; it cannot prove behavior.

`build_scripts/database_package.py create` preserves a source script and generates
an editable adapter, manifest and agent instructions. `build` shares archive
validation with the host, rejects unfinished adapters and produces a versioned ZIP.
No package code is executed by either command. See the package authoring guide.

Culture history 1.0.2 restores Data.py's original well ordering and first-N
selection. Its adapter explicitly stringifies SQL NULL as `None`, preserving the
legacy pandas behavior under bundled pandas 3. The 1.0.1 missing-well rejection was
an unintended behavior change and is removed. Do not special-case culture IDs or
exclude rows independently of the reference script. The regression compares whole
workbooks with an extra NULL-well culture 98500000 on plate 985 and with selected
missing/ancestral wells. SQL Server validation of the actual experiment remains a
VM check. This correction ships as a ZIP compatible with the existing executable.
