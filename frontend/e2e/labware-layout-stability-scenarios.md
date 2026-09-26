# Quiet workbench failure scenarios

Recorded before the production refinement. This changes presentation and background-read handling, not the tip geometry or write API.

- The deck and enlarged rack must share one bounded surface. Their edges meet on desktop; the editor must not remain a detached, centered card inside an empty column.
- At 1280px and 3840px, the joined surface starts at the same horizontal position as the page heading and action toolbar. On a 720px-high laptop, its bottom border remains visible when 44px wells fit; trim surrounding vertical padding before reducing usable targets.
- Available width is measured independently from the resulting fitted workspace. No ResizeObserver loop, repeated resizing, or cell-size change while scrolling/dragging. Sidebar/window changes retain selection and drafts.
- Preserve all five racks in each carrier, backend order, and column-major 8×12 coordinates. At 3840×2160 the map grows; at 1280×720 and 1366×768 its last row fits when 44px cells fit. At 1024×600 and on phones, normal/local scrolling preserves 44px targets.
- Quiet wells retain status fill, tip numbers, an unsaved marker, selected-block feedback, and a static visible keyboard-focus outline. Keyboard focus must not start an infinite ripple, including with reduced motion.
- A background GET must not insert a progress bar, move the deck/grid, replace their DOM nodes, disable/dim editing controls, or remove focus from Refresh. Reading status occupies a reserved caption.
- Starting a valid selection or edit synchronously invalidates an already-running GET before it resolves. A late response must not replace the frozen snapshot, chosen corners, or drafts. Save/Undo/cancel continue to work and no write occurs before Save.
- Save still freezes mutations, read-only remains read-only, and initial/error/retry states remain explicit. Reset keeps its confirmation; no-op or canceled actions must not stop polling indefinitely.

Repeat from frontend with `npx playwright test labware-layout-stability.spec.ts labware.spec.ts`. The synthetic API never writes to hardware. Each new browser check retains a full viewport screenshot; delayed-read checks also attach sampled geometry, focus, DOM identity and animation evidence. Existing Playwright traces record the full interaction.
