# Quiet workbench failure scenarios

Recorded before the production refinement. This changes presentation and background-read handling, not the tip geometry or write API.

## Full-page adaptive sizing

Recorded before this revision's production changes. These requirements supersede the earlier fitted-card and square-cell assumptions:

- The outer Tip surface must fill the available PageContent width, with no 2200px maximum. When space permits, the overview/editor split is 40/60. When 60% cannot hold twelve 44px targets plus 4px gaps and 24px padding, keep that editor minimum and give the remainder to the overview down to its 320px minimum. Below that combined minimum, retain the overview and focused-rack dialog.
- The two panes share header, diagram and footer tracks. All five rack rows fill the same diagram top/bottom as the eight editor rows. Their body bounds must match; stretching only the outer border is insufficient.
- Horizontal and vertical pitches may differ. Both dimensions of each editor target stay at least 44px, and every status dot stays circular. Remove the 400px overview, 132px cell and 9px miniature-dot upper caps; real 4K screenshots must demonstrate growth.
- Each miniature retains 8 rows, 12 columns and at least 5px circular dots, plus a readable title. Allow the shared diagram to exceed the viewport when these minima require it. A single desktop stage scroll must reach the header, last tip row and footer; no nested vertical editor scroll.
- Phone layout retains two carrier columns, ordinary vertical flow, 44px focused targets and local horizontal scrolling. Touch scrolling still preserves a first corner, while resizing the available container cancels an incomplete selection.
- Toolbar wrapping, sidebar changes, polling, stage scrolling and status updates must not create resize oscillations or replace the selected rack/draft. Save/Undo/permissions and synchronous late-read protection remain unchanged.
- Very long rack IDs retain their full accessible name/title, while the visual name ellipsizes beside a reserved unsaved-count area. Adding or clearing 96 pending tips must not wrap the title or move either diagram. Overview labels may scale modestly from 12 to 18px on large screens.

- The deck and enlarged rack share one continuous surface. Their edges meet on desktop.
- At 1280px and 3840px, the joined surface starts at the same horizontal position as the page heading and action toolbar. On a 720px-high laptop, its bottom border remains visible when 44px wells fit; trim surrounding vertical padding before reducing usable targets.
- Available width is measured independently from the resulting fitted workspace. No ResizeObserver loop, repeated resizing, or cell-size change while scrolling/dragging. Sidebar/window changes retain selection and drafts.
- Preserve all five racks in each carrier, backend order, and column-major 8×12 coordinates. At 3840×2160 the map grows; at 1280×720 and 1366×768 its last row fits when 44px cells fit. At 1024×600 and on phones, normal/local scrolling preserves 44px targets.
- Quiet wells retain status fill, tip numbers, an unsaved marker, selected-block feedback, and a static visible keyboard-focus outline. Keyboard focus must not start an infinite ripple, including with reduced motion.
- A background GET must not insert a progress bar, move the deck/grid, replace their DOM nodes, disable/dim editing controls, or remove focus from Refresh. Reading status occupies a reserved caption.
- Starting a valid selection or edit synchronously invalidates an already-running GET before it resolves. A late response must not replace the frozen snapshot, chosen corners, or drafts. Save/Undo/cancel continue to work and no write occurs before Save.
- Save still freezes mutations, read-only remains read-only, and initial/error/retry states remain explicit. Reset keeps its confirmation; no-op or canceled actions must not stop polling indefinitely.

Repeat from frontend with `npx playwright test labware-layout-stability.spec.ts labware.spec.ts`. The synthetic API never writes to hardware. Each new browser check retains a full viewport screenshot; delayed-read checks also attach sampled geometry, focus, DOM identity and animation evidence. Existing Playwright traces record the full interaction.
