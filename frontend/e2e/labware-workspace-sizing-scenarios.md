# Adaptive Labware sizing failures

Recorded before changing the shared measurement or page limits. Verify using disposable browser fixtures; no unit tests.

- Full-width modules must use the available main content width at 1280, 1920 and 3840 CSS pixels, including after the sidebar changes width. Page headings and actions must share their leading edge.
- Toolbar wrapping and viewport/browser zoom changes must recalculate remaining space. Scrolling must not grow or shrink the workspace. Hidden retained sections must not publish zero sizes.
- Child layout output must not become its own size input: no ResizeObserver loop, oscillation, repeating animation or background-refresh geometry movement.
- Near the desktop minimum, an internal scrollbar must not reduce the measured breakpoint width and repeatedly toggle desktop/compact mode. Measure the outer content box independently of scrollbar presence.
- Tips use 40/60 when both panels fit. Intermediate widths reserve the editor minimum before switching to the focused-rack view. Circular dots and 44px editor targets must survive non-square cell spacing.
- Five overview rows and eight editor rows share the same diagram bounds. Unsaved labels and refresh text must not shift those bounds; actual resizing cancels unfinished selection but preserves drafts.
- Cytomat fills the available register height, with equal base rows and minimum 48px rows/44px actions. Long values, the inline editor and unexpected positions remain reachable without overlapping or clipping.
- Packaged output must include the new full-width sizing, not the previous capped assets. Repeat desktop/phone screenshots and geometry assertions in the relocated executable smoke check.
