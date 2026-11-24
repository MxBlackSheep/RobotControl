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

The manifest declares `contract_version: 2`, a unique lowercase hyphenated package
`id`, display `name`, three-part `version`, `libraries`, and a `tools` array. Each
tool has a globally unique `id`, `name`, `kind` (`operation`, `report` or `preparation`),
`entrypoint` (`module:function`) and `inputs`. Input definitions use `name`, `label`,
`type`, `required` and optionally `choices`. Types: `text`, `integer`, `number`,
`boolean`, `choice`, `date`, `lookup`. Unknown inputs and invalid types are rejected.

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
- **Preparation** (contract version 2 or later): `entrypoint` names `prepare(context, inputs)`;
  no `preview` or `confirmation_field`. A local administrator attaches it to a schedule
  under **Before this run**; saving pins the package file hash and the package's operation
  connection (its id, server and database). Before each run, RobotControl runs it unattended
  in a separate process with a two-minute limit (60 s per statement), SERIALIZABLE with
  XACT_ABORT, and commits after it returns. `context.connection` is the operation
  connection, `context.connections` the declared read sources, `context.run` has
  `schedule_id`, `execution_id`, `experiment_name`, `experiment_path`, `scheduled_for`
  and `started_at`. Return `{"message": "..."}` (at most 500 characters shown in the
  receipt). Its `commit()`, `rollback()`, `autocommit` and `with context.connection:` refuse (also commit/rollback on cursors); do not issue `COMMIT`/`ROLLBACK` statements or touch anything outside the database: raising
  rolls back and stops the run (failed); a timeout or crash is an unknown outcome. Both
  mark the schedule for recovery and are never retried. Updating or removing the package,
  or rebinding its connection, is refused while an active schedule uses it; a changed
  package blocks the run until an administrator saves the schedule again. Example:
  [examples/preparation](examples/preparation).

## Contract version 3: experiment types

Version 3 adds declarative `experiment` tools. Existing report, operation and
preparation contracts keep their meaning, including required Python entrypoints.
Versions 1 and 2 remain supported but cannot declare experiment tools. Package ID
`experiments` is reserved for the host's shared writing connection.

An experiment tool has exactly `id`, `name`, `kind: "experiment"`, `parameters`,
and optionally `layout`. Its version is the containing package's version. It has
no entrypoint, preview, inputs, sources, confirmation field, SQL or callback. Even
empty code-related fields are refused. Other tool kinds refuse experiment fields.
An experiment-only ZIP contains `manifest.json` and optional documentation, no
Python, and declares no libraries. Mixed packages may contain Python for their
other tools; experiment registration never imports it. Archive size, path and
duplicate-ID checks apply to all kinds.

`parameters` is an ordered list of 1–20 definitions:

| Field | Contract |
| --- | --- |
| `name` | `[A-Za-z][A-Za-z0-9_]{0,49}`, unique ignoring case; case is preserved. |
| `label` | Nonblank string, at most 100 characters. |
| `type` | `number`, `integer`, `text` or `choice`. |
| `default` | Required value of that type satisfying every constraint. Numbers must be finite; booleans are never numbers; integers must be JSON integers. Text/choice values are nonblank strings of at most 255 characters. |
| `min`, `max` | Optional inclusive numeric bounds; integers require integer bounds. Reversed bounds and bounds on text/choice are refused. |
| `allowed` | Optional nonempty list of at most 100 distinct, correctly typed values within bounds. Required for choice. Numeric equality defines numeric membership. |
| `group` | Required `main` or `more`; affects presentation only. |
| `fixed` | Optional boolean, default false. When true, submission must equal the declared default. |

Registration requires exactly the declared names, without filling missing values.
Parameter writes follow definition order. Text is preserved after nonblank checks;
numbers are bound as numbers. Names and values are SQL parameters, never SQL syntax.
Unknown definition keys and explicit null constraints are refused.

