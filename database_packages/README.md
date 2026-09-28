# Database package contract, version 1

Packages are reviewed Python code running with RobotControl's permissions, not a
sandbox. Only local administrators can install them. They cannot install libraries.
Supported libraries are the bundled versions of pandas, openpyxl, pyodbc and numpy,
plus the Python standard library modules included in the application. Verify every
new import against a packaged candidate; adding dependencies requires an app update.

## Make a package

Start with your existing Python script. There are two jobs: **adapt the Python**
to use RobotControl's services, then **build the package**. The helper handles the
manifest and ZIP; it does not convert arbitrary Python automatically.

On your development PC, from the RobotControl repository:

```powershell
uv run --locked python build_scripts/database_package.py create ../MyDatabasePackages/my-report --script C:/Scripts/Data.py
```

Answer the prompts for name, stable ID (e.g. `my-culture-report`), report/operation,
version, libraries and form inputs. For an experiment selector enter
`experiment_id:experiment:Experiment`. Enter a blank line after the final input.
The supported types are experiment, text, integer, number, boolean and choice;
for choices use `state:choice:State:Clean,Dirty`. Inputs created by the helper are
required. Optional inputs can set `required: false` in the generated manifest.

The new folder contains:

| File | Your next step |
| --- | --- |
| `reference/Data.py` | Unchanged original; keep it for comparison. It is not included in the ZIP. |
| `handler.py` | Move/adapt the original logic here. The comments show the required interface. |
| `manifest.json` | Generated name, version, libraries and form fields. |
| `AGENTS.md` | Adaptation instructions for you or a coding agent. |

For example, replace `sys.argv[1]` with `inputs["experiment_id"]`, your SQL
connection creation with `context.connection`, and a fixed export path with
`context.output_dir / "report.xlsx"`. Return `"report.xlsx"`. Keep calculation,
plate/parent selection and workbook formatting rules unchanged unless intentionally
redesigning the report. Do not call the original standalone `main()`.

If using a coding agent, give it this instruction:

> Read this package's AGENTS.md and original script in reference/. Adapt handler.py
> to RobotControl's interface. Preserve the report rules and formatting. Explain
> any ambiguity before changing it. Do not run against production data. Record the
> relevant failure cases and verify the result using disposable data.

When the adapter is complete, remove its `ADAPT_BEFORE_BUILD` marker and build:

```powershell
uv run --locked python build_scripts/database_package.py build ../MyDatabasePackages/my-report
# After editing an existing package, increase its version:
uv run --locked python build_scripts/database_package.py build ../MyDatabasePackages/my-report --version 1.0.1
```

The helper prints the versioned ZIP path. It checks archive contents, entry-point
definitions, Python syntax and declared bundled libraries without importing the
package. These checks do not verify calculations, query safety or every import.
Upload through **Database → Manage packages → Add package**, review it, then
install. Test the report/operation with disposable data before production use.

For an update, keep the package and tool IDs unchanged. Click **Update** beside
the installed package, choose the new ZIP and review the old/new versions. If an
installation changed since review, review it again. Updating RobotControl itself
does **not** replace installed packages; deliver their updated ZIPs separately.
Deployment PCs need neither Python nor UV. The commands above are authoring tools
for the development PC, where the project's Python environment is available.

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
Version 1.0.1 handles missing well labels on pandas 3 without converting them into
fake well names. When every culture on the chosen plate is included, missing wells
remain blank and sort after known wells. If selecting only a subset would require
ordering cultures with missing well positions, it stops with the affected plate
and culture IDs instead of guessing which cultures to export.

The application exposes `/api/database/tools/catalogue`, `/experiments`, `/packages`,
`/operations/{id}/preview`, `/operations/execute`, `/reports/{id}` (POST), and
`/reports/{job_id}` / `/download` (GET). All require authentication. Installation,
removal, preview and execution additionally require a local administrator. The
former `/api/database/query` and `/execute-procedure` routes return HTTP 410.

Do not describe fixture checks as SQL Server validation: the disposable adapter
translates the procedure and metadata queries. Verify the actual ODBC driver,
schema, `dbo.DeleteExperiment` transaction behavior and report output on the VM.
