# Frontend Maintenance Page Guide

The Maintenance page controls the persistent HxRun launch block. It is separate
from the temporary API pause used while restoring a database.

## Files and navigation

- `pages/MaintenancePage.tsx`: status, reason, action and conflict dialog.
- `services/hxrunMaintenanceApi.ts`: GET/PUT `/api/maintenance/hxrun`.
- `components/navigation.tsx`: sidebar and breadcrumb metadata.
- `App.tsx`: `/maintenance` route.

## Operator flow

The current state is Allowed or Blocked for maintenance. The last change shows its
operator and time. A verified Allowed state offers Enter maintenance; a verified
blocked state offers Allow HxRun launches. The optional Reason accompanies a
change. Remote sessions can inspect; changes require backend local permission.

Initial failure or malformed state displays State unavailable. A failed refresh also marks the state
unavailable and disables changes, even if a previous reading remains. Loading and
saving disable the action. Never treat missing state as Allowed. Refresh preserves
an edited Reason; a successful save accepts the server's returned reason.

A 409 response when entering maintenance opens the HxRun-running dialog and keeps
the previous state. The backend remains the authority; changing UI permissions
does not grant permission to change the flag.

## Layout and checks

This is a task/form PageContent, limited to1120px, with one status/action card.
Do not stretch the small form to fill the height or add decorative summary cards.
Use the common theme and compact PageHeader. The page scrolls naturally on short
screens and with an onscreen keyboard.

Run `npm run build` and `npx playwright test` in `frontend`. The appearance E2E
spec checks initial error, disabled action, retry and retained Reason. The broader
appearance matrix covers desktop/phone dark rendering. Reports and browser traces
are saved under `recovery/viewer-verification`.
