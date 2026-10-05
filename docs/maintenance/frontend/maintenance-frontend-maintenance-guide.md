# Frontend Maintenance Page Guide

The Maintenance page controls the persistent HxRun launch block. It is separate
from the temporary API pause used while restoring a database.

## Files and navigation

- `pages/MaintenancePage.tsx`: status, reason, action and conflict dialog.
- `services/hxrunMaintenanceApi.ts`: GET/PUT `/api/maintenance/hxrun`.
- `components/navigation.tsx`: sidebar and section-tab metadata.
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

The page uses the 1120px task width for its heading, Refresh and content. The HxRun
launches card and Right now panel share a two-column grid from 900px of workspace
width; below that they stack. Both use normal panel padding and headings. Right now
reads the shell's robot status context
(HxRun, scheduler, current run, whether scheduled runs are held) and starts no request.
While HxRun runs, the card names the run and the time left by the user's estimate (or how
far past it); this is information only, and the backend still decides with its 409.
Do not stretch the small form to fill the height. On phones (under 600px) "Last change" sits under
the description in the card, since the header band has no room for it beside the label.
Use the common theme and compact PageHeader. The page scrolls naturally on short
screens and with an onscreen keyboard.

For changes to this page, build changed frontend inputs and run
`npx playwright test appearance.spec.ts --grep maintenance` in `frontend`.
These cases check initial error, disabled action, retry and retained Reason.
Use the broader appearance cases when theme or shared layout changes. See
`frontend/e2e/README.md` for reports and trace options; documentation edits need
neither a browser run nor a build.
