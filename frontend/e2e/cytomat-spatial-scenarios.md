# Cytomat shelf failures (before implementation)

## Full-workspace refinement (recorded before implementation)

- On desktop, the register must use the available page width and remaining height. Its nine normal summaries share that height equally, without an 800px cap or 60px row cap.
- Minimum rows stay 48px with 44px actions. Phones and very short windows use natural page flow; desktop has one internal register scroll area for expanded content.
- Opening one inline editor, adding unsaved text, or rendering a long identifier must not clip content or resize every other shelf. Extra IDs remain available below the nine shelves through an explicit Other positions shortcut.
- Sidebar/window changes and returning from a retained hidden section recalculate external space without remounting an open editor or losing drafts. Row sizing must not observe its own rendered output or respond to polling.
- A 1920 CSS-pixel screen at 2× device scale uses the same CSS layout as 1920 at 1×; no whole-page transform, zoom or font scaling simulates a larger workspace.
- Screenshots and geometry artifacts must cover 3840×2160, 1920×1080, 1280×720, 320px phones, a short desktop and an editor resized between desktop and phone.

## Continuous register refinement (recorded before implementation)

- The initial successful view shows a continuous shelf register, not seven open selectors; an explicit Edit position action opens exactly one inline selector without hiding other shelf assignments.
- Keyboard and phone users can open, change and close a shelf editor with at least 44px action targets. Closing an editor leaves its draft visible in the register; opening another row preserves that draft.
- Opening an editor during a slow GET synchronously invalidates that read. A late response must not replace the working snapshot, revoke the displayed editing controls, or clear a draft.
- Polling pauses while an editor is open, even before its value changes; closing the editor resumes polling only when no drafts or writes remain.
- Background polling must not move shelf rows, temporarily disable Edit controls, remove keyboard focus from Refresh, or replace the last good view with loading content. Initial loading remains explicitly visible.
- Save freezes the single open selector and row actions. A failed save preserves the current editor and all submitted drafts; success clears only matching drafts.
- Empty, missing, duplicate, unused and unexpected position semantics remain unchanged. No generic HTTP 503 behavior is changed by this layout refinement.
- At 1280×720, the normal nine-position register fits vertically without scrolling to see unused positions 8/9. Compact rows still provide 44px Edit targets; unexpected extra positions and an open editor may extend below the viewport.

- Database order must not change the physical shelf order: position 1 stays at the top, position 7 at the bottom on 4K, medium, low-resolution desktop and phones.
- Positions 8/9 remain visible as Unused and never offer editing, even when the database reports a saved plate there.
- Missing active positions read Unavailable, not Empty, and never produce fabricated update targets.
- Unexpected IDs (including 01) remain visible separately with their original IDs; they are not dropped or aliased to a physical shelf.
- Duplicate raw IDs make that position unavailable/ambiguous without hiding unaffected shelves or silently choosing one assignment; duplicate unexpected IDs render once without an editor.
- Empty is a valid plate assignment; delayed/failed batch saves must retain drafts, freeze all editors and never clear later unrelated work.
- Read-only sessions keep complete shelf state without mutation controls. Drafts survive section changes; inactive sections and unsaved data preserve the existing polling policy.
- Long plate identifiers must wrap without widening the page; shelf shapes and labels remain useful at 320px and 3840px.

Run `npx playwright test cytomat-spatial.spec.ts` against the built frontend. Browser routes provide disposable snapshots and capture writes. Screenshots and traces are retained in the viewer-verification report.
