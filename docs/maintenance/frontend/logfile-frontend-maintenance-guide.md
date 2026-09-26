# Log viewer maintenance

## Operator workflow

1. Open Logs and choose Python logs, Hamilton traces or RobotControl logs in the
   sidebar. RobotControl is available remotely to administrators, and locally to
   authenticated users. Source permissions come from the backend.
2. For RobotControl, Current logs opens the active folder and History opens its
   `history` subfolder. Breadcrumbs always identify the actual location.
3. Search filenames in the current folder, change sorting or apply type/date
   filters. Folder paging defaults to 50 entries (25/100 are available). This is
   filename search, not recursive disk or file-content search.
4. Select a plain/gzip file, or open a ZIP and select its text member. The reader
   prepares a captured version and initially shows the latest section. Preparation
   displays progress and Cancel; it can fail explicitly on corrupt/oversized input.
5. Use Beginning, Older section, Newer section and Latest to read the complete
   captured file. Only one section is rendered. Find in this section searches
   this displayed text; its query survives section changes and results reset.
6. Expand gives the reader the full screen. Escape closes it and restores focus.
   On a phone, Back to files returns to the retained catalogue position.
7. More contains wrapping and Details. Details shows the authoritative server
   path, ZIP member separately, encoding, captured time and decoded byte range.
   Copy path reports success or offers manual copying when clipboard access fails.

## Components and ownership

`LogFilePage` resolves sources and sidebar sections. `LogSourceBrowser` retains
folder/filter/page/selection state and uses `InspectionWorkspace` for the 300px
catalogue and 900-pixel content-width desktop/phone transition. `LogReader` owns its
reading session, section requests, Find, follow polling and expanded dialog.
`services/logFileApi.ts` contains the typed old/new endpoint wrappers.

The shared workspace measures available height below the app header and controls.
Do not reintroduce hardcoded viewport deductions or stack the entire catalogue
above content on phones. All viewer actions have labelled, 44px touch targets.

## Lifecycle rules

- Selection identity includes source, path, archive and member. A filename alone
  is insufficient. Requests from older selections must not replace newer content.
- Initial selection creates a reader; its preparation is polled serially. Cancel
  and cleanup issue DELETE, including when create finishes after navigation away.
- Visible ready readers renew their lease every 60 seconds. Hidden readers do not
  renew. A 403/404 ends renewal and offers Reopen while retaining displayed text.
- Leaving the file releases the session. Switching sidebar sections retains a
  completed snapshot without renewing its lease; preparation/follow is stopped.
  Returning restores its section. Expired readers offer an explicit Reopen.
- Follow latest is explicit and only available for active plain files outside
  `history`. It uses the legacy bounded tail API every 5 seconds after the previous
  request settles. Archives never follow. Hiding the document pauses requests;
  leaving the reader stops following. Cancel aborts polling. Errors retain the
  last displayed preview and stop following.
- Beginning/Older leave follow mode and prepare a snapshot. Latest does not enable
  follow. A user reading above the bottom is offered Jump to latest rather than
  being scrolled away from their current position.
- File-list Refresh and reader Refresh are separate. Same-file read failures
  retain text with an explicit error. Reopening prepares a new captured version;
  normal appends do not change the content of an existing snapshot.

## Verification

Failure cases are written in `frontend/e2e/scenarios.md`; `logs.spec.ts` covers
real HTTP archive reading/checksums, access, cancellation/capacity/expiry and phone
inspection. Run `npm run build` and `npx playwright test` from frontend. Reports,
screenshots, traces and a fixture manifest are under
`recovery/viewer-verification`. The fixture server uses disposable filesystem data
and synthetic database/camera endpoints; it never starts production services.
