# Cytomat shelf failures (before implementation)

- Database order must not change the physical shelf order: position 1 stays at the top, position 7 at the bottom on 4K, medium, low-resolution desktop and phones.
- Positions 8/9 remain visible as Unused and never offer editing, even when the database reports a saved plate there.
- Missing active positions read Unavailable, not Empty, and never produce fabricated update targets.
- Unexpected IDs (including 01) remain visible separately with their original IDs; they are not dropped or aliased to a physical shelf.
- Duplicate raw IDs make that position unavailable/ambiguous without hiding unaffected shelves or silently choosing one assignment; duplicate unexpected IDs render once without an editor.
- Empty is a valid plate assignment; delayed/failed batch saves must retain drafts, freeze all editors and never clear later unrelated work.
- Read-only sessions keep complete shelf state without mutation controls. Drafts survive section changes; inactive sections and unsaved data preserve the existing polling policy.
- Long plate identifiers must wrap without widening the page; shelf shapes and labels remain useful at 320px and 3840px.

Run `npx playwright test cytomat-spatial.spec.ts` against the built frontend. Browser routes provide disposable snapshots and capture writes. Screenshots and traces are retained in the viewer-verification report.
