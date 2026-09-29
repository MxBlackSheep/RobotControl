# Frontend database maintenance guide

## Database settings and author workflow (2026-09-28)

The local-admin **Database settings** section (`DatabaseSettings.tsx`) shows saved
connections, their uses, package assignments and scheduling's active/pending target.
It reuses `ReportConnections` and `SourceMappings`; there is no second credential
store. The admin selects one server-persisted **Viewer database**; Tables and Stored
procedures display its name without a dropdown. Package rows show tool
counts, Download package, Connections, Update and Remove. Tool `kind` controls
Operations versus Data retrieval; the selector remains visible with one tool.

**Add tool**, **Edit report** and **Edit operation** use `ToolAuthoring.tsx`.
Prepared Python supplies the form, with no second input editor. Source/connections
sit beside the generated trial form, stacking on phones. File or connection edits
clear readiness. The backend checks the saved revision, source snapshot and installed
base before enabling. Reports need a successful workbook; operation trials call
preview only and expose no execution token. An explicit review checkbox permits
publishing. Supporting files and sibling tools are preserved by default; Replace
all files supports deletions/renames and rejects incomplete source sets. Parent
changes clear dependent answers recursively. Versions are suggested by the server.

**Schedule preparation** shows active setup first. **Change setup** reveals the
laboratory database; preparation implementation is under Advanced. The existing
laboratory connection is an explicit option, never a blank selection. Experiment
selection remains in each schedule, separate from installation settings.

`ReportWizard.tsx` remains only for older drafts; its endpoints stay compatible.
New additions use static TOOL declarations described in `database_packages/README.md`.
Import package ZIP retains existing package transfer; it does not adapt standalone
scripts. Inspection is not a correctness or sandbox guarantee. `ReportInputs` is
shared between trial and installed-tool forms.

Read-only account review describes capabilities before technical grants. The
Windows account is the application's process identity. Certificate trust stays
visible; successful connection saves remember the checkbox in this browser's
`database-certificate-trust` map under the exact server string. New servers default
to verification; connection failure never changes this preference.

The Database page is a read-only inspector for table rows, stored procedures and functions. Restore and Operations are separate existing tools with their existing permissions and confirmations. Viewing a SQL definition never executes it.

## Where the code lives

- `frontend/src/pages/DatabasePage.tsx` loads the table catalogue and selects the module section.
- `frontend/src/components/DatabaseTable.tsx` owns the selected table's query, row/cell inspection and exports.
- `frontend/src/components/StoredProcedures.tsx` loads definitions and provides the SQL, Parameters and Details tabs.
- `frontend/src/components/InspectionWorkspace.tsx` lays out the catalogue and detail area. Read [the shared workspace guide](inspection-workspace-maintenance-guide.md) before changing heights or breakpoints.
- `frontend/src/components/InspectionTextViewer.tsx` provides the SQL reading controls.
- `frontend/src/services/api.ts` supplies the existing `databaseAPI` request helpers.

## Navigation and layout

`components/navigation.tsx` defines the sidebar sections and URLs: `/database?section=tables`, `procedures`, `restore` and `operations`. Do not introduce another module navigation bar. `SectionPanel` retains visited sections; readers receive an `active` flag to avoid loading hidden sections.

The table and definition catalogues are 300 pixels wide when enough space is available. Below 900 pixels of workspace width, choosing an item opens its details; Back restores the catalogue. These transitions hide rather than unmount either side, preserving search and scroll. The table catalogue shows all schemas. The selected connection is visible above tables and procedures; Restore does not use that selection.

The workspace measures the space remaining below the page heading. The table scrolls locally with sticky column headers and a sticky row-inspection column; pagination stays below it. Avoid hardcoded viewport percentages. Extremely short windows can scroll the outer viewer to keep its controls reachable.

## Table reading and queries

Search text and column conditions are drafts until Apply or Enter is chosen. The query effect cancels or ignores superseded responses. Refresh retains useful rows while loading; failures explicitly label the retained rows. Switching to another table resets its query, while Back and Expand retain it.

Pagination includes First, Previous, Next, Last and a page-number input. `query` is the requested state; `displayedQuery` belongs to the last successful rows. Row numbers, footer ranges, page size and exports must use `displayedQuery`, so a failed page/filter request never relabels retained rows. Refresh retries the requested query. If the result count shrinks beyond the requested page, the reader requests the new last page. Page jumps accept only whole numbers within the known range.

