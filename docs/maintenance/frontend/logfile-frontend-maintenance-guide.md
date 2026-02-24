# Frontend LogFile Page Maintenance Guide

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
