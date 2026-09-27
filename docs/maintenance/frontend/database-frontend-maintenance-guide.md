# Frontend database maintenance guide

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

The table and definition catalogues are 300 pixels wide when enough space is available. Below 900 pixels of workspace width, choosing an item opens its details; Back restores the catalogue. These transitions hide rather than unmount either side, preserving search and scroll. The table catalogue starts with Important tables only enabled. Has data and Empty are availability descriptions, not row counts.

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

1. **No tables:** clear Find a table and switch off Important tables only. Inspect the catalogue response if it remains empty.
2. **No rows:** clear applied search and filters through More. Distinguish an empty table from no matches or a failed refresh.
3. **Details are hidden on a phone:** choose a catalogue item. Back changes the visible pane; it does not discard the selected item's state.
4. **A long value is shortened:** use its cell button or the row-inspection button. Hidden grid columns remain available in the row inspector.
5. **Copy fails:** browser clipboard permission may be unavailable. The value remains selectable, and the reader shows that fallback.
6. **Reader has very little space:** inspect shared workspace sizing and toolbar wrapping before adding another viewport-height constant.

## Repeatable checks

`frontend/e2e/database-failure-scenarios.md` records failure cases written before the production changes. `frontend/e2e/database.spec.ts` exercises the built application against synthetic read responses at 390, 1280 and 1920 pixels. It covers table navigation, complete row inspection, search, expansion/focus, SQL Find/tabs, read failures and clipboard failure. The shared suite saves screenshots, traces and an HTML report; use the command in `frontend/e2e/scenarios.md` to repeat it. No unit tests were added for this change.

`inspection-pagination.spec.ts` adds last-page/page-jump and failed-page label checks, plus phone SQL Top/Bottom/Go to line. Its failure scenarios were recorded first in `inspection-labware-failure-scenarios.md`.

## Package-backed operations and retrieval (2026-09-27)

`DatabaseTools.tsx` supplies shared forms and package management. Operations and Manage
packages require a local admin; Data retrieval accepts any signed-in user. Experiment
selection uses paginated server search. Package fields and endpoints are documented
in [the contract](../../../database_packages/README.md).

Review shows the target and requires typed confirmation. Check result reuses its token;
never create a new token or silently retry after an uncertain response. Reports run in
the background and poll only while their section is active. Downloads are authenticated.
Changing report inputs clears the previous download to avoid mistaking it for new output.
