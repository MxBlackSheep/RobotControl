# Frontend Database Maintenance Guide

This write-up explains every moving part of the database browser UI. It is designed for maintainers with minimal React experience—follow the exact steps and you will avoid breaking the admin workflow.

---

## 1. High-Level Architecture

- `frontend/src/pages/DatabasePage.tsx`  
  Main screen with tabs for Tables, Stored Procedures, Restore, and Operations. Handles initial data loads, filters, and error banners.

- `frontend/src/components/DatabaseTable.tsx`  
  Heavy-lifting table viewer. Supports pagination, column filtering, CSV/JSON export, and cell inspection dialogs.

- `frontend/src/components/StoredProcedures.tsx`  
  Lists stored procedures and allows execution with parameters. Uses the same Axios client.

- `frontend/src/components/DatabaseOperations.tsx`  
  Collection of maintenance actions (e.g., reindex, stats updates) exposed in the Operations tab.

- `frontend/src/components/DatabaseRestore.tsx`  
  UI for triggering restores and showing backup metadata.

- `frontend/src/services/api.ts` (`databaseAPI`)  
  Wrapper around the REST endpoints for tables, stored procedures, and status.

**Rule of thumb:** Keep network calls in the page or the specific component responsible for the feature. Don’t have random child components call `fetch` directly; use the `databaseAPI` helpers so error handling and headers stay consistent.

---

## 2. Typical User Journey

1. **Page mount** → `DatabasePage` calls `loadTablesAndStatus()` with `showImportantOnly = true`.  
   - Fetches `/api/database/tables?important_only=true`, maps response into `TableInfo[]`, and updates `tableStats`.

2. **Tables tab**  
   - On selecting a table (`handleTableSelect`), `DatabaseTable` loads data via `databaseAPI.getTableData(tableName, page, limit, params)`.  
   - The component memoises columns and rows, handles pagination events, and uses a Drawer for filters.

3. **Stored Procedures tab**  
   - `StoredProcedures` fetches the list once (`databaseAPI.getStoredProcedures`).  
   - Running a procedure posts to `/api/database/execute-procedure` with `procedure_name` and `parameters`.

4. **Restore tab**  
   - `DatabaseRestore` displays available backups (from `/api/admin/backup/list`) and exposes restore/delete actions (admin token required).

5. **Operations tab**  
   - `DatabaseOperations` groups actions (clear cache, rebuild indexes). Each button maps to a backend endpoint exposed under `/api/database/...`.

6. **Error handling**  
   - Any failure sets `error` in `DatabasePage`, which renders `ServerError` with retry buttons.

---

## 3. Key State & Props

- `DatabasePage` state:
  - `tables` – list of tables shown in the sidebar.  
  - `selectedTable` – currently viewed table name.  
  - `showImportantOnly` – toggles important-only filter.  
  - `activeTab` – which MUI tab is visible (Tables/Procedures/Restore/Operations).  
  - `tableStats` – counts displayed in the tooltip.

- `DatabaseTable` state:
  - `data` (columns, rows, totals) – transformed backend payload.  
  - `page`, `rowsPerPage`, `sortColumn`, `filters`, `searchTerm` – all trigger data reloads when changed.  
  - `selectedCell` – opens the detail dialog for long values.  
  - `exportMenuAnchor`, `filterDrawerOpen` – UI controls.

- Props to keep consistent:
  - `DatabaseTable` expects `tableName` and an `onError` callback.  
- `StoredProcedures` and `DatabaseOperations` rely on `onError`/`onSuccess` to surface issues; `DatabaseRestore` only fires `onError` while loading its backup list—restore failures must stay inside the status dialog so the page doesn’t show double errors.

---

## 4. Working With API Helpers

