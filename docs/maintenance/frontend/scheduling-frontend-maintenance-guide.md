# Frontend scheduling

The Scheduling page: schedules and their editor, the runtime queue and recovery, the
method library, notifications and history. Backend behavior is in
[the backend scheduling guide](../backend/scheduling-maintenance-guide.md).

## Ownership

- `pages/SchedulingPage.tsx` owns the open form (`{ schedule?, method? } | null`), dialogs,
  permissions and the queue/recovery view. Schedules and Archived share one
  `InspectionWorkspace` with `ScheduleCollection` and the same detail; each shows the
  selection only when it lists it. Narrow containers show one pane with Back.
- `hooks/useScheduling.ts` owns schedule and archive loading, the one selection (Schedules,
  Archived, History and the delete dialog; a reload drops it when neither list holds it),
  contacts and notification settings. Recovery, delivery-log, method-library and protocol
  components make their own requests through `services/schedulingApi.ts`, whose `call`
  helper turns every reply into data or the server's message; the calendar derives its
  entries from loaded schedules. The shared `error` dialog is for schedule loads and edits
  only. Mutations reload what they change; a failed delete reloads both lists. An update
  sends the version the form opened as `expected_updated_at` (body only), so a stale edit
  returns 409.
- Queue, scheduler and recovery state come from the frame's one status read
  (`useRobotStatusContext`, `/status/queue` with the scheduler's `is_running`). The page shows
  its failure inline ("Status not updated"), cleared by the next successful read; Refresh
  queue and recovery actions call its `refresh`. A reply without `is_running` or
  `manual_recovery` is a failed read, never an idle scheduler.
- `ExecutionHistory` polls history itself through `useSerialPolling` and must not create
  another `useScheduling`; see the polling guide.
- `services/schedulingApi.ts` normalizes responses (older payloads get defaults, for
  example a 3-minute log inactivity threshold) and builds the create and update body from
  the form's `ScheduleFormValues` (`buildScheduleRequest`).

`ScheduleCollection` searches, filters (All/Active/Inactive/Recovery, with counts) and
sorts the loaded list. In `InspectionWorkspace`'s `layout="table"` it is the wide side and
the details are a 400px panel; from 640px of its own width (a container query) it shows the
table columns Experiment, Repeats, Next run, Last run and Status, otherwise one stacked row
per schedule. On a phone (under 600px) opening a schedule scrolls its details to the top and
focuses the name; a Next run block shows the stored next run large (an inactive, archived,
held or under-review schedule says it will not run), and the schedule's actions sit
in a bar pinned above the page bar (`pinnedBarSx`), with the same permission and disabled rules;
remote users see the read-only line there. A **remote** session on a phone does not get this page
for Schedules and History: `SchedulingRoute` shows `PhoneRuns`, the read-only Runs tab with an
Agenda/History switch kept in `?section=`. Agenda lists today and tomorrow: the running schedule
first, active schedules, and held ones (fetched with `active_only=false`, because holding clears
`is_active`), never inactive or archived ones; rows expand to their facts. History groups the
last 50 executions by day; only problems get a chip, and a failed run expands to its error.
The workstation's own browser keeps the full page at any width, so narrowing it never unmounts
an open draft. Checks: `phone-runs.spec.ts`. Back from details on a phone focuses the open row (`aria-current`), not the
selected filter button, which is also `.Mui-selected`. Archived uses the same list without
the status filter. `scheduleState` (exported from `ScheduleCollection`) is the one mapping
from a schedule to its label and tone: Needs review and Recovery required are amber (needs
action), Active green, Inactive and Archived grey. The list and detail panel use it through
`StatusChip`. The calendar shows the chip only for entries that are not plain Active (an
inactive schedule still has a `next_run`, so it must not read as a run that will happen).
Calendar groups derive from the current schedule array. Show the backend's `next_run` and
`last_run` only (never `start_time` as a next run) and never recalculate run times in the
browser. The detail shows dates with `dayTime`, the list's format ("Sun 27 Sep 14:30"),
and adds Last run, Created by and Created.

A schedule with `review_reason` failed the server's check of its stored fields and never
runs: the list shows Needs review with the reason as the row's second line, the detail an
alert with the reason, and the calendar, Overview's Up next and the phone agenda leave it
out. It offers Edit and Delete only. An archived schedule offers Restore and Delete only:
restore it first, then edit. Notification history in the detail opens the Notifications
section; the page keeps no copy of delivery rows.

A contact with `review_reason` gets no mail: its row in Notifications > Contacts shows the
Needs review chip in place of Active/Inactive and the reason under the name. Edit opens the
stored values; a saved edit clears the chip. Delete is unchanged. Email settings with
`review_reason` show "Needs review: <reason>" at the top of the panel; the form opens with
the stored values and a successful save clears it.

## Layout and sections

Scheduling uses `PageContent`/`PageHeader`; the heading owns **Create schedule** and
**Import methods** (so `MethodLibraryPanel` gets `showImportAction={false}`). Sections are
sidebar URLs through `useSchedulingSection` (`/scheduling?section=methods`); internal panel
indices are implementation details and there is no second section bar. Notifications keeps
its own Contacts/History/Email settings tabs. Visited sections stay mounted through
`SectionPanel`: History receives `active`, so leaving it stops polling but keeps filters.

The list and runtime queue use a named CSS container query: two columns only when at
least 1100px remains after navigation and gutters (not a viewport breakpoint). The
service strip shows scheduler state, Refresh queue, Recovery required and a Queue
details disclosure. The collection has a Schedules heading with Refresh,
then search, status filters and sort controls at a compact 16px inset. Refresh queue
and the collection's Refresh keep separate request scopes. History, notification
and method tables scroll inside their container; the Methods table uses page scrolling while its folder tree scrolls on its own. Opening or
resizing any view never starts, resumes, archives or deletes a schedule.

## Local and remote sessions

`isLocalUser(user)` (`components/navigation.tsx`) is how screens read the server's
`session_is_local`; a session without that answer counts as remote. The page computes it
once and passes it down as `isLocal`. Which sections need the RobotControl computer lives
only in `sectionRegistry`; the page renders by section. Remote sessions get no Create, Edit, Delete,
Archive, Restore, Import or recovery controls; handlers also return early. The
backend enforces the same rules and is authoritative.

## Schedule editor

`ImprovedScheduleForm` is full screen below the medium breakpoint. The page mounts it per
opening with the stored schedule (edit), a library method or nothing (create); its draft
starts once from that snapshot and the form derives create or edit, the saved database step
and its state from it. Background refreshes of method choices or props must keep focus,
cursor, scroll, expanded sections and values, and must not reapply initial focus (MUI Dialog
owns focus). A schedule under review opens with no schedule type chosen (the stored one may
no longer be offered) and Save is refused until one is picked. The interval is kept once as
`interval_hours`; the preset choice and the custom hours and minutes are derived from it, so
a custom value equal to a preset stays custom.
Cancel, Escape and the backdrop ask before discarding edits, and reload/close is guarded
while dirty. A failed save keeps the values and shows the error inline; a 409 asks the
operator to cancel, refresh and reopen. Create and update each reload the list once.

- New schedules cannot start before the current local time.
- **Log inactivity threshold (minutes)** defaults to 3, takes a positive whole number, is
  separate from estimated duration and the late-start cleanup timeout, and applies from the
  next launch. Omitted update values keep the saved setting; copies must keep it.
- **Run in VENUS Simulation Mode** sets the schedule's `mode` (`simulation` when on, `real`
  when off, the default). The form sends the mode it shows. The schedule table, Calendar and
  phone run details mark simulation schedules. Checks: `scheduling-lab.spec.ts`.
