# Admin & Monitoring Overview

## Frontend Layout
- `frontend/src/pages/AdminPage.tsx`: Admin-only dashboard with three tabs (System Status -> `MonitoringDashboard`, Database operations, User Management). Fetches `/api/admin/*` endpoints for database + user flows; note that the `systemStatus` state is currently unused.
- `frontend/src/pages/MonitoringPage.tsx`: Role-agnostic full-screen monitoring view combining `MonitoringDashboard` with the more detailed `SystemStatus` widget for read-only insight.
- Shared navigation surfaces (tabs, mobile drawer, breadcrumbs, keyboard shortcuts) all register `/admin` as the canonical admin entry point.

## Backend Surfaces
- `backend/api/admin.py`: Auth-protected admin namespace offering system status summary, user listing/toggling, and database cache/health tools.
- `backend/api/system_config.py`: Separate router but still mounted under `/api/admin/system/*`; powers the System Configuration page.
- `backend/api/backup.py`: Lives under `/api/admin/backup`; UI entry is the Backup page but routing/breadcrumbs tie back to `/admin`.
- `backend/api/monitoring.py`: Read-only metrics plus websocket orchestration consumed by both `MonitoringDashboard` and `SystemStatus`.

## Shared Components & Hooks
- `frontend/src/components/MonitoringDashboard.tsx`: Core metrics grid used in BOTH Admin tab 0 and Monitoring page.
- `frontend/src/components/SystemStatus.tsx`: Detailed experiment/database status readout; used on Monitoring page and available for reuse elsewhere.
- `frontend/src/hooks/useMonitoring.ts`: Central polling hook hitting `/api/monitoring` REST endpoints; drives both components above.

## Relationship & Overlap Observations
- Admin tab "System Status" is the same monitoring view rendered on `/monitoring`; no additional admin-only data is shown there.
- Admin-exclusive functionality lives in the other tabs (database cache/health controls, user activation toggles) and the separate routes `/admin/backup` and `/admin/system-config`.
- Several UI affordances (keyboard shortcut Alt+6, breadcrumbs, return buttons) expect `/admin` to exist even if the first tab duplicates Monitoring.

## Removal Considerations
1. Re-home admin-only tooling:
   - Database cache plus health controls would need a new location (for example, fold into Monitoring or Database tabs) and updated copy.
   - User toggle actions currently have no other UI surface; removal strands `/api/admin/users/*` endpoints.
2. Update navigation and shortcuts: tabs, drawer, breadcrumbs, and `useKeyboardNavigation` all assume an Admin hub.
3. Revisit dependent pages: Backup and System Config breadcrumbs/buttons navigate back to `/admin`; they would require new parent destinations.
4. Authorization cues: Admin page is the only consolidated place showing admin-only context and messaging; alternative UX would be needed if removed.

## Quick Checklist Before Dropping Admin Page
- [ ] Decide where user management and database maintenance lives.
- [ ] Refactor `/admin` references across navigation, breadcrumbs, shortcuts, and error fallbacks.
- [ ] Ensure backup plus system-config pages have a new parent path or standalone nav entry.
- [ ] Update backend routing (optionally) if the admin namespace should be renamed or collapsed.
- [ ] Provide alternative success/error messaging previously surfaced via Admin dashboard alerts.

## Recommendation Snapshot
Keep Monitoring page as the primary read-only dashboard, but the Admin page still aggregates critical write operations and navigation anchors. Removing it outright currently breaks those flows; consider refactoring or merging rather than deleting.