The API request includes `page`, `limit`, `search`, `order_by`, `sort_direction` and serialized `filters`. Preserve these names. Search applies to supported scalar text, numeric and date columns; it does not include binary/complex columns. The backend validates column names and parameterizes values. Sorting and paging cannot promise a stable snapshot while records are being written.

Click a numbered row button to inspect **every** column, including columns hidden from the grid. Click a cell to inspect just its complete value. NULL and empty strings have distinct labels. Copy reports success or explains the manual select-and-copy fallback. JSON-shaped values are displayed as formatted text. Browsing does not modify a record.

More contains Columns, Export, Wrap cells and Clear search and filters. At least one grid column must remain visible. Expanded tables use a MUI full-screen Dialog; Escape restores focus to Expand. Query, scroll and column state live outside the Dialog.

## Exports

The export dialog offers Current page or All matching rows, in CSV or JSON. Both use the applied search, conditions, sorting and visible columns.

`databaseExport.ts` collects all matching data in 1,000-row requests. Cancellation, count changes, incomplete batches or its 50 MB memory bound stop the export with an explanation. Do not replace this with a single unbounded request. Concurrent database writes can affect a multi-request export; it is not a transaction snapshot. NULL remains NULL in JSON and becomes an empty CSV field.

## Stored procedures and functions

The catalogue supports name search and a definition-type filter. Selecting an item opens SQL by default. Parameters and Details have their own tabs, leaving the SQL reading area free of stacked metadata cards.

The compact SQL toolbar provides Find, Copy, Expand and More. Find reveals its field and previous/next match controls. Top and Bottom reach either end; More includes wrapping and Go to line. Line jumps accept an existing line number. Wrap preference is independent of logs. Parameters retain their type, length and direction from the server. Definition payloads are normalized so missing parameter arrays or SQL do not crash the page.

Refresh preserves the selected item by type plus name. If it disappeared from the refreshed response, the reader clears the selection and explains why. A failed refresh retains the previous definitions. The component requests fresh data on explicit Refresh and ignores results after it becomes inactive.

## Access rules

Restore remains available to admins or local sessions. Operations remains local-only. Backend checks remain authoritative. No SQL editing, procedure execution or database mutation was added to the viewers.

## When something looks wrong

1. **No tables:** check the selected connection and clear Find a table. Inspect the catalogue response if it remains empty.
2. **No rows:** clear applied search and filters through More. Distinguish an empty table from no matches or a failed refresh.
3. **Details are hidden on a phone:** choose a catalogue item. Back changes the visible pane; it does not discard the selected item's state.
4. **A long value is shortened:** use its cell button or the row-inspection button. Hidden grid columns remain available in the row inspector.
5. **Copy fails:** browser clipboard permission may be unavailable. The value remains selectable, and the reader shows that fallback.
6. **Reader has very little space:** inspect shared workspace sizing and toolbar wrapping before adding another viewport-height constant.

## Repeatable checks

`frontend/e2e/database-failure-scenarios.md` records failure cases written before the production changes. `frontend/e2e/database.spec.ts` exercises the built application against synthetic read responses at 390, 1280 and 1920 pixels. It covers table navigation, complete row inspection, search, expansion/focus, SQL Find/tabs, read failures and clipboard failure. The shared suite saves screenshots, traces and an HTML report; use the command in `frontend/e2e/scenarios.md` to repeat it. No unit tests were added for this change.

`inspection-pagination.spec.ts` adds last-page/page-jump and failed-page label checks, plus phone SQL Top/Bottom/Go to line. Its failure scenarios were recorded first in `inspection-labware-failure-scenarios.md`.

## Package-backed operations and retrieval (2026-09-27)

`DatabaseTools.tsx` supplies task forms; `DatabasePackages.tsx` owns installation review. Operations and Manage
packages require a local admin; Data retrieval accepts any signed-in user. Experiment
selection uses paginated server search. Package fields and endpoints are documented
in [the contract](../../../database_packages/README.md).

Review shows the target and requires typed confirmation. Check result reuses its token;
never create a new token or silently retry after an uncertain response. Reports run in
the background and poll only while their section is active. Downloads are authenticated.
Changing report inputs clears the previous download to avoid mistaking it for new output.


### Authoring and update workflow

