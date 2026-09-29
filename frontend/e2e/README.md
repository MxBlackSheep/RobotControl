# Frontend browser checks

Choose checks for the behavior being changed; a full suite is not required for
every edit.

Each spec file and backend check starts with a comment listing the failure cases
for its area. Check the tests themselves before assuming a case is covered. For
work in progress, list new failure cases in [scenarios.md](scenarios.md), then move
them into the matching header once the checks exist.

## Routine work (PowerShell, repository root)

Install dependencies once using the root README. Rebuild when frontend inputs
changed; the fixture server serves `frontend/dist`, not the development source.

```powershell
npm --prefix frontend run build
Set-Location frontend
npx playwright test labware-layout-stability.spec.ts --grep "joined workbench"
Set-Location ..
```

This example checks Labware sizing. Narrow or broaden it to the actual change:

| Area | Existing spec files to select from |
| --- | --- |
| Tip layout and refresh | `labware-layout-stability.spec.ts` |
| Tip editing and saving | `labware.spec.ts` |
| Cytomat | `cytomat-spatial.spec.ts` |
| Tables and SQL | `database.spec.ts`, `inspection-pagination.spec.ts` |
| Log readers | `logs.spec.ts` |
| Camera | `camera.spec.ts` |
| Scheduling and archives | `operations.spec.ts` |
| Theme, navigation and system pages | `appearance.spec.ts`, `system-pages.spec.ts` |

Use `--grep` for a specific case; use `npx playwright test --list --reporter=list`
to list cases without running them.

## Evidence and isolation

Playwright uses installed Microsoft Edge and starts its own fixture server on
port 8016. Do not run another harness on that port concurrently. The fixture uses
real log routes and disposable files; most other APIs, including Labware writes,
are synthetic. It starts no robot services and cleans its temporary files at exit.

`test-output/viewer-verification/report/index.html` is the latest run, which may be
focused rather than full. `results.json` identifies the cases actually run.
Successful screenshots requested by the config/specs remain available. Traces are
retained on failure by default; use `--trace on` for a release or investigation
that needs successful traces. Explicit screenshot matrices still run when selected.

Record the command, code/build identity and result beside the report. The fixture
manifest records log checksums; spec files define other fixtures. Preserve a report
referenced by a delivered candidate before overwriting it. Do not archive a full
copy after every passing local run. Evidence stays Git-ignored. Traces can contain
fixture credentials; these belong only to the disposable process.

## Broader verification and Windows delivery

Use the full suite when shared behavior is affected, uncertainty remains, or the
release acceptance requires it. After relevant checks pass, package only when a
Windows candidate is needed. Commands below use a **new** candidate directory;
replace `review-candidate` with the chosen name.

```powershell
# From frontend; for a justified full run with complete traces:
npx playwright test --trace on
# From the repository root; built frontend must be current:
uv run --locked python build_scripts/embed_resources.py
uv run --locked --group build python build_scripts/pyinstaller_build.py --output-dir dist/review-candidate
uv run --locked python backend/e2e/packaged_viewer_smoke.py dist/review-candidate/RobotControl
```

The packaged check runs a relocated copy on port 8017 with automatic recording and
scheduler autostart disabled, disposable authentication and a nonproduction SQL
address. It checks embedded viewers, the relocated log root, complete archive
reading and reader cleanup. It removes its process/copy; the original candidate
is preserved. Results and trace are `packaged-smoke.json` and `packaged-trace.zip`.
Its real 1 MiB log-section assertions allow 20 seconds; investigate failures rather
than repeatedly raising that limit. Copy the whole candidate, including `_internal`.

To confirm every page still works against the real packaged backend (for example
after removing code or endpoints), run the walkthrough with the same isolation:

```powershell
uv run --locked python backend/e2e/packaged_walkthrough.py dist/review-candidate/RobotControl
```

It opens all 28 page/section URLs as a local admin and fails on any API 401/403/404/405,
missing asset, page error, lazy-load failure or blank page. Evidence (summary, per-page
requests and screenshots) is in `test-output/packaged-walkthrough/<candidate>/`. SQL
Server is deliberately unreachable, so it proves the app runs, not SQL behavior.

## Native zoom and practical limits

When zoom behavior is affected, run `node frontend/e2e/labware-native-zoom.cjs`
from the repository root with port 8016 free; set the dedicated Edge window to
200% within three minutes. `native-zoom.cjs` is the equivalent reader check.
These save screenshots/JSON/traces and stop their own processes. Reduced viewport
size or a device scale factor does not by itself prove native browser zoom works.

Synthetic browser checks do not certify real SQL writes, robot operations, camera
hardware, remote networking or an actual phone keyboard. Verify the affected real
boundary when required; do not claim it from screenshots or test totals.

Historical results and candidate paths belong in
[implementation notes](../../docs/implementation-notes.md) and the corresponding
release evidence, not in this current run guide. Existing reports are preserved.

## Database packages and delivery logs

Browser checks for package authoring, the report wizard and tool authoring were
removed on 29 September 2026 because they no longer matched the screens; the HTTP
and packaged checks below remain. Add new browser cases in the existing spec files
when these screens next change.

