# Database inspection failure scenarios

## Package and configuration workflows (before implementation, 2026-09-28)

- Export must use the installed version, exclude generated/cache/config files, preserve authored assets, and reinstall without executing during export. Unauthorized exports and missing packages fail. Old updates cannot replace an intervening version unnoticed.
- Editing downloads retain original Python and configured inputs; missing adaptation is visible before trying. Multiple report/operation choices retain the correct classification, form and target. No demonstration package ships installed.
- Connection settings expose assignments and uses. Certificate trust is remembered only for the same exact server after explicit successful setup, never on failed connections. Account review distinguishes target, new identity and temporary authority.
- Scheduling settings are local-admin-only. Review reads schema without preparation writes. Save rechecks configuration/source revision, robot idle, healthy safety store, recovery and active/queued work under launch protection. Active schedules must be disabled; existing bindings remain unchanged. Active and pending settings differ until restart; cancelling restores the original file. Changing sources after review must reject the save. Existing EvoYeast configuration and unrelated schedule edits retain their behavior.

Written before production changes for the September 2026 viewer work.

- A narrow screen puts the complete catalogue above the selected table or SQL; Back loses the current selection, search draft or scroll position.
- The table, toolbar or pagination exceeds the visible workspace; wide data makes the whole page scroll horizontally.
- Expand closes/reopens data requests, clears filters, resets SQL Find, or traps keyboard focus after Escape.
- A row inspector omits hidden columns, NULL, empty strings or long values; copy succeeds silently or reports success when the clipboard failed.
- Search applies on every keystroke, filtering ignores applied values, descending sort is lost, or older responses overwrite the current selection.
- A refresh failure clears useful data or presents old rows as a successful fresh response.
- Procedure parameters/metadata consume the definition area; mobile cannot reach SQL without scrolling past a tall list.
- SQL Find misses repeated matches, loses its term during expansion, or labels a partial search as a server-wide search.
- Empty procedure searches look broken; an item deleted by refresh remains presented as current.
- View-only actions accidentally call procedure execution or other mutation endpoints.

`database.spec.ts` checks these through the running application with synthetic read responses. Playwright retains screenshots and its HTML report as repeatable evidence. No unit tests are added.
# Portable actions and reports (2026-09-27)

Before implementation, exercise these boundaries with disposable data:
- Upload/update/remove a package; reject traversal, binaries, duplicate identifiers,
  missing libraries and incompatible contracts. Failed updates preserve the active version.
- Anonymous/remote/non-admin callers cannot manage packages or change the database.
- Preview is bound to the user, package version and inputs; wrong confirmation,
  repeated execution, missing experiments and SQL failures cannot cause unintended writes.
- Busy/unknown robot state, unresolved recovery and unavailable safety storage block
  changes. Scheduler launch and a database change cannot overlap.
- Report output matches upstream values, parent/plate choices, columns and formatting;
  downloads are private, bounded workers reject excess work, expired files are removed.
- SMTP pending/sent/error records appear through HTTP and the screen. Manual/test/recovery
  emails are included. Partial refusal and log-storage failure must not resend accepted mail.
- A relocated executable installs and runs packages without a system Python or UV.
# Authoring, updates and task workspace (2026-09-28)

- An existing script must remain untouched when creating a working package. The
  generated adapter must fail clearly until adapted; creating/building a package
  must not import or execute its Python code. Reject unsafe ZIPs, syntax errors,
  missing entry points and unsupported declared libraries before installation.
- Inspecting an update must not activate it or import Python. Show installed and
  incoming versions; reject a changed installation or a different package between
  review and activation. Keep the installed version when validation fails.
- A missing WellID currently crashes pandas 3 report generation. Preserve all
  selected cultures; if missing locations make the selection of a subset ambiguous,
  identify the plate/cultures instead of silently excluding or choosing them.
- A wide desktop must use the available width for experiment selection and task
  results. On a phone, Back must retain search, selection and completed download.
  Reject late searches; changing inputs must clear the previous result/error.
- Verify author-created ZIP through the actual upload/report HTTP path, the update
  review in the browser, and the relocated executable. Use disposable SQL rows;
  the actual experiment 333 data and SQL Server remain a separate VM check.

## Culture-history compatibility correction (2026-09-28)

The 1.0.1 missing-well guard above changed upstream selection behavior. Regression:
plate 985 contains an extra culture 98500000 with SQL NULL WellID alongside the
requested well-addressed cultures. The packaged report must match the original
script's legacy string conversion, ordering, first-N selection and workbook, not
reject the extra record or special-case a CultureID pattern. Also compare a selected
missing well and missing ancestral labels so restoring selection does not change
exported values. Use the pinned original script with legacy string inference as the
reference; keep that compatibility setting scoped to the synchronous verifier.
Install the new ZIP into the already-built executable and run the fixture report;
no frontend or executable rebuild is required for this package-only correction.
# Report wizard and read-only sources (2026-09-28, before implementation)

- Upload must not import Python. An unfinished adapter cannot be tried/installed.
- Draft Back/reload and edited-handler upload retain input/source settings. Stale
  saves and another administrator's draft requests must not replace a draft.
