# Inspection viewer failure scenarios (written before implementation)

Run from frontend: `npx playwright test`. The fixture server uses real log HTTP
routes and disposable filesystem data, synthetic database/camera responses, and
the built application. It never starts robot services or opens production data.

1. Development/deployment log roots diverge; a remote administrator cannot open
   history; a remote non-admin or another reader owner bypasses permissions.
2. A folder, ZIP entry or malicious relative path escapes the configured root.
3. Beginning/latest-only previews omit the middle of a large archived log.
4. Section boundaries lose/duplicate UTF-8, UTF-16, CRLF or very long lines.
5. Appending, replacing or truncating the source produces a mixed snapshot.
6. Corrupt gzip/ZIP, binary input, missing/locked files, capacity exhaustion or
   expiry hangs the reader or replaces useful existing text with an empty pane.
7. Cancel/file-switch leaves a worker and temporary reading copy running; a late
   response overwrites newer selection; hidden readers continue follow polling.
8. A phone stacks the entire catalogue above the content or scrolls horizontally.
9. Back, resize or expansion loses selection, filters, section, scroll or focus.
10. Camera Fit cuts off a marked corner; Fill hides its warning; zoom/expansion
    changes recording, starts a second stream or loses stale status.
11. SQL definitions, long cell values, NULL and empty strings are ambiguous;
    keyboard-only users cannot use Find, close inspectors or restore focus.

Retain Playwright HTML report, screenshots and traces plus the fixture manifest
and checksums in recovery/viewer-verification. Fixtures/cache are temporary and
cleaned at server shutdown. Source-backed E2E tests are retained in this folder.
