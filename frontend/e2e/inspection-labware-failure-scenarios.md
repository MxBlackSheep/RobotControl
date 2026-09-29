# Inspection and Labware failure scenarios

Written before the implementation. Browser checks use the full application and intercept only these feature APIs; no robot writes occur.

- A table with many pages needs First, Last and a validated page jump. Empty tables and a shrinking result count must not produce an invalid page.
- A failed next/last/filter request must keep both the previous rows and their correct page/range labels. Retrying must use the requested query.
- SQL must reach its final line without repeated scrolling. Find, line jumps, wrapping and expanded view must preserve reader state; small windows must keep controls reachable.
- A tip overview must show rack summaries, not hundreds of tiny click targets. One selected rack has a keyboard-accessible map and a touch-friendly coordinate/list alternative at 320px.
- Pending tip edits survive family/section changes and failed saves. Every edit/reset/refresh control is protected while Save is running; success clears only submitted edits. Any family's pending changes pause refresh.
- Loading failures must show an error and Retry, never a false empty/healthy state. Retrying can recover.
- Remote Labware remains readable without mutation controls. Tip selection and Cytomat position selection are labelled and keyboard accessible.
- Cytomat edits apply to the selected position, preserve empty values, retain pending changes on failed saves, and block new edits while saving.
- Inactive module sections do not poll. Existing browser-tab refresh behavior is preserved. Theme changes and responsive reflow retain selection and drafts; reload/close warns while edits are pending.

Repeat with `npx playwright test inspection-pagination.spec.ts labware.spec.ts`. Playwright traces and screenshots are retained under `test-output/viewer-verification`. The later spatial Labware revision is covered by `labware-spatial-failure-scenarios.md`.
