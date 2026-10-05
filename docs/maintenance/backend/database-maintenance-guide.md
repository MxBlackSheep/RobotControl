# Backend database

SQL Server backup and restore, the table and definition viewer, saved database
connections, read-only account creation, and database packages (Excel reports and
database operations). The screens are described in
[the frontend database guide](../frontend/database-frontend-maintenance-guide.md).
How scheduling prepares laboratory data is in
[the scheduling guide](scheduling-maintenance-guide.md). The package format, contract
versions, bundled tool details and authoring steps are owned by
[database_packages/CONTRACT.md](../../../database_packages/CONTRACT.md) and
[database_packages/README.md](../../../database_packages/README.md).

## Files and ownership

- `services/backup.py`: `BackupService` is the entry point for backup, restore and
  delete. Creation and both restore paths take `_operation_lock`; deletion does not. `SqlCommandExecutor` runs `sqlcmd -E`;
  `BackupMetadataStore` owns the `.json` file beside each `.bak`. API routes and new code
  must not call the executor or write metadata directly. Routes: `api/backup.py`.
- `services/database.py`: `DatabaseService` (singleton `get_database_service()`) opens its
  own pyodbc connections to the native SQL Server in `settings.DB_CONFIG_PRIMARY`. Monitoring
  and scheduling use it internally; there is no public raw-SQL route.
- `utils/odbc_driver.py`: `build_connection_string` builds the native Database, Labware and
  backup connection strings. `services/labware_connection.py` shares connection handling for
  tip tracking and Cytomat, including driver fallback. Saved report sources keep their own
  quoted connection strings and permission checks.
- `services/workspace_database.py`: `WorkspaceDatabase` subclasses `DatabaseService` to browse
  the selected viewer connection, never the native connection. Routes: `api/database.py`.
- `services/report_sources.py`: `ReportSources` owns saved connections, encrypted passwords,
  the viewer choice, package connection assignments, the read-only permission check and
  dropdown (choice) queries. Stored in `data/database-tools/report-sources.json`.
- `services/database_access.py`: reviewed creation of a new read-only SQL account.
- `services/database_packages.py`: `PackageCatalogue` owns `installed.json` (the installed
  package index and history), package inspection, installation, removal and export.
- `services/database_tools.py`: `DatabaseTools` (`get_database_tools()`) owns operation
  preview and execution, report jobs and connection snapshots. `report_worker.py` runs one
  report in its own process.
- `services/report_authoring.py`: owner-only drafts, Python inspection and the activation
  journal, under `data/database-tools/report-drafts`. `tool_definition.py` reads `TOOL`.
- `api/database_tools.py`: every `/api/database/tools` route.
- `build_scripts/database_package.py`: `create` and `build` for authors; neither runs package code.
- `database_packages/`: bundled starter packages Culture history, Delete Experiment and Select
  EvoYeast experiment, all 1.0.0. Each `CHANGELOG.md` section is the default history message
  for its version and the import review's suggested note (`changelog_note` in
  `database_packages.py`). Publishing a draft adds its change note as the new version's
  section (`changelog_with_note`, called from `ReportAuthoring.archive(note=…)`) when
  RobotControl builds the ZIP; `export` always returns the retained ZIP, unchanged.
  Updating the executable never replaces an installed package; update through Manage packages.

## Backup and restore

`LOCAL_BACKUP_PATH` resolves to `BACKUP_DIR` (default `data/backups`, relative to the application folder).
SQL Server writes the `.bak` directly to that path, so the SQL Server service account needs
write access there and RobotControl needs read and delete access. Both must see the folder
under the same path. The unused `SQL_BACKUP_PATH` setting has been removed; old values in
`.env` are ignored. Backup commands use `BACKUP_TIMEOUT` (300 seconds); managed-file restore
and path restore use `RESTORE_TIMEOUT` (600 seconds). Recovery commands keep the 300-second default.

- **Create** (`POST /api/backup/create`, local session): description required, at most 1,000
  characters; file name `<database>_<yyyymmdd_hhmmss>.bak`. The disk-space estimate only logs
  a warning. After `BACKUP DATABASE` the service confirms the file exists, then saves metadata.
- **List** (`GET /api/backup/list`): pairs `.bak` and `.json`, newest first. A `.bak` without
  metadata is listed as "[Orphaned backup - no metadata]".
