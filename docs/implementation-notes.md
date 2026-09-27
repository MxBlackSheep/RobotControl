## 2026-09-27 Proportionate engineering and clearer guidance

- Reviewed testing, communication and code structure. Tracked `AGENTS.md` now defines requirement-first design, justified abstractions, verification matched to impact, release-only packaging and concrete user-facing explanations. Retired the standing frontend specialist workflow.
- Replaced the browser run guide's release history with focused commands, corrected blanket testing instructions, added a documentation map and retained the review in `docs/engineering-review-2026-09-27.md`. Playwright now retains traces on failure by default; full traces remain available with `--trace on`. Existing tests, screenshots and release artifacts are preserved.
- Checked local documentation links, diff formatting and Playwright configuration discovery (100 existing cases). No browser tests or application build were needed; the previous release report is unchanged.

## 2026-09-27 Adaptive full-workspace Labware sizing

- Removed desktop width caps and fitted-size ceilings. Tip tracking uses a 40/60 overview/editor split when minimum controls fit, shared diagram bounds, adaptive spacing and circular dots. Smaller windows retain focused rack viewing and usable minimum targets.
- Cytomat fills available width/height with nine equal base rows, one desktop register scroll area and normal compact-page flow. Inline editors, long values and unexpected positions remain reachable. Shared external measurement avoids child-size feedback; refresh, selection and draft safeguards remain.
- Verification: all 100 integrated browser checks and native 200% Edge zoom passed. Two frontend specialists independently reviewed corrected desktop/phone screenshots. Frontend build, embedding, Windows compilation and relocated-package checks passed. Candidate: `dist/labware-adaptive-20260927/RobotControl`; repeat commands, initial failure traces, final HTML results, native-zoom evidence and checksums: `recovery/viewer-verification`. The packaged archive assertion now allows 20 seconds for a real 1 MiB section; its first five-second timeout and successful retry are retained. Actual phones and physical equipment remain VM/operator checks.

## 2026-09-26 Quiet Labware workbench and stable refresh

- Applied the selected A direction as a layout refinement: a joined deck/rack surface, aligned bounded heading/actions, quieter tip wells and a compact Cytomat shelf register with one inline editor. Width and height fitting retain the physical layout and readable phone targets.
- Background reads use fixed-space status text instead of moving progress bars or repeatedly disabling controls. Static keyboard focus replaces the pulsing tip ripple. Starting an edit synchronously invalidates an unfinished read before React pauses polling; draft, Undo and Save safeguards remain.

- Verification: all 92 integrated browser checks passed; two specialists reviewed the final desktop/phone screenshots. Frontend build, resource embedding, Windows compilation and relocated-package checks passed. Candidate: `dist/labware-workbench-20260926/RobotControl`; repeat commands, HTML reports, screenshots, traces and hashes: `recovery/viewer-verification`. Disposable fixtures/processes were removed. Native zoom, actual phones and physical equipment remain VM checks.

## 2026-09-26 Labware visual alternatives awaiting selection

- Prepared three isolated interactive concepts for Tip tracking and Cytomat: Quiet workbench, Rack tray and Deck first. Two frontend specialists reviewed the alternatives and investigated reported flashing. Production integration and packaging wait for the user's visual choice.
- Browser recordings confirm a 12px background-refresh layout jump, disabled-control flicker/focus loss and MUI's repeating focus ripple. A synthetic 503 also opens the global maintenance overlay; this is not established as the user's incident. Complete blanking was not reproduced across 1,078 frames at the normal refresh cadence.
- Preview captures, browser checks, source identification and reproducible flashing traces are retained in `recovery/labware-concepts-20260926`; start with `flashing-findings.md`. The editable conversation preview is `C:/Users/Hamilton/.codex/visualizations/2026/09/26/01a0dca6-5c7b-7110-98b3-4cf4d9271115/labware-design-options.html`. No production frontend or backend files changed.

## 2026-09-26 Responsive tip selection and Cytomat shelves

- Sized the selected tip rack to both available width and height, with scalable dots/labels, a bounded workspace for 4K displays and readable minimum targets on short screens. Replaced Paint/Rectangle modes and row/column/range tools with Set tips to, block selection and Set entire rack; Undo and batch Save remain.
- Applied the operator-confirmed Cytomat order: positions 1–7 from top to bottom, with 8–9 marked Unused and noneditable. Plate assignments sit beside their shelves. Missing/duplicate positions remain unavailable; unexpected IDs retain their exact names separately.
- Two frontend specialists independently reviewed geometry, input behavior and screenshots across desktop/high-DPI/phone sizes. Their cross-review also identified and corrected stable dropdown naming and selection across horizontally scrolled phone columns. Updated the repeatable browser scenarios and Labware maintenance guide; no unit tests added.

- Verification: all 76 integrated browser checks passed, including native touch selection across offscreen columns. The regression was reproduced before the fix and passed afterward. Frontend build, resource embedding, Windows compilation and relocated-package checks passed. Candidate: `dist/labware-layout-20260926/RobotControl`; repeat commands, HTML reports, screenshots, traces and checksums: `recovery/viewer-verification`. Temporary fixtures/processes were removed. Native browser zoom, actual phones and physical equipment remain VM checks.

## 2026-09-26 Physical tip deck and clearer System Status

- Restored the two-carrier tip overview in backend rack order, with all rack patterns visible and an enlarged editor for state-first click/tap and rectangular painting. Undo, cancellation, batch Save and failed-save drafts preserve deliberate control; phone Back returns to the same deck selection. Two frontend specialists reviewed geometry and interaction behavior against the original layout and professional deck-map patterns.
- Replaced System Status's two technical cards with one compact Connection details disclosure. Database errors remain visible; live-view session capacity no longer appears alongside ambiguous bandwidth/utilization measures.
- The Cytomat API contains position names but no physical rack/shelf mapping. A matching physical map awaits the operator's mapping; existing Cytomat reading/editing remains available. See `docs/labware-spatial-review-2026-09-26.md`.
- Verification: all 58 integrated browser checks passed, plus a focused touch-editor screenshot rerun with animations completed. Frontend build, resource embedding and PyInstaller succeeded; the relocated candidate passed embedded deck/status, real log-root, archive checksum and cleanup checks. Candidate: `dist/spatial-labware-20260926/RobotControl`; reports, screenshots, traces and checksums: `recovery/viewer-verification`. Fixtures and temporary processes were removed. Physical equipment mapping, native zoom and actual-phone behavior remain VM/operator checks.

## 2026-09-26 Unified responsive frontend and appearance

- Added persistent System/Light/Dark appearance, compact shared page patterns, keyboard-resizable inspection selectors and readable phone navigation. Logs now use one reader toolbar with Find on demand and folder controls inside the selector.
- Added table First/Last/page jumps with correct retained-data labels after failures; SQL Top/Bottom/line navigation; focused rack/Cytomat editors with keyboard/touch access, protected pending saves and recoverable malformed-data errors.
- Scheduling now uses a retained list/detail workspace, compact queue/recovery controls and protected phone editor drafts. Camera archives use responsive bounded lists; live frame/session behavior is preserved. Two frontend specialists cross-reviewed both scopes.
- Maintenance treats unknown/failed state explicitly and preserves edited reasons. System Status has one polling owner and distinguishes service availability from resource use. Local storage repair has its own Admin section. Product copy stays concise; maintenance guides describe extension rules for future tabs.
- Verification: all 50 browser E2E checks passed; frontend build, resource embedding and the separate Windows PyInstaller candidate completed. Relocated executable checks passed, including embedded dark/phone viewers, real log root, archive checksum and reader cleanup. Browser/relocated-package results, checksums, screenshots and traces are retained under `recovery/viewer-verification`; candidate is `dist/ui-redesign-20260926/RobotControl`. Native browser zoom could not be completed because computer-use app access timed out; real phone keyboard and VM hardware checks remain in the delivery checklist.

## 2026-09-26 Whole-application UI review

- Reviewed all active frontend routes, shared navigation/theme and the supplied log screenshot with two frontend specialists. Proposed four reusable page patterns, a shared space/action/state policy, System/Light/Dark appearance and route-by-route changes in `docs/frontend-ui-review-2026-09-26.md`.
- Identified missing first/last-page controls, excess log toolbars, tiny labware targets and code-reviewed state/save/pagination/polling problems to cover before the next redesign. This pass changed documentation only; no new application build or live-device verification was performed.

## 2026-09-26 Desktop and phone inspection viewers

- Two frontend specialists researched and peer-reviewed the shared inspection layout, table/full-row reader, searchable SQL catalogue and camera viewport. Back/Expand retain state; camera Fit preserves the whole frame, with explicit cropped Fill, zoom and bounded pan using the existing streaming session.
- RobotControl log browsing now uses the running logger's actual directory and permits remote administrators or authenticated local users. Complete plain/gzip/ZIP text is available through cancellable captured readers, bounded sections, section Find and opt-in live following. Source archives and existing retention behavior are preserved.
- Reader ownership, actual-peer access checks, Unicode/CRLF boundaries, temporary storage limits, idle expiry and startup/shutdown cleanup are enforced. Maintenance guides and repeatable browser/HTTP fixtures are updated; no new unit tests were added.
- Validation: all 29 browser/HTTP E2E checks passed, including deterministic camera focus recovery during a source-change gap. Frontend build, resource embedding and Windows compilation passed. The relocated candidate passed authenticated archive reconstruction, actual log-root, orphan cleanup and desktop/phone browser checks with disposable data and automation disabled. Physical camera/SQL and native phone-keyboard/browser-zoom acceptance remain VM/operator checks.
- Verification commands and limits: `frontend/e2e/README.md`. Retained reports, screenshots, traces and checksums: `recovery/viewer-verification/`. Windows candidate: `dist/viewer-review-20260926/RobotControl/` (copy the whole folder for VM testing).

## 2026-09-17 Deployment recovery guidance and GitHub validation

- Documented full executable/support-folder replacement and reviewed offline reconciliation of conflicting live/archive run history, preserving originals and explicit scheduler resume.
- Excluded local `recovery/` databases and reports from Git. Deployment data and generated binaries remain local.
- Validation: 316 backend tests passed with temporary data paths; all 80 frontend tests and the production frontend build passed. Frontend embedding and Windows PyInstaller compilation passed into `dist/github-validation-20260917/RobotControl`; the new executable was not launched against robot hardware.

## 2026-09-14 SQLite safety and explicit scheduler resume

- Recovery now commits schedule/global flags, revision and audit together. Database guards reject recovery/running-run deletion and archive; queued deletion preserves cancelled history. Ordinary edits no longer overwrite recovery fields.
- Added missing-schedule acknowledgement and a separate persisted Resume action. Local operators must confirm robot readiness; stale revisions and unknown HxRun state block changes. Storage failures pause dispatch and retain monitoring.
- Enabled SQLite foreign keys, replaced execution REPLACE writes with upsert, preserved orphan notification metadata, and added reviewed administrator health/repair with verified retained backups for scheduling/authentication databases.
- Validation: 191 backend tests and 80 frontend tests passed. Frontend embedding and Windows PyInstaller compilation passed. The final executable passed isolated clean/legacy SQLite smoke checks, reviewed repair, missing-schedule acknowledgement, restart persistence and explicit Resume, with automation disabled and no robot methods launched.
- Built into `dist/sqlite-safety-release/RobotControl` using the new optional `--output-dir`, preserving the existing executable folder and its runtime databases.
- See `docs/maintenance/backend/sqlite-safety-maintenance-guide.md` for APIs, locking, reviewed repairs and offline restore. Tests use isolated databases and mocked robot execution.

