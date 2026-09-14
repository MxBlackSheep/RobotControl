# Backend LogFile API Maintenance Guide

This guide explains the backend API used by the **LogFile** page.  
Purpose: provide a **read-only**, **allowlisted** log browser with preview support for normal text logs and compressed history logs.

---

## 1. Files You Must Know

- `backend/api/logfiles.py`  
  Main LogFile API router (`/api/logfiles/*`).

- `backend/main.py`  
  Includes the router so the frontend page can call it.

- `backend/api/dependencies.py`  
  `require_local_access` is used to keep LogFile access local-only.

---

## 2. API Endpoints (Current)

- `GET /api/logfiles/sources`  
  Returns fixed source folders and availability status.

- `GET /api/logfiles/browse`  
  Lists directories/files under one source using `source_id + relative_path`.

- `GET /api/logfiles/preview`  
  Text preview for normal files and `.gz` files (`head`/`tail` mode).

- `GET /api/logfiles/archive/browse`  
  Browse entries inside a `.zip` archive.

- `GET /api/logfiles/archive/preview`  
  Preview a text file entry inside a `.zip` archive.

All endpoints are authenticated and local-only.

---

## 3. Security Model (Important)

This API intentionally does **not** accept arbitrary absolute paths from the frontend.

It uses:

1. `LOGFILE_SOURCES` allowlist (fixed roots)
2. `source_id` + `relative_path`
3. Relative path sanitization (rejects absolute paths and `..`)
4. Root containment check after path resolution

It also uses **per-source access policy** (`access_scope`):

- `Python Log` / `Hamilton LogFiles`: `all_authenticated`
- `RobotControl Logs`: `local_only`

If you add a new source, add it to `LOGFILE_SOURCES` and keep a stable `id`.

---

## 4. Locked / In-Use Files

Some log files may be open by HxRun or other programs.

Current behavior:

- If Windows allows shared read access, preview works normally.
- If the file is locked/inaccessible, API returns:
  - HTTP `423`
  - standardized error code: `FILE_LOCKED`

The frontend shows a warning and keeps the rest of the page usable.

---

## 5. Compression Support

- `.gz`  
  Preview is handled directly in `/preview` (decompress server-side, return text preview only).

- `.zip`  
  Use archive-specific endpoints:
  - `/archive/browse`
  - `/archive/preview`

The backend does not extract archives to disk for previewing.

### Source-specific file filtering

- `Hamilton LogFiles` source is intentionally filtered to `.trc` files only.
- Direct preview calls for other extensions in that source return a validation error.
- Reason: the folder may contain non-log files and operators only want TRC logs there.

---

## 6. Text Decoding and Formats

The backend tries multiple text encodings for previews:

- `utf-8`
- `utf-16`
- `cp1252`
- `latin-1`

This helps with mixed log types (`.trc`, `.txt`, `.md`, `.log`, etc.).

If the content looks binary, the response marks `is_binary=true` and does not return text content.

---

## 7. Preview Limits

- Preview is capped server-side (`MAX_PREVIEW_BYTES`, currently `1 MB`)
- Supports `mode=head` and `mode=tail`

Reason:
- avoids huge payloads
- keeps UI responsive
- still useful for active troubleshooting

---

## 8. Common Tasks

| Task | Where | What to change |
|------|-------|----------------|
| Add a new log source | `backend/api/logfiles.py` (`LOGFILE_SOURCES`) | Add `id`, label, path. Keep `id` stable for frontend selection. |
| Increase preview size cap | `backend/api/logfiles.py` (`MAX_PREVIEW_BYTES`) | Raise carefully; large previews can slow the UI. |
| Add more archive formats | `backend/api/logfiles.py` | Extend preview/browse helpers. Keep all archive reads in-memory (no extraction to disk). |
| Change local-only policy | `backend/api/logfiles.py` endpoint dependencies | Replace `require_local_access` only if you explicitly want remote log viewing. |

---

## 9. Debug Checklist

1. `403` on every LogFile request:
   - Check caller is local (`x-forwarded-for`/proxy config).
   - Confirm endpoints still depend on `require_local_access`.

2. Source shows unavailable:
   - Check the configured Windows path exists on the host machine.
   - Check service account permissions.

3. `.gz` preview fails:
   - Confirm file is a valid gzip file.
   - Check response `message/details` for `BadGzipFile`.

4. `.zip` archive browse works but preview fails:
   - Check `entry_path` points to a file, not a folder.
   - Confirm archive entry is text-like (not binary).

5. User can escape source root (should never happen):
   - Re-check relative path sanitizer and containment validation in `logfiles.py`.


### September 2026: paged log browsing and reader

Use the Logs sidebar sections (Python logs, Hamilton traces, RobotControl logs). Source permissions still come from the backend; RobotControl logs require a local session. Missing/inaccessible sources show a retryable explanation. Each visited source keeps its own folder, search, page, selection and reading state until the page is left.

The file list defaults to 50 entries and offers 25/100. Filename search is submitted explicitly and applies to the **whole current directory before pagination**, including ZIP directories. It does not search file contents or recurse through the disk. Sort by Name/Modified/Size; type/date filters affect files while retaining reachable folders. The list retains its last successful folder/results if a request fails. New responses cannot overwrite later navigation.

The existing browse endpoints accept optional `search` (up to 200 characters), `file_type=all|text|traces|archives`, `modified_from`, `modified_to` (ISO dates), `sort_by=name|modified|size`, `sort_direction=asc|desc`, `page` and `limit` (up to 200). Calls omitting these options retain the old newest-first, first-200 behavior. Filesystem and ZIP routes share filtering/paging and deterministic name ties. The API remains read-only, uses configured roots and extension restrictions, and executes blocking filesystem work in FastAPI's worker pool.

Refresh files updates the directory list. Refresh in the reader updates the selected preview. Latest/Beginning remain limited to 1 MB; Find in preview searches only returned text (up to 500 highlighted matches), not the rest of the file. Details exposes the full path, Copy path and technical metadata. On narrow screens use Back to files and Reading tools. Expand opens a full-screen reader; Escape restores focus to Expand.

Follow latest is off by default. When enabled it refreshes a selected plain file every five seconds **after the preceding request settles**. It stops on source/file changes, hidden sections/documents and errors, and is unavailable for ZIP/gzip previews. Reading above the bottom keeps the scroll position; Jump to latest is offered when new content arrives. Failed same-file reads retain an explicitly stale preview. Source/path/archive-entry identity prevents same-name files from sharing previews.

Tests: `backend/tests/test_logfiles_api.py` covers large folders/ZIPs, sorting, filters, permissions and preview formats. `frontend/src/components/LogSourceBrowser.test.tsx` covers request races, refresh separation, stale retention, follow lifecycle and expanded-reader accessibility. Browser checks use read-only access; do not enable camera streaming or run methods merely to validate these views.