- **Email alert recipients** warns when no active contact is selected.
- **Before this run** holds the schedule's one database step (`PreparationStepField`): a local
  administrator picks an installed preparation tool, such as Select EvoYeast experiment, and
  its inputs (rendered by `ReportInputs`); others see it read-only. Local administrators can
  open Database settings from there to assign the package's connections. The form's `preparation` stays undefined until
  changed, so timing edits never send it and the server keeps the pinned step; `null`
  removes it. `preparation_state` from the schedule shows Ready / Needs review / Not
  installed; `schedulingApi.normalizeSchedule` passes it through (unknown values show as
  unknown, never ready). The schedule detail, list and Archive show `preparationSummary`.
- The retired `legacy_preparation` field and automatic preparation suggestions are removed. The form no longer prefills a database step from tokens and never sends `prerequisites`. A local administrator must choose the database step explicitly; a schedule with old tokens arrives with `review_reason` naming them.

## Runtime queue and recovery

Hamilton status and log condition are separate: SQL status 1 is Running and 2 is Paused
(`Hamilton: Paused · Log inactive`). A paused method still occupies the robot and log
monitoring continues. Running jobs show **Waiting for run/log**, **Monitoring**, **Log
inactive**, **Monitoring unavailable** or **Run ended; finalizing**, with threshold, trace
file, last activity and reason from the queue's optional `monitoring` object; payloads
without it still render. `queued_job_details[].waiting_reason` explains blocked jobs, in
Queue details and in the selected schedule's detail.