# RobotControl Development Log (Chronological)

## 2026-09-14 Camera controls, stale-frame display and packaged validation

- Live streaming now includes admin camera discovery/selection, connect/reconnect and recording controls. Capture, recording and viewer connection are separate. Selection/focus survives polling; operation errors stay inline and requests abort on navigation. Reconnect live view affects only that viewer.
- The shared frame store timestamps receipt even for identical images. Inline/fullscreen overlays mark missing frames stale after ten seconds without rerendering the page per frame. No motion/frozen-image detector is introduced.
- Hardware validation found and fixed a DirectShow COM apartment conflict. First selection after camera-less startup retains recording intent. A spawned blocked-worker regression test verifies termination/reaping. Full backend suite: 283 passing; frontend suite and final focused camera tests pass.
- Isolated Windows package recording, WebSocket delivery, manual reconnect, preview-only reconnect after stop, readable clips and helper cleanup passed using a redirected Logi C270. See `docs/camera-recovery-validation.md`. Direct USB unplug/replug, actual multi-device/remote workloads and endurance remain unverified. Previous packages/runtime data are preserved.

## 2026-09-14 Camera health and manual control APIs

Added authenticated cached camera health and admin-only asynchronous discovery, selection, connect/reconnect and recording operations. Existing numeric recording routes execute off the event loop. Automatic startup retains recording intent when no camera is available and the later manual connection reattaches archival monitoring without duplicate callbacks. Health distinguishes frame freshness from recording and reports generations/progress to opt-in diagnostics. Partial clips are excluded from storage cleanup and download. Full backend suite: 281 passing.

## 2026-09-14 Camera process ownership and device identity

Camera capture and MJPEG writing now run in one spawned helper. The parent owns serialized operations, fixed-size preview IPC, generation checks and clip acknowledgements. Manual reconnect verifies helper exit before replacement. DirectShow metadata enumeration replaces capture probing; selection is saved by device identity. Finalized clips carry actual metadata sidecars; interrupted clips remain partial. Packaged children divert before application startup. Lifecycle and worker tests use isolated storage and mocked devices (22 passing).

## 2026-09-14 Bounded camera delivery and N100 candidate

- Streaming wakes on coalesced frame notifications, shares current-frame JPEG variants in two bounded encoding workers, and gives each viewer one latest-frame slot and an independent delivery task. Slow/disconnected viewers cannot backlog native work or block other viewers. Existing recording/quality settings and resource guard remain intact.
- Camera images use a shared current-frame store for inline/fullscreen rendering; the containing page no longer rerenders per frame. Pending session creation is aborted on unmount, socket handlers are detached on cleanup, and per-frame console logging is removed. Video attachment preparation now releases captures and partial outputs on failure. Diagnostics also sample event-loop task counts.
- Final automated validation: 278 backend tests and 69 frontend tests pass; production frontend build, embedding and isolated Windows PyInstaller packaging pass. Package smoke test verified all 22 JavaScript assets, authenticated sampled health, and two diagnostic samples. Candidate: `dist/RobotControl-optimized/RobotControl.exe` with `_internal`; runtime data and previous packages are preserved.
- Browser checks used an isolated synthetic fixture: a schedule draft/dropdown survived multiple polling cycles; 1,000 methods remained paged at 25; inline/fullscreen video and a separate status view remained usable, including narrow layouts and background streaming. These are not real remote-network/camera endurance results.
- Three ten-second probe trials per scenario against `d228f51` reduce repeated buffer reads about 61–67% with comparable delivered frames. Two-viewer CPU improves, but one-viewer CPU increases slightly with worker overhead; see `docs/performance-report.md` and raw measurements. N100 real-camera, 24-hour and ten-day acceptance remain pending; no long-term memory-leak resolution is claimed.

---

## 2026-09-14 Serialized UI polling and non-blocking status reads

- System Status uses one request/retry owner: 60-second normal refresh, existing 30-second recovery cadence, no overlaps or callback-driven restart loop, and stale/auth-changed response protection. Hidden pages retain polling. History no longer instantiates the entire scheduler hook and its duplicate background requests; it has its own serial history loader. Simultaneous queue/status reads are coalesced only while pending, scoped by login token.
- Added a shared five-second system-health sampler; REST and monitoring consume its timestamped snapshot instead of blocking for a one-second CPU sample. Blocking SQL calls in Database, Experiments and monitoring readers use the bounded Starlette thread pool. Operational dispatch/run monitoring freshness is unchanged.
- Added polling, cleanup, read-coalescing, sampler and event-loop responsiveness tests. Public API envelopes and database storage remain compatible.

---

## 2026-09-14 Streaming and attachment resource ownership

- Pending camera sessions now expire using the existing 60-second timeout; duplicate WebSocket attachments cannot replace live handlers. Failure/disconnect cleanup checks handler identity, detaches under lock and closes sockets outside the lock with an idempotent bounded close.
- Camera filesystem cleanup permits only one queued/running job. Alert attachment cleanup now covers preparation failures as well as SMTP failures.
- Added accelerated 100-session abandonment and duplicate/failed attachment tests. These fixes address demonstrated lifecycle defects; they do not establish the cause of the reported total-machine RAM growth.

---

## 2026-09-14 Resource baseline for N100 optimization

- Added opt-in 60-second JSONL diagnostics with bounded rotation, process-tree/private versus resident memory, SQL/browser separation, CPU/I/O and existing-service counts. Disabled by default; no allocation tracing, SQL tuning or operational service initialization.
- Added an isolated deterministic 720p streaming probe (zero/one/two viewers, three trials). Baseline from `d228f51` is in `docs/performance-baseline.json`; this is synthetic, not N100/camera/endurance evidence.
- Validation: 267 backend tests pass. See the performance maintenance guide for matched workload measurements and the required 24-hour/ten-day operator tests.

---

## 2026-09-14 Paged Logs workspace and Windows delivery

- Added per-source sidebar navigation, 50-entry paging (25/100 options), filename search across each directory/ZIP before pagination, metadata filters and deterministic sorting. Existing API callers retain the 200-entry default. Root/extension/local-session restrictions remain enforced, including direct archive requests.
- Replaced the bulky browser with a file panel and text reader: separate file/preview refresh, Latest/Beginning, preview-only Find, wrap, details/copy path, full-screen expansion and a narrow-screen Back/Reading tools flow. Successful folder/preview snapshots survive errors with stale explanations; superseded requests cannot replace newer content. Follow latest is opt-in, plain-file-only, waits for each request, stops when hidden/on error, and respects reading position.
- Browser validation covered 390/1280/1920 widths, source selection and Find retention, Escape/focus restoration, all new sidebar sections, a Cytomat draft retained across sections then discarded, and no streaming session started by Camera navigation. The packaged UI reached entries 201–250 of 1,816 logs. Tested 640×360 as the layout equivalent of 200% at 1280×720; native browser zoom remains an operator check.
- Validation: 65 focused frontend tests and 266 backend tests pass. Windows frontend build, resource embedding and isolated PyInstaller packaging succeed. SQL search and paged log reads were checked through the package. Candidate: `dist/RobotControl-browsing/RobotControl.exe` with `_internal`. Runtime data and earlier packages are preserved; disposable validation files and package-generated test data are removed after checks.

---

## 2026-09-14 Database browsing and applied queries

- Replaced the cramped table catalogue with a collapsible searchable panel and an explicit narrow-screen list/detail view. Removed fabricated 1,000-row counts. Tables retain rows during refresh, distinguish NULL/empty values, expose keyboard cell details and visible-column controls. Procedure/function browsing now has search and preserves its selection on refresh.
- Search and filter drafts apply explicitly. One cancellable request lifecycle protects table state from stale responses. Server search uses parameterized literal matches over supported scalar types; count and rows share predicates. Validated sort direction reaches both modern and legacy SQL pagination, with primary-key tie breaks and 30-second SQL command timeouts.
- Current-page/all-matching CSV and JSON exports use batches of at most 1,000 rows, progress/cancellation and a 50 MB guard. Changed counts and prematurely exhausted results fail explicitly; the UI explains that concurrent writes prevent snapshot guarantees.
- Validation: 15 SQL service tests and four focused component/export tests pass; TypeScript passes. Browser confirmed a real unmatched query returns zero rows, section Back retains the search draft, and 390px uses a Back-to-tables view without page overflow. No SQL records were changed.

---

## 2026-09-14 Section navigation across operational functions

- Shared permission-aware section registry now drives Database, Camera, Labware, Logs, Administration and Scheduling sidebar links, rail menus, breadcrumbs and URL selection. Base routes and Scheduling numeric navigation remain compatible; invalid/inaccessible section links fall back safely.
- Removed duplicate page tabs/source selection. Visited Database/Camera/Labware panels retain their local state; hidden Labware panels stop polling, preserving pending edits. Section navigation does not start/stop camera sessions or execute database operations.
- Navigation tests cover new rail menus and the distinct admin-or-local Restore/local-only Operations and RobotControl log rules. TypeScript checks pass. Browser integration and Windows packaging follow with the browsing changes.

---

## 2026-09-14 Compact application pages and layout validation

- Added shared page content/headers, one compact account/breadcrumb bar, fluid operational widths and bounded settings/readable content. Scheduling now has heading actions and a service strip; list/runtime columns follow actual available width. At 1280×720, normal operational content begins around 190px. Removed duplicate page navigation rows and the duplicate system-monitoring title.
- Browser integration polished folder breadcrumbs, common-root relative paths, method-table scrolling and sidebar expansion labels. Create/cleanup pickers preserve drafts and restore focus; a dropdown remained open with its draft and scroll through two polling cycles. Reviewed narrow and desktop layouts with 1,000 disposable imported methods. In-app browser zoom shortcuts are unavailable; checked the equivalent 640×360 layout for 200% zoom, with native zoom still requiring an operator check.
- Validation: 50 focused frontend tests and the full 260-test backend suite pass. Windows frontend build, resource embedding and isolated PyInstaller packaging pass. Packaged UI checks covered the 1,000-method library, page-only selection across two pages, search clearing selection, refresh retention and opening the saved method folder. Embedded JavaScript matches the final build.
- Candidate: `dist/RobotControl-layout/RobotControl.exe` with `_internal`. Removed disposable package data and validation fixtures; preserved the running installation and earlier candidates. No API, SQLite, scheduling/execution or live runtime-data changes.

---

## 2026-09-14 Shared sidebar and Scheduling section links

- Replaced desktop tabs/mobile-only navigation with one responsive AppSidebar and shared permission-aware navigation definitions. Desktop uses a remembered 240px/64px preference (expanded initially at 1440px); below 900px it becomes an overlay. Scheduling exposes its seven sections inline or in a collapsed-rail menu, with the latest observed recovery warning.
- Scheduling sections now use stable `?section=` links, including creation/recovery/notification handoffs; invalid or inaccessible sections return to Schedules. Added role/local-access, URL history, mobile-close, preference and keyboard tests. Global shortcuts defer to open MUI modals/menus so drafts and focus restoration remain intact.

---

## 2026-09-14 Folder-first method selection

