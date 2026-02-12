# Labware Frontend Maintenance Guide

This guide explains the Labware UI module. Read this before changing the `LABWARE` tab or TipTracking behavior.

---

## 1. Where The Code Lives

- Page route shell: `frontend/src/pages/LabwarePage.tsx`
- TipTracking UI and interactions: `frontend/src/components/labware/TipTrackingPanel.tsx`
- API client for this module: `frontend/src/services/labwareApi.ts`
- App navigation wiring:
  - Desktop tabs: `frontend/src/App.tsx`
  - Mobile drawer: `frontend/src/components/MobileDrawer.tsx`
  - Breadcrumb labels: `frontend/src/components/NavigationBreadcrumbs.tsx`
  - Keyboard shortcut map/help: `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`

---

## 2. What The User Sees

1. A top-level `LABWARE` tab appears between `Camera` and `System Status`.
2. Inside the page, there is a secondary tab system (currently only `TipTracking`).
3. TipTracking shows two families:
   - `1000ul`
   - `300ul`
4. Each family renders two columns of racks (`ColA`, `ColB`) with 96 tip dots per rack.
5. Users can select one tip and inspect status.
6. Local sessions can edit status and reset.
7. Remote sessions are read-only (inspect only).

---

## 3. Read-Only vs Editable Rules

- The backend sends `permissions.can_update` with the tip snapshot.
- UI behavior in `TipTrackingPanel.tsx`:
  - If `can_update=false`: show info alert and disable update/reset controls.
  - If `can_update=true`: allow apply/save/discard/reset actions.
- Do not remove backend enforcement. UI disabling is only user guidance.

---

## 4. Data Flow

1. `TipTrackingPanel` calls `labwareApi.getTipTrackingSnapshot()` on load.
2. Response includes:
   - rack layout,
   - status order and colors,
   - tip status map,
   - permission flags,
   - auto-refresh interval.
3. User edits are stored in local `pendingByFamily` state (not sent immediately).
4. `Save` sends a batch payload via `labwareApi.updateTipTracking(...)`.
5. `Reset` calls `labwareApi.resetTipTracking(...)` and reloads state.
6. Auto-refresh runs only when there are no pending edits for the active family.

---

## 5. Important Internal State (TipTrackingPanel)

- `snapshot`: last backend snapshot.
- `selectedFamilyId`: active family tab (`1000ul` or `300ul`).
- `selectedTip`: currently selected tip (`labwareId + position`).
- `pendingByFamily`: queued edits keyed by `family -> "labware::position"`.
- `tipStatusChoice`, `rackStatusChoice`: selected status in controls.
- `rackChoice`: selected rack for “Apply to Whole Rack”.

If edits look lost, inspect `pendingByFamily` first.

---

## 6. How To Add Another Labware Sub-Module

If you want a second secondary UI tab (example: `PlateTracking`):

1. Create `frontend/src/components/labware/PlateTrackingPanel.tsx`.
2. Add a new `<Tab>` + `<TabPanel>` block in `LabwarePage.tsx`.
3. Add a dedicated API client file or extend `labwareApi.ts`.
4. Keep permission rules explicit for local-only writes if needed.

Do not merge unrelated sub-modules into `TipTrackingPanel.tsx`; keep each module separate.

---

## 7. Common Maintenance Tasks

- Change status colors/order:
  - Prefer backend source of truth; UI consumes what backend returns.
- Add a new tip family:
  - Backend first (family config + tables), then UI auto-renders if response shape is consistent.
- Adjust auto-refresh:
  - Backend `auto_refresh_ms` is the authoritative value.
- Improve dot rendering performance:
  - Keep dot nodes lightweight; avoid heavy per-dot components.

---

## 8. Troubleshooting

1. `LABWARE` tab is missing:
   - Check user role (`admin` or `user`) and `App.tsx` tab/route guards.

2. Save button disabled unexpectedly:
   - Check `permissions.can_update` in snapshot response.
   - Confirm request came from local session.

3. Colors look wrong:
   - Inspect `status_colors` from backend response in browser network tab.

4. Changes disappear after refresh:
   - Expected if user discarded or saved.
   - Pending edits are only local until Save is pressed.

5. Column apply targets wrong tips:
   - Verify the 8-row column math in `applyToColumn()` in `TipTrackingPanel.tsx`.

