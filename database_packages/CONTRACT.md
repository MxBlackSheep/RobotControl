# Database package reference

For normal authoring, use the [Python-defined tool workflow](README.md).
RobotControl generates the manifest and archive. This file describes the runtime
interface and restrictions for advanced authors and maintainers.

Packages are reviewed Python code running with RobotControl's permissions, not a
sandbox. Only local administrators can install them. They cannot install libraries.
Supported libraries are the bundled versions of pandas, openpyxl, pyodbc and numpy,
plus the Python standard library modules included in the application. Verify every
new import against a packaged candidate; adding dependencies requires an app update.

For advanced authors, either starter package can also be copied directly. A ZIP
contains `manifest.json`, Python modules and optional `.md`/`.txt` documentation at
its root (no enclosing folder, binaries, symlinks or nested directories). Helper
modules in the same folder are imported relatively (`from .calculations import x`),
as in the [README](README.md). Upload through **Database → Manage packages**.

Build a starter package with the `build` command in the [README](README.md#existing-projects-and-drafts);
no manual ZIP assembly is needed.

The manifest declares `contract_version: 1`, a unique lowercase hyphenated package
`id`, display `name`, three-part `version`, `libraries`, and a `tools` array. Each
tool has a globally unique `id`, `name`, `kind` (`operation`, `report` or `preparation`),
`entrypoint` (`module:function`) and `inputs`. Input definitions use `name`, `label`,
`type`, `required` and optionally `choices`. Types: `text`, `integer`, `number`,
`boolean`, `choice`, `experiment`. Unknown inputs and invalid types are rejected.

Both kinds implement `run(context, inputs)`. Operations receive the application
`connection`; reports receive an explicitly assigned read-only connection and
`output_dir`. Use parameterized queries. Close
cursors. Never keep a connection or per-request state in module globals.

- **Operation:** also declare `preview` (`module:function`) and
  `confirmation_field` naming a required input. Preview returns
  `{"summary": "What will change", "details": {...}}`; it must be deterministic
  for unchanged data. Run returns a dictionary including a short `message`.
  The host compares the preview immediately before execution and owns commit and
  rollback. Package code must not commit, change transaction settings or perform
  external side effects. All operations require a local admin and an idle robot.
- **Report:** use SELECT queries only. Return the filename of a completed `.xlsx`
  directly inside `output_dir`. Never write fixed paths. Reports may run concurrently;
  do not change globals. A Python package can technically bypass these conventions:
  code review is the trust boundary.
- **Preparation** (contract version 2 only): `entrypoint` names `prepare(context, inputs)`;
  no `preview` or `confirmation_field`. A local administrator attaches it to a schedule
  under **Before this run**; saving pins the package file hash and the package's operation
  connection. Before each run, after any lab adapter step, RobotControl runs it unattended
  in a separate process with a two-minute limit (60 s per statement), SERIALIZABLE with
  XACT_ABORT, and commits after it returns. `context.connection` is the operation
  connection, `context.connections` the declared read sources, `context.run` has
  `schedule_id`, `execution_id`, `experiment_name`, `experiment_path`, `scheduled_for`
  and `started_at`. Return `{"message": "..."}` (at most 500 characters shown in the
  receipt). Its `commit()`, `rollback()` and `autocommit` refuse (also on cursors); do not issue `COMMIT`/`ROLLBACK` statements or touch anything outside the database: raising
  rolls back and stops the run (failed); a timeout or crash is an unknown outcome. Both
  mark the schedule for recovery and are never retried. Updating or removing the package,
  or rebinding its connection, is refused while an active schedule uses it; a changed
  package blocks the run until an administrator saves the schedule again. Example:
  [examples/preparation](examples/preparation).

## Contract version 2: database choices

Version 1 remains supported without changing its calculations. Its report connection
requires an explicit `primary` mapping in Manage packages; a missing mapping blocks
generation. Operations retain their existing writer and safety checks. An operation's writable
target is assigned locally in Manage packages, never in the package; changing it
invalidates pending operation confirmations.

Version 2 reports declare `sources`, a list of logical aliases (up to eight). Local
administrators map these to named SQL Server connections. Python receives them in
`context.connections[alias]`; `context.connection` remains the `primary` alias or
the first declared source. `sources: []` declares a report without a database:
`context.connections` is empty and `context.connection` is None. SQL dialect conversion
is not automatic; SQLite is not implemented. Source mappings and credentials are
excluded from exported packages.

Version 2 operations may also declare reading `sources` for lookup inputs and
receive them in `context.connections`. Their `context.connection` remains the
separately assigned operation target. Choice membership is checked before preview
and execution. Preview takes the robot/scheduler safety gate and always rolls back
the host transaction; authors must not commit or perform external side effects.

New input types: `date` (ISO `YYYY-MM-DD`) and `lookup`. A lookup field supplies:

```json
{"name":"plate_id","label":"Plate","type":"lookup","required":true,
 "lookup":{"source":"plates","query":"SELECT PlateID AS value, PlateName AS label FROM dbo.Plates WHERE ProjectID = ?",
           "parameters":["project_id"],"value_type":"integer"}}
```

Declare `project_id` separately. Parameters refer to input names in placeholder
order; unknown names and cycles are rejected. Choices are searchable and paginated
(25 per page); a query must be a composable SELECT without comments/trailing
semicolon, and must return `value` and `label`. Use unique stable values. The host
checks submitted membership with the same query before running Python. Values stay
typed (`text`, `integer`, `number`); labels are only for display. Lookups time out
after 30 seconds. SQL statement restrictions aid composition, not security.

Supplied SQL Server identities must have SELECT-only access. Effective permissions
are checked on every opened connection, including other accessible databases,
column grants and privileged EXECUTE/IMPERSONATE grants. `VIEW ANY DATABASE` is
required to enumerate those databases (normally provided by SQL Server's public
role). The empty system guest schema and temporary objects do not contain report
data. System metadata read permissions and endpoint CONNECT are allowed. Unknown
or elevated grants fail closed; errors identify the grant to review. No production
grants are changed automatically. Python can still bypass supplied connections;
these permissions do not sandbox trusted code or restrict other credentials.

Passwords use the existing machine-bound Windows DPAPI helper. Re-enter credentials
after moving a connection configuration to another machine. SQL credentials should
be scoped by the database administrator to the tables/views the reports need.

## Saved authoring drafts

Local-admin drafts retain the original Python, edited handler, inputs, aliases and
local source mappings under `data/database-tools/report-drafts`. Saving and exporting
do not import Python. Explicit trial/report execution imports the handler in a child process.
Original reference scripts are never included in the runnable ZIP. Inspection is
not calculation validation. Draft saves carry a revision; stale saves return 409.
Drafts are private to the author, capped at 100 with 1 MiB per Python file. Removing
a draft removes its trial package but does not remove the installed report.

Reports use a captured connection configuration while running; later source changes
apply to future runs. Trials share the two-report worker limit and private download
expiry with installed reports. Do not store per-run globals in package code.
Raise `ValueError` with a short sentence for a problem the user can fix; other
exceptions show "Report generation failed" with the text under Details.

Installation checks syntax and entry-point definitions without importing. Keep
imports free of side effects; there are no installation hooks or automatic SQL migrations. Any required
stored procedures must already exist. Updates replace a matching package ID;
conflicting tool IDs in other packages are rejected. Installation/removal is blocked
while that package runs. Old confirmations are invalid after a package update.

Limits: 20 MiB ZIP, 50 MiB expanded, 100 files; multipart requests require a known
Content-Length. Two concurrent reports, no waiting queue; 100 MiB maximum completed
workbook; finished report files expire after 15 minutes, renewed on download.
Report SQL statements time out after 120 seconds. Report processes are terminated
after five minutes or shutdown; this is not an OS sandbox or a memory limit.
Operation SQL statements time out after 30 seconds. Operation
confirmations expire after 10 minutes. Preview and report ownership use the user ID.

Installed versions and their atomic index live under `data/database-tools/packages`.
The index is also the removal record: do not delete it to reset one package. Starter
packages are seeded only on first installation, so user removals survive restarts.
Operation receipts survive restart under `data/database-tools/operations.sqlite3`;
an interrupted execution is unknown and must be checked before repeating. There is
no automatic retry of database changes. Temporary reports are removed on restart.

## API

The application exposes `/api/database/tools/catalogue`, `/experiments`, `/packages`,
`/operations/{id}/preview`, `/operations/execute`, `/reports/{id}` (POST), and
`/reports/{job_id}` / `/download` (GET). All require authentication. Installation,
removal, preview and execution additionally require a local administrator. The
former `/api/database/query` and `/execute-procedure` routes return HTTP 410.

## Culture history package

`culture-history/UPSTREAM.txt` records the exact upstream revision. The calculation
functions keep upstream behavior, including latest-plate/first-parent choices, the
original well sorting and first-N culture selection. The adapter supplies RobotControl's
connection and output folder, reads rows through pyodbc, avoids selecting the same OD
column twice under different casing, and converts SQL NULL well labels to the string
`None` as the original script's pandas did. No CultureID pattern is filtered. The
reference check runs the original script with legacy string inference in the verifier;
the package never changes global pandas options.

## Verify

Use the database section of `frontend/e2e/README.md`. Those checks use disposable
fixtures; verify the actual ODBC driver, schema, `dbo.DeleteExperiment` transaction
behavior and report output on the VM.