- Added a shared catalogue-only folder explorer for primary/cleanup selection and Methods management. It compresses empty ancestor chains, supports drive/UNC roots and global name/path search, and keeps relative legacy paths in Needs path review. Picker confirmation is explicit; cancel and catalogue refresh preserve the schedule draft.
- Added 25/50/100-row pagination, page-scoped bulk selection that persists across pages, concise relative paths and full-path copying. Folder/search/filter changes clear management selection; refresh retains browsing state. Added 1,000-method, keyboard, cancellation, pagination and refresh regressions. No backend API or database changes.

---

## 2026-09-12 Reviewed method path correction

- Added manual/host-browser path correction with validated preview, separate primary/cleanup references, unchecked selection and disabled busy/archived schedules. Save revalidates the file, catalogue revision and selected schedule versions; catalogue and selected paths commit in one SQLite transaction. Scheduler locks coordinate enqueue/dispatch and cache refresh. Ordinary edit/archive writes cannot overwrite a concurrent correction; version checks no longer accept changes within a one-second tolerance.
- Unselected paths, labels, timing, contacts, archive state, import provenance, execution history and monitoring records stay intact. Canonical path collisions and stale previews fail without partial changes. Conflict messages preserve the draft and require a fresh review.
- Validation: 260 backend tests and 31 focused frontend tests pass, including rollback, enqueue/edit/archive races and paused monitoring preservation. Browser checks confirmed direct host-folder preview, archive/restore, cleanup-only correction, keyboard focus restoration and desktop/narrow layouts. Frontend build, resource embedding and Windows PyInstaller packaging pass. The isolated packaged app passed host browsing/import, archived reimport/restore, cleanup-only correction, stale-edit rejection, path checks and local-only access with its scheduler stopped.
- Candidate: `dist/RobotControl-method-library/RobotControl.exe` with its `_internal` directory. Validation data was removed; existing `dist/RobotControl`, `dist/RobotControl-setup` and runtime data were preserved. No Hamilton method was executed or email sent during validation.

---

## 2026-09-12 Method library management

- Added a local Methods tab with search, folder/status/archive filters, sorting, path checks, usage details (including cleanup references), schedule creation and selected archive/restore actions. Existing schedule paths and files are unchanged by archive; saved form selections remain visible when absent from new choices.
- Added backward-compatible archive, revision and validation fields. Checks persist Available/Missing/Inaccessible/Invalid/Not checked separately from archive. Revision checks reject stale changes. Reimport preserves archive and provenance and prefers a unique current entry over archived duplicates. Migration and API tests cover legacy validity, access, reimport, references and unchanged schedules.

---

## 2026-09-12 Host folder browsing for method import

- Replaced browser uploads with a local host folder browser: breadcrumbs, drives, parent navigation, imported-folder shortcuts and automatic absolute-path selection. Manual entry remains available and explains the missing required path. Failed navigation preserves the last usable folder/selection; linked folders are disabled.
- Added local-only `/experiments/browse` metadata access and shared directory helpers with the existing system browser, preserving database-restore behavior. Import still uses the existing host validation and per-file outcomes. Targeted backend and frontend tests cover navigation, access failures, linked folders and direct preview handoff.

---

## 2026-09-12 Verified Hamilton method import

- Replaced the import dialog with Choose folder → Review methods → Import results. Both browser and manual modes require an absolute host folder; selection sends paths only. Valid New/Update rows are selected by default, invalid rows explain failures, and searchable results report actual Added/Updated/Failed outcomes. Creating a schedule remains an explicit next action.
- Added a local-only, read-only preview endpoint and shared host filesystem validation for both import routes. Imports revalidate containment, metadata and case-insensitive `.med` files, preserve valid absolute-path callers, and reject unresolved relative requests. Canonical paths identify methods; old records are never automatically repaired or deleted. Database outcomes account for per-file failures and transaction rollback.
- Validation: all 235 backend tests and 25 focused frontend tests pass; TypeScript/Vite build, resource embedding and Windows PyInstaller packaging pass. Canonical-path regressions cover older path spellings without replacing record IDs and ambiguous legacy duplicates without automatic repair. Browser checks covered draft/focus/scroll stability across polling, keyboard/dropdown behavior, import preview/results/schedule handoff, and SMTP/import at 390px and 1280px widths. The isolated packaged app passed embedded UI/authentication, preview, Added/Updated results and local-access checks using disposable metadata files, never executable Hamilton methods.
- Candidate build: `dist/RobotControl-setup/RobotControl.exe` with its `_internal` directory. Existing `dist/RobotControl` and runtime data were preserved; the candidate contains no validation data. Operator simulator checks remain: pause/resume alerts, restart during an already-alerted pause without duplicates, and silence after completion. No real email was sent or Hamilton run launched during validation.

---

## 2026-09-12 Clear SMTP account setup

- Reorganized email setup around one account address, with existing custom login/From addresses preserved under Advanced settings. A single security selector replaces mutually exclusive switches and never silently changes ports. Manual recovery correctly falls back to the schedule's active contacts.
- A shared draft serializer preserves existing API/password semantics. Blank keeps the encrypted password; explicit replacement/removal is sent only on Save, with undo before saving. Refresh/discard requires an explicit choice for dirty drafts and retains entries after failures.
- Save precedes Test; dirty settings cannot be tested, saves never send email, and test progress/results stay inline. Twenty-one focused frontend tests and TypeScript checks passed. Browser review used an isolated instance; no real credentials were changed and no external email was sent.

---

## 2026-09-12 Stable schedule form refresh

- Removed duplicate custom focus trapping from create/edit and method import dialogs; MUI manages focus restoration and trapping. Schedule initial focus runs once on entry, and drafts initialize only once per open session. Polling and refreshed props cannot overwrite entered values or expanded sections.
- Edit saves use the version captured on opening, preserve drafts after conflicts, and explain how to reload. Removed duplicate post-save list fetches. Empty recipient selection now has an explicit warning that observation continues without email delivery.
- Nine frontend tests passed, including two simulated 30-second refreshes preserving focus/scroll/data, reopening a fresh draft, and retaining entries after a save conflict. TypeScript checks passed. Browser/package acceptance continues on an isolated instance.

---

## 2026-09-12 Hamilton paused-state consistency

- Confirmed mapping: 1 = Running, 2 = Paused. Shared SQL mapping, experiment enum, dashboard/system display, monitoring API progress and scheduler/email diagnostics now agree. Paused remains an unfinished execution and never invokes recording completion.
- The exact trace is observed in both states. SQL state transitions do not reset inactivity or create a new pause; trace writes do. Observation/status/email context includes the normalized and raw SQL state, with backward-compatible defaults for saved observations.
- Added regression coverage for state parsing, pause/resume/restart deduplication, terminal priority, progress and completion callbacks, plus a minimal frontend test harness for this and subsequent UI changes. Operator simulator acceptance remains required after packaging.
- Validation: 79 targeted backend tests, six frontend status tests, and the Windows frontend build passed. The Vitest harness leaves the existing legacy Jest suites unchanged and excludes them pending a separate migration.

---

## 2026-09-12 Simulator acceptance checkpoint

- Operator testing confirmed real SMTP delivery and one `log_inactive` email. Notification history records that email at 13:04:51, followed by `monitoring_unavailable` emails at 13:09:21 and 13:17:37. Receiving three messages does not yet verify repeated inactivity alerts.
- Restart at approximately 13:10 restored the same execution and Hamilton GUID without creating another execution. The unavailable warning also occurred before restart, so it is not specific to restoration.
- Read-only SQL inspection while the simulator was paused returned `RunState = 2`, with no end time; the matching trace recorded a pause. The current mapping recognizes numeric states 1, 64 and 128 only. State 2 therefore becomes unknown and triggers the unavailable warning instead of continuing trace observation. This is a known limitation of this checkpoint; the next change should handle the observed pause state explicitly, retain terminal-state priority, and report unknown raw states clearly.
- SMTP delivery now works with the operator's corrected QQ settings. Schedule contacts must be selected separately from creating a global contact; missing recipients appear as delivery errors. Clearer sender/login labels and recipient warnings remain follow-up work.
- Existing validation remains 205 passing backend tests, successful frontend/resource/Windows builds, and isolated packaged responsiveness checks. Full simulator pause/rearm acceptance, restart during an already-alerted pause, and completion silence remain to be verified after the pause-state correction. This checkpoint changes documentation only after those builds; it does not alter the running application.

---

## 2026-09-12 Email responsiveness and Hamilton process inspection

- Fixed API freezes during test/custom email sending and manual recovery actions by moving blocking work to the request thread pool. Interactive email uses one attempt with a 10-second timeout per SMTP operation; the test-email UI waits up to 60 seconds for the detailed result. Background monitoring delivery retains its retry policy.
- SMTP failures now identify the host, port and failed step (connection/greeting, TLS, authentication or submission). TLS verifies server certificates, rejected credentials are not repeatedly retried, and socket cleanup cannot cause an accepted email to be resent.
- Replaced the scheduler process monitor's shared WMI/COM client with the existing psutil dependency. Busy checks and status details share one detection path; a hidden, five-second tasklist fallback handles unavailable inspection. Unusable detection reports an error and blocks dispatch. Background monitoring stops promptly and can restart.
- All 205 backend tests and the frontend build passed. Tests cover responsive concurrent API requests during stalled email/recovery, SMTP failures/retries and process inspection/recovery from background threads. Native Windows main/worker/background process checks passed. Independent unauthenticated Gmail probes timed out at the greeting on port 587 and TLS handshake on port 465; actual external email delivery remains dependent on resolving SMTP connectivity. Camera behavior was left unchanged as requested.
- Resource embedding and the standard Windows PyInstaller build passed. The isolated executable sent to a loopback SMTP stub, then returned a deliberate greeting timeout after 10.23 seconds while 14 concurrent health/queue checks remained responsive. Background process monitoring and scheduler restart passed without COM errors. Original runtime data was restored with hash verification, temporary test/build copies were removed, and the user app remains stopped. No external email or Hamilton method was launched during validation.

---

## 2026-09-12 Scheduler run log inactivity monitoring

- Replaced the twice-estimated-duration watchdog with exact SQL RunGUID-to-trace monitoring. Each schedule has a positive whole-minute threshold (default 3); changes apply to the next launch. Actual cleanup targets are tracked. Removed the executor's 120-minute process kill while retaining late-start cleanup behavior.
- Added durable observation state and per-pause email identifiers. SQL/file outages get a distinct three-minute warning; new trace activity rearms inactivity alerts. Email retries/attachments run on one background delivery worker, with exact trace selection and revalidation before sending.
- Startup restores observations and preserves alert deduplication. Shared atomic finalization reconciles process/SQL outcomes once, including archived executions. Existing manual recovery acknowledgement can close unowned orphan observations only after HxRun is absent.
- Added API/model/storage/form wiring, running-job monitoring details, and maintenance guidance. All 181 backend tests passed, covering threshold validation, trace matching, outages, restart, retries, terminal races, archival and unlimited runtime.
- Frontend build, resource embedding and Windows PyInstaller packaging passed. The isolated executable passed health, OpenAPI, embedded scheduling UI, authenticated queue and disabled-schedule create/update checks (default 3; omitted updates preserve the setting). Read-only live SQL lookup matched an exact local trace. Existing packaged runtime data was restored with file-hash verification; temporary smoke files were removed. Operator-led Hamilton simulator pause/resume/restart and real email delivery remain to be checked.

---

## 2026-09-12 uv migration and Windows setup