`RecoverySafetyPanel` lists every pending incident, including missing and archived
schedules. Acknowledgement needs the displayed safety revision and a robot-ready
confirmation (and a note for a missing schedule); it never resumes jobs. Resume is a
separate button that warns due jobs may start at once. After a conflict, refresh; never
retry automatically with a newer revision. Storage errors stay visible and keep the
controls disabled. Delete and archive respect recovery flags. Local administrators find
SQLite repairs in Administration (`SQLiteHealthPanel`; see the SQLite safety guide).

## Methods

`MethodExplorer` and `methodFolders` build a case-insensitive folder tree from catalogue
paths only (never the host filesystem). Drive and UNC paths are supported; relative or
unresolved paths go to Needs path review. Single-child folder chains are compressed for
display only. Breadcrumbs keep the original case. With one imported root, paths are shown
relative to it once; full paths stay in details, tooltips and Copy full path.

- **Picker** (`MethodPicker`, primary and cleanup fields): a row is provisional until
  **Use this method**; Cancel changes nothing. Reopening starts at the saved method's
  folder and page. Search overrides the folder until cleared. Keep component identity
  stable on refresh so search, focus, expansion and scroll survive. Choosing a method
  never scans the filesystem.
- **Library table** (`MethodLibraryPanel`): 25 rows per page (50/100 optional). Header
  selection covers the page; selection survives paging and clears when folder, search,
  status or archive filter changes. Archive/restore needs explicit rows and confirmation,
  sends each row's revision and reports partial failures; archiving never stops schedules
  or deletes files. Check paths revalidates; Refresh library reloads. Saved paths missing
  from the choices stay visible with an explanation. `catalogueVersion` refreshes choices
  without resetting an open schedule draft.
- **Import** (`FolderImportDialog`): Choose folder → Review methods → Import results. It
  only adds catalogue entries. `HostMethodBrowser` browses the RobotControl host (regular
  subfolders; linked folders are not scanned) and keeps the last usable folder after an
  error; manual absolute paths also work. The read-only preview lists every method as
  New/Update/Invalid with valid rows selected; search never changes the selection. The
  server revalidates and returns Added/Updated/Failed; show partial results even when
  `success` is false.
