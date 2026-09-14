# Frontend Scheduling Maintenance Guide

## Section navigation

Scheduling sections live beneath Scheduling in the application sidebar, using the shared `useSchedulingSection` URL mapping. Keep the existing internal panel indices only as implementation details; links use stable section names. Do not add a second horizontal Scheduling section bar. Notifications retains its own Contacts/History/Email settings tabs. Existing polling provides the sidebar's latest recovery warning through context.

## Catalogue folder navigation

`MethodExplorer` and `methodFolders` derive a case-insensitive folder hierarchy from current catalogue paths only. They do not call the host filesystem browser. Absolute drive and UNC paths are supported; relative or unresolved paths remain in Needs path review. Empty single-child ancestor chains are compressed for display without rewriting saved paths or catalogue records.

`MethodPicker` wraps the explorer for both primary and cleanup fields. Choosing a radio row is provisional until Use this method; Cancel leaves the form unchanged. The picker starts at the saved method's folder/page when reopening. Global search temporarily overrides the folder; clearing it returns to that folder. Keep component identity stable on catalogue refresh to preserve search, focus, expansion and scrolling.

The Methods table uses the same explorer, with 25 rows per page by default (50/100 optional). Header selection affects only that page; selection persists across page changes but clears on folder/search/status/archive filter changes. Full paths remain in details and Copy full path; table rows show paths relative to the selected folder. `MethodExplorer.test.tsx` exercises 1,000 methods and path/keyboard/refresh behavior; library tests cover selection across pages.

## Drafts and background refresh

Create/edit and method import use MUI Dialog focus management, not `useModalFocus`. Do not reapply initial focus on polling updates. A schedule draft is initialized once per open session; refreshing method choices or parent props must preserve focus, cursor, scroll, accordion expansion and field values. Only closing/reopening starts a new draft. The edit timestamp is captured at opening; a 409 response keeps entries and asks the operator to cancel, refresh and reopen. Creation/update each refresh the list once. `Email alert recipients` must show a clear warning when no active contact is selected.

Hamilton status and log condition are separate: SQL 1 means Running and 2 means Paused. Runtime rows show both (for example, `Hamilton: Paused · Log inactive`). A paused method remains an active execution occupying the robot, and log inactivity monitoring continues.

Run `npm test` for the focused Vitest suites beside scheduling components/hooks. `vitest.config.ts` deliberately excludes older Jest suites under `__tests__`; those require separate migration. `npm run build` remains the production TypeScript/Vite check.

## Email setup

The account address normally supplies both SMTP login and From address. `smtpForm.ts` converts saved settings to a draft and back to the existing API. Keep custom login/From addresses and null-login fallback compatible. Password keep omits the field; update sends the new value; clear sends an empty string. Never return the stored password to the browser. Security is one selector mapped to the existing `use_ssl`/`use_tls` booleans, without automatic port changes.

Save settings first, then send a test. Unsaved changes disable testing; saving never sends mail. Refresh/discard asks before replacing a dirty draft and only replaces it after a successful fetch. Results are persistent inline alerts, not timed dialogs. The SMTP test request still waits up to 60 seconds; the backend uses one send attempt with a ten-second timeout per SMTP operation. Keep detailed backend errors to distinguish connection, TLS and authentication failures. Manual-recovery recipient overrides are separate from the schedule's normal alert recipients.

## Change a method path

Open a method's details in the Methods tab, then choose Change path. `MethodPathDialog` accepts a manual absolute `.med` path or a file selected with `HostMethodBrowser`. Review shows the original/replacement path and separates busy, archived, active and inactive schedule references. Primary and cleanup references have separate checkboxes. All start unchecked, and busy/archived references are disabled. The summary explains how many references retain their old paths.

Save sends the preview's method revision and only the selected schedule references with their exact version strings. Do not round timestamps or preselect matching schedules. A 409/error retains the preview, entries and choices. Review again fetches current references and clears the choices for explicit review. Success reports the actual number of changed schedules and retained references; it refreshes the library, method choices and schedule list. Closing the dialog restores focus using MUI. A catalogue-only correction must leave every existing schedule unchanged.

`MethodPathDialog.test.tsx` covers partial selection, disabled paused/archived references, confirmation results and conflict draft retention. The host-browser tests cover file selection and navigation failures without losing the current folder.

## Import Hamilton methods

The local Methods tab uses `MethodLibraryPanel`: filters and sorting apply to loaded catalogue rows; changing filters clears bulk selection so hidden entries cannot be changed accidentally. Archive/restore requires explicit selected rows and confirmation, sends each row's revision, and reports partial failures. Check paths refreshes validation; Refresh library reloads stored data. Details include both primary and cleanup schedule references. `catalogueVersion` refreshes choices without resetting schedule drafts. Saved paths absent from current choices remain visible with an explanation. Archiving never stops existing schedules or deletes files.

