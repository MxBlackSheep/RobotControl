# Spatial tip editing failure scenarios

Recorded before production edits. Use synthetic snapshots and intercept writes.

- A full five-rack Col A and five-rack Col B deck must retain backend order on desktop and 320px phone; Col B never stacks below Col A. Missing tip data is unknown, not empty.
- Opening a rack retains the deck on desktop. Phone Back restores the same selected rack and pending edits without losing orientation.
- Choosing a paint status must survive rack/family selection and arrow-key navigation. Focusing or navigating tips never paints; Enter/Space and a deliberate click/tap do.
- A rectangle follows column-major coordinates, includes both corners and works in either direction. A drag previews only; release commits one undoable draft operation, never a backend write.
- Escape, pointer cancellation, release outside the rack, and rack/family changes cancel the preview. A synthetic click after a drag must not create another paint operation.
- Phone rectangle editing supports two corner taps and a visible Cancel action; normal touch scrolling must not paint. Coordinate controls and row/column/rack actions work without dragging.
- Undo restores the exact prior draft state, including removal of newly added drafts, and does not alter another family. Save/discard/reset clear obsolete undo history.
- Delayed Save freezes paint, bulk, Undo, Discard, family and reset controls. Failed Save preserves drafts; successful Save clears only submitted matching edits.
- Read-only sessions can inspect the complete deck and focused map but cannot paint. Existing error/retry/malformed-response handling remains intact.

Repeat with `npx playwright test labware.spec.ts`. Save full-deck desktop/phone screenshots and input traces in the existing viewer verification report.