- Replaced both conflicting requirements files with one root uv project and lockfile; pinned managed Python 3.14.7, modernized application dependencies, and separated dev/build groups. Passlib 1.7.4 and bcrypt 4.3.0 remain pinned to preserve existing password hashes. Windows dependencies include pywin32 and WMI.
- Installed user-local uv and Node.js 24/npm, synchronized `.venv`, and built the frontend. Updated setup, maintenance, and packaging instructions and aligned the existing backend Docker recipe and nginx proxy with port 8005.
- Repaired stale test imports, property mocks, SQLite singleton isolation, Windows file-lock simulation, and scheduler polling timing. Replaced obsolete failover database tests with primary-only service tests and added stored-password compatibility coverage.
- Enabled the recording download handler's existing HEAD behavior with separate OpenAPI operation IDs. Moved process-wide shutdown hooks into the entrypoint so test and packaging imports do not register them. Added optional `ROBOTCONTROL_AUTO_RECORDING_ENABLED=0` for interface development; automatic recording remains enabled by default.
- Fixed Hamilton busy detection when a worker cannot use WMI's COM connection: fall back to `tasklist`, and block dispatch if process detection fails. Regression tests cover COM failures, busy/idle results, timeouts, and command errors.
- PyInstaller now collects application modules and embedded frontend assets without copying backend tests, local configuration, or runtime data. A fresh `uv sync --locked`, lockfile check, dependency compatibility check, all **141 backend tests**, frontend build, and final Windows onedir build passed. Existing dependency/deprecation warnings remain.
- Verified source and compiled `/health`, `/openapi.json`, frontend/JavaScript assets, browser login, authenticated profile requests, and refresh-token persistence across restart. Verified graceful shutdown in source and a temporary compiled console build; the tray's Terminate menu was not automated. The independent reviewer completed a follow-up review after both findings were fixed and reported no remaining actionable issues.
- Live robot actions and camera recording were not exercised. A read-only SQL dashboard query succeeded on this host; full SQL workflows, Linux deployment, and a separate VM remain unverified. The standard executable is retained at `dist/RobotControl/RobotControl.exe`; temporary downloads, test files, and the console smoke build were removed.

---
## 2026-02-24 LogFile Remote Access Split (Per Source)

- Removed the frontend’s page-wide local-session block for LogFile and switched to source-level availability messaging/selection state, so remote `user/admin` sessions can use allowed sources (`frontend/src/pages/LogFilePage.tsx`).
- Added backend per-source access policy (`access_scope`) in `backend/api/logfiles.py`: `Python Log` and `Hamilton LogFiles` are remote-accessible, while `RobotControl Logs` remains local-only.
- `GET /api/logfiles/sources` now returns per-source `permissions.can_access` and `access_scope`, and browse/preview endpoints enforce access after source resolution.

---
## 2026-02-24 LogFile Hamilton Source Filter (TRC Only)

- Restricted the `Hamilton LogFiles` LogFile source to `.trc` files only (directories still visible for navigation), so non-log files in that folder no longer appear in the LogFile page and direct preview requests for non-`.trc` files are rejected (`backend/api/logfiles.py`).
- Added backend tests covering Hamilton source filtering and non-`.trc` preview rejection (`backend/tests/test_logfiles_api.py`).

---
## 2026-02-24 LogFile Review (Dedicated Tab + Archive-Aware Viewer)

- Added a new top-level **LogFile** page/route (`/logfile`) for read-only log browsing and previewing, with desktop tab/mobile drawer/breadcrumb/keyboard shortcut integration (`frontend/src/App.tsx`, `frontend/src/pages/LogFilePage.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/components/NavigationBreadcrumbs.tsx`, `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`).
- Added a dedicated backend API router `backend/api/logfiles.py` (`/api/logfiles/*`) using a fixed allowlist of log roots (Python Log, Hamilton LogFiles, RobotControl logs) instead of arbitrary path browsing.
- Implemented preview support for normal text logs plus `.gz` history logs and `.zip` archive browsing/preview, with `head`/`tail` modes and server-side preview size caps.
- Added graceful handling for locked/in-use files by returning a structured `423 FILE_LOCKED` response so the UI can show a warning instead of failing the whole page.
- Added backend tests covering source listing, traversal rejection, text preview, gzip preview, zip archive browsing/preview, and locked-file error handling (`backend/tests/test_logfiles_api.py`).
- Added LogFile maintenance guides for backend/frontend and updated main application maintenance guides to include the new router/page (`docs/maintenance/backend/logfile-maintenance-guide.md`, `docs/maintenance/frontend/logfile-frontend-maintenance-guide.md`, `docs/maintenance/backend/main-application-maintenance-guide.md`, `docs/maintenance/frontend/main-application-frontend-maintenance-guide.md`).

---
## 2026-02-22 OD Auto-Reschedule Email Notification (Schedule Contacts)

- Added `POST /api/scheduling/notifications/send` to send a custom email through the existing SMTP settings to the active notification contacts attached to a specific schedule (`backend/api/scheduling.py`).
- Updated `backend/scripts/scheduling_api_cli.py` (OD prediction auto-rescheduler) to send a schedule-contact email only after a successful schedule update, including previous vs updated start time plus OD summary context (last data timestamp and average latest OD per culture).
- Email delivery failures are logged as warnings in the CLI and do not roll back the successful reschedule.
- Updated backend scheduling maintenance guide with the new endpoint/CLI behavior (`docs/maintenance/backend/scheduling-maintenance-guide.md`).

---
## 2026-02-18 Scheduling API CLI Prerequisites Visibility

- Updated `backend/scripts/scheduling_api_cli.py` list/update row rendering to include `prerequisites`, so external operators can identify required pre-execution database flags while selecting target schedules.
- Updated scheduling backend maintenance guide to document that `list` now shows `prerequisites` (`docs/maintenance/backend/scheduling-maintenance-guide.md`).

---
## 2026-02-18 Scheduling API Automation CLI (Target + Update Without Frontend)

- Added `backend/scripts/scheduling_api_cli.py`, a small script for backend-only scheduling automation:
  - `list` command to find target schedules by ID/name.
  - `update` command to patch one schedule directly through `PUT /api/scheduling/{schedule_id}`.
- Script performs login (`/api/auth/login`), handles bearer auth, supports optional `X-Forwarded-For`, and uses `expected_updated_at` optimistic locking by default by fetching a fresh schedule snapshot before updating.
- Updated backend scheduling maintenance guide with a new section documenting external API automation workflow and concrete command examples (`docs/maintenance/backend/scheduling-maintenance-guide.md`).

---
## 2026-02-18 Scheduler Blueprint Reconciliation (SCHEDULER_FULL_PICTURE)

- Revalidated `SCHEDULER_FULL_PICTURE.txt` against current scheduling code (`backend/services/scheduling/scheduler_engine.py`, `backend/services/scheduling/experiment_executor.py`, `backend/api/scheduling.py`) and rewrote stale sections so the file can be used as handbook blueprint.
- Removed outdated retry/`RetryConfig` descriptions and replaced them with current `TimeoutConfig` behavior (`continue` vs `run_cleanup_and_terminate`) including queue-wait-aware timeout evaluation at launch time.
- Documented real single-worker dispatch gating (`HxRun maintenance`, `manual recovery`, `schedule recovery_required`, `HxRun busy`), queue `waiting_reason`, and cancellation behavior for removed/deactivated schedules before dispatch.
- Clarified current API constraints in plain language: no duplicate-minute guard, preserved timestamp precision, create-time past-start rejection, and runtime-truth queue status from `/api/scheduling/status/queue`.

---
## 2026-02-18 Queue-First Dispatch Refactor (Checks Folded Into Worker)

- Refactored scheduler dispatch to queue-first behavior: due jobs are always queued, and HxRun maintenance/manual recovery/HxRun busy checks now run inside the single worker before switching a job from queued to running (`backend/services/scheduling/scheduler_engine.py`).
- Added runtime queue metadata (`queued_at`, `waiting_reason`) so blocked jobs remain visible as queued (not running) with explicit wait reasons in `/api/scheduling/status/queue`.
- Updated executor contract to focus on launch + timeout action resolution only; scheduler worker now owns readiness gating (maintenance/manual/busy checks) (`backend/services/scheduling/experiment_executor.py`).
- Updated schedule list next-run rendering to use backend canonical timestamp directly (removed client interval recomputation), preventing UI drift where displayed due time differs from actual launch timing (`frontend/src/types/scheduling.ts`, `frontend/src/components/ScheduleList.tsx`).
- Added regression coverage for “busy robot keeps schedule queued until available,” and refreshed executor timeout-action tests to match the new worker-owned gating model (`backend/tests/test_scheduler_single_worker.py`, `backend/tests/test_hxrun_maintenance_executor.py`).

---
## 2026-02-18 Scheduler Timeout Refactor (No Retry Logic + Queue Visibility)

- Replaced schedule retry configuration with timeout configuration across backend models/API/storage: schedules now persist `timeout_config` (`timeout_minutes`, `action`, optional cleanup method) and no longer accept/use `retry_config` (`backend/models.py`, `backend/api/scheduling.py`, `backend/services/scheduling/sqlite_database.py`).
- Simplified execution path to single-attempt launches: removed executor retry loop, added timeout action routing (`continue` or `run_cleanup_and_terminate`), tied HxRun-availability wait to schedule timeout when configured, and when cleanup action is triggered the schedule is deactivated for subsequent runs (`backend/services/scheduling/experiment_executor.py`, `backend/services/scheduling/scheduler_engine.py`).
- Added create-time start timestamp guard in backend (`start_time` cannot be in the past) and updated scheduling create-guard tests, including new rejection coverage for past timestamps (`backend/api/scheduling.py`, `backend/tests/test_scheduling_create_guard.py`).
- Extended scheduler tests for timeout cleanup termination behavior and adjusted executor-maintenance test stubs for the new single-attempt executor contract (`backend/tests/test_scheduler_single_worker.py`, `backend/tests/test_hxrun_maintenance_executor.py`).
- Updated frontend scheduling types/services/forms/pages for timeout config editing and rendering, removed retry fields from scheduling payloads, and added a runtime queue panel that shows both running and queued schedules from `queueStatus` (`frontend/src/types/scheduling.ts`, `frontend/src/services/schedulingApi.ts`, `frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/hooks/useScheduling.ts`).
- Updated scheduling maintenance guides to document timeout behavior and queue detail surfaces (`docs/maintenance/backend/scheduling-maintenance-guide.md`, `docs/maintenance/frontend/scheduling-frontend-maintenance-guide.md`).

## 2026-02-17 Scheduler Policy Simplification (No Lateness Miss, No Timestamp Guard)