`FolderImportDialog` has three stages: Choose folder, Review methods, Import results. Import adds catalogue entries only; it never creates schedules or starts Hamilton. `HostMethodBrowser` navigates the RobotControl host and supplies its absolute path directly with Use this folder. Manual absolute-path entry remains available. Both discover regular subfolders; linked folders are not scanned. No browser file upload or second path entry is involved. The same browser supports `.med` selection for path correction. Keep its last usable folder/selection after navigation errors.

Call the read-only preview endpoint first. Display every returned method and full host path, with New/Update/Invalid labels. Select valid rows by default, allow deselection, and disable invalid rows. Search filters the displayed list without silently changing selection. Submit the chosen relative paths with the preview's canonical folder; the server revalidates and returns actual Added/Updated/Failed results. Partial failures still have useful result data: do not discard it just because `success` is false. Lists are scrollable and searchable without a ten-row limit.

Successful imports invalidate method choices through `catalogueVersion`, preserving any open schedule draft. Only the explicit Create a schedule action opens the schedule form. Local-access controls exist in both UI and backend. Component tests cover browser/manual selection, required host paths, deselection, invalid entries, long results and partial failures; backend tests cover filesystem/database validation.

This document spells out how the scheduling UI is wired together. It assumes you need every instruction spelled out—no prior knowledge required. Follow it exactly so you don’t break experiment management.

---

## 1. High-Level Architecture

- `frontend/src/pages/SchedulingPage.tsx`  
  Primary screen. Renders tabs for schedules, notifications, execution history, etc. Manages dialogs (create/update schedule, folder import).

- `frontend/src/hooks/useScheduling.ts`  
  Single source of truth for scheduling data. Fetches schedules, archived schedules, queue status, manual recovery flags, contacts, and notification logs. Exposes `actions` for CRUD operations.

- Key components:
  - `frontend/src/components/ScheduleList.tsx` – Displays active/archived schedules, handles selection, action buttons.
  - `frontend/src/components/scheduling/ImprovedScheduleForm.tsx` – Dialog form for creating/editing schedules.
  - `frontend/src/components/scheduling/NotificationContactsPanel.tsx` – UI for managing notification contacts.
  - `frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx` – SMTP configuration panel.
  - `frontend/src/components/scheduling/FolderImportDialog.tsx` – Bulk import wizard.
  - `frontend/src/components/ExecutionHistory.tsx` – Combined execution log viewer.

- `frontend/src/services/schedulingApi.ts`  
  Low-level Axios helpers (`schedulingAPI`) and a higher-level convenience wrapper (`schedulingService`). Handles response normalisation and manual recovery mapping.

**Rule of thumb:** Let `useScheduling` manage all backend interactions. Components should consume `state` and `actions` from the hook instead of talking to the REST API directly.

---

## 1.5 Local vs Remote Sessions

- `SchedulingPage` calculates `isLocalSession` from the authenticated user (`session_is_local` when available, otherwise it falls back to checking whether the browser is hitting a localhost hostname). Do not try to outsmart this—fetch the flag from `useAuth()` instead of inventing your own detection.
- When `isLocalSession` is `false`, all destructive controls disappear: the Create/Edit/Delete/Archive buttons are replaced with a notice, and the manual recovery buttons (“View Schedule”, “Resolve Manual Recovery”) are hidden. The read-only cards stay visible so remote viewers still see status updates.
- The confirm handlers (`handleViewRecoverySchedule`, `handleResolveManualRecovery`) bail out early if `isLocalSession` is false. Leave those guards in place—remote browsers should never trigger backend mutations through devtools tricks.
- Folder import is also gated; the button stays visible only when the session is local (and falls back to hostname detection for development). Remote users should see the explanatory caption instead of touchy file dialogs.
- The archived schedules tab only wires up the delete callback when the session is local, so remote users never see the trash icon and cannot purge historical runs.

---

## 2. Scheduling Workflow Overview

1. **Page mount** → `const { state, actions } = useScheduling();`.  
   - `useScheduling` immediately calls `loadSchedules()` and `loadQueueStatus()`.  
   - While loading, `SchedulingPage` shows skeletons or progress indicators.

2. **Viewing schedules**  
   - `ScheduleList` receives `state.schedules` and displays them with quick-action buttons (activate/deactivate, archive, delete).  
   - Selecting a schedule updates `state.selectedSchedule`, which drives detail panels and the edit form.

