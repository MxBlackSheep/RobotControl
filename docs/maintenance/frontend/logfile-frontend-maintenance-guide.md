# Frontend LogFile Page Maintenance Guide

## Shared page spacing

This page uses `PageContent` and `PageHeader` from `components/PageLayout.tsx`. The application shell supplies navigation, the breadcrumb and outer padding; do not add another outer Container or Back/breadcrumb row. Keep this module's functional tabs and controls. Operational content fills the space beside the sidebar; Maintenance uses the readable-width variant. See [the main application layout guide](main-application-frontend-maintenance-guide.md#shared-page-layout-september-2026) before changing page spacing.

This guide explains the **LogFile** page (top-level tab) used to browse and preview log files from fixed backend-approved folders.

Important: this page is **read-only**. Do not add file edit/delete actions casually.

---

## 1. Files You Must Know

- `frontend/src/pages/LogFilePage.tsx`  
  Main UI for source selection, folder/archive browsing, and text preview.

- `frontend/src/services/logFileApi.ts`  
  API wrapper for `/api/logfiles/*`.

- Navigation wiring:
  - `frontend/src/App.tsx`
  - `frontend/src/components/MobileDrawer.tsx`
  - `frontend/src/components/NavigationBreadcrumbs.tsx`
  - `frontend/src/hooks/useKeyboardNavigation.ts`
  - `frontend/src/components/KeyboardShortcutsHelp.tsx`

---

## 2. What the Page Supports

- Browse fixed log sources (provided by backend)
- Browse folders/files
- Open `.zip` files as archive folders (browse entries inside)
- Preview `.gz` files directly (backend decompresses)
- Preview normal text log files (`.trc`, `.txt`, `.md`, `.log`, etc.)
- Switch preview mode:
  - `Tail` (default)
  - `Head`

Note:
- The **Hamilton LogFiles** source is backend-filtered to **`.trc` files only**. If you do not see `.txt`/other files there, that is expected.

---

## 3. Local vs Remote Behavior

The page is available to both local and remote authenticated users, but source access is restricted per source by the backend.

Current policy:

- Local sessions:
  - Can access all configured sources (including `RobotControl Logs`)

- Remote sessions:
  - Can access `Python Log`
  - Can access `Hamilton LogFiles`
  - Cannot access `RobotControl Logs` (shown as `local only`)

Backend is the final authority (`403` if bypassed).

---

## 4. Page State Model (Mental Model)

The page has two browser modes:

1. `filesystem`
   - browsing actual directories/files under a selected source

2. `archive`
   - browsing entries inside a selected `.zip` file

`.gz` is not treated as an archive folder in the UI; it is previewed directly as a file.

---

## 5. Data Flow

1. Page load → `logFileApi.getSources()`
2. User selects source → `logFileApi.browse(sourceId, relativePath)`
3. Click file:
   - normal / `.gz` → `logFileApi.preview(...)`
   - `.zip` → `logFileApi.browseArchive(...)`
4. Click zip entry file → `logFileApi.previewArchive(...)`
5. Preview mode toggle (`Tail` / `Head`) reloads current preview

---

## 6. Locked File Handling

If backend returns `423 FILE_LOCKED`:

- Page shows a warning banner
- Browser list remains usable
- User can switch files/folders and continue

Do not convert this into a fatal modal. Locked files are expected during robot operation.

---

## 7. Common Tasks

| Task | Where | What to change |
|------|-------|----------------|
| Change preview default (`tail`/`head`) | `LogFilePage.tsx` | Update initial `previewMode` state. |
| Add filters/search in file list | `LogFilePage.tsx` | Filter `browseItems` before rendering; keep raw API data unchanged. |
| Change preview size | `logFileApi.ts` + backend `MAX_PREVIEW_BYTES` | Keep frontend/backend caps aligned. Backend cap is the real limit. |
| Add route/tab label changes | `App.tsx`, `MobileDrawer.tsx`, `NavigationBreadcrumbs.tsx` | Keep all labels in sync. |
| Change shortcut | `useKeyboardNavigation.ts` + `KeyboardShortcutsHelp.tsx` | Update both files together. |

