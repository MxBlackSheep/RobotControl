# Extend section navigation and improve Database / LogFile browsing

Status: implemented 14 September 2026 in separate navigation, Database and Logs commits. See implementation notes for validation and the packaged candidate.

## Findings

- At 1280×720, the Database table list is about 178px wide and clips long names, while unused table space occupies most of the page. On a narrow screen the entire table list sits above the selected table.
- DatabasePage displays 1,000 rows whenever the API says a table has data. The inspected Experiments table actually reports 33 rows. The placeholder must be removed.
- DatabaseTable advertises search across all columns but does not send or apply that search. Entering an unmatched search string left the displayed rows unchanged. The sort direction also stays in frontend state: the API accepts only the column and SQL sorts ascending.
- Table/filter loading uses overlapping effects and replaces the table with a spinner. Table-list refresh replaces the whole page. Slow responses can overwrite newer selections because there is no request identity check.
- The export implementation requests the entire row count as one page, although the table API caps pages at 1,000 rows. Large exports need bounded requests and explicit scope.
- The Python log source currently contains 1,802 items; the API returns only the first 200. There is no paging or filename search to reach the remainder.
- The log text starts around 515px down the desktop screen. On mobile, the long file list appears before the preview. Long names clip horizontally; metadata chips and the source controls consume substantial space.
- Log Refresh reloads directory entries only, leaving selected preview content unchanged. Failed directory loads clear existing entries; directory changes can leave an old preview visible. Requests are not protected against out-of-order completion.

Relevant code: [navigation](../../frontend/src/components/navigation.tsx), [Database page](../../frontend/src/pages/DatabasePage.tsx), [Database table](../../frontend/src/components/DatabaseTable.tsx), [LogFile page](../../frontend/src/pages/LogFilePage.tsx), [database API](../../backend/api/database.py), [database service](../../backend/services/database.py), [log API](../../backend/api/logfiles.py).

## 1. Shared section navigation

Apply the Scheduling nested-sidebar pattern to every function with meaningful sections:

| Function | Sidebar sections | Default |
| --- | --- | --- |
| Database | Tables, Stored procedures, Restore, Operations | Tables |
| Camera | Video archive, Live streaming | Video archive |
| Labware | Tip tracking, Cytomat | Tip tracking |
| LogFile (display label: Logs) | Python logs, Hamilton traces, RobotControl logs | First permitted available source |
| Administration | User accounts, Password reset requests | User accounts |
| Scheduling | Existing seven sections | Schedules |

Dashboard, Maintenance, System Status and About remain direct destinations; they currently do not need an artificial intermediate section.

- Generalize the shared navigation registry, section URL helper and section hook; Sidebar and breadcrumbs consume the same definitions. Remove the corresponding module-level horizontal tabs and the duplicate log-source selector.
- Use stable links such as `/database?section=tables`, `/camera?section=live`, `/labware?section=cytomat`, `/logfile?section=hamilton` and `/admin?section=password-resets`. Preserve existing base URLs and Scheduling links. Back/Forward and reload resolve the same section; unknown or unauthorized section names fall back safely.
- Preserve existing access rules, including local-only database Operations and RobotControl logs, admin-only Administration/Notifications, and the existing Restore permission rule. Navigation visibility does not replace backend enforcement. A permitted but unavailable log source shows an explanation rather than appearing empty.
- Keep the 240px/64px desktop sidebar and mobile overlay. Expanded groups and collapsed section menus use the same keyboard/accessibility behavior. Retain the Scheduling recovery warning.
- Keep controls inside a task where they belong: restore input modes, notification settings subviews, procedure/function accordions and log beginning/latest controls are not additional top-level functions.
- Preserve page-session selections, search, paging and scroll when moving between sibling sections. Explicitly retain or guard unsaved Labware and settings drafts. Avoid keeping hidden polling/stream components active just to retain state. Navigation must not start/stop camera streaming, run maintenance, restore data or execute procedures.

## 2. Database browsing

### Layout and interaction

- Use a master/detail workspace: a collapsible 280–320px table panel and the remaining width for rows. Add Search tables and put Important / All filtering inside that panel, where it is relevant.
- Show full names on hover/focus and in the selected-table heading. Avoid a horizontal scrollbar for the table-name list. Use actual metadata; do not invent schema names or row counts. Show Has data / Empty when only that information is available, and the real total for the selected table.
- At narrow content widths, switch between Choose table and the selected table with a Back to tables control; do not stack the whole catalogue above the data.
- Use one compact table toolbar: search, Filters with applied-count indicator, Columns, Refresh and Export. Keep a persistent column header and pagination footer around one table scrolling area. Default to 25 rows, with 50/100 options. The Columns menu hides/shows columns for browsing without changing export scope implicitly.
- Show explicit NULL versus empty strings. Allow keyboard access to complete cell values in a MUI dialog; remove duplicate custom modal focus management.
- Keep existing rows during refresh, with a small loading indicator and last successful update. Preserve filters, page, focus, column choices and scroll. Distinguish initial loading, empty table, no matches and failed refresh.

