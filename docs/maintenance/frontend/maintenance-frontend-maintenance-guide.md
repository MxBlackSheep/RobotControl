# Frontend Maintenance Page Guide

This guide covers the new top-level **Maintenance** tab/page used to manage **HxRun Maintenance Mode**.

Important: this page is **not** the same as the existing database-restore maintenance dialog.

---

## 1. Files You Must Know

- `frontend/src/pages/MaintenancePage.tsx`  
  UI for viewing and toggling HxRun maintenance mode.

- `frontend/src/services/hxrunMaintenanceApi.ts`  
  API wrapper for `GET/PUT /api/maintenance/hxrun`.

- Navigation wiring:
  - `frontend/src/App.tsx`
  - `frontend/src/components/MobileDrawer.tsx`
  - `frontend/src/components/NavigationBreadcrumbs.tsx`
  - `frontend/src/hooks/useKeyboardNavigation.ts`
  - `frontend/src/components/KeyboardShortcutsHelp.tsx`

---

## 2. Permission Rules in UI

- Local sessions:
  - Can enable/disable the flag.
  - Can edit reason text.

- Remote sessions:
  - Can view state only.
  - See “Local Access Required” info message.

The backend is still the final authority (remote `PUT` returns 403 even if UI is bypassed).

---

## 3. Data Flow

1. Page load calls `hxrunMaintenanceApi.getState()`.
2. API response includes:
   - `enabled`
   - `reason`
   - `updated_by`
   - `updated_at`
   - `permissions.can_edit`
3. Button click calls `hxrunMaintenanceApi.updateState(enabled, reason)`.
4. UI refreshes from returned state.
5. If enable is rejected with `409` (HxRun already running), the page opens a blocking dialog with the backend message and keeps the flag unchanged.

---

## 4. Separation from Old Maintenance Dialog

Do not mix these two systems:

- Old system (`MaintenanceManager`, `MaintenanceDialog`)  
  Temporary frontend API pause for database restore windows.

- New system (this page)  
  Persistent HxRun execution block.

If you rename labels, keep this distinction obvious.

---

## 5. Common Tasks

| Task | Where | What to change |
|------|-------|----------------|
| Change tab order | `App.tsx` + `MobileDrawer.tsx` | Keep Maintenance between Labware and System Status. |
| Adjust shortcuts | `useKeyboardNavigation.ts` + `KeyboardShortcutsHelp.tsx` | Keep bindings/help text in sync. |
| Add extra state fields | `hxrunMaintenanceApi.ts` + `MaintenancePage.tsx` | Extend interface and render cards/rows. |
| Change read-only messaging | `MaintenancePage.tsx` | Edit the info `Alert` copy only. |
| Change "HxRun already running" dialog copy/behavior | `MaintenancePage.tsx` | Keep backend as source-of-truth; frontend should display server message for `409` conflicts. |

---

## 6. Debug Checklist

1. Page missing from top navigation:
   - Check `tabItems` in `App.tsx`.
   - Check route exists: `/maintenance`.

2. Page exists on desktop but not mobile:
   - Check `navigationItems` in `MobileDrawer.tsx`.

3. Breadcrumb label wrong:
   - Check `routeConfigs` in `NavigationBreadcrumbs.tsx`.

4. Shortcut goes to wrong route:
   - Check both `useKeyboardNavigation.ts` and `KeyboardShortcutsHelp.tsx`.

5. Remote session can click toggle:
   - Check `canEdit` logic in `MaintenancePage.tsx`.
   - Verify backend still returns `permissions.can_edit`.

6. Local enable button does nothing:
   - Check browser network response for `PUT /api/maintenance/hxrun`.
   - If status is `409`, HxRun is still running; close HxRun first.
