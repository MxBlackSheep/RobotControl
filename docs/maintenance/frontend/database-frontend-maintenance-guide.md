# Frontend database

The Database page: read-only table and definition viewer, Restore, Operations, Data retrieval,
Manage packages and Database settings. Server behavior, permissions and safety rules are in
[the backend database guide](../backend/database-maintenance-guide.md); the package format and
authoring steps are in [database_packages/README.md](../../../database_packages/README.md).

## Ownership

- `pages/DatabasePage.tsx` chooses the section and loads the table catalogue. It reads the one
  server-chosen viewer from `/api/database/tools/viewer-sources` and passes its ID to each read;
  there is no per-browser viewer choice or dropdown. A changed viewer or revision clears the
  selected table and definition; moving between sections keeps them.
- `DatabaseTable.tsx` owns the selected table's query, row and cell inspection and exports;
  `databaseExport.ts` collects and formats export rows.
- `StoredProcedures.tsx` loads definitions and shows SQL, Parameters and Details tabs;
  `InspectionTextViewer.tsx` provides the SQL reading controls.
- `InspectionWorkspace.tsx` lays out catalogue and details; read
  [the shared workspace guide](inspection-workspace-maintenance-guide.md) before changing
  heights or breakpoints.
- `DatabaseRestore.tsx`: backup list, restore and maintenance mode.
- `DatabaseTools.tsx`: Operations and Data retrieval task forms; `ReportInputs.tsx` renders
  inputs for installed tools and trials.
- `DatabasePackages.tsx`: Manage packages. `ToolAuthoring.tsx` adds and edits Python-defined
  tools; `ReportWizard.tsx` only resumes older, non-code drafts and its endpoints stay compatible.
- `DatabaseSettings.tsx`: saved connections and their uses, the viewer database and Schedule
  preparation. `ReportConnections.tsx` (with `SourceMappings`) is the single connection editor,
  reused by settings, packages and authoring.
- `services/api.ts` supplies `databaseAPI`.

## Sections and access

`components/navigation.tsx` defines the sidebar sections `/database?section=tables`,
`procedures`, `restore`, `operations`, `retrieval`, `packages` and `settings`; there is no second
section bar. `SectionPanel` keeps visited sections mounted, and readers receive `active` so hidden
sections do not load or poll.

- Tables, Stored procedures and Data retrieval: any signed-in user.
- Restore is visible to admins or local sessions. Executing a restore requires a local
  session with role `admin` or `user`; remote administrators can see the section but the API
  rejects their restore request.
- Operations, Manage packages and Database settings: local administrators only; the page does
  not render them for others.

The backend is authoritative for every request. The viewers never edit SQL, execute
procedures or change data.

## Restore feedback

The Restore form is capped at 1120px and aligns with the module heading. Source
tabs sit on the form surface, without a raised nested panel. Refresh List sits beside
the managed backup selector (below on phones). The selector shows the filename;
the full selection details and description appear once below it. Metadata retains
the Valid/Invalid indicator and its expandable database/server/timestamp fields.
Actions follow a divider. All restore confirmations and request ownership remain
in `DatabaseRestore.tsx`.

Restore requests use a 660-second timeout: the backend's 600-second restore allowance
plus a minute of overhead. Other API calls retain the shared 10-second timeout.
The confirmation stays busy with Restore and Cancel disabled until a response or timeout.

`DatabaseRestore.tsx` checks the restore response's `success` flag, including HTTP 200
responses. Failure shows a `StatusDialog` with the server message and `data.error_details`
(or a fallback), keeps the selected file and confirmation checks for retry, and does not
activate maintenance. HTTP errors show the server's `detail`. Success closes and resets
the confirmation and activates the existing maintenance recovery flow. Since the request
waits for SQL, success says **Restore Completed**. `data.warnings` remain visible;
a completed restore with warnings uses warning styling. Failure also includes recovery warnings.