### Correctness

- Add backward-compatible validated `search` and `sort_direction` parameters to table reads. Search the complete table across supported scalar columns, not just the loaded page. Use parameterized values and allowlisted columns/operators/directions, bounded query execution and existing SQL Server compatibility.
- Search and filter editing use draft values with Apply/Enter and Clear. Fetch only the applied query, avoiding a database request for every keystroke. Counts and rows use the same search/filter conditions.
- Consolidate overlapping fetch effects into one request lifecycle. Cancel/ignore stale requests when table or query changes. Tie-break sorting with a reliable unique key where available; do not promise snapshot-stable paging for tables without one or during concurrent writes.
- Keep CSV/JSON export, explicitly offering Current page and All matching rows. Preserve the applied filter/search/sort. Fetch in bounded pages, report progress/cancellation, and never silently truncate or claim all rows when only a page was exported. Make the concurrency limitation clear if the database changes during a multi-request export.
- Stored procedures use the same searchable list/detail approach and retain definition/parameter views. Restore and Operations keep their existing behavior and confirmations.

## 3. Log browsing and reading

- Use a compact location row with clickable folder/archive breadcrumbs, Up and Refresh files. Sources live beneath Logs in the sidebar.
- Use a narrower collapsible file panel (roughly 320–400px) and allocate the rest to preview. Name, Modified and Size are distinct sortable fields; show a readable shortened filename with its full name/path accessible in details and Copy path.
- Add filename search in the current directory, type/date filters and server-backed paging (50 by default; 25/100 options). Show the full matching total. Search must cover all directory entries before pagination, including entries beyond the current 200-item cap. It does not read every log's contents or recursively search the whole disk.
- Extend both directory and ZIP-entry browsing with optional validated query/paging/sort fields, preserving existing callers and the allowed source roots, extension restrictions and local-access rules. Keep response sizes bounded. Sort ties deterministically; retain the selected file by source + relative path + archive entry, never filename alone.
- Preview header: selected filename, modified time, Refresh preview, Latest / Beginning, Find in preview, Wrap lines and Expand preview. Move encoding/scanned-byte details behind Details; retain a clear truncation indicator and the existing 1MB preview bound. Find in preview searches only the returned text and says so.
- On narrow screens, selecting a file opens the reader with Back to files; preserve file-list position. Use a full-screen reader option on desktop too. Keep text size readable and keyboard navigation complete.
- Make refresh scope explicit. Refresh files preserves the selected identity; Refresh preview rereads that exact file. Optional Follow latest is off by default and only polls the selected plain-text file while visible, with no overlapping requests. Stop following on source/file change, failure or unmount. Only scroll to the end when the operator is already there; otherwise offer Jump to latest. Do not repeatedly decompress archives in follow mode.
- Preserve useful content on same-location refresh failure and mark it stale. On navigation, clear or explicitly label the old preview until the new target loads. Reject late responses after source/path/selection changes. Show distinct missing, inaccessible, locked, binary and empty states.

## Delivery and validation

1. Commit shared section navigation and its page integrations.
2. Commit Database browsing and the small read-only API corrections.
3. Commit Logs browsing/reader and backward-compatible directory paging.

No SQLite migration, catalogue repair, filesystem mutation, automatic procedure execution or scheduler changes are needed. This work is mainly frontend, but working whole-table search/descending sort and access to older logs require read-only backend changes.

Add focused tests for permissions, direct URLs/history, draft retention, camera lifecycle, actual counts, search/sort/filter consistency, export paging, stale responses, and large directory/archive lists exceeding 200 entries. Verify long names, empty/null values, missing/locked files, delayed responses and refresh recovery. Review at 390, 1280 and 1920px, expanded/collapsed navigation, keyboard access and zoom. Native browser zoom needs an operator check if the automation browser still lacks that control.

Update maintenance guides and implementation notes with each implementation commit. Run relevant frontend/backend tests, the full backend regression suite, frontend build, resource embedding and isolated Windows packaging. Use disposable fixtures and read-only live inspection; preserve runtime data and remove validation artifacts.
