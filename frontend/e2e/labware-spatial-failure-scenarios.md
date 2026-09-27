# Spatial tip editing failure scenarios

Recorded before production edits. Use synthetic snapshots and intercept writes.

## Earlier responsive bulk-selection revision

The sizing rules in this section are historical. The full-page 40/60 layout, independent horizontal/vertical pitches and shared diagram bounds in `labware-layout-stability-scenarios.md` supersede fitted-card, square-cell and maximum-size assumptions below. Selection, permission, draft and cancellation cases remain current.

Recorded before this revision's production changes:

- A 4K canvas must grow the rack, status dots and labels together; the rack card must end near the actual grid rather than stretching around a small fixed grid.
- Fit square cells to BOTH available width and available viewport height. At 1280×720 and 1366×768, a wider rack must not push its last row off screen if 44px cells can fit. At short windows, preserve 44px targets and ordinary scrolling.
- Retain the two-carrier overview at desktop widths, and show both carrier columns on narrow screens. Test 3840×2160, 1920×1080, 1366×768, 1280×720, 1024×768, 1024×600, 390×844, 320×720 and 1920 CSS pixels at deviceScaleFactor2.
- Provide one Set tips to selector and Set entire rack. Remove separate Inspect/Paint/Rectangle modes and row/column/range commands.
- A first click/tap/Enter only anchors a selection; the second chooses the opposite corner. Choosing the same tip twice changes one tip. Mouse/pen drag previews then commits at release. All paths use the same chosen state and one Undo operation.
- A selected state survives rack changes. Keyboard navigation, touch scrolling and canceled selections never edit. Keep the selection strip's height stable and freeze geometry during drag; resizing or changing rack cancels the selection.
- Screenshot realistic long IDs and all seven states in light and dark appearance, including the actual focused rack at each viewport, not only its overview.

- A full five-rack Col A and five-rack Col B deck must retain backend order on desktop and 320px phone; Col B never stacks below Col A. Missing tip data is unknown, not empty.
- Opening a rack retains the deck on desktop. Phone Back restores the same selected rack and pending edits without losing orientation.
- Choosing a target status must survive rack/family selection and arrow-key navigation. Focusing or navigating never edits; two deliberate Enter/Space/click/tap activations choose the block's corners.
- A rectangle follows column-major coordinates, includes both corners and works in either direction. A drag previews only; release commits one undoable draft operation, never a backend write.
- Escape, pointer cancellation, release outside the rack, and rack/family changes cancel the preview. A synthetic click after a drag must not create another paint operation.
- Phone bulk editing supports two corner taps and a visible Cancel action. Normal touch scrolling never edits and must preserve an already chosen first corner, so a block can span columns beyond the visible viewport. Set entire rack is the only separate bulk action; row/column/range controls were removed.
- Undo restores the exact prior draft state, including removal of newly added drafts, and does not alter another family. Save/discard/reset clear obsolete undo history.
- Delayed Save freezes paint, bulk, Undo, Discard, family and reset controls. Failed Save preserves drafts; successful Save clears only submitted matching edits.
- Read-only sessions can inspect the complete deck and focused map but cannot paint. Existing error/retry/malformed-response handling remains intact.

Repeat with `npx playwright test labware.spec.ts`. Save full-deck desktop/phone screenshots and input traces in the existing viewer verification report.
