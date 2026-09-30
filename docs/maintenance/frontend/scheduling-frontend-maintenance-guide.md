# Frontend scheduling

The Scheduling page: schedules and their editor, the runtime queue and recovery, the
method library, notifications and history. Backend behavior is in
[the backend scheduling guide](../backend/scheduling-maintenance-guide.md).

## Ownership

- `pages/SchedulingPage.tsx` owns selection, dialogs, permissions and the queue/recovery
  view. Its `InspectionWorkspace` keeps list and details mounted; narrow containers show
  one pane with Back.
- `hooks/useScheduling.ts` owns every schedule, archive, calendar, queue, contact and
  notification request. Components use its `state` and `actions`, never the REST API. It
  refreshes scheduler and queue status every 30 seconds. Each status read owns its error
  (`queueError`, `schedulerError`), shown inline and cleared by that read's next success;
  the shared `error` dialog is for schedule loads and edits only. Both reads carry
  `manualRecovery`, so only the most recently requested answer is applied. Mutations reload what they change;
  `updateSchedule` adds `expected_updated_at` so a stale edit returns 409.
- `ExecutionHistory` polls history itself through `useSerialPolling` and must not create
  another `useScheduling` (that would start a second scheduler poller); see the polling guide.
- `services/schedulingApi.ts` normalizes responses (older payloads get defaults, for
  example a 3-minute log inactivity threshold).

`ScheduleCollection` searches and sorts the loaded list; `ScheduleList` remains the
archived table. Calendar groups derive from the current schedule array. Use the
backend's `next_run`/`start_time`; never recalculate run times in the browser.

## Layout and sections

Scheduling uses `PageContent`/`PageHeader`; the heading owns **Create schedule** and
**Import methods** (so `MethodLibraryPanel` gets `showImportAction={false}`). Sections are
sidebar URLs through `useSchedulingSection` (`/scheduling?section=methods`); internal panel
indices are implementation details and there is no second section bar. Notifications keeps
its own Contacts/History/Email settings tabs. Visited sections stay mounted through
`SectionPanel`: History receives `active`, so leaving it stops polling but keeps filters.

The list and runtime queue use a named CSS container query: two columns only when at
least 1100px remains after navigation and gutters (not a viewport breakpoint). The
service strip shows scheduler state, Refresh, Recovery required and a Queue details
disclosure. History, notification and method tables scroll inside their container; the
Methods table uses page scrolling while its folder tree scrolls on its own. Opening or
resizing any view never starts, resumes, archives or deletes a schedule.

## Local and remote sessions

`isLocalUser(user)` uses the server's `session_is_local`, falling back to a localhost
hostname only when the flag is absent. Remote sessions get no Create, Edit, Delete,
Archive, Import, recovery or archived-delete controls; handlers also return early. The
backend enforces the same rules and is authoritative.

## Schedule editor

`ImprovedScheduleForm` is full screen below the medium breakpoint. A draft starts once per
opening; background refreshes of method choices or props must keep focus, cursor, scroll,
expanded sections and values, and must not reapply initial focus (MUI Dialog owns focus).
Cancel, Escape and the backdrop ask before discarding edits, and reload/close is guarded
while dirty. A failed save keeps the values and shows the error inline; a 409 asks the
operator to cancel, refresh and reopen. Create and update each reload the list once.

- New schedules cannot start before the current local time.
- **Log inactivity threshold (minutes)** defaults to 3, takes a positive whole number, is
  separate from estimated duration and the late-start cleanup timeout, and applies from the
  next launch. Omitted update values keep the saved setting; copies must keep it.
- **Email alert recipients** warns when no active contact is selected.
- Preparation choices come from `GET /api/scheduling/lab/preparation`: Experiment for
  EvoYeast or Batch for the SQLite example. Stale reads are discarded after refresh/close;
  a failed read keeps the saved ID and offers Retry. A downstream lab failure is a 502,
  because a 503 opens the database-maintenance dialog.
- Saving keeps the whole prerequisite array and its order; only an explicit selection
  replaces the selection tokens. Other steps such as ResetHamiltonTables stay and are
  listed separately. Saved IDs missing from the current choices are still shown.
  EvoYeast saves the ScheduledToRun + EvoYeastExperiment pair; the batch example saves
  `Batch:<code>`. Changing the Database viewer connection does not change these choices.
- Local administrators can open Database settings from the preparation controls. That
  page changes only the EvoYeast/Batch integration, shows Active now separately from
  Saved (restart required), reviews affected schedules and offers Cancel change.

## Runtime queue and recovery

Hamilton status and log condition are separate: SQL status 1 is Running and 2 is Paused
(`Hamilton: Paused · Log inactive`). A paused method still occupies the robot and log
monitoring continues. Running jobs show **Waiting for run/log**, **Monitoring**, **Log
inactive**, **Monitoring unavailable** or **Run ended; finalizing**, with threshold, trace
file, last activity and reason from the queue's optional `monitoring` object; payloads
without it still render. `queued_job_details[].waiting_reason` explains blocked jobs.

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

Delivery logs show all statuses by default (sent, pending, error, partial, unknown,
cancelled), refresh serially every five seconds while visible and stop when hidden;
request generations stop an old filter's response replacing a newer one. `long_running`
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
- **Editor shows old values:** the page must pass the current initial data when opening.
- **Edit returns 409:** someone else saved first; reopen after refresh.
- **Archived list empty:** `loadArchivedSchedules` runs when the section first opens
  (`archivedInitialized` prevents repeats).
