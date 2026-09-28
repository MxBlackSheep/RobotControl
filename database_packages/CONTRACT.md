# Database package reference

For the first report, follow [the worked example](README.md). This file describes
the runtime interface and restrictions for authors and maintainers.

Packages are reviewed Python code running with RobotControl's permissions, not a
sandbox. Only local administrators can install them. They cannot install libraries.
Supported libraries are the bundled versions of pandas, openpyxl, pyodbc and numpy,
plus the Python standard library modules included in the application. Verify every
new import against a packaged candidate; adding dependencies requires an app update.

For advanced authors, either starter package can also be copied directly. A ZIP
contains `manifest.json`, Python modules and optional `.md`/`.txt` documentation at
its root (no enclosing folder, binaries, symlinks or nested directories). Use one
self-contained Python module per entry point; sibling-module imports are not part
of this first contract. Upload through **Database → Manage packages**.

Use the same `build` command for a starter package. No manual ZIP assembly is needed.

The manifest declares `contract_version: 1`, a unique lowercase hyphenated package
`id`, display `name`, three-part `version`, `libraries`, and a `tools` array. Each
tool has a globally unique `id`, `name`, `kind` (`operation` or `report`),
`entrypoint` (`module:function`) and `inputs`. Input definitions use `name`, `label`,
`type`, `required` and optionally `choices`. Types: `text`, `integer`, `number`,
`boolean`, `choice`, `experiment`. Unknown inputs and invalid types are rejected.

Both kinds implement `run(context, inputs)`. The context supplies a database
`connection`; reports also receive `output_dir`. Use parameterized queries. Close
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

Installation imports modules to check entry points. Keep imports free of side
effects; there are no installation hooks or automatic SQL migrations. Any required
stored procedures must already exist. Updates replace a matching package ID;
conflicting tool IDs in other packages are rejected. Installation/removal is blocked
while that package runs. Old confirmations are invalid after a package update.

Limits: 20 MiB ZIP, 50 MiB expanded, 100 files; multipart requests require a known
Content-Length. Two concurrent reports, no waiting queue; 100 MiB maximum completed
workbook; finished report files expire after 15 minutes, renewed on download.
Report SQL statements time out after 120 seconds; trusted Python computation has no
forced termination. Operation SQL statements time out after 30 seconds. Operation
confirmations expire after 10 minutes. Preview and report ownership use the user ID.

Installed versions and their atomic index live under `data/database-tools/packages`.
The index is also the removal record: do not delete it to reset one package. Starter
packages are seeded only on first installation, so user removals survive restarts.
Operation receipts survive restart under `data/database-tools/operations.sqlite3`;
an interrupted execution is unknown and must be checked before repeating. There is
no automatic retry of database changes. Temporary reports are removed on restart.

## Verify and maintain

Use the focused commands in `frontend/e2e/README.md`. The culture-history package
records its exact upstream revision in `UPSTREAM.txt`. Its calculation functions
retain upstream behavior, including latest-plate/first-parent choices. The adapter
uses RobotControl's connection and output directory, reads rows through pyodbc
directly, and avoids selecting the same OD column twice under different casing.
Version 1.0.2 restores the original well sorting and first-N culture selection.
It explicitly converts SQL NULL well labels to the string `None`, matching the
original script's legacy pandas conversion. The pandas 3 crash and the additional
1.0.1 rejection are removed. No CultureID pattern is filtered or special-cased.
The reference check runs the original script with legacy string inference in the
synchronous verifier; the production package never changes global pandas options.


The application exposes `/api/database/tools/catalogue`, `/experiments`, `/packages`,
`/operations/{id}/preview`, `/operations/execute`, `/reports/{id}` (POST), and
`/reports/{job_id}` / `/download` (GET). All require authentication. Installation,
removal, preview and execution additionally require a local administrator. The
former `/api/database/query` and `/execute-procedure` routes return HTTP 410.

Do not describe fixture checks as SQL Server validation: the disposable adapter
translates the procedure and metadata queries. Verify the actual ODBC driver,
schema, `dbo.DeleteExperiment` transaction behavior and report output on the VM.