---

## 8. Debug Checklist

1. Tab missing on desktop:
   - Check `tabItems` in `App.tsx`
   - Check route `/logfile` exists

2. Tab missing on mobile:
   - Check `navigationItems` in `MobileDrawer.tsx`

3. Breadcrumb label wrong:
   - Check `/logfile` route config in `NavigationBreadcrumbs.tsx`

4. `.zip` opens as normal file instead of archive:
   - Check file-click branch in `LogFilePage.tsx` for `.zip`

5. `.gz` previews fail:
   - Check backend response message
   - Confirm backend `/api/logfiles/preview` supports `.gz` (not archive endpoints)

6. Preview mode toggle does not refresh:
   - Check the `previewMode` effect in `LogFilePage.tsx`
   - Confirm a file is selected and preview is present


### September 2026: shared section navigation

`components/navigation.tsx` is the source of section names, URLs and UI permissions. Use `useModuleSection` and `moduleSectionUrl`; do not add another horizontal page tab bar. The sidebar supports expanded links, rail menus and mobile navigation. `SectionPanel` mounts on first visit and retains drafts/scroll within the page session. Components that poll must take an active flag and suspend their timer when hidden. Camera navigation never starts/stops a session. Database Restore remains admin **or** local; Operations and RobotControl logs remain local-only. Backend permissions still apply.


### September 2026: paged log browsing and reader

Use the Logs sidebar sections (Python logs, Hamilton traces, RobotControl logs). Source permissions still come from the backend; RobotControl logs require a local session. Missing/inaccessible sources show a retryable explanation. Each visited source keeps its own folder, search, page, selection and reading state until the page is left.

The file list defaults to 50 entries and offers 25/100. Filename search is submitted explicitly and applies to the **whole current directory before pagination**, including ZIP directories. It does not search file contents or recurse through the disk. Sort by Name/Modified/Size; type/date filters affect files while retaining reachable folders. The list retains its last successful folder/results if a request fails. New responses cannot overwrite later navigation.

The existing browse endpoints accept optional `search` (up to 200 characters), `file_type=all|text|traces|archives`, `modified_from`, `modified_to` (ISO dates), `sort_by=name|modified|size`, `sort_direction=asc|desc`, `page` and `limit` (up to 200). Calls omitting these options retain the old newest-first, first-200 behavior. Filesystem and ZIP routes share filtering/paging and deterministic name ties. The API remains read-only, uses configured roots and extension restrictions, and executes blocking filesystem work in FastAPI's worker pool.

Refresh files updates the directory list. Refresh in the reader updates the selected preview. Latest/Beginning remain limited to 1 MB; Find in preview searches only returned text (up to 500 highlighted matches), not the rest of the file. Details exposes the full path, Copy path and technical metadata. On narrow screens use Back to files and Reading tools. Expand opens a full-screen reader; Escape restores focus to Expand.

Follow latest is off by default. When enabled it refreshes a selected plain file every five seconds **after the preceding request settles**. It stops on source/file changes, hidden sections/documents and errors, and is unavailable for ZIP/gzip previews. Reading above the bottom keeps the scroll position; Jump to latest is offered when new content arrives. Failed same-file reads retain an explicitly stale preview. Source/path/archive-entry identity prevents same-name files from sharing previews.

Tests: `backend/tests/test_logfiles_api.py` covers large folders/ZIPs, sorting, filters, permissions and preview formats. `frontend/src/components/LogSourceBrowser.test.tsx` covers request races, refresh separation, stale retention, follow lifecycle and expanded-reader accessibility. Browser checks use read-only access; do not enable camera streaming or run methods merely to validate these views.