The `.bck` browser reads `data.items` inside the standard API response body. Editing
Current Directory changes a draft; Enter or Go loads it. Navigation clears selection,
ignores older requests and preserves the trailing slash at a drive root. Close/reopen
also clears selection. After a load the box shows the server's resolved `current_path`
only if the submitted text is unchanged; a newer draft stays available for Enter/Go;
Parent Directory splits on `\` or `/`. Directory errors show `error.details` from the
standard error body (then `message`, then FastAPI `detail`) and allow retry. The selected path is inline. `frontend/e2e/database-restore.spec.ts`
covers both file types, failure details, retry, HTTP errors and success using synthetic API
responses; the real SQL restore boundary is covered by `backend/e2e/backup_restore_check.py`.

## Tables

The catalogue (300 pixels when space allows) lists all schemas, with search; labels mean Has
data or Empty, not row counts. Below 900 pixels of
workspace width, choosing an item shows its details and Back returns; both sides stay mounted,
keeping search, drafts and scroll. The workspace fills the space below the heading; the table
scrolls inside it with sticky headers and a sticky row-inspection column, and pagination stays
below. Avoid viewport-percentage heights.

- Search text and column conditions are drafts until Apply or Enter. The single query effect
  cancels or ignores superseded responses. Refresh keeps rows while loading and labels them if
  the refresh fails. Switching table resets the query; Back and Expand keep it.
- `query` is the requested state and `displayedQuery` belongs to the rows on screen. Row
  numbers, footer ranges, page size and exports use `displayedQuery`, so a failed request never
  relabels old rows. If the result shrinks below the requested page, the last page is requested.
  Page jumps accept whole numbers in range.
- Requests send `page`, `limit`, `search`, `order_by`, `sort_direction` and serialized
  `filters`; keep these names.
- The numbered row button shows every column, including hidden ones; a cell button shows its
  complete value. NULL and empty strings are labelled differently, JSON-shaped values are
  formatted, and Copy reports success or explains the manual fallback.
- More holds Columns (at least one stays visible), Export, Wrap cells and Clear search and
  filters. Expand uses a full-screen Dialog; Escape returns focus to Expand, and query, scroll
  and column state live outside the Dialog.

**Exports** offer Current page or All matching rows, as CSV or JSON, using the applied search,
conditions, sort and visible columns. All matching rows are fetched in 1,000-row pages;
cancellation, a changed row count, a short page or more than 50 MB stops the export with an
explanation. Do not replace this with one unbounded request. An export is not a transaction
snapshot. NULL stays null in JSON and becomes an empty CSV field.

## Stored procedures and functions

Name search and a type filter; selecting opens SQL. Parameters (type, length, direction) and
Details have their own tabs. The toolbar has Find with previous/next, Copy, Expand and More
(wrap, Go to line); Top and Bottom reach either end. Wrap preference is stored separately from
log viewers. Missing parameter arrays or SQL must not crash the page. Refresh keeps the selection
by type and name, explains when it disappeared, keeps the previous definitions on failure, and
ignores results after the section becomes inactive.

## Operations and Data retrieval

- One experiment input gives a 40/60 experiment-list/task layout; below 900 pixels of
  container width the same mounted panes use Back. Experiment search and paging are
  server-side. Returning to the same experiment keeps its result; another clears it. One tool
  shows its name; several show a chooser.
- A report without its connections shows "Connection setup needed"; local admins get
  Configure. Reports run in the background and poll only while their section is active.
  Changing inputs clears the previous download. Changing a parent input clears dependent
  answers, and superseded choice requests are cancelled. Unexpected errors have a short message
  and expandable Details.
- An operation preview shows the target and requires typing the confirmation value. After an
  uncertain response the button becomes **Check result**, which resubmits the same token and
  returns the saved result; never create a new token or retry silently.

## Manage packages

- Each package row shows Excel report or Database operation, and offers Edit, Download package,
  Connections (report mappings and operation target), History and Remove. A package that needs
  setup cannot run. History lists metadata and file-change names, not source rollback; older
  installations say they have none.
- **Import package ZIP** inspects first. Review shows installed and incoming versions and flags
  unchanged, same-version-different-code and older packages; installing sends the reviewed
  package ID and installed hash, so another administrator's change requires a new review. A
  failed request keeps the chosen file.
- **Add tool** and **Edit** open `ToolAuthoring`. The form comes from the Python's
  `TOOL['inputs']`. Replace Python replaces the defining script, even when renamed; helpers are
  kept, and helper upload and Replace all files live under Supporting files. File or connection
  edits clear readiness. Reports need a successful workbook; operation trials only preview and
  expose no execution token. Publishing needs the review checkbox. The optional change note
  appears in History. Success returns to the list with a versioned message; after a lost
  response the exact publication request is kept so Retry works although the draft was retired.
- `ReportWizard` offers Save and close, and Discard and close (confirmed; deletes only the
  draft). Busy work or a running trial blocks both; Keep editing, Escape or the backdrop dismiss
  the confirmation. Removing a draft from the list also asks first.

## Database settings

- Shows each saved connection with its uses (viewer, packages, scheduling now or after restart).
  **Viewer database** is saved on the server for everyone.
- Connection setup offers an existing account or **Create read-only account**, which reviews
  capabilities before grants. Administrator credentials are transient and cleared on success,
  failure or close; a failed creation keeps the non-secret fields and shows the server's cause.
  The Windows option uses RobotControl's process identity. Certificate trust is remembered per
  exact server string in this browser's `database-certificate-trust` storage, only after a
  successful save; new servers default to verification.
- **Schedule preparation** shows the active setup first; **Change setup** reveals the laboratory
  database, with the preparation rules under Advanced. The existing laboratory connection is an
  explicit option, never a blank. Review lists affected schedules; saving applies after restart
  and shows Saved separately from Active, with **Cancel change**. Experiment selection stays in
  each schedule.

## Checks

Build with `npm --prefix frontend run build`; commands and evidence folders are in
[frontend/e2e/README.md](../../../frontend/e2e/README.md). Failure cases are in each spec's header:

- `database.spec.ts`: table navigation, row inspection, search, expansion and focus, SQL Find
  and tabs, read and clipboard failures, no write calls.
- `inspection-pagination.spec.ts`: last page, page jump, failed-page labels, SQL Top, Bottom
  and Go to line on a phone.
- `database-workspace.spec.ts`: settings, viewer switching, account setup failure, dependent
  choices, operation choices, certificate trust.
- `database-tools.spec.ts`: delivery log statuses.

Manage packages, `ToolAuthoring` and `ReportWizard` have no browser check; their server
workflows are covered by the HTTP checks in the backend guide. Vitest: `DatabaseTable.test.tsx`
(`npx vitest run` from `frontend`).

## Troubleshooting

- **No tables:** check the viewer database in Database settings and clear Find a table; then
  inspect the catalogue response.
- **No rows:** clear search and filters through More; distinguish an empty table from no
  matches or a failed refresh.
- **Details hidden on a phone:** choose a catalogue item; Back switches panes without losing
  the selection.
- **Value shortened:** use its cell button or the row inspector, which also shows hidden columns.
- **Copy fails:** clipboard permission may be missing; the value stays selectable.
- **Reader has very little space:** check shared workspace sizing and toolbar wrapping before
  adding another viewport-height constant.