- **Restore** (`POST /api/backup/restore`): local session with role `admin` or `user`;
  `require_local_access` rejects remote administrators too. The request names either a managed
  `filename` or a `file_path` to a `.bak`/`.bck`, never both. Both formats use `_restore_database` and
  `SQL_RESTORE_TEMPLATE`, which first switches to `master`, sets `SINGLE_USER WITH
  ROLLBACK IMMEDIATE`, restores `WITH REPLACE`, then sets `MULTI_USER`. A failure or
  timeout retries `MULTI_USER` from `master`; failure of that recovery adds a warning.
  The restore failure and a failed recovery are both logged at ERROR.
  Path restore
  (`restore_backup_from_path`) first rejects a missing file, a folder or an extension other
  than `.bak`/`.bck` without running SQL, then runs the same script through sqlcmd under the
  same operation lock. If SQL Server rejects it, `MULTI_USER` is set again. It does not
  confine the path to the backup folder; SQL Server must be able to read the file.
  After either restore succeeds, `_recover_database_connections` retries `SELECT 1`
  through `open_restore_connection` with a 30-second retry window; a timeout becomes a warning.
  Each attempt opens and closes a direct connection, trying Windows authentication to
  `LOCALHOST\HAMILTON` first, then the configured `VM_SQL_*` login. There is no shared pool to
  reset. Requests handled by the restore route are audit-logged. Restore does **not** take the
  scheduler's `database_change_guard`, so it does not check for an active run; the operator must.
- **Delete** (`DELETE /api/backup/{filename}`, local admin): removes `.bak` and `.json` and
  reports partial success if one remains. **Health** (`GET /api/backup/health`): admin.

Backups contain laboratory data; keep `BACKUP_DIR` and any share restricted.

## Table and definition viewer

All `/api/database` routes require sign-in. `/tables`, `/tables/{name}` and
`/stored-procedures` use the one viewer connection a local admin chose
(`PUT /api/database/tools/viewer-source`). On upgrade, the first read-only connection is saved
once as the viewer. With none chosen the routes return 409 with a setup message; they never
fall back to the native or robot connection. A request whose `source_id` differs from the
current viewer returns 409 ("refresh"). `/query` and `/execute-procedure` return 410.

- Table names come from `INFORMATION_SCHEMA` metadata and are quoted with their schema, so
  views and equal names in different schemas work. Column names are checked against metadata
  and values are parameters.
- `search` (at most 200 characters) covers scalar text, numeric and date columns, not
  binary or complex ones; `sort_direction` is `asc` or `desc`. Commands time out after 30 seconds.
- Paging uses `ROW_NUMBER` for SQL Server 2008. Primary keys break sort ties; tables without a
  unique key cannot promise stable pages while rows are written.
- Stored procedure and function definitions are only read; viewing never executes them.

## Saved connections

Passwords are encrypted with `backend/utils/secret_cipher.py` and never returned. A
connection's `access` is `read` (default) or `operation` and cannot be changed later; create a
separate connection instead.

- Every open of a read connection runs `assert_read_only`: server and database permissions
  are checked in every database the account can reach, `VIEW ANY DATABASE` is required for
  that check, and any additional permission is rejected. Do not work around a rejected account
  by weakening the check; the accepted grants are in the contract.
- The viewer and report mappings accept only read connections. Each package with an operation
  is assigned one operation connection. No report or operation falls back to the native writer
  connection; after an upgrade, assign a read-only `primary` connection to each older report.
- A connection cannot be removed while it is the viewer or assigned to a package.
  `LabSettings.change_source` also refuses to edit or remove a connection that scheduling uses
  now or after restart (409); create a separate connection and review the change in Database
  settings.
- Saving a connection gives it a new revision, which invalidates pending operation previews.

## Creating a read-only account

`database_access.py` creates a new SQL login only after a local admin reviews the grants.

- The review token is owner-bound, single-use and expires after ten minutes. The new password
  is generated; administrator credentials are used once and never stored or audited. Windows
  authentication uses the identity running RobotControl, not the browser user's.
- The account gets database-wide `CONNECT`, `SELECT` and `VIEW DEFINITION` (including future
  tables) and `DENY EXECUTE`, which overrides public execute grants. Use an existing, narrower
  account if the lab needs table-level restrictions. Existing logins or users are rejected,
  never altered.
- After the DDL commits, reader verification and the encrypted save must both succeed.
  Otherwise cleanup ends sessions of that new login only and drops its user and login; if that
  fails, the message asks the administrator to remove the named account before retrying.
  Accounts left by earlier releases are not repaired.