- Export contains no credentials; installing elsewhere requires source mappings.
- Missing mappings never use the writer. SQL Server permissions, not SELECT success
  or query scanning, must establish source eligibility. Reject writes, DDL, elevated
  permissions and executable user procedures; connection errors are actionable.
- Multiple sources, duplicate labels, typed values, empty choices, dependencies,
  rapid parent changes and forged values must behave consistently at trial and run.
- Cycles, unknown dependencies/sources and invalid queries fail without activation.
- Active jobs keep their source snapshot; failed/stale updates preserve packages.
- Legacy report output and operation guards remain unchanged. Verify the real SQL
  permission boundary separately; a SQLite adapter cannot establish that result.
- Desktop/phone: create, resume, try, download, install and choose among reports.
# Configurable workspace and upload-first authoring (2026-09-28)

Before implementation: changing the viewer target must not change scheduler,
labware, Restore or a pending operation. Check two disposable SQL databases with
different schemas (including duplicate table names); no writer fallback for an
unconfigured viewer/report. Reject remote/non-admin connection changes, writable
report mappings, changed operation configurations and stale UI responses.

Account creation: review before applying, no existing-login modification, escaped
identifiers, rollback on failed grants, one-off administrator credentials never
saved/logged, created identity can SELECT but cannot INSERT/UPDATE/DELETE/DDL.
Failed verification must not leave a saved or silently usable connection.

Upload: syntax errors, nested imports, unavailable and dynamic imports, wrong run
signature, replacement clearing old results. Upload must never execute Python.
Try the no-database example and resume a real draft; keep secrets out of downloads.
Check desktop plus one phone width, then the relocated packaged boundary.

## Read-only account setup errors (2026-09-28, before changes)

Reproduce an existing login name and an account without CREATE LOGIN authority
through HTTP with disposable SQL objects. Distinguish these from sign-in,
driver/connection and database-access failures without returning raw driver text
or credentials. A rollback/cleanup failure must not hide the original stage or
suggest that the new login was removed. Existing principals remain untouched.
The form must retain non-secret settings after a failed creation, clear authority
credentials, explain that the new login is separate from the administrator, and
display the returned reason. No new unit tests; extend focused HTTP/browser checks.
### Report discard, release contents and inherited EXECUTE (2026-09-28, before changes)

- Discarding a fresh report must close without creating a draft. For an autosaved/resumed draft, confirmation removes only that draft; cancel keeps it. Failed deletion must keep the editor open with its values. A running trial must still block deletion. Save and close must continue to retain the draft.
- Dropping broad pandas collection must remove its test suite from the frozen archive without losing pandas/openpyxl Excel generation in a relocated executable.
- A disposable database with a public EXECUTE grant on a diagram-style procedure must produce a newly provisioned reader that cannot execute it or write data. Existing-account validation must still reject EXECUTE. Failed post-creation verification must remove only the new login, including its pooled verification session; existing identities remain untouched.
# Simplified setup and report editing (2026-09-28)

- Viewer choice must persist on the server; a non-admin or stale source ID cannot select another database. Removing the selected connection must fail until reassigned.
- EvoYeast experiment selection must review without the optional reset procedure. Explicit reset steps still fail safely if it is missing. Default connection must be visible, not blank.
- Editing an installed report must retain sibling tools, supporting files, inputs, mappings and identifiers. Discard must leave installation untouched. A changed installed base or mapping must prevent publishing an old draft.
- Changing a parent choice must clear descendants; stale/forged child values must fail before reports or operations run. Opening an advanced query must not rewrite it.
- Report failure, timeout or process exit must leave the backend responsive and release its slot; report workers receive only the selected read connections. This is not a sandbox for hostile Python.
- Preview must use the same robot/scheduler gate as execution and roll back its transaction. Concurrent configuration and execution must acquire locks in the same order.
- Check one desktop and phone authoring flow, downloaded workbook, administrator restrictions, restart persistence and a relocated packaged worker. Retain commands, fixture identity and focused evidence.

## Python-defined reports and operations (before implementation)

- Importing a prepared Python file must not execute it. Reject nonliteral definitions,
  bad inputs/dependency cycles, missing entry functions, unavailable libraries and
  unsafe or duplicate supporting filenames. An ordinary script needs an explicit
  adaptation message. Never overwrite an existing definition silently.
- The same Add flow must reach a real report download and an operation preview,
  without editing a manifest or constructing a ZIP. Selecting another experiment
  clears its plate; forged values fail on the server. Relative helper imports work.
- Only the draft owner/local administrator can configure, try or enable. Report
  mappings cannot use writers. Operation trials use the robot safety gate and
  rollback, create no execution token and never call the execution function.
- Enabling requires a successful trial and explicit review for the current code
  and connection snapshot. Replacement, stale draft saves, failed trials, source
  edits, concurrent installed updates and restarts must not reuse old readiness.
- Existing packages, report drafts, sibling tools and supporting files remain
  usable. Export transfers code/definitions without local credentials or mappings.
- Check focused HTTP workflows plus desktop/phone browser addition and editing;
  then verify the prepared-Python route in a relocated Windows candidate.
