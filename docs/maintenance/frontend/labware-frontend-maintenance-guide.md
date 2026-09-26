# Labware frontend maintenance

Labware uses the shared spatial page layout and sidebar sections. It has two independent workspaces: Tip tracking and Cytomat. Browsing a position does not write anything. Changes are sent only with Save changes, or the existing confirmed Reset family action.

## Files

- `pages/LabwarePage.tsx`: authorized route and retained section panels.
- `components/labware/TipTrackingPanel.tsx`: family/rack selection, drafts, per-family Undo history and writes.
- `components/labware/TipDeckOverview.tsx`: fixed Col A/Col B rack overview, in backend order.
- `components/labware/TipRackEditor.tsx`: enlarged rack, status palette, pointer/keyboard painting and rectangle preview.
- `components/labware/CytomatPanel.tsx`: position list and selected-position editor.
- `components/labware/useLabwareSnapshot.ts`: snapshot reading and draft protection using the existing serial polling hook.
- `services/labwareApi.ts`: unchanged request/response types and endpoints.
- `components/InspectionWorkspace.tsx`: Cytomat's responsive list/detail layout. Tip tracking has its own spatial layout.

## Tip tracking

Choose a family, then a rack on the deck. Col A and Col B stay side by side, including on a 320px phone. Render `left_racks` and `right_racks` exactly in backend order: those arrays encode placement, and some IDs are deliberately not sorted numerically. Every rack shows a compact 8×12 status pattern. Its whole card is a labelled button; miniature dots are not tiny interactive targets.

At 1000px available content width the deck remains beside the enlarged rack. Below that width, tapping a rack opens a full-screen dialog. Back restores focus to the selected rack. The dialog keeps Back and Save in its fixed header; family/Refresh/Reset stay on the deck. Rack/tip selections, paint status and drafts live in the parent, so resizing or switching families does not lose them.

Both maps preserve column-major numbering: tip 1 is at the first row/column; tip 8 is the bottom of that column for an eight-row rack. The enlarged map uses labelled 44px buttons and local horizontal scrolling. Arrow keys navigate without editing, including at column edges; Enter/Space activates. Inspect is the initial state. Choosing a status enables painting; clicking a tip then creates a draft. Navigation never changes the selected paint status. Status dots retain their color when selected; borders, text and unsaved asterisks provide other cues.

Rectangle accepts mouse/pen drag or two corner taps/keyboard activations. Dragging previews the inclusive row/column range; pointer-up commits one draft operation. Touch scrolling uses the browser's normal behavior and never draws a rectangle. Escape, Cancel, pointer cancellation, off-rack release, and context changes cancel the preview. Pointer capture uses actual hit-testing for the endpoint; the compatibility click after a drag is suppressed once. A fresh pointer press or keyboard activation must not be swallowed. Paint row/column/rack and the two numeric corner fields provide alternatives to dragging.

`pending` is keyed by family and a JSON `[rack, position]` key. Returning to the saved status removes that draft. Each Undo entry stores affected keys' previous draft values, including absence; this restores earlier unsaved work exactly. Undo affects the selected family. Save, Discard and Reset clear obsolete history. Save changes submits the selected family's drafts; other families retain their drafts and show a pending count.

Save captures the family and submitted edits before awaiting the PUT. A synchronous busy guard prevents duplicate submissions; mutation controls and family changes are disabled. Success patches the displayed snapshot, removes only submitted entries that still match, and resumes reading when no drafts remain. Failure retains drafts with an error. Discard affects the current family only. Reset family lives in More, requires the original confirmation, and is disabled while any drafts or writes are pending.

## Cytomat

Search positions or plate IDs, then choose a position. The detail shows its saved plate and, for an editable session, one labelled plate selector. Empty is a valid pending value; use property presence or nullish fallback, never a truthiness check. The selector uses `displayEmpty` and a render label so an empty string visibly reads Empty. Save submits all pending positions. A failed save retains them. The selector and Discard are disabled during Save.

## Permissions, reading and errors

`permissions.can_update` is authoritative for displaying editors. Read-only sessions keep lists, maps and selection but do not show mutation controls. Backend permissions still enforce each write.

Serial polling performs one read at a time. Inactive sections, pending edits in **any** family, writes, and unfinished rectangle gestures pause polling and invalidate late results. Save/Reset stay disabled while a rectangle is unfinished. Existing browser-tab visibility behavior is preserved. A successful response replaces the snapshot only while reading is enabled. Each panel validates the collections and permissions it renders; malformed payloads show an unavailable error instead of crashing or claiming the inventory is empty. The last good data remains after read failures and is explicitly labelled. Initial failures show Error + Retry before any empty state; empty means a successful response actually had no entries.

SectionPanel retains drafts and selection when switching Labware sections. Back, resizing and appearance changes do not recreate the workspace. Reload/close warns while drafts or writes exist. Drafts are not stored in browser storage and are not shared across logins. Leaving the Labware route unmounts its local state; this is not cross-route draft persistence.

## Repeatable browser checks

Failure cases were recorded in `frontend/e2e/inspection-labware-failure-scenarios.md` and `frontend/e2e/labware-spatial-failure-scenarios.md` before implementation. Run `npx playwright test labware.spec.ts` from `frontend` after a build. Tests intercept Labware GET/PUT endpoints with synthetic snapshots, so no robot data changes. Full 5+5 deck screenshots use long real rack IDs and all seven backend states at 1280×720 and 320×720. Checks cover keyboard geometry, rectangle commit/cancel/Undo, real touch scrolling/two-corner input, delayed/failed saves, polling pause, subsection retention, reload warnings, error recovery, malformed responses and read-only permissions. Screenshots and traces are retained in `recovery/viewer-verification`.

The deck plus focused-rack design follows the same spatial-context principle as [Opentrons deck visualization and slot spotlights](https://docs.opentrons.com/flex/opentrons-app/protocol-viz/). Touch and numeric alternatives to dragging follow [W3C dragging-movement guidance](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements).