- Removed lateness-based miss rules from due-job detection; scheduler now enqueues any active schedule whose `start_time <= now` and no longer auto-marks overdue jobs as `missed` based on fixed thresholds (`backend/services/scheduling/scheduler_engine.py`).
- Removed API timestamp constraints on schedule create/update: no minute rounding and no duplicate-minute conflict checks (`backend/api/scheduling.py`).
- Removed now-unused duplicate-minute lookup helpers from scheduling DB manager/SQLite layers (`backend/services/scheduling/database_manager.py`, `backend/services/scheduling/sqlite_database.py`).
- Updated schedule create/update tests to match the new policy (timestamps are accepted as provided and duplicate-minute checks are not enforced) (`backend/tests/test_scheduling_create_guard.py`).
- Fixed double error pop-up on save failures by keeping create/update failures local to the form dialog path (throw to caller without setting page-level scheduling error banner in mutation handlers) (`frontend/src/hooks/useScheduling.ts`, `frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `frontend/src/pages/SchedulingPage.tsx`).
- Updated scheduler maintenance/explainer docs to reflect the simplified behavior (`docs/maintenance/backend/scheduling-maintenance-guide.md`, `docs/maintenance/frontend/scheduling-frontend-maintenance-guide.md`, `SCHEDULER_FULL_PICTURE.txt`).

## 2026-02-17 Scheduling Form Save-Failure Dialog (No Silent Close)

- Fixed scheduling create/update mutation behavior so failures now propagate to callers instead of being swallowed inside `useScheduling`; the hook still sets `state.error`, but now also throws to let dialog submit handlers react (`frontend/src/hooks/useScheduling.ts`).
- This enables `ImprovedScheduleForm` submit flow to keep the form open and show `StatusDialog` (for example on duplicate active timestamp `409`) instead of closing as if save succeeded (`frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `frontend/src/pages/SchedulingPage.tsx`).
- Updated frontend scheduling maintenance docs to reflect this contract: read-path errors remain inline (`state.error`), while create/update form failures should be handled via `try/catch` + modal status dialog (`docs/maintenance/frontend/scheduling-frontend-maintenance-guide.md`).

## 2026-02-17 Single-Worker Scheduler Queue + Minute Timestamp Guard

- Reworked scheduler dispatch to a true single-worker queue model: due jobs are enqueued and consumed serially by `SchedulerJobWorker`, and the legacy scheduler-side capacity reservation/retry layer was removed to avoid double-gating before HxRun launch (`backend/services/scheduling/scheduler_engine.py`).
- Updated `/api/scheduling/status/queue` to report queue/running snapshots directly from scheduler runtime state instead of the detached legacy queue manager so UI queue status reflects actual execution flow (`backend/api/scheduling.py`, `backend/services/scheduling/scheduler_engine.py`).
- Added a minute guard for active schedule timestamps on both create and update: incoming `start_time` values are normalized to minute precision and conflicts are rejected when another active non-archived schedule already uses that minute (`backend/api/scheduling.py`, `backend/services/scheduling/database_manager.py`, `backend/services/scheduling/sqlite_database.py`).
- Normalized manual-recovery timestamp persistence to one local-naive serialization path for mark/resolve/global recovery writes, eliminating the previous UTC-vs-local inconsistency (`backend/services/scheduling/sqlite_database.py`).
- Added regression coverage for single-worker serial execution behavior plus duplicate-minute create/update rejection and timestamp normalization (`backend/tests/test_scheduler_single_worker.py`, `backend/tests/test_scheduling_create_guard.py`).
- Refreshed scheduler documentation to match the new architecture and rewrote the root-level plain-language explainer for the current flow (`docs/maintenance/backend/scheduling-maintenance-guide.md`, `SCHEDULER_FULL_PICTURE.txt`).

## 2026-02-14 Labware Cytomat Visualization + Controlled PlateID Editing

- Added a dedicated Cytomat backend service and API endpoints under `/api/labware/cytomat` so users can view `CytomatPos` + `PlateID` and apply batch `PlateID` updates with the same auth/locality guard model as TipTracking (`backend/services/labware_cytomat.py`, `backend/api/labware.py`).
- Cytomat dropdown options are now sourced from `Plates.PlateID`, with ordering enforced as: empty option first, then descending numeric IDs, then descending non-numeric IDs; empty selection is persisted as `NULL` in `Cytomat.PlateID`.
- Added a new Labware secondary tab and Cytomat UI panel with row-level dropdown editing, pending-change queue, save/discard controls, read-only behavior for remote sessions, and refresh/autorefresh behavior (`frontend/src/pages/LabwarePage.tsx`, `frontend/src/components/labware/CytomatPanel.tsx`, `frontend/src/services/labwareApi.ts`).
- Added backend API regression coverage for Cytomat read permissions, local-only write enforcement, successful local writes, and invalid PlateID rejection (`backend/tests/test_labware_api.py`).
- Updated backend/frontend labware maintenance guides to document the new Cytomat module and maintenance workflow (`docs/maintenance/backend/labware-maintenance-guide.md`, `docs/maintenance/frontend/labware-frontend-maintenance-guide.md`).

---
## 2026-02-14 HxRun Maintenance Enable Guard (Do Not Kill Existing Session)

- Added a backend pre-check on `PUT /api/maintenance/hxrun`: when enabling maintenance mode, RobotControl now first checks if `HxRun.exe` is already running and blocks the toggle with `409` instead of enabling and terminating HxRun (`backend/api/maintenance.py`, `backend/services/hxrun_maintenance.py`).
- Added a clear operator-facing conflict message (`HxRun is running. Please close the software before entering maintenance mode.`) so local users know exactly why the toggle is rejected.
- Added API regression coverage for the blocked-enable path and verified that state persistence is skipped when HxRun is running (`backend/tests/test_hxrun_maintenance_api.py`).
- Updated the Maintenance page to show a dedicated dialog when this conflict happens, instead of silently failing or relying only on inline error text (`frontend/src/pages/MaintenancePage.tsx`).

## 2026-02-12 HxRun Maintenance Mode (Event + Fallback Enforcement)

- Added a new persistent **HxRun Maintenance Mode** (separate from the existing database-restore maintenance window) with a dedicated backend API: authenticated users can inspect state, while toggles require loopback/local access (`backend/api/maintenance.py`, `backend/main.py`).
- Extended scheduler SQLite global state to store `hxrun_maintenance_enabled` plus reason/user/timestamp metadata, including auto-migration for existing databases (`backend/services/scheduling/sqlite_database.py`, `backend/services/scheduling/database_manager.py`, `backend/models.py`).
- Introduced a global enforcement service that uses **event-driven process-start watching** for `HxRun.exe` with **1s fallback polling**; when enabled, any detected HxRun process is terminated and a Windows popup explains the block (`backend/services/hxrun_maintenance.py`, `backend/main.py`).
- Added hard backend guards so scheduler dispatch pauses while maintenance mode is enabled and experiment execution exits early with a clear maintenance-blocked error instead of launching HxRun (`backend/services/scheduling/scheduler_engine.py`, `backend/services/scheduling/experiment_executor.py`).
- Added an independent top-level `MAINTENANCE` page/tab between Labware and System Status, with local-only edit controls and remote read-only inspection (`frontend/src/pages/MaintenancePage.tsx`, `frontend/src/services/hxrunMaintenanceApi.ts`, `frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/components/NavigationBreadcrumbs.tsx`, `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`).
- Added API + executor regression tests for local/remote permissions and maintenance launch blocking (`backend/tests/test_hxrun_maintenance_api.py`, `backend/tests/test_hxrun_maintenance_executor.py`).

## 2026-02-12 Camera Download Resume + Retry

- Upgraded camera recording downloads to support resumable transfers over unstable links by adding `HEAD` + `GET` range handling on `/api/camera/recording/{recording_id}`; responses now include `Accept-Ranges`, `Content-Range` (for `206`), `ETag`, and `Last-Modified`, and return `416` for invalid ranges (`backend/api/camera.py`).
- Kept compatibility with existing archive UI endpoints while hardening transfer semantics (full download still works, partial resume now works, and `If-Range` mismatch correctly falls back to full-body responses).
- Fixed archive download file resolution for experiment recordings stored in nested subfolders: backend lookup now scans `experiments/` recursively and selects the newest match when duplicate filenames exist, which resolves false `404` responses for files visible in the archive list (`backend/api/camera.py`).
- Added API-focused regression tests that validate full download, partial download, suffix range, invalid range, `If-Range` fallback, and metadata-only `HEAD` behavior (`backend/tests/test_camera_download_api.py`).
- Reworked frontend archive download flow to support resume-aware retries with exponential backoff, live byte progress, and user cancellation; one active download can continue from the last successful byte instead of restarting from zero on transient network failures. Client now stops auto-retrying non-retryable `4xx` responses (notably `404`) and shows a direct error instead (`frontend/src/pages/CameraPage.tsx`, `frontend/src/components/camera/VideoArchiveTab.tsx`).

## 2026-02-12 Labware TipTracking Web Module

- Added a dedicated Labware backend module with SQL-backed tip tracking for `1000ul` and `300ul` families, including snapshot read APIs plus batch update/reset operations (`backend/services/labware_tip_tracking.py`, `backend/api/labware.py`, `backend/main.py`).
- Enforced the requested permission model: authenticated admin/user sessions can inspect tip state, while write endpoints require local network access via `require_local_access` (remote sessions are read-only by design).
- Added a new `LABWARE` top-level page between Camera and System Status with a secondary tab architecture (`TipTracking` as the first module) and a full interactive tip editor (select/apply tip, apply column, apply rack, pending queue, save/discard/reset, legend, auto-refresh) (`frontend/src/pages/LabwarePage.tsx`, `frontend/src/components/labware/TipTrackingPanel.tsx`, `frontend/src/services/labwareApi.ts`).
- Updated navigation and discoverability for the new route across desktop tabs, mobile drawer, breadcrumbs, and keyboard shortcuts/help text (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/components/NavigationBreadcrumbs.tsx`, `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`).
- Added backend and frontend maintenance guides for the new module and refreshed main-application guides to list the new route/router (`docs/maintenance/backend/labware-maintenance-guide.md`, `docs/maintenance/frontend/labware-frontend-maintenance-guide.md`, `docs/maintenance/backend/main-application-maintenance-guide.md`, `docs/maintenance/frontend/main-application-frontend-maintenance-guide.md`).

## 2025-10-22 Local Scheduling Guardrails

- Reworked schedule management controls to respect the session’s `session_is_local`/`last_login_ip_type` flags so remote browsers stay in read-only mode while the local workstation still gets full CRUD (`frontend/src/pages/SchedulingPage.tsx`).
- Hid the manual recovery action buttons for remote users while keeping the status display intact; handlers now short-circuit when the session is not local to prevent accidental calls from devtools (`frontend/src/pages/SchedulingPage.tsx`).
- Replaced the Database Operations tab with an informational card for remote sessions so destructive experiment tooling never renders outside the lab (`frontend/src/pages/DatabasePage.tsx`).
- Fixed the “local session” check to rely on the live `session_is_local` flag (with hostname fallback only when the flag is missing) so remote logins that previously logged in locally no longer gain restore or scheduling controls (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseRestore.tsx`, `frontend/src/pages/SchedulingPage.tsx`).
- Archived schedule deletion buttons now respect the same guard, keeping remote users from removing runs while still letting them review history (`frontend/src/pages/SchedulingPage.tsx`).

## 2025-10-21 Schedule Timestamp Localisation