- Errors name a duplicate login or user, a rejected sign-in, insufficient authority, an
  inaccessible database or a missing ODBC driver; otherwise the stage plus SQLSTATE and native
  codes. Logs keep only those diagnostics, never raw driver text that could contain SQL or
  credentials.
- Manual setup: download the SQL, replace `<REPLACE_WITH_STRONG_PASSWORD>`, run it as a SQL
  administrator, then use **Use existing account**. Do not also run **Create account** for the
  same login.

## Database packages

Packages are trusted Python, not sandboxed SQL definitions. The host owns installation,
confirmations, receipts, SQL transactions and downloads.

### Permissions

Every `/api/database/tools` route requires sign-in. A local administrator is required for
connections, the viewer choice, scheduling settings, drafts and authoring, and for listing,
inspecting, installing, exporting, removing and viewing history of packages, and for operation
choices, preview and execution. Any signed-in user may list the catalogue and run reports,
their choices and experiment searches. Catalogue responses omit query text and connection details.

### Installation and history

- `POST /packages/inspect` reads and compiles the ZIP without importing Python or writing, and
  returns the manifest and the installed hash. `POST /packages` takes `expected_current` (that
  hash, or `absent`) and `expected_package`; a mismatch returns 409. Uploads are limited to
  20 MB. A running package cannot be replaced or removed.
- Activation checks syntax and entry points without importing; it cannot prove behavior.
  `installed.json` is the activation point. The same atomic update records history: version,
  previous version, UTC time, publisher, optional note, checksum and added/changed/removed files.
  Old installations may have no history; nothing is invented. Removal discards history.
- Export returns the retained `.package.zip` after checking it against the recorded hash (409 if
  changed); older installations rebuild the ZIP from their flat files. Exports never contain
  local connection assignments or output, but authored code may itself contain secrets.

### Reports

At most two run at once (429) in spawned processes with a five-minute limit; shutdown or
timeout ends the process, and a crash releases the slot. The child receives only the selected
read connections and starts no catalogue or scheduler. This is process separation, not a
sandbox: the child has the application user's file and network access and no memory limit.
It must write one `.xlsx` in its folder. Package Python is imported only in this child, so an
import failure fails that run, not installation. A `ValueError` from the child (such as a stale
choice) becomes the job's `error`; any other exception gives a short `error` and the exception
text in `error_details`. Choice queries are one `SELECT` with `ROW_NUMBER`
paging, and chosen values are checked again before running. The lookup's `order` (default
`label`) picks the `ROW_NUMBER` ordering from the fixed `LOOKUP_ORDER_SQL` table in
`report_sources.py`; an `ORDER BY` inside the package query is not used.

### Operations

1. **Preview** takes the scheduler's `database_change_guard`, then the catalogue lock, then the
   connections lock; runs the package preview on the operation connection; and rolls back. The
   token records owner, connection, choice connections, package hash and a digest of the
   preview; it expires after ten minutes (at most 200 open).
2. **Execute** (local session) requires the typed confirmation. Before running it stores an
   `unknown` receipt in `data/database-tools/operations.sqlite3`, so repeating a token returns
   the saved result and never executes twice. Under the same guard and locks it compares the
   connection, choices and package again (409), sets `SERIALIZABLE` with `XACT_ABORT`, reruns
   the preview and requires the same digest, runs the operation and commits.
3. When a commit cannot be confirmed the result is `unknown`: inspect the database before
   repeating. If the receipt cannot be updated, the response warns and nothing retries.

`database_change_guard` holds the scheduler's schedule and job locks and refuses while storage
is unhealthy, recovery or Resume is pending, a run is owned or unfinished, or HxRun is running
or cannot be detected. It coordinates with RobotControl's own dispatch only; it cannot stop
robot software started outside RobotControl. Package code must not commit inside preview, open
other connections or start independent work, and its SQL procedures must respect the host
transaction; the host cannot enforce this against hostile Python. Keep the lock order guard →
catalogue → connections; publication takes catalogue then connections.

### Drafts and publication

- `report_authoring.inspect_python` parses the syntax tree only. It finds imports (including
  nested ones), Excel engines, compatible entry points and common adaptations; dynamic imports
  and local modules need manual review. It never runs Python or certifies calculations.
- `POST /authoring/import` creates or replaces a code-defined draft; `mode` is `python` (one
  defining file, replaced even when renamed), `supporting` (helpers; another `TOOL` is
  rejected) or `all` (complete source set, the default). `POST /authoring/{kind}/{id}/edit`
  opens an installed tool; `POST /reports/{id}/edit` keeps the older ZIP-editing path.