Operations and Data retrieval use the full inspection height and width. A single
experiment input gets a 40/60 experiment-list/task layout; below 900px container
width the same mounted panes use Back navigation. Search and pagination stay with
the experiment list. Selecting the same experiment after Back retains its report;
selecting a different experiment clears the old result and error. One tool shows
its name as a heading; multiple installed tools show a chooser. Non-experiment
inputs continue to use the manifest's typed fields.

Manage packages inspects a chosen ZIP before installation. Review shows the
installed/incoming versions and detects unchanged, same-version/different-code and
older packages. Update beside a package rejects a different package's ZIP. The
activation request includes the reviewed installed hash so another administrator's
intervening update requires a fresh review. A request failure does not clear the
selected file. Unexpected report errors have a short message and expandable Details.

Package creation now has a saved wizard in Manage packages. `ReportWizard.tsx`
owns its draft, revision, inputs and trial; `ReportInputs.tsx` renders shared runtime
fields and cancels superseded dropdown requests. Parent changes clear all dependent
values. `ReportConnections.tsx` configures named local sources; packages map logical
aliases separately. Original uploads and completed handlers remain distinct. Editing
Python happens outside the browser. Removing drafts requires confirmation.

Unconfigured reports show Connection setup needed before generation, including on
phones. Local admins get Configure; ordinary users get concise setup guidance.
Multiple reports retain the labelled Report chooser. Updating the executable does
not replace installed packages. See the [authoring guide](../../../database_packages/README.md).

The report wizard has no browser check since 29 September 2026 (the old cases no
longer matched the screen). `backend.e2e.report_wizard_check` covers SQL permissions
and installation over HTTP; evidence goes to `test-output/report-wizard-verification`.


## Configurable connections and upload-first reports (2026-09-28)

`DatabasePage` owns the viewer connection ID, retained locally across visits. Source
changes clear the prior table/definition; section navigation retains the selection.
Source revisions refresh the workspace after connection settings change. The target
selector is only shown for tables/procedures, never for native Restore. Each table
request/export includes its captured source ID. Package operations use a separately
assigned writable target and repeat it in confirmation; reports use their aliases.

`ReportConnections` offers existing-account setup or reviewed reader creation. It
uses the same settings dialog from viewers, packages and the saved report wizard.
Administrator credentials are transient and cleared on completion/close. The server
owns permission enforcement and review tokens. Package Connections supports report
mappings plus Operation target; a package needing setup cannot run.

Reader creation distinguishes the new SQL login from the temporary administrator
identity. The Windows option uses RobotControl's process identity, which needs SQL
account-creation authority. A failed creation keeps connection fields, clears the
review and administrator credentials, and displays the backend's actionable cause.
The `account setup explains` browser case covers that retry flow and phone overflow.

`ReportWizard` starts with Upload Python or Try an example. The inspect endpoint
returns libraries/adaptation findings without executing Python. IDs/version/manual
library overrides are under Details. Compatible uploads become the runnable handler;
other scripts remain reference material until the author uploads an adapter. Replacing
Python clears old results/reviews. The example is an ordinary saved draft with zero
sources and bundled sample rows; it does not install a report or touch a database.

The wizard offers **Save and close** to retain work and **Discard and close** to
delete the current draft after confirmation. Discard uses the existing owner-checked
draft endpoint, creates no draft for an unsaved report, and leaves installed packages
unchanged. A failed deletion keeps the editor/confirmation open. Busy operations and
running trials block both exit actions. Keep editing, Escape or the backdrop dismisses
the confirmation without deleting the draft.

Focused browser check: `database-workspace.spec.ts` (settings, account review,
dependent choices, viewer switching, operation choices and certificate trust). SQL
permissions and transaction behavior are verified separately through HTTP with
disposable SQL data.

## Tool publication and history

`ToolAuthoring.tsx` uses Replace Python for the defining script, including renamed
files. Helpers are preserved; helper upload and complete replacement live under
Supporting files. Input forms remain derived from `TOOL['inputs']`.

Successful publication closes the editor and shows a versioned success message on
Manage packages. The backend retires the completed draft. A lost response retains
the publication request for safe retry. Optional change notes persist with drafts
and appear in History. `DatabasePackages.tsx` shows Excel report/Database operation
instead of zero-count labels; per-row Edit is the Python workflow, while the global
Import package ZIP action also accepts updates. History is metadata and file-change
names, not source rollback. Existing installations without records say so.