3. **Creating a schedule**  
   - Clicking “New Schedule” opens `ImprovedScheduleForm` (modal).  
   - Form enforces local-time guard: create requests cannot use a `start_time` earlier than current local time.
   - Timeout behavior is configured in the same form (`timeout_minutes`, `timeout_action`, optional cleanup method).
   - On submit, `actions.createSchedule(formData)` calls the backend, then reloads schedules and focuses the new entry.

4. **Editing a schedule**  
   - `scheduleFormMode` switches to `"edit"` and pre-populates the form using `state.selectedSchedule`.  
   - `actions.updateSchedule(scheduleId, payload)` handles optimistic concurrency by passing `expected_updated_at`.

5. **Archive / Manual Recovery / Notifications**  
   - Tabs inside `SchedulingPage` let users view archived schedules (`actions.loadArchivedSchedules`), manage contacts (`actions.loadContacts`), update SMTP config, and review notification logs.

6. **Execution history**  
   - `ExecutionHistory` fetches logs from the hook (`actions.loadExecutionHistory`) when the tab opens.  
   - Filters (schedule ID, status) are stored locally in the component, but the hook owns the actual network call.

---

## 3. Key State Fields

From `useScheduling`:

- `state.schedules`, `archivedSchedules` – arrays of `ScheduledExperiment`.  
- `state.selectedSchedule` – the item currently highlighted.  
- `state.operationStatus` – one of `Idle`, `Loading`, `Creating`, `Updating`, etc. Use this to show spinners on buttons.  
- `state.queueStatus`, `state.hamiltonStatus` – metadata for the robot queue (including `running_job_details` and `queued_job_details`).  
  `queued_job_details[].waiting_reason` now explains why a queued job is blocked (for example maintenance/manual recovery/HxRun busy).
- `state.manualRecovery` – indicates if manual recovery is required and who flagged it.  
- `state.contacts`, `state.notificationLogs`, `state.notificationSettings` – used on the Notifications tab.

Useful derived flags provided by the hook:

- `state.loading` / `state.archivedLoading` – drive `LoadingSpinner` placements.  
- `state.error` / `state.archivedError` – show the inline warning cards in the schedule list panels.  
- `state.initialized` – prevents the page from showing “empty” states before the first load completes.

---

## 4. Working With the Hook

1. **Always destructure `state` and `actions`.**  
   ```ts
   const { state, actions } = useScheduling();
   const { schedules, selectedSchedule } = state;
   const { loadSchedules, createSchedule } = actions;
   ```

2. **Reload data after every mutation.** Actions like `createSchedule` already call `loadSchedules` internally. If you add new actions (e.g., pause scheduler), make sure they refresh the relevant state.
   - Queue telemetry refreshes every 30 seconds via `getQueueStatus()`; keep this interval when adding new queue-dependent widgets.
   - Do not recalculate next-run interval times on the client. Use backend-provided `next_run`/`start_time` as the canonical timestamp so UI matches actual launch timing.

3. **Handle errors gracefully.** Read-path failures still surface through `state.error`. Create/update form mutations now reject (`throw`) without setting the page-level error banner, so submit handlers must stay in `try/catch` and show a modal status dialog.

4. **Respect optimistic locking.** When updating a schedule, include `expected_updated_at`. The hook already injects it, but if you add new update flows, reuse the same pattern to prevent 409 conflicts.

5. **Keep forms and dialog state local to `SchedulingPage`.** The hook should not store modal flags—leave that to the page to avoid unwanted rerenders.

---

## 5. Common Maintenance Tasks

| Task | Where | Step-by-step |
|------|-------|--------------|
| Add a new schedule field (e.g., priority) | `ImprovedScheduleForm`, `useScheduling`, `ScheduleList` | Update form inputs, extend `CreateScheduleFormData`/`UpdateScheduleRequest`, pass through `schedulingService.buildScheduleRequest`, and display the field in lists and detail panels. |
| Show additional execution log columns | `ExecutionHistory.tsx` | Adjust the table header and row renderer. Ensure the backend includes the new field in the history API. |
| Reorder tabs or rename them | `SchedulingPage.tsx` | Update the `Tabs` component and the `TabPanel` labels. Ensure indexes still align with the correct content. |
| Add bulk schedule actions | `ScheduleList.tsx` + new action in `useScheduling` | Track selected rows, send a bulk request, then reload schedules. Show a toast to confirm completion. |
| Surface manual recovery banner globally | `SchedulingPage` | Read `state.manualRecovery` and display a `Warning` chip or banner at the top of the page. |

---

## 6. Passive vs Active Messaging