1. **Use `databaseAPI` methods** (`getTables`, `getTableData`, `getStoredProcedures`, etc.). They automatically use `axios` and include the auth header.  
2. **Pass params explicitly.** Pagination uses parameters `page` and `limit`; filters are encoded as JSON via `params.filters = JSON.stringify(...)`. Keep that shape if you add new operators.  
3. **Normalise responses** inside each component. The backend returns `columns` and `rows` as objects; `DatabaseTable` converts them to arrays to match MUI’s expected format.
4. **Throttle re-renders.** Expensive state (like the table data) is wrapped in `useMemo`. Keep these memos if you add fields or rows so performance stays acceptable on big tables.

---

## 5. Common Maintenance Tasks

| Task | Where | Instructions |
|------|-------|--------------|
| Change the default filter (important tables) | `DatabasePage` (`showImportantOnly` state) | Flip the `useState(true)` default. Update tooltip strings to match the new default. |
| Add column-specific tooltips | `DatabaseTable` rows | Modify the map that renders rows and add `Tooltip` around `TableCell`. |
| Support additional filter operators | `DatabaseTable.tsx` (`ColumnFilter`) | Extend the `operator` union and update backend interpretation. Add UI controls in the filter drawer. |
| Enable CSV export in a new format | `DatabaseTable` export handlers | Adjust the `handleExport` logic to map rows to your desired shape before building the download. |
| Display table row counts in the sidebar | `DatabasePage` list render | Include `table.row_count` when mapping to `<ListItemButton>`. Remember to update the data mapping in `loadTablesAndStatus()`. |

---

## 6. Extending or Modifying Behaviour

### 6.1 Add a chart/visualisation for a table
1. In `DatabasePage`, add another tab (e.g., “Visualise”).  
2. When selected, call a new component that uses the already-fetched data or triggers `databaseAPI.getTableData` with a specific shape.  
3. Use a chart library (Recharts, etc.) and document the expected data format in the component.

### 6.2 Add a search across all tables
1. Provide a new text input in the header.  
2. On submit, call a backend endpoint that supports global search (if available).  
3. Show results in a temporary list or direct the user to the relevant table (set `selectedTable` and hand `DatabaseTable` a prebuilt filter).

### 6.3 Allow editing table rows (admin only)
1. Add edit/delete buttons to each row.  
2. Wire them to new endpoints (PATCH/DELETE).  
3. After a mutation, call `loadData()` to refresh the table and keep pagination intact.

---

## 7. Quick Reference

| Function / Component | Purpose | Notes |
|----------------------|---------|-------|
| `DatabasePage` | Page layout + orchestration | Controls tabs, filters, and error banners. |
| `DatabaseTable` | Render tabular data | Supports pagination, filters, exports. Keep `loadData()` logic intact. |
| `databaseAPI.getTables(importantOnly)` | Fetch important/all tables | Returns `table_details`, `important_count`, `all_count`. |
| `databaseAPI.getTableData(name, page, limit, params)` | Load table rows | Accepts optional filter/sort params encoded as JSON. |
| `StoredProcedures` | Run stored procedures | Expects backend to return parameter metadata. |
| `DatabaseRestore` | Restore backups | Uses admin endpoints `/api/admin/backup/*`. Requires admin role. |

---

## 8. When Something Goes Wrong

1. **Tables list is empty**  
   - Backend likely returned `important_count=0`. Toggle “Important tables only” off to confirm the API is healthy. Use browser dev tools to inspect the response payload.

2. **Table viewer keeps reloading**  
   - Check dependencies on `useEffect`. If you added state to `DatabaseTable` without memoising, you may trigger an infinite loop (e.g., forgetting to skip `loadData` when `tableName` is empty).

3. **CSV download is garbled**  
   - Ensure you’re stringifying rows correctly (wrap values that contain commas). Check the MIME type and file extension in the download helper.

4. **Restore tab shows 401**  
   - Only admins can see backup endpoints. Confirm the signed-in user has the `admin` role; otherwise hide the tab via `user?.role`.

5. **Filters never apply**  
   - Inspect the network request; the backend expects `filters` as JSON string. Verify you updated both the UI state and the serialization logic when adding new operators.

Follow these instructions and the database UI will stay easy to maintain and hard to break.