- Stopped writing UTC-naive strings for new schedules by stamping `created_at` / `updated_at` with the local wall-clock and persisting those values explicitly in SQLite (`backend/models.py`, `backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`).
- Guarded the Database Restore tab so only admins or users coming from a “local” login see the restore UI; remote non-admins now see a friendly notice instead of stacked API error pop-ups (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseRestore.tsx`).
- `AuthContext` now preserves the session metadata (`session_is_local`, IP classification, client IP) FastAPI returns, so future guards can make local-vs-remote decisions without another round trip (`frontend/src/context/AuthContext.tsx`).

## 2025-10-20 Restore Reconnect Hardening

- Fixed the maintenance bypass flag so `/health` polls escape the interceptor by checking `headers.has('X-Allow-Maintenance')` before rejecting, which lets the UI drop maintenance mode as soon as the backend responds (`frontend/src/services/api.ts`).
- Reworked the backup restore flow to open its own pyodbc connection, then clear pooled handles and wait for a clean `SELECT 1` before reporting success; the helper covers both managed `.bak` restores and the direct path workflow (`backend/services/backup.py`).
- Added a `reset_pools()` hook on the async connection manager so disruptive operations can drop stale handles, and wired `DatabaseConnectionManager.reset_pools()` through for legacy callers (`backend/core/database_connection.py`).
- Simplified the database service to use only the primary connection profile and removed the unused secondary config entry to reflect current deployments (`backend/services/database.py`, `backend/config.py`).

## 2025-10-20 Archived Deletion & Logging Cleanup

- Added delete controls to the archived schedules table/cards and route them through the existing confirmation dialog so archived jobs can be purged without switching tabs (`frontend/src/components/ScheduleList.tsx`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/types/scheduling.ts`).
- Disabled daily alias files in backend logging so `data/logs/` now only holds the live `robotcontrol_backend.log` and `robotcontrol_backend_error.log`; rotated files are compressed directly into `data/logs/history` (`backend/utils/logging_setup.py`).
- Reworked the system tray stop callback to flag the running uvicorn server to exit instead of calling `sys.exit`, which eliminates the `SystemExit` traceback from pystray when shutting down from the tray menu (`backend/main.py`).

## 2025-10-20 Restore Error Messaging

- Prevented Database Restore failures from firing both the modal status dialog and the page-level banner by removing the extra `onError` call in the restore handler, so users now see a single validation message when a restore cannot start (`frontend/src/components/DatabaseRestore.tsx`).

## 2025-10-19 Modal Notifications

