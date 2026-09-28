# Database inspection failure scenarios

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
