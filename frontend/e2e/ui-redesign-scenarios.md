# Whole-application redesign failures (before implementation)

1. System/Light/Dark leaves light panels, unreadable selection or a white flash; changing theme resets a reader, draft, stream or selected record.
2. A small desktop pane uses a wide toolbar because only window width is checked; phone/keyboard/zoom hides Back or Save.
3. Logs give less than 60% of app height to text at 1280×720 in default state; Find/sections/Follow lose state after collapse, expansion or resize.
4. Last/page-jump loses current filters, requests the wrong index, or labels retained rows with a failed requested page. Counts shrink while on the last page.
5. SQL Find is undiscoverable when collapsed; Go to line, Top/Bottom and copy lose focus or scroll.
6. Maintenance failed initial load looks like HxRun is allowed; stale state allows an unsafe-looking action; Refresh overwrites the operator's reason draft.
7. A labware tip cannot be selected by keyboard/touch; saving clears newer edits; switching rack/family loses pending changes; read errors look empty.
8. Scheduling actions/queue sit below the entire mobile list; selecting a record or resizing loses form drafts; recovery gating or local-only actions change.
9. Schedule form/date/history/contact controls overflow on a phone; closing an edited form loses unsaved input.
10. Camera expansion/theme/source changes create a stream or hardware operation; archive folder/back navigation loses position or clips variable filenames.
11. Monitoring issues duplicate dataset polls or shows CPU utilization as overall service health; errors do not preserve a truthful stale snapshot.
12. Account lists, repair tools, login, About, modal errors, notifications and help retain inconsistent surfaces or excessive explanatory text.

Use disposable real log HTTP fixtures and synthetic feature API routes. Retain
HTML results, traces, screenshots, viewport/content-height and color measurements.
Inspect at 1280×720, 1920×1080, 320/390px and landscape, plus real browser zoom.
Test one visible pane without discarding its state. Do not add unit tests.