- Replaced every inline error/success banner with the modal-based `ErrorAlert` suite so feedback now appears as dialogs instead of shifting layouts; the shared component renders Material UI dialogs with retry/close actions (`frontend/src/components/ErrorAlert.tsx`).
- Updated all consumers—camera, scheduling, backups, authentication dialogs, and system settings—to trigger the modal notifications and removed legacy snackbars/alerts (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/BackupManager.tsx`, `frontend/src/pages/BackupPage.tsx`, `frontend/src/components/ChangePasswordDialog.tsx`, `frontend/src/components/SystemConfigSettings.tsx`, `frontend/src/components/scheduling/FolderImportDialog.tsx`, `frontend/src/components/BackupActions.tsx`, `frontend/src/components/BackupListComponent.tsx`).
- Trimmed success messaging so one concise dialog appears per action and removed redundant inline alerts (e.g., backup creation/deletion, database restore, experiment deletion) for a single-source notification (`frontend/src/components/ErrorAlert.tsx`, `frontend/src/components/BackupManager.tsx`, `frontend/src/components/DatabaseRestore.tsx`, `frontend/src/components/DatabaseOperations.tsx`, `frontend/src/pages/BackupPage.tsx`).
- Adjusted restore confirmation copy so the warnings live directly in the dialog instead of duplicated modals, and clarified outage expectations in a short bullet list (`frontend/src/components/DatabaseRestore.tsx`).

## 2025-10-19 Camera Stream Aspect Ratio

- Let the live streaming card size itself to the incoming frame by capturing each `<img>`’s natural dimensions and applying an `aspectRatio`, replacing the old fixed 360 px viewport so portrait feeds fill the panel while placeholders keep a sensible minimum height; the fullscreen control now appears only after frames arrive (`frontend/src/pages/CameraPage.tsx`).
- Kept the reusable camera viewer ready for portrait feeds by syncing its aspect ratio to each frame’s natural size (`frontend/src/components/CameraViewer.tsx`).

## 2025-10-19 Frontend Maintenance Guides

- Added idiot-proof walkthroughs for the authentication, camera, database, scheduling, monitoring, and application shell UI so every frontend module now has a matching maintenance manual (`docs/maintenance/frontend/authentication-frontend-maintenance-guide.md`, `docs/maintenance/frontend/camera-frontend-maintenance-guide.md`, `docs/maintenance/frontend/database-frontend-maintenance-guide.md`, `docs/maintenance/frontend/scheduling-frontend-maintenance-guide.md`, `docs/maintenance/frontend/monitoring-frontend-maintenance-guide.md`, `docs/maintenance/frontend/main-application-frontend-maintenance-guide.md`).
- Each guide mirrors the backend documentation style—high-level architecture, lifecycle steps, key state, tasks, extension patterns, and troubleshooting—so future contributors have consistent references across the stack.

## 2025-10-19 Maintenance Guides Expansion

- Documented the authentication stack for future operators, covering the `AuthService`, SQLite schema, REST endpoints, and frontend token wiring so password resets, token refreshes, and config tweaks stay predictable (`docs/maintenance/authentication-maintenance-guide.md`).
- Captured the full monitoring/notifications pipeline—background loops, experiment polling, WebSocket channels, and scheduler email alerts—so the real-time dashboard and alerting remain stable during tweaks (`docs/maintenance/monitoring-maintenance-guide.md`).
- Wrote a main-application guide describing FastAPI startup/shutdown, static asset serving, logging directories, and packaging scripts to make backend deployments and PyInstaller builds idiot-proof (`docs/maintenance/main-application-maintenance-guide.md`).

## 2025-10-18 Scheduling Maintenance Trim

- Added a project-level `.gitignore` so transient build outputs (PyInstaller bundles, frontend builds, venvs, caches) stop polluting status checks while still leaving the generated files in place for runtime use (`.gitignore`).
- Removed the obsolete `database_manager_backup.py` module entirely; all scheduling paths now import the single primary database manager implementation (`backend/services/scheduling/database_manager.py`).
- Encapsulated scheduler capacity acquisition in a dedicated helper, leaving `_execute_job` easier to follow while preserving the existing retry semantics and logging (`backend/services/scheduling/scheduler_engine.py`).
- Moved execution-history deduplication into the SQLite layer so the API now returns a single authoritative record per execution; the React view simply renders the list without client-side merging (`backend/services/scheduling/sqlite_database.py`, `frontend/src/components/ExecutionHistory.tsx`).
- Centralised manual-recovery normalisation in the scheduling API client so hooks and services share one mapping definition (`frontend/src/services/schedulingApi.ts`, `frontend/src/hooks/useScheduling.ts`).
- Dropped stale backend service singletons by making `get_services()` fetch fresh dependencies each call, avoiding hidden global state while keeping endpoint signatures unchanged (`backend/api/scheduling.py`).
- Removed the unused refactored camera route and demo components after folding their improvements into the main camera page, trimming dead UI code (`frontend/src/pages/CameraPageRefactored.tsx`, `frontend/src/components/examples/*`, `frontend/src/components/camera/index.ts`, `frontend/src/components/camera/TabPanel.tsx`).
- Simplified the camera backend to use the standard config/data-path helpers and rely solely on the shared frame buffer/LiveStreaming service for streaming, eliminating the legacy per-camera frame cache and fallback imports (`backend/services/camera.py`, `backend/services/live_streaming.py`, `backend/tests/test_camera.py`).
- Broke the backup service into a `SqlCommandExecutor` and `BackupMetadataStore`, removing duplicated SQL/metadata handling logic and making the core service focused on orchestration (`backend/services/backup.py`).

---
## 2025-10-17 Archive Feature Finalization

- Removed every reference to the legacy `failed_execution_count` field so new databases no longer create or maintain the column while existing files stay compatible; scheduling models, API payloads, and SQLite operations now ignore the obsolete counter (`backend/models.py`, `backend/api/scheduling.py`, `backend/services/scheduling/sqlite_database.py`, `frontend/src/types/scheduling.ts`, `frontend/src/services/schedulingApi.ts`).
- Hardened archive toggling on the backend by reusing the standard update path, forcing scheduler cache invalidation, and keeping optimistic locking timestamps accurate so archived schedules reliably stay dormant (`backend/api/scheduling.py`).
- Completed the frontend archive experience with dedicated loading states, list labelling, and hook state for archived schedules, allowing the “Archive” tab and buttons to stay in sync after archive/unarchive actions (`frontend/src/hooks/useScheduling.ts`, `frontend/src/components/ScheduleList.tsx`, `frontend/src/pages/SchedulingPage.tsx`).

## 2025-10-17 Scheduler Concurrency Queueing

- Added a backlog tracker for schedules deferred because the concurrency limit is hit so we log “Max concurrent jobs reached” only once per waiting job and avoid losing it from the queue (`backend/services/scheduling/scheduler_engine.py`).
- Prevented one-time schedules from being auto-marked “missed” while they are waiting for capacity, letting them run as soon as the current job finishes instead of flipping to “Not scheduled” (`backend/services/scheduling/scheduler_engine.py`).
- Folded the scheduler’s concurrency limit into the same five-attempt retry loop we use for HxRun launches: when capacity is saturated the job logs a retry, waits 120 s, and after five tries it is treated as failed and rescheduled to its next interval (`backend/services/scheduling/scheduler_engine.py`).
- When a schedule is deleted we now persist its name/path snapshot with every archived execution so Execution History keeps the original experiment label instead of dropping to “Archived Schedule” (`backend/api/scheduling.py`, `backend/services/scheduling/database_manager.py`, `backend/services/scheduling/sqlite_database.py`, `backend/services/scheduling/scheduler_engine.py`).

## 2025-10-17 Scheduling Failure Handling Refresh

- Removed the legacy `failed_execution_count` bookkeeping and now rely on HxRun launch retries alone; each scheduled occurrence attempts to start the robot up to five times before reporting failure (`backend/services/scheduling/scheduler_engine.py`, `backend/services/scheduling/experiment_executor.py`).
- When a run aborts, the scheduler marks the schedule inactive via manual recovery and emails the configured contacts using the existing notification pipeline (`backend/services/scheduling/scheduler_engine.py`, `backend/services/scheduling/sqlite_database.py`).
- Non-abort launch failures now trigger an “execution_failed” notification so operators are alerted even when the robot never started (`backend/services/scheduling/scheduler_engine.py`).
- Introduced an `archived` flag for schedules, API support to list/archive/unarchive them, and a dedicated frontend tab so operators can review retired experiments without cluttering the active list (`backend/models.py`, `backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`, `frontend/src/hooks/useScheduling.ts`, `frontend/src/components/ScheduleList.tsx`, `frontend/src/pages/SchedulingPage.tsx`).

## 2025-10-17 Schedule Deletion Concurrency Fix

- Background scheduler updates now avoid touching the `updated_at` field by passing `touch_updated_at=False` whenever they persist interval/next-run metadata. This keeps optimistic locking tokens stable for UI operations (`backend/services/scheduling/scheduler_engine.py`, `backend/services/scheduling/database_manager.py`, `backend/services/scheduling/sqlite_database.py`).
- Added a `touch_updated_at` flag through the scheduling data layer so API writes still bump timestamps while automated maintenance writes do not, preserving multi-user safeguards without spurious 409s on delete requests (`backend/services/scheduling/database_manager.py`, `backend/services/scheduling/sqlite_database.py`).
- Updated the scheduler manual-recovery test stub to support the new signature (`backend/tests/test_scheduler_manual_recovery.py`).
- Experiment execution now resolves stored relative experiment paths against the Hamilton `Methods` root, so imports from “Active Experiment” (and other sibling folders) run without falling back to the legacy LabProtocols directory (`backend/services/scheduling/experiment_executor.py`).
- Scheduling API writes now persist the exact `updated_at` values supplied by the caller instead of relying on SQLite’s UTC `CURRENT_TIMESTAMP`, eliminating timezone drift between optimistic-lock headers and stored records (`backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`, `backend/models.py`).
- Manual recovery helpers write explicit UTC timestamps to keep schedule metadata consistent with other updates (`backend/services/scheduling/sqlite_database.py`).

## 2025-10-16 Tray Menu Simplification & Log History Relocation

- Replaced the Windows tray menu with the three requested actions so the icon only exposes `Open in Browser`, `Show Data`, and `Terminate` (`backend/utils/system_tray.py`); terminate still runs the graceful stop callback before forcing the process down.
- Logging setup now writes rotated archives into `data/logs/history`, keeps only the active-day aliases in `data/logs`, and moves existing dated `.log`/`.log.gz` files into the history folder during startup (`backend/utils/logging_setup.py`).

## 2025-10-15 README Completion

- Filled the missing sections in `README.md` to align with project conventions: completed Implemented Modules for SQL Server, Camera, and Scheduling; and added a concise Local Development guide.
- Documented key API groups and data paths, included an example `backend/.env` snippet, and called out the Microsoft ODBC driver requirement for SQL Server connectivity.
- Kept existing highlights, repository layout, and Windows packaging steps; no code changes required.

## 2025-10-15 Database Browser Layout Tuning

- Limited the database browser cards to responsive `maxHeight` values and contained overflow so table content scrolls inside the card instead of stretching past the viewport on mobile (`frontend/src/pages/DatabasePage.tsx`).
- Reworked the table container to keep pagination anchored below the scroll area and moved filter editors into a responsive drawer so the data grid keeps its height even with multiple conditions (`frontend/src/components/DatabaseTable.tsx`).
- Increased the responsive height allowances for the database cards and enforced larger minimum table heights so roughly 10 rows remain visible on desktop and more rows show on mobile even when chips are present (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseTable.tsx`).

## 2025-10-14 Branding Refresh

- Renamed all user-facing strings, documentation, environment defaults, and packaging assets from “PyRobot” to “RobotControl” (`README.md`, `backend/main.py`, `frontend/src/**/*`, `build_scripts/*`, `RobotControl.spec`, etc.).
- Updated environment variable prefixes to `ROBOTCONTROL_` and adjusted default credentials/subjects accordingly (`backend/services/auth.py`, `.env.example`, `backend/services/notifications.py`).
- Regenerated packaging spec as `RobotControl.spec` with relative project paths so branding stays consistent without hard-coded directories.
- Cleaned up scheduling/monitoring UI copy, removed the discovery auto-scan, limited folder imports to localhost, trimmed summary cards, and simplified system-status widgets (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/scheduling/FolderImportDialog.tsx`, `frontend/src/pages/MonitoringPage.tsx`, `frontend/src/components/MonitoringDashboard.tsx`, `frontend/src/App.tsx`).
- Formatted archive video labels to display friendly timestamps while keeping actions accessible on mobile (`frontend/src/components/camera/VideoArchiveTab.tsx`).
- Refined the top navigation bar layout so the title, user info, and buttons wrap cleanly on small screens (`frontend/src/App.tsx`).
- Widened the database browser layout so the table list keeps its refresh button and the data card/pagination stay fully visible even with multiple filters (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseTable.tsx`).

## 2025-10-14 Camera Page Streamlining

- Camera page now focuses on two tabs (Archive + Live Streaming); dropped the inline system-status modal and live camera grid so health info stays on the dedicated System Status screen (`frontend/src/pages/CameraPage.tsx:392-760`).
- Streaming panel shows only session ID and connection state while keeping fullscreen playback support; removed quality/bandwidth/FPS details per UX request (`frontend/src/pages/CameraPage.tsx:660-750`).
- Video archive folders/files wrap cleanly on mobile and always expose action buttons thanks to responsive tweaks and loading spinners (`frontend/src/components/camera/VideoArchiveTab.tsx:200-464`).

## 2025-10-14 Scheduling Recovery Reference & Camera Notes

- Interval miss grace is half the configured interval hours; see `backend/services/scheduling/scheduler_engine.py:575-599` where `_find_due_jobs` computes `grace_period_minutes = (experiment.interval_hours * 60) / 2`.
- Missed runs log `start_time` plus the current timestamp as `end_time`, so execution history shows a long `calculated_duration_minutes`; originates in `_find_due_jobs` (`backend/services/scheduling/scheduler_engine.py:583-599`) and the formatter `get_execution_history` (`backend/services/scheduling/sqlite_database.py:1399-1424`).
- New pre-execution steps register via `_register_builtin_steps` (`backend/services/scheduling/pre_execution.py:103-160`); implement handlers with cleanup similar to `_scheduled_to_run_step`.

## 2025-10-13 Admin User Controls

- Limited the admin API to user email updates and account deletion, adding dedicated endpoints while preventing self-deletion and duplicate email assignment (`backend/api/admin.py`, `backend/services/auth.py`, `backend/services/auth_database.py`).
- Simplified the admin UI to match: user management now supports only editing email addresses or removing accounts, with refreshed UX feedback (`frontend/src/components/UserManagement.tsx`, `frontend/src/pages/AdminPage.tsx`, `frontend/src/services/api.ts`).

## 2025-10-13 Dashboard & Layout Cleanup

- Removed descriptive footer panels from Scheduling and Backup pages to keep the UI focused on actionable controls (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/pages/BackupPage.tsx`).
- Centered About page cards and ensured they stretch evenly by flexing grid items, eliminating the right-leaning layout (`frontend/src/pages/AboutPage.tsx`).
- Streamlined the Dashboard by dropping the Quick Actions card and centering the experiment widget; the latest experiment panel now loads after a 1 s handshake instead of 3 s (`frontend/src/pages/Dashboard.tsx`, `frontend/src/components/ExperimentStatus.tsx`).

## 2025-10-13 Multi-User Concurrency & Token Refresh

- Added optimistic concurrency to schedule update/delete/manual-recovery routes using `If-Unmodified-Since` tokens from the UI; stale submissions now raise HTTP 409 and trigger an automatic reload (`backend/api/scheduling.py`, `frontend/src/hooks/useScheduling.ts`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/services/schedulingApi.ts`, `frontend/src/types/scheduling.ts`).
- Scheduler now exposes `invalidate_schedule` and returns the manual-recovery snapshot as part of `/status/scheduler`, keeping the cache encapsulated and the recovery banner in sync with the 30 s poll (`backend/services/scheduling/scheduler_engine.py`, `frontend/src/hooks/useScheduling.ts`).
- Axios interceptors retry once with the stored refresh token before logging out, and a custom event keeps `AuthContext` aligned when a new access token is issued (`frontend/src/services/api.ts`, `frontend/src/context/AuthContext.tsx`).

## 2025-10-13 Multiline Alert Rendering & Status Dialogs

- Normalized newline handling so backend strings containing `\n` render as real line breaks in shared alerts and restore status dialogs via the new `normalizeMultilineText` helper (`frontend/src/components/ErrorAlert.tsx`, `frontend/src/components/DatabaseRestore.tsx`, `frontend/src/utils/text.ts`).
- Added a reusable `StatusDialog` wrapper to keep success/error feedback consistent on mobile and migrated the scheduling admin panels (`NotificationEmailSettingsPanel`, `NotificationContactsPanel`, `ImprovedScheduleForm`, and `DatabaseRestore`) to use it (`frontend/src/components/StatusDialog.tsx`, `frontend/src/components/DatabaseRestore.tsx`, `frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`, `frontend/src/components/scheduling/NotificationContactsPanel.tsx`, `frontend/src/components/scheduling/ImprovedScheduleForm.tsx`).
- Scheduler delete now falls back to the SQLite manager when the in-memory engine isn't loaded, so admins can remove schedules even if the scheduler service is offline (`backend/api/scheduling.py`).
- Database restore kicks off a health-check watcher that clears maintenance mode as soon as the backend responds again instead of waiting the full sixty-second timeout (`frontend/src/components/DatabaseRestore.tsx`).

## 2025-10-13 Camera Archive Virtualization

- Replaced the archive card-grid with a collapsible tree that virtualizes video rows via `react-window`; per-folder state now lives inside `VideoArchiveTab` and supports optional lazy loading (`frontend/src/components/camera/VideoArchiveTab.tsx`, `frontend/src/types/components.ts`).
- Updated the camera page to consume the shared archive component so the optimized UI appears on the main route (`frontend/src/pages/CameraPage.tsx`).
- Added a full-screen dialog for the live streaming preview triggered from the inline player, closing automatically if the session drops (`frontend/src/pages/CameraPage.tsx`).
- Standardised SQL backup writes to `data/backups` and removed the compressed backup attempt so Express Edition uses the same reliable sqlcmd path as the legacy UI (`backend/config.py`, `backend/services/backup.py`).

## 2025-10-13 Persistent Auth Rework

- Replaced the in-memory AuthService with a SQLite-backed store (`backend/services/auth.py`, `backend/services/auth_database.py`) seeded with `admin / ShouGroupAdmin`, introduced hashed refresh-token tracking, registration, change-password, and admin reset flows (`backend/api/auth.py`, `backend/api/admin.py`, `backend/scripts/auth_cli.py`).
- Added regression tests for the new flows (`backend/tests/test_auth.py`) and CLI helpers for operators; note pytest is required to run the suite.
- Updated the React client with self-serve registration, change-password dialog, and refreshed auth context (`frontend/src/context/AuthContext.tsx`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/components/ChangePasswordDialog.tsx`, `frontend/src/App.tsx`, `frontend/src/services/api.ts`).
- Introduced password reset request queue + admin tooling and forgot-password UI (`backend/api/auth.py`, `backend/api/admin.py`, `frontend/src/components/UserManagement.tsx`, `frontend/src/pages/LoginPage.tsx`).
- Hardened live streaming session tracking so stale sessions no longer block new users (`backend/services/live_streaming.py`).
- Tweaked Monitoring page to avoid duplicate headings and hide experiment card in the detail view (`frontend/src/pages/MonitoringPage.tsx`, `frontend/src/components/SystemStatus.tsx`).
- Restored a lightweight `/admin` console that surfaces the new user management tooling and hides non-admin routes (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/pages/AdminPage.tsx`).

## 2025-10-12 Maintenance UX & Modal Alerts

- Added centralized maintenance tracking so destructive workflows (e.g. database restore) trigger a short-lived maintenance window that pauses API polling, surfaces a countdown dialog, and resumes once the backend is reachable (`frontend/src/utils/MaintenanceManager.ts`, `frontend/src/hooks/useMaintenanceMode.ts`, `frontend/src/services/api.ts`).
- Refresh Flow: Database restore confirmations now show a dedicated modal summarizing the operation impact and, on success/failure, follow-up pop-up dialogs ensure mobile users see status immediately (`frontend/src/components/DatabaseRestore.tsx`, `frontend/src/components/MaintenanceDialog.tsx`).
- Next session: migrate other admin/scheduling pages to reuse the shared pop-up dialog pattern so error/success feedback is consistent across desktop and mobile.

## 2025-10-12 Connection Locality Detection

- Added `backend/utils/network_utils.py` and `backend/api/dependencies.py` so endpoints can classify requests as local vs remote using IP heuristics. Auth endpoints now attach session locality metadata to login and `/api/auth/me` responses for the frontend to consume.
- Locked down `/api/backup/restore` to local callers via the new dependency and emit structured audit events for restore attempts (`backend/api/backup.py`, `backend/utils/audit.py`). Locality now means loopback-only (127.0.0.1/::1).
- Restricted `/api/database/execute-procedure` to loopback connections, logging every invocation (or error) with the initiating user for audit purposes (`backend/api/database.py`). Deferred: extend checks to additional write endpoints, bubble locality flags into the frontend to hide destructive UI, and surface audit history.
- Scheduling mutations are now loopback-only: create, update, delete, manual recovery, and notification management endpoints depend on the locality guard and emit audit entries (`backend/api/scheduling.py`). Remaining UI work: hide restricted controls when the session is remote.
- Backup creation/deletion and database cache clearing require a loopback connection and log every attempt (`backend/api/backup.py`, `backend/api/database.py`).
- Added modal status dialogs for backup create/restore flows and introduced a maintenance window gate that pauses background API calls and surfaces a countdown dialog after restores (`frontend/src/components/DatabaseRestore.tsx`, `frontend/src/utils/MaintenanceManager.ts`, `frontend/src/components/MaintenanceDialog.tsx`, `frontend/src/services/api.ts`).
- Corrected the restore warning copy so bullet points render properly in the confirmation banner (`frontend/src/components/DatabaseRestore.tsx`).

## 2025-10-12 Performance Logging Cleanup

- Removed the unused performance logging subsystem (router, middleware, utilities) so the backend stops emitting empty `performance_*.log` files (`backend/api/performance.py`, `backend/middleware/performance.py`, `backend/utils/logger.py`, `backend/main.py`).

## 2025-10-12 Backup Path Persistence

- Pointed the backup service at the managed data directory so PyInstaller builds persist backups beside `RobotControl.exe` rather than the temp `_MEI` unpack location (`backend/services/backup.py`).

## 2025-10-11 Manual Recovery Dropdown

- Swapped the manual recovery recipient text area for a multi-select fed by Notification Contacts, keeping custom addresses visible and clarifying the helper copy (`frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`).
- Passed the contact list through to the email settings panel so selections stay synchronized with the scheduler contact management view (`frontend/src/pages/SchedulingPage.tsx`).

## 2025-10-11 Manual Recovery Distribution

- Manual recovery recipient lists persist in NotificationSettings and flow through the admin API/UI; legacy `ROBOTCONTROL_*` email fallbacks were removed so delivery now depends on stored configuration (`backend/api/scheduling.py`, `backend/services/scheduling/sqlite_database.py`, `backend/services/notifications.py`, `backend/tests/test_notifications.py`).
- Hamilton TRC attachments convert to `.log` files with predictable names before mailing, and scheduler alerts prefer the configured distribution list when present (`backend/services/notifications.py`, `backend/tests/test_notifications.py`).
- Restored missing FastAPI imports so the scheduling router initializes correctly in packaged builds (`backend/api/scheduling.py`); rebuilt frontend assets, refreshed embedded resources, and regenerated the PyInstaller executable to capture all changes (`frontend build output`, `backend/embedded_static.py`, `dist/RobotControl.exe` via `build_scripts/pyinstaller_build.py`).

## 2025-10-10 Long-Run Alerts & SMTP Test Harness

- Scheduler watchdog now fires long-running alerts strictly at 2x the estimated duration and falls back to a stitched MP4 summary built from the latest three rolling clips (recorded at 7.5 fps) when no experiment archive exists (`backend/services/notifications.py`, `backend/services/scheduling/scheduler_engine.py`, `backend/tests/test_notifications.py`).
- Camera recorder targets 7.5 fps for rolling clips and the unit suite asserts the new writer configuration (`backend/services/camera.py`, `backend/tests/test_camera.py`).
- Added `/api/scheduling/notifications/settings/test`, UI wiring, and build safeguards: Send Test Email button, hook integration, and preserved `dist/data/backups` during PyInstaller rebuilds (`backend/api/scheduling.py`, `frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`, `frontend/src/services/schedulingApi.ts`, `frontend/src/hooks/useScheduling.ts`, `frontend/src/pages/SchedulingPage.tsx`, `build_scripts/pyinstaller_build.py`).

## 2025-10-10 SMTP Config Panel

- Swapped Fernet secrets for Windows DPAPI so SMTP credentials encrypt/decrypt without a shared key (`backend/utils/secret_cipher.py`, `backend/services/notifications.py`).
- Added NotificationSettings persistence + admin API and extended the scheduling UI with an Email Settings tab (DPAPI-backed password storage) (`backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`, `frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`).
- Added encrypted NotificationSettings storage and admin API so the scheduler reads SMTP host/sender/password from SQLite instead of environment variables (`backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`, `backend/services/notifications.py`).
- Extended the scheduling admin UI with an Email Settings tab that encrypts passwords via Fernet and guides operators through key setup (`frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/hooks/useScheduling.ts`).

## 2025-10-10 Scheduler SQLite Def Fix

- Removed the duplicated, truncated `_row_to_scheduled_experiment` helper that left a dangling try block and broke PyInstaller execution (`backend/services/scheduling/sqlite_database.py`).
- Verified the corrected module via `python -m compileall backend/services/scheduling/sqlite_database.py` to ensure the packaged build loads cleanly.

## 2025-10-09 Scheduler Watchdog & Admin Notifications

- Implemented long-running and abort alert dispatch with notification logging, attachment bundling, and contact cache refresh (`backend/services/scheduling/scheduler_engine.py`, `backend/services/notifications.py`, `backend/services/scheduling/sqlite_database.py`).
- Added admin-facing notifications tab with contact CRUD, filterable delivery history, and surfaced latest alert status on schedule detail cards (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/scheduling/NotificationContactsPanel.tsx`, `frontend/src/hooks/useScheduling.ts`).
- Extended schedule form to select contacts and wired notification log API plus persistence helpers; added backend tests covering notification logging CRUD (`frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `backend/api/scheduling.py`, `backend/tests/test_notification_logging.py`).

## 2025-10-09 Notification Contact Cache Bridge

- Added scheduling database-manager wrappers for contact CRUD so API and future services reuse the same SQLite helpers and keep timestamps aligned (`backend/services/scheduling/database_manager.py`).
- Scheduler now caches notification contacts and refreshes them on demand for upcoming alert logic (`backend/services/scheduling/scheduler_engine.py`).
- Contact management API endpoints trigger a cache refresh after create/update/delete operations to keep the engine in sync (`backend/api/scheduling.py`).

## 2025-10-09 Scheduling TZ & Video Archive Adjustments

- Normalized scheduling ISO timestamps to local naive datetimes so non-UTC systems no longer see start-time drift (`backend/utils/datetime.py`, `backend/api/scheduling.py`, `backend/models.py`, `backend/services/scheduling/*`, `backend/services/experiment_monitor.py`).
- Routed experiment archiving through StorageManager to keep original one-minute clips and surface richer metadata to automation (`backend/services/camera.py`, `backend/services/automatic_recording.py`, `backend/tests/test_camera.py`).
- Resolved PyInstaller data paths so packaged builds read/write the real data/videos directory beside the executable (`backend/config.py`).

## 2025-10-09 Camera Resolution ASCII Fix

- Replaced the multiplication symbol in camera resolution displays and fullscreen hint with ASCII `x` so Windows clients no longer see kanji U+8133 (Japanese "brain") in place of the separator (`frontend/src/pages/CameraPage.tsx`, `frontend/src/components/CameraViewer.tsx`).

## 2025-10-08 Streaming Guard & UI Polish (Binary Refresh)

- Refined the streaming CPU guard to sample the RobotControl process with a rolling window, preventing false "CPU limit reached" shutdowns while keeping the soft/hard protections (`backend/services/live_streaming.py`).
- Widened scheduling layout padding so desktop cards and calendars no longer hug the container edges (`frontend/src/pages/SchedulingPage.tsx`).
- Execution history's experiment filter now includes a short schedule-id suffix to distinguish duplicate method names (`frontend/src/components/ExecutionHistory.tsx`).
- Restored the lightweight camera live-stream view without frame counters while retaining start/stop controls (`frontend/src/pages/CameraPage.tsx`).
- Rebuilt the frontend, re-embedded static assets, and produced a fresh PyInstaller binary with the updated bundle (`build_scripts/embed_resources.py`, `build_scripts/pyinstaller_build.py`, `dist/RobotControl.exe`).

## 2025-10-08 Streaming Guard & Scheduling Polish

- Reworked the streaming CPU guard to sample the RobotControl process, smooth spikes, and require consecutive hits before terminating sessions (`backend/services/live_streaming.py`).
- Widened scheduling tab padding and card content so laptop layouts breathe instead of hugging the edges (`frontend/src/pages/SchedulingPage.tsx`).
- Execution history's experiment filter now shows each schedule's short id alongside the name to avoid duplicate labels (`frontend/src/components/ExecutionHistory.tsx`).

## 2025-10-08 Scheduling Layout & Streaming Consolidation

- Reordered top-level navigation so System Status sits beside About, updating both the desktop tabs and mobile drawer (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`).
- Relaxed the scheduling page spacing with wider gutters, roomier tabs, and padded cards while keeping manual recovery and calendar content consistent (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/ScheduleList.tsx`).
- Extended monitoring data to carry streaming status and reliable timestamps, then surfaced the service metrics on the System Status dashboard (`frontend/src/hooks/useMonitoring.ts`, `frontend/src/components/SystemStatus.tsx`, `frontend/src/components/MonitoringDashboard.tsx`).
- Streamlined the Camera streaming tab to just session controls, removing the metrics card and video preview while keeping start/stop flows intact (`frontend/src/pages/CameraPage.tsx`).

## 2025-10-08 Monitoring & Scheduling Tweaks

- Refined the scheduling form so the improved modal now powers both create and edit flows, requires an explicit experiment prep option, and removes the unused Hamilton tables flag (`frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/hooks/useScheduling.ts`).
- Mobile monitoring header now wraps cleanly, simplifies the status chip, and keeps last-update info readable at small widths (`frontend/src/components/MonitoringDashboard.tsx`).
- Latest bundle embedded and PyInstaller binary refreshed after UI fixes (`backend/embedded_static.py`).

## 2025-10-08 Navigation & Mobile Polish

- Database tables lose the nested scroll on phones by relaxing the card height on `DatabasePage` and only constraining `TableContainer` on md+ breakpoints so pagination stays in view (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseTable.tsx`).
- Removed the unused Admin surface, renamed Monitoring to System Status, and introduced a dedicated About page with navigation hooks across tabs, the mobile drawer, breadcrumbs, and keyboard shortcuts (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/components/NavigationBreadcrumbs.tsx`, `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`, `frontend/src/pages/AboutPage.tsx`).
- Compact experiment summaries now wrap their header/status controls and stack timestamps on narrow widths, avoiding truncated chips and timestamps (`frontend/src/components/ExperimentStatus.tsx`).
- Dashboard quick actions point at the new System Status route and expose a shortcut to the About page while retiring the redundant system info card (`frontend/src/pages/Dashboard.tsx`).
- Added a PyInstaller runtime hook that filters the deprecated `pkg_resources` warning so packaged binaries start cleanly, and wired it into the spec (`build_scripts/runtime_hooks/silence_pkg_resources_warning.py`, `Py
