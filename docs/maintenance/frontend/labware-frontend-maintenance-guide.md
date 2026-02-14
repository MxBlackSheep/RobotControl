# Labware Frontend Maintenance Guide

This guide explains the Labware UI module (`TipTracking` + `Cytomat`).

---

## 1. Where The Code Lives

- Page shell + sub-tabs: `frontend/src/pages/LabwarePage.tsx`
- TipTracking panel: `frontend/src/components/labware/TipTrackingPanel.tsx`
- Cytomat panel: `frontend/src/components/labware/CytomatPanel.tsx`
- API client: `frontend/src/services/labwareApi.ts`
- App navigation wiring:
  - Desktop tabs: `frontend/src/App.tsx`
  - Mobile drawer: `frontend/src/components/MobileDrawer.tsx`
  - Breadcrumbs: `frontend/src/components/NavigationBreadcrumbs.tsx`
  - Keyboard shortcuts/help: `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`

---

## 2. What The User Sees

1. Top-level `LABWARE` page.
2. Secondary tabs:
   - `TipTracking`
   - `Cytomat`
3. TipTracking supports family/rack/tip status operations.
4. Cytomat shows a row list of `CytomatPos` and editable `PlateID` dropdowns.

---

## 3. Read-Only vs Editable Rules

- Backend returns `permissions.can_update` for each labware snapshot.
- In both panels:
  - `can_update=false`: show info alert and disable write controls.
  - `can_update=true`: allow edit/save operations.
- Backend locality checks are authoritative. Frontend disabling is guidance only.

---

## 4. Cytomat Data Flow

1. `CytomatPanel` loads `labwareApi.getCytomatSnapshot()`.
2. Snapshot includes:
   - `rows` (`cytomat_pos`, `plate_id`)
   - `plate_options` (empty first, then descending IDs)
   - `permissions`
   - `auto_refresh_ms`
3. Edits are stored in `pendingByPos` and not sent immediately.
4. `Save` sends only changed rows via `labwareApi.updateCytomat(...)`.
5. Auto-refresh runs only when there are no pending edits.

---

## 5. Cytomat Internal State

- `snapshot`: latest backend Cytomat payload.
- `pendingByPos`: map of unsaved changes (`cytomat_pos -> plate_id`).
- `saving`: disables controls during PUT request.

If edits look missing, inspect `pendingByPos` first.

---

## 6. Extension Pattern

For any new labware sub-module:

1. Create a dedicated panel component under `frontend/src/components/labware/`.
2. Add a separate tab in `LabwarePage.tsx`.
3. Add explicit API types and functions in `labwareApi.ts`.
4. Keep state and interactions isolated per module.

Do not merge unrelated modules into `TipTrackingPanel.tsx` or `CytomatPanel.tsx`.

---

## 7. Troubleshooting

1. `LABWARE` tab missing:
   - Confirm route/tab guards for user role in `frontend/src/App.tsx`.

2. Cytomat dropdown cannot save:
   - Check `permissions.can_update`.
   - Confirm session is local.
   - Confirm selected `PlateID` still exists in backend `plate_options`.

3. Cytomat list does not refresh:
   - Verify `pendingByPos` is empty (auto-refresh pauses while pending edits exist).
