# Labware frontend maintenance

Labware uses the shared spatial page layout and sidebar sections. It has two independent workspaces: Tip tracking and Cytomat. Browsing a position does not write anything. Changes are sent only with Save changes, or the existing confirmed Reset family action.

## Files

- `pages/LabwarePage.tsx`: authorized route and retained section panels.
- `components/labware/TipTrackingPanel.tsx`: family/rack summaries, selected rack, tip editor, drafts and writes.
- `components/labware/CytomatPanel.tsx`: position list and selected-position editor.
- `components/labware/useLabwareSnapshot.ts`: snapshot reading and draft protection using the existing serial polling hook.
- `services/labwareApi.ts`: unchanged request/response types and endpoints.
- `components/InspectionWorkspace.tsx`: responsive list/detail layout. See the shared workspace guide before changing widths or scrolling.

## Tip tracking

Choose a family, then a rack. The rack list retains Col A/Col B placement and status counts. Only the selected rack renders individual tips; this avoids hundreds of tiny controls across every rack.

Map preserves the server's column-major position order: position 1 is at the first row/column, position 8 is the bottom of that column for an eight-row rack. Each tip is a labelled button at least 44 pixels square. Arrow keys move spatially and stop at column edges; Home/End reach the first/last tip. Map scrolling stays inside its pane. List is the phone default and provides readable statuses; Tip position also selects a coordinate directly. Color swatches retain server colors, while labels, selected state and unsaved asterisks provide non-color information.

The contextual editor chooses a new status and a scope: this tip, its column, or its rack. Apply status creates drafts; it does not call the backend. `pending` is keyed by family and a JSON `[rack, position]` key. Returning to the saved status removes that draft. Family changes retain other families' drafts and show their pending count. Save changes saves the selected family's drafts.

Save captures the family and submitted edits before awaiting the PUT. A synchronous busy guard prevents duplicate submissions; mutation controls and family changes are disabled. Success patches the displayed snapshot, removes only submitted entries that still match, and resumes reading when no drafts remain. Failure retains drafts with an error. Discard affects the current family only. Reset family lives in More, requires the original confirmation, and is disabled while any drafts or writes are pending.

## Cytomat

Search positions or plate IDs, then choose a position. The detail shows its saved plate and, for an editable session, one labelled plate selector. Empty is a valid pending value; use property presence or nullish fallback, never a truthiness check. The selector uses `displayEmpty` and a render label so an empty string visibly reads Empty. Save submits all pending positions. A failed save retains them. The selector and Discard are disabled during Save.

## Permissions, reading and errors

`permissions.can_update` is authoritative for displaying editors. Read-only sessions keep lists, maps and selection but do not show mutation controls. Backend permissions still enforce each write.

Serial polling performs one read at a time. Inactive sections, pending edits in **any** family, and writes pause polling and invalidate late results. Existing browser-tab visibility behavior is preserved. A successful response replaces the snapshot only while reading is enabled. Each panel validates the collections and permissions it renders; malformed payloads show an unavailable error instead of crashing or claiming the inventory is empty. The last good data remains after read failures and is explicitly labelled. Initial failures show Error + Retry before any empty state; empty means a successful response actually had no entries.

SectionPanel retains drafts and selection when switching Labware sections. Back, resizing and appearance changes do not recreate the workspace. Reload/close warns while drafts or writes exist. Drafts are not stored in browser storage and are not shared across logins. Leaving the Labware route unmounts its local state; this is not cross-route draft persistence.

## Repeatable browser checks

Failure cases were recorded in `frontend/e2e/inspection-labware-failure-scenarios.md` before implementation. Run `npm run test:e2e -- labware.spec.ts` from `frontend` after a build. The tests intercept Labware GET/PUT endpoints with synthetic snapshots, so no robot data changes. They cover keyboard map edges, 320px list editing, delayed/failed saves, polling pause, subsection retention, reload warnings, read failure recovery, malformed responses and read-only permissions. Screenshots and traces are retained in `recovery/viewer-verification`.