An optional layout has `kind: "plate96"`, `assignments`, `default`, `required`, and
optional `rules`. Omitting layout means no plate; explicit null is refused.
Assignments are 1–96 objects with distinct nonblank `value` strings (at most 50
characters), nonblank `label` strings (at most 50), and distinct one-character
nonblank `symbol` strings. Empty wells are omitted. `default` is an ordered list
of up to 96 `[well, assignment]` pairs: distinct wells A1 through H12, with declared
assignments. `required` is a distinct subset of assignment values, each present in
the default and submitted layout. Empty layouts are allowed when none are required.

Rules have exactly this shape:

```json
{"kind":"whole_count","parameter":"TopFractionToPropagate","assignment":"Cells"}
```

The referenced parameter must be numeric and the assignment declared. The count of
matching wells times the submitted decimal value must be an integer. The host
uses exact integer numerator/denominator arithmetic, without rounding or tolerance:
27 culture wells at 0.5 are refused; 32 at 0.5 are accepted. Defaults must also pass.
Unknown rule kinds and references are refused.

A layout type requires an explicit layout list at submission. A type without layout
accepts omission or an empty list and never accesses the plate pattern table. Wells
are written in column order (A1, B1 through H12). All experiment types use the host's
`experiments` writing binding and transaction/safety gates, not package Python.

`GET /api/database/tools/experiments/types` returns installed definitions with
`package_id`, `package_version` and package `sha256`. Both listing and registration
require a local administrator. POST registration supplies `type_id`, the reviewed
`package_version` and `sha256`, `user_defined_id`, `note`, integer `schedule` (0/1),
`parameters`, optional `layout`, and a 32-character lowercase hexadecimal `token`.
The host reserves the installed package and checks its identity before writing;
a changed or missing definition requires reloading. A completed receipt can still
be replayed by its owner after removal, without re-executing SQL.

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
semicolon, and must return `value` and `label`. The optional lookup `order` lists
choices by `label` (default), `label_desc`, `value` or `value_desc`; other values are
rejected. The host pages the query as a derived table, so an `ORDER BY` inside it is
not used. Manifests omit `order` when it is `label`; one that sets it needs
RobotControl 0.1.5 or later (older versions reject the key). Declare the package's
minimum application version with `min_robotcontrol_version` (see below). Use unique
stable values. The host
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

Local-admin drafts retain the tool's Python files, inputs, aliases and local source
mappings under `data/database-tools/report-drafts`. Saving and exporting do not import
Python. Explicit trial/report execution imports the handler in a child process. Package
checks are not calculation validation. Draft saves carry a revision; stale saves return 409.
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

The application exposes `/api/database/tools/catalogue`, `/packages`,
`/operations/{id}/preview`, `/operations/execute`, `/reports/{id}` (POST), and
`/reports/{job_id}` / `/download` (GET). All require authentication. Installation,
removal, preview and execution additionally require a local administrator. The
former `/api/database/query` and `/execute-procedure` routes are removed (HTTP 404).

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

## RobotControl version declaration

Every runnable package declares `"min_robotcontrol_version": "1.0.0b1"` in
`manifest.json` (or the later version it requires). For example:

```json
{
  "contract_version": 2,
  "min_robotcontrol_version": "1.0.0b1",
  "id": "my-report",
  "name": "My report",
  "version": "1.0.0",
  "libraries": [],
  "tools": [{"id": "my-report", "name": "My report", "kind": "report", "entrypoint": "handler:run", "sources": []}]
}
```

The minimum is a canonical PEP 440 version with three release components; beta,
release-candidate, development and postrelease suffixes are supported. Ranges,
epochs, local suffixes and V prefixes are not. RobotControl compares versions,
including prereleases, against `backend.version.__version__`.

A declared, satisfied minimum permits use subject to the existing permissions,
connections and robot gates. An undeclared ZIP installs as **Needs review** and
cannot run; import or republish a copy that declares the field to clear it. A
newer requirement is **Needs newer RobotControl** and installation is refused
with 409. An already installed newer package stays visible but blocked.
There is no approval button, approval record or automatic starter exception.

App publication and private authoring trials generate a minimum of the running
RobotControl version, preserving any higher source declaration or installed-package
minimum. Replacing Python updates the draft requirement from its current source.
The CLI create command writes the running version; build and export preserve the
manifest declaration and validate syntax without requiring that minimum locally.
Receipts and monitoring of already-dispatched runs remain recoverable.