- `/drafts/{key}/check` checks files and connections without importing Python. `/try` runs a
  report through the worker, or an operation preview under the guard with rollback and no
  execution token. Trial code is still trusted code.
- `/drafts/{key}/install` requires the saved revision; code-defined drafts also need a successful
  trial and `reviewed`. The installed base and mappings must be unchanged and every declared
  alias mapped. It holds the authoring, job, catalogue and connection locks in that order.
  Before assigning connections it writes `report-drafts/activation.pending` (previous mappings
  and the new archive hash, no passwords); startup restores the previous mappings if that hash
  was never activated. Trials store connection fingerprints, not credentials; a restart
  invalidates readiness. Note-only edits keep the trial; code or connection edits clear it.
- A publication receipt in the history hides the completed draft. Repeating the same request
  returns the installed result without another history event; if the package has changed
  since, it returns 409.
- `/drafts/{key}/editing-files` downloads the original Python, handler, inputs and editing
  instructions. It is not an installable package and downloading runs nothing.
- Drafts, `installed.json` and `report-sources.json` are written to a `.tmp` file and swapped in
  with `utils/filesystem.replace_file`. It uses a POSIX-semantics rename because `os.replace`
  fails with WinError 5 while antivirus or an indexer briefly has the file open.

## Checks

Commands, fixtures and evidence folders are in
[frontend/e2e/README.md](../../../frontend/e2e/README.md) (section Database tools, packages and
notifications). Each check lists its
failure cases in its header:

- `backend.e2e.database_tools_check`: operations, receipts, scheduler guard, workbook parity.
- `backend.e2e.database_workspace_check`: viewer, account creation and rollback, operation
  connection revisions.
- `backend.e2e.report_wizard_check`, `tool_authoring_check`, `bundled_tools_check`: real SQL
  permissions, authoring, publication and bundled tool updates.
- `backend.e2e.packaged_database_smoke`: the same boundary in a relocated executable.
- `backend.e2e.draft_replace_check [--stress N]`: draft writes while another program has the
  file open; no SQL Server.
- `.venv/Scripts/python.exe -m backend.e2e.backup_restore_check`: real SQL Server backup,
  listing, managed-file and `.bck` path restore (with an open session), the restore timeout
  argument, invalid path and invalid-backup rejection and multi-user recovery using a disposable `RC_BackupCheck_<id>` database. Requires `sqlcmd`
  and local Windows access to `LOCALHOST\HAMILTON`; evidence is written to
  `test-output/backup-restore-verification/results.json`.
- `uv run --locked python -m pytest backend/tests/test_database_service.py`: mocked native
  connection, paging and failure handling; no SQL Server.

Real-SQL checks create UUID-named disposable databases and logins with local Windows
administrator authentication and remove them; never point them at a deployment server. Fixture
checks translate SQL and are not SQL Server validation: verify the actual ODBC driver, schema,
`dbo.DeleteExperiment` and report output on the VM. The backup check removes its own files;
it does not exercise the delete API or a restore lasting ten minutes. Verify
those separately with disposable data when changing their behavior.

## Troubleshooting

- **"sqlcmd failed … not recognized":** install the SQL Server command-line tools and make them
  available on the PATH of the account running RobotControl.
- **"Backup file was not created by SQL Server":** the SQL Server service account cannot write
  to `BACKUP_DIR`, or security software removed the file.
- **Database left single-user after a failed restore:** close other connections, then run
  `ALTER DATABASE [EvoYeast] SET MULTI_USER` with `sqlcmd`.
- **Restore succeeded with "Database connectivity check after restore …":** SQL Server was not
  back within 30 seconds. Confirm it is online; the Restore page clears maintenance mode once
  the API answers again.
- **"[Orphaned backup - no metadata]":** copy the `.json` with the `.bak`, or delete the orphan.
- **Viewer shows "Ask an administrator…" or "The viewer database changed":** choose the viewer
  in Database settings, or refresh the page.
- **"Report account has … permission":** use a dedicated SELECT-only account.
- **"Connection setup needed":** assign a read-only connection to every alias in Manage
  packages → Connections.
- **"Finish the run and resolve recovery before changing the database":** the scheduler guard
  refused; finish the run and recovery first.
- **Operation result `unknown`:** check the database before repeating.
- **Draft save or Try fails with "WinError 32 … being used by another process":** a program
  holds the draft, package index or connections file open without allowing deletion (scanners
  normally allow it). Find it with Resource Monitor → CPU → Associated Handles, searching for
  `report-drafts`, and exclude `data/database-tools` from that program.
