# Frontend Scheduling Maintenance Guide

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

## 2. Scheduling Workflow Overview

1. **Page mount** → `const { state, actions } = useScheduling();`.  
   - `useScheduling` immediately calls `loadSchedules()` and `loadQueueStatus()`.  
   - While loading, `SchedulingPage` shows skeletons or progress indicators.

2. **Viewing schedules**  
   - `ScheduleList` receives `state.schedules` and displays them with quick-action buttons (activate/deactivate, archive, delete).  
   - Selecting a schedule updates `state.selectedSchedule`, which drives detail panels and the edit form.

3. **Creating a schedule**  
   - Clicking “New Schedule” opens `ImprovedScheduleForm` (modal).  
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
- `state.queueStatus`, `state.hamiltonStatus` – metadata for the robot queue.  
- `state.manualRecovery` – indicates if manual recovery is required and who flagged it.  
- `state.contacts`, `state.notificationLogs`, `state.notificationSettings` – used on the Notifications tab.

Useful derived flags provided by the hook:

- `state.loading` / `state.archivedLoading` – drive `LoadingSpinner` placements.  
- `state.error` / `state.archivedError` – show `Alert` banners.  
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

3. **Handle errors gracefully.** `useScheduling` surfaces errors via `state.error`. Display them using `<Alert>` or `<ServerError>` so users understand what happened.

4. **Respect optimistic locking.** When updating a schedule, include `expected_updated_at`. The hook already injects it, but if you add new update flows, reuse the same pattern to prevent 409 conflicts.

5. **Keep forms and dialog state local to `SchedulingPage`.** The hook should not store modal flags—leave that to the page to avoid unwanted rerenders.

---

## 5. Common Maintenance Tasks

| Task | Where | Step-by-step |
|------|-------|--------------|
| Add a new schedule field (e.g., priority) | `ImprovedScheduleForm`, `useScheduling`, `ScheduleList` | Update form inputs, extend `CreateScheduleFormData`/`UpdateScheduleRequest`, pass through to `actions`, and display the field in lists and detail panels. |
| Show additional execution log columns | `ExecutionHistory.tsx` | Adjust the table header and row renderer. Ensure the backend includes the new field in the history API. |
| Reorder tabs or rename them | `SchedulingPage.tsx` | Update the `Tabs` component and the `TabPanel` labels. Ensure indexes still align with the correct content. |
| Add bulk schedule actions | `ScheduleList.tsx` + new action in `useScheduling` | Track selected rows, send a bulk request, then reload schedules. Show a toast to confirm completion. |
| Surface manual recovery banner globally | `SchedulingPage` | Read `state.manualRecovery` and display a `Warning` chip or banner at the top of the page. |

---

## 6. Extending or Modifying Behaviour

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

## 7. Quick Reference

| Function / Component | Purpose | Notes |
|----------------------|---------|-------|
| `useScheduling()` | Returns `{ state, actions }` | Centralised data + mutations. Do not replicate this logic elsewhere. |
| `actions.loadSchedules(activeOnly, focusId)` | Refresh schedules | Pass `focusId` to keep selection highlighted. |
| `actions.createSchedule(formData)` | Create new schedule | Handles errors, reloads list, focuses new entry. |
| `actions.updateSchedule(id, payload)` | Update schedule | Adds `expected_updated_at`. Automatically reloads list. |
| `actions.toggleScheduleActive(id, bool)` | Activate/deactivate | Use when wiring toggle buttons. |
| `ScheduleList` | Renders schedule cards | Accepts callbacks for edit/delete/archive. |
| `ImprovedScheduleForm` | Schedule editor dialog | Controlled via props from the page (`open`, `mode`, `initialValues`). |

---

## 8. When Something Goes Wrong

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