For Python-defined tool addition/editing:

```powershell
.venv/Scripts/python.exe -m backend.e2e.tool_authoring_check
```

The HTTP check creates/removes UUID-named disposable SQL Server databases and logins
using Windows administrator authentication. It does not use laboratory tables.
Evidence and downloaded workbook checksums belong in `test-output/tool-authoring-verification`.

Focused checks from the repository root:

```powershell
.venv/Scripts/python.exe -W ignore::UserWarning -m backend.e2e.database_tools_check
.venv/Scripts/python.exe -W ignore::UserWarning -m backend.e2e.notification_delivery_check
Set-Location frontend
npx playwright test database-tools.spec.ts --trace on
Set-Location ..
.venv/Scripts/python.exe -m backend.e2e.packaged_database_smoke dist/<candidate>/RobotControl
```

Evidence: `test-output/database-verification` and the current Playwright HTML report.
Before the first reference comparison, download the revision in
`database_packages/culture-history/UPSTREAM.txt` to
`test-output/database-verification/upstream.py`.

HTTP checks use disposable SQLite-backed SQL rows and real package/API code. SMTP
uses a local mail sink and disposable storage. Browser checks use real package/report
endpoints; notification rows are UI fixtures. The packaged check strips Python/UV
from the child PATH and uploads a trusted fixture package into a temporary relocated
executable. It substitutes database connections only in that disposable process;
no production test endpoint is added. Real SQL Server/procedure/hardware behavior
remains a VM check. Owned temporary processes and databases are removed afterwards.


For authoring/update/workspace changes only, run `database_tools_check`. It also
creates an author project from an existing script, rejects an unfinished adapter,
builds its ZIP and exercises update review/activation without production data.
Missing well fixtures compare selection and workbook output against the original
script with legacy pandas string inference, including culture 98500000 on plate 985.
For a package-only correction, `packaged_database_smoke` accepts `--report-package`
to verify the ZIP against an existing executable without recompiling. Both HTTP and
packaged checks accept `--evidence` to preserve earlier release results.

## Report creation wizard

Failure cases are in the header of `backend/e2e/report_wizard_check.py`. Use the current reference
`upstream.py` from the preceding report verification, or fetch the pinned revision
in `database_packages/culture-history/UPSTREAM.txt`, into the evidence directory.

```powershell
.venv/Scripts/python.exe -m backend.e2e.report_wizard_check
.venv/Scripts/python.exe -X utf8 -W ignore::UserWarning -m backend.e2e.database_tools_check --evidence test-output/report-wizard-verification
.venv/Scripts/python.exe -m backend.e2e.packaged_database_smoke dist/<candidate>/RobotControl --wizard --evidence test-output/report-wizard-verification
```

`report_wizard_check` uses local SQL Server `.\HAMILTON` with Windows administrator
authentication to create uniquely named disposable databases and a SELECT-only
login. It verifies actual SQL permission denial and removes its owned SQL objects.
The packaged `--wizard` check uses the real disposable SQL fixture, checks DPAPI
storage, package upload and Excel from a relocated executable with Python/UV absent
from PATH. These commands neither inspect production rows nor change production
grants. Evidence is under `test-output/report-wizard-verification`.


## Configurable Database workspace

```powershell
.venv/Scripts/python.exe -m backend.e2e.database_workspace_check
# Copy the pinned upstream.py from the preceding report evidence first.
.venv/Scripts/python.exe -X utf8 -W ignore::UserWarning -m backend.e2e.database_tools_check --evidence test-output/database-workspace-verification
npm --prefix frontend run build
Set-Location frontend
$env:ROBOTCONTROL_E2E_EVIDENCE='../test-output/database-workspace-verification'
npx playwright test database-workspace.spec.ts --trace retain-on-failure
Set-Location ..
.venv/Scripts/python.exe -m backend.e2e.packaged_database_smoke dist/<candidate>/RobotControl --wizard --evidence test-output/database-workspace-verification
```

The workspace HTTP check reuses the real SQL fixture above and creates an additional
reader through the reviewed API. It verifies provisioning rollback, existing-login
rejection, write denial, schema-qualified browsing, operation target revision and
rollback/deduplication, nested import inspection and the zero-database example.
The legacy check retains scheduler safety gates and workbook parity. The browser
uses disposable package APIs and synthetic viewer data; its account flow stops at
review. The packaged wizard check now also creates a reader and browses the real
SQL fixture. These SQL checks require Windows SQL administrator access only to
create/drop UUID-named fixture objects; no production grants/rows are changed.

## System Status stall check

A manual browser/HTTP check for the polling request deadline. It bundles the real
System Status page (`MonitoringPage`) against a simulated loopback API; no robot, SQL or
credentials are used.

```powershell
uv run --locked python frontend/e2e/status-stall-probe.py
```

Open the printed URL, then: Hold next health response → Refresh → Allow new
requests. Within about 20 seconds the page must show "Request timed out" with
Refresh enabled and the status chip showing "Stale data"; Refresh then reconnects. Release stalled response last.
Evidence: `test-output/status-stall-evidence.json`. For remote-path timing, run
`backend/scripts/network_probe.py` on both computers (see its header).
