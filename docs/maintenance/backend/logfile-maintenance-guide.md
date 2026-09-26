# Log browsing and complete-file reading

## What owns the paths

`backend/main.py` sets `app.state.log_root` from the application logging handler's
actual filename. The RobotControl source resolves that value for every endpoint.
In development it is `<checkout>/data/logs`; in a packaged installation it is
`<executable folder>/data/logs`. Never add a developer's absolute path to this API.
The fallback path manager exists for standalone router hosts; tests can set app
state explicitly. Python Log and Hamilton LogFiles retain their existing roots.

Current application and warning/error logs are in the root. Rotated gzip logs
are under `history`. The configured 14/30-day retention values do not currently
reliably remove history files: the rotating handler scans another directory.
This viewer change does not change retention or delete original archives.

## Access and paths

All endpoints require authentication. Python logs and Hamilton traces permit
all authenticated users. RobotControl permits administrators from any address,
and authenticated users connecting locally. Local means loopback, not LAN/Wi-Fi.
The shared connection classifier never lets a forwarded header promote a remote
TCP peer into a local client. Uvicorn peer rewriting is disabled in both launch
modes. A reverse proxy must preserve the real client IP in `X-Forwarded-For`.

Requests specify an allowed source ID and relative path, never arbitrary disk
paths. Absolute paths, traversal and paths resolving outside the source are
rejected. Hamilton LogFiles continues to allow `.trc` files only. Reader status,
section reads and release also check ownership, the current source root and its
permissions. Another user's reader ID returns 404.

## Endpoints

The existing GET `/api/logfiles/sources`, `/browse`, `/preview`,
`/archive/browse` and `/archive/preview` remain compatible. Browse supports
filename search, file type/date filters, name/modified/size sorting and paging
(default 200, maximum 200; UI default 50). Filtering happens before pagination.
The legacy preview API supports head/tail with approximately 1 MiB returned;
compressed tail previews scan the compressed stream. Existing encoding detection
and locked-file errors are retained for those endpoints.

Complete-file reading uses these routes:

1. POST `/api/logfiles/readers` with `source_id`, `relative_path`, and optional
   `entry_path` for a ZIP member. Return `id`, `state`, progress and file metadata.
2. GET `/api/logfiles/readers/{id}` until state is `ready` or `error`. Every
   successful authorized request renews the 15-minute idle lease.
3. GET `/api/logfiles/readers/{id}/sections?cursor=last` (or `first`). Continue
   with the returned `previous_cursor`/`next_cursor`. Do not construct offsets.
   Responses include section number/count, text, encoding, source path, captured
   time, decoded byte range and whether the section starts inside a long line.
4. DELETE `/api/logfiles/readers/{id}` when finished or cancelled. It releases
   the reader and signals any active preparation worker to stop.

`backend/services/log_readers.py` owns preparation and resource accounting.
Plain text, gzip files and text ZIP members are decoded once into generated
UTF-8 temporary files. ZIP member names never determine temporary filenames.
The original source is opened read-only. Plain-file capture stops at its opening
size; later appends do not invalidate the copy. Replacement/truncation detected
during preparation fails with a retryable explanation. Later changes are exposed
as `source_changed`; a finished reading copy remains usable.

Encoding is selected once (UTF-8/BOM, UTF-16 or Windows-1252 fallback), decoded
incrementally, and invalid-character replacements are reported. Section boundaries
preserve characters and CRLF. Long lines may continue into another section.

## Limits and cleanup

Defaults are 1 MiB text per section, 1 GiB per prepared reader, 2 GiB total
prepared storage, two preparation workers and 64 open readers. Busy/capacity
failures are explicit; they never claim that a truncated snapshot is complete.
Partial output counts against capacity. Cache files live under
`data/temp/log-readers/reader-process-<pid>-<random>/`.

Cancel, close, idle expiry and application shutdown clean copies. A janitor checks
expiry every 30 seconds. At application startup, directories belonging
to dead processes are removed; live process caches are preserved. Do not manually
remove another running application's reader directory.

## Troubleshooting and verification

- Wrong files: compare Sources/Details path with the running logger filename.
- 403: check role and actual client classification; hiding navigation is not authorization.
- Missing history: check the resolved root and folder. No fallback folder is silently substituted.
- Preparation error: corrupt archive, unsupported/binary content, disk permissions,
  changed source or capacity can explain it; reopen after correcting the cause.
- Expired reader: displayed text remains in the UI; Reopen creates a fresh copy.

Run `npm run build` then `npx playwright test` from `frontend`. The disposable
fixture server exercises these real HTTP routes without importing the production
app or starting robot services. See `frontend/e2e/scenarios.md`; retain the report,
traces and fixture checksums under `recovery/viewer-verification`.