- **Change path** (`MethodPathDialog`, from a method's details): a manual absolute `.med`
  path or a host-browser file. Review separates busy, archived, active and inactive
  schedule references with separate primary/cleanup checkboxes, all unchecked, busy and
  archived disabled. Save sends the preview's revision and only the chosen references
  with their exact version strings. A 409 keeps the preview and choices; Review again
  clears the choices. A catalogue-only correction leaves every schedule unchanged.

## Notifications

The account address normally supplies both SMTP login and From address; custom values
and a null login stay supported (`smtpForm.ts`). Password: keep omits the field, update
sends it, clear sends an empty string; the stored password never reaches the browser.
One Security selector maps to `use_ssl`/`use_tls` without changing the port. Save before
testing: unsaved changes disable Send test and saving never sends mail. Refresh/discard
asks before replacing a dirty draft and only replaces it after a successful read. Results
stay as inline alerts. The test request waits up to 60 seconds; keep the backend's
detailed connection/TLS/authentication errors. Manual-recovery recipient overrides are
separate from a schedule's alert recipients. Contacts help explains that email needs an
active contact.

Delivery logs (`NotificationLogPanel`) own their filters, rows and poll. They show all
statuses by default (sent, pending, error, partial, unknown, cancelled), refresh serially
every five seconds while visible and stop when hidden; the panel stays mounted, so filters
survive a section switch, and a request counter stops an old filter's response replacing a
newer one. `long_running`
entries remain for history; new events are `log_inactive` and `monitoring_unavailable`.
`cancelled` means the condition cleared before sending. A sent pause is not repeated
after restart. SMTP-test log-storage warnings appear even when the email was sent.

## Messages

Failed reads show inline in their panel with Retry. Destructive actions go through
`DeleteConfirmationDialog`, never `window.confirm`. Create/update failures are always
shown (inline in the open editor or in `StatusDialog`) and keep the draft.

## Checks

Failure cases are in the headers of `frontend/e2e/operations.spec.ts` and
`scheduling-lab.spec.ts`; run them after `npm --prefix frontend run build`. They use
intercepted APIs, never robot services, and write evidence to
`test-output/viewer-verification`. Vitest suites sit beside the components
(`MethodExplorer`, `MethodLibraryPanel`, `MethodPathDialog`, `HostMethodBrowser`,
`FolderImportDialog`, `ImprovedScheduleForm`, `NotificationEmailSettingsPanel`,
`RecoverySafetyPanel`); run `npx vitest run` from `frontend`. Run-log state transitions
are covered by the backend trace tests; the simulator/email acceptance sequence is in
the backend guide.

## Troubleshooting

- **Schedules never load:** check `/api/scheduling/list` in the network tab;
  the hook's `state.error` must be displayed.
- **Editor shows old values:** the page must mount the form with the schedule as listed when
  Edit is pressed.
- **Edit returns 409:** someone else saved first; reopen after refresh.
- **Archived list empty:** `loadArchivedSchedules` runs on mount, after archive, restore
  or delete, and when Archived is refreshed; check `state.archivedError`.

## PyHSL schedules and the Run page

`ImprovedScheduleForm` chooses the runner. For a PyHSL protocol, `PyHslProtocolField` searches
`GET /api/pyhsl/protocols` by name or ID, sorted by name, and offers only the modes the chosen protocol allows
(Simulation first when allowed). Choosing a protocol or a mode runs `POST /api/pyhsl/validate`, whose reply draws the
parameter fields; a schedule saves only after a protocol PyHSL accepted. A VENUS schedule keeps its Simulation Mode switch.

`/pyhsl?run=<id>` (`PyHslRunPage`) shows PyHSL's Monitoring API view (PyHSL's `docs/api/notes.md`, "Monitoring API"):
Run Control's Run page without controls. `PyHslMonitor` loads an iframe with `sandbox="allow-scripts"` and no same
origin, so PyHSL's code cannot reach RobotControl's sign-in tokens. When the frame says "ready" (again after it was
replaced), it receives `/api/pyhsl/monitor.js` by message and runs it as a script element, then `{deck, state, theme}`
with the two bodies as received. The page polls `/api/pyhsl/runs/{id}` every five seconds (30 once ended). After a
successful run read it reads `/api/pyhsl/deck` (about 2 MB) once for that run ID, again only after a failed read;
PyHSL keeps the deck fixed while a run is in progress. Without `?run=` the page follows the active run from
`usePyHslStatus`. The view fills the window below the title (`useLabwareWorkspace`; the warning lines sit in an
always-present box so the fit is measured again) and scrolls its own panels. RobotControl adds only the title,
"Run Control not reachable since HH:MM" (the last reading stays), "Loading" or "Run view not shown: <reason>" in the
view's place, and Show report for an ended run; the report opens in a dialog in an iframe with an empty `sandbox`.
Failure cases are in `frontend/e2e/pyhsl.spec.ts`.
