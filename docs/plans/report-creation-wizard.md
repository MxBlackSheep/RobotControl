# Report creation wizard — implementation brief

2026-09-28. Implemented direction. SQL Server first, SQLite later. Verification
commands are in `frontend/e2e/README.md`; release evidence is under
`recovery/report-wizard-verification`.

## Observable outcome

An author brings a Python script, defines its inputs and database sources, tries
it, then installs or exports a report package without hand-writing a manifest or
assembling a ZIP. Report users choose a report, enter its inputs and download Excel.
No assumption that reports use Experiments, culture tables or Culture history rules.

The author owns Python calculations, optionally assisted by a coding agent. The
wizard handles integration; it cannot reliably convert arbitrary script logic.

## Author flow

Local administrators create reports through Manage packages:

1. **Script:** name the report and upload Python. Inspect syntax, declared imports
   and entry points without importing or running it. Preserve the original file.
2. **Data and inputs:** choose named report connections and define labelled fields.
   Support ordinary typed fields, dates, fixed choices, database choices and choices
   filtered by earlier inputs. A database choice specifies its source, value and
   display columns; advanced authors can supply a parameterized lookup query.
3. **Try report:** show the actual user form. An explicit action runs a sample using
   the existing bounded report worker and offers the workbook for inspection.
   A successful run proves execution, not calculation accuracy.
4. **Install or export:** produce the normal reviewed package. Keep current atomic
   activation, compatibility checks and update/removal restrictions.

A script already implementing `run(context, inputs)` can proceed directly. Otherwise
offer a downloadable starter adapter and a short adaptation brief containing the
chosen input names, source aliases and output contract. The author edits Python
outside the application and uploads the adapted file. Do not offer automatic
conversion, an embedded Python IDE or automatic dependency installation.
Keep this as a saved local-admin draft: downloading and re-uploading `handler.py`,
leaving the wizard and returning must retain its field/source settings. The wizard
assembles the final package; the author never needs to edit JSON or assemble ZIPs.

## Inputs and report selection

Example: Project comes from one database; Plate comes from another and depends on
Project; Format is a fixed Summary/Full choice. The author defines that relationship
explicitly. Do not infer joins between unrelated databases.

- Store typed values separately from display labels. Use searchable, paginated
  database choices; run their lookups through approved read-only connections.
- Changing a parent clears affected children. Disable children until required
  parents exist. Reject late responses and dependency cycles.
- Validate values and dependent membership again before generation. Browser
  requests submit registered report/field identifiers and values, never SQL or
  Python paths. Bound lookup results and query duration.
- One installed report shows its name. Multiple reports show a labelled selector
  above the workspace, using the existing catalogue behavior. Switching reports
  clears incompatible inputs/results; disable switching during an active job.
- Keep the existing experiment browser where appropriate. General reports use a
  form for their own inputs and a result area; do not impose an experiment selector.
  Use available width with readable controls, stacking on phones.

## Connections and write protection

Administrators configure named SQL Server report connections once. Packages declare
logical source aliases; installation maps these to local connections. Exclude
credentials and machine-specific connection settings from exported packages.
Reuse the existing Windows secret encryption helper. Moving profiles to another
machine requires configuring its credentials again.
Updates retain mappings for unchanged aliases and show added/removed aliases for
review. Changes to a source used by an active report must not replace its connection
mid-run.

Use dedicated SQL Server identities with SELECT access to approved tables/views
and without write, DDL or privileged procedure permissions. Database permissions
are the protection against accidental writes through supplied connections. A query
scan or ODBC read-only setting alone is insufficient. Connection checking must
distinguish connectivity from verified permissions; do not label a successful
SELECT as proof of read-only access. Do not modify production grants automatically.

Reviewed, trusted Python remains required. Same-process Python can bypass supplied
connections; this is not a sandbox or a guarantee against deliberately hostile code.
Restricted execution is a separate feature. Operations retain their writable
connection, local-admin checks, confirmations and scheduler safety guard.

## Existing reports and implementation boundaries

- Introduce a new manifest version for source aliases and dynamic input definitions;
  explicitly retain version 1 support. Keep the archive format and package lifecycle.
- Add a report-specific connection service rather than rewriting the application's
  database service. Keep provider-specific connection and lookup SQL separate from
  field definitions. SQLite support will still require checking report SQL; no
  automatic SQL dialect translation is promised.
- Map legacy `context.connection` to an explicitly configured primary read-only
  report source. Expose additional connections by their package aliases. If mapping
  is missing, show a setup error; never fall back to the application's writer.
- Preserve Culture history 1.0.2 calculations, NULL handling and workbook formatting.
  List reports needing connection setup before enabling the new runtime.
- Extend `database_packages.py` for definitions/validation, `database_tools.py` for
  report connections/lookups, and the authenticated database tools API. Source
  management and authoring require local admin; runtime access enforces each report's
  allowed sources and existing job ownership. Never expose connection secrets.
- Reuse package inspection/activation and report jobs. Keep wizard state in one
  owner; preserve entered configuration when going Back or correcting an error.

## Failure cases and focused acceptance

Before implementation, use these cases to guide existing browser/HTTP checks:

- An arbitrary script is never executed merely by upload; missing entry points or
  libraries produce an actionable adaptation error. Invalid updates retain the
  working package. Export/reinstall preserves fields and excludes credentials.
- A report with two sources and dependent dropdowns submits the correct typed
  values; rapid parent changes cannot restore stale choices. Cover empty results,
  duplicate labels, unavailable sources and unauthorized field/source requests.
- Missing or invalid read-only configuration blocks execution. On disposable SQL
  Server data, SELECT works and INSERT/UPDATE/DELETE/DDL fail under the report
  identity. Inspect effective grants; fixture adapters cannot prove SQL permissions.
- A migrated Culture history package produces the same workbook as the accepted
  reference. Operation safeguards and private report downloads remain intact.
- Complete creation, correction, install, report selection and download on desktop
  and one phone size. Retain repeat command, fixture/build identity, result and useful
  screenshots/failure traces; no new unit tests or full viewport matrix.
- Verify generated packages in a separate relocated Windows candidate without
  Python/UV installed before release. Update only affected authoring/maintenance
  guides and implementation notes when the functionality is delivered.