- **Passive dashboard** – List and detail panels show inline warning cards for errors (e.g., failed schedule fetch). If you add new read-only panels, keep the message in the panel and add a retry button.
- **Active operations** – Deleting schedules, resolving recovery, or other destructive changes must go through the shared `DeleteConfirmationDialog` / modal flows. Create/update form failures should surface in `StatusDialog` (not silent close). Don’t revert to `window.confirm` prompts.
- **Titles & buttons** – Keep inline card titles short (“Failed to load schedules”) and wire the existing action buttons (`Try Again`, `Retry`). Only escalate to modal to confirm irreversible changes.

---

## 7. Extending or Modifying Behaviour

### 6.1 Calendar view for schedules
1. Use `state.calendarEvents` (already provided by the hook).  
2. Add a new tab or component (`SchedulerCalendar`) that renders the events using your preferred calendar library.  
3. Provide a click handler so selecting a calendar event sets `selectedSchedule`.

### 6.2 Integrate drag-and-drop rescheduling
1. Allow dragging an event/date in your calendar component.  
2. On drop, call `actions.updateSchedule(scheduleId, { start_time: newDate })`.  
3. Handle concurrency errors by reloading the schedule list if the backend returns 409.

### 6.3 Send custom notifications from the UI
1. Add a button in the Notifications tab.  
2. Call a new backend endpoint (`POST /api/scheduling/notifications/custom`).  
3. Use `setNotificationLogs` to append the result so the log reflects the manual send.

---

## 8. Quick Reference

| Function / Component | Purpose | Notes |
|----------------------|---------|-------|
| `useScheduling()` | Returns `{ state, actions }` | Centralised data + mutations. Do not replicate this logic elsewhere. |
| `actions.loadSchedules(activeOnly, focusId)` | Refresh schedules | Pass `focusId` to keep selection highlighted. |
| `actions.createSchedule(formData)` | Create new schedule | Handles errors, reloads list, focuses new entry. |
| `actions.updateSchedule(id, payload)` | Update schedule | Adds `expected_updated_at`. Automatically reloads list. |
| `actions.toggleScheduleActive(id, bool)` | Activate/deactivate | Use when wiring toggle buttons. |
| `ScheduleList` | Renders schedule cards | Takes selection/refresh callbacks plus optional `onDeleteSchedule` for the archived tab delete buttons. |
| `ImprovedScheduleForm` | Schedule editor dialog | Controlled via props from the page (`open`, `mode`, `initialValues`). |

---

## 9. When Something Goes Wrong

1. **Schedules never load (spinner forever)**  
   - Check browser network tab for `/api/scheduling/schedules`. If it fails, the hook sets `state.error`; ensure you display it.  
   - Confirm the component is inside `<AuthProvider>` so the token exists.

2. **Form keeps submitting old values**  
   - Ensure you pass the latest `scheduleFormInitialData` when opening the dialog. After closing, reset the form state to avoid stale data.

3. **409 conflicts when editing schedules**  
   - Means optimistic locking detected stale `updated_at`. The hook already re-fetches; show an `Alert` prompting the user to reopen the form.

4. **Notification settings never save**  
   - `NotificationEmailSettingsPanel` uses `actions.updateNotificationSettings`. Double-check the payload matches backend expectations (e.g., encryption flags).

5. **Archived schedules do not display**  
   - Call `actions.loadArchivedSchedules()` when the archived tab first opens. The hook sets `archivedInitialized`; use it to avoid duplicate loads.

Stick to this blueprint and the scheduling UI will stay maintainable even for new contributors.


## Run log monitoring controls (September 2026)

- The create/edit schedule form includes **Log inactivity threshold (minutes)**, default 3. Enter a positive whole number. It is separate from estimated duration and the optional late-start cleanup timeout. Changes affect the next launch.
- `ScheduledExperiment`, create/update request types, request normalization and form payloads carry `log_inactivity_threshold_minutes`. Omitted update values preserve the saved setting; older server payloads normalize to 3. Copying schedule data must preserve this field. The older forms in `ScheduleActions` expose it too.
- Notification Contacts help text explains that an active contact is needed for email. A continuing pause sends one email; new trace activity rearms the monitor for a later pause. A missing SQL connection or trace produces an unavailable-monitoring warning instead of claiming the method stalled.
- Running jobs display **Waiting for run/log**, **Monitoring**, **Log inactive**, **Monitoring unavailable**, or **Run ended; finalizing**, plus the threshold, trace filename, last observed activity and available diagnostic reason. The queue API's optional `monitoring` object supplies these values. Old payloads without this object still render.
- Notification history retains historical `long_running` entries and shows new `log_inactive` / `monitoring_unavailable` events. `cancelled` means the condition resolved before an email could be sent. Errors can retry; a sent pause is not repeated after restart.
- To test, save a non-default threshold, reopen the edit form, and verify it round-trips. Use the backend's controlled trace tests for state transitions; the operator should perform the simulator/email acceptance sequence described in the backend scheduling guide.
