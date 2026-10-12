# Inspection workspace

The Database, Logs, Scheduling and video archive screens use the same small layout component. Camera keeps a specialized image viewport. All use the existing MUI theme, readable labels, and controls at least 44 pixels high.

## Layout component

Import the default `InspectionWorkspace` from `frontend/src/components/InspectionWorkspace.tsx`.

Pass these props:

- `label`: accessible name describing the workspace.
- `selector`: optional catalogue UI. Its root should use `display: flex`, `flexDirection: column`, `flex: 1` and `minHeight: 0`; its list should scroll independently.
- `selectorLabel`: the catalogue name, such as `Tables` or `Files`.
- `detailOpen` and `onBack`: the owning page controls whether the operator has opened an item on a narrow screen.
- `onDetailVisibilityChange`: optional notification of actual detail visibility. Use this for reader polling/leases; `detailOpen` alone is insufficient because resizing wide also reveals the detail.
- `boundedDetail`: the detail is a text reader with its own scrolling pane (the SQL and log readers). Follow, Top/Bottom and scroll restore need that pane, so on phones it keeps the measured height.
- `children`: the detail viewer, with its own toolbar and footer.

The component measures the actual space below the page heading and above the bottom padding of `main`, the app's one scroll area (`heightBelow`, see the main application guide). A ResizeObserver updates it when the available width or header changes. Do not add another `65vh` height or subtract a guessed header height inside a viewer. A 320-pixel minimum lets controls remain usable in very short windows; the page can scroll in that case.

Below 900 pixels of **workspace width**, the catalogue and detail alternate. This is different from the browser width because the app sidebar takes some space. At wider widths the catalogue starts at 300 pixels and can be resized from 240–480 pixels using the divider (drag or Left/Right keys). Hide/Show is on the divider, so it consumes no content toolbar row. Both catalogue and detail remain mounted, so Back and resizing retain state. Selecting another table intentionally resets that table's query through its React key.

## Phones (under 600 pixels)

Below 600 pixels of **browser** width (`usePhoneWorkspace()`, MUI's xs) the workspace has no height of its own: lists and tables scroll with the page (`main`), so there is one scroll and nothing inside the workspace scrolls vertically. The exception is a `boundedDetail` reader while it is shown. Back and the list/detail alternation are unchanged.

- Anything pinned inside the flowing workspace uses `position: sticky`. Every ancestor below `main` must be `overflow: visible` or `clip`, never `hidden` or `auto`: those make a scroll container and the element sticks to it instead of `main`. `Panel` uses `clip` for this reason. The app header is outside `main`, so `top: 0` is already below it.
- `pinnedBarSx` pins a bar to the bottom of `main`, which ends at the phone page bar. Sticky stops at `main`'s padding edge, so its `bottom` is minus that padding, or rows show through a 16px gap; the page bar owns the iOS home-indicator inset.
- `LoadMoreBar` ("50 of 2,000 files", Load more) replaces paging in phone lists. Logs appends the next API page (same `page`/`limit` requests; files that shifted between pages are listed once, and Refresh or a folder change starts from page 1). The archive shows one more client page. Scheduling's list needs neither: it flows.
- `InspectionName`: the open table's or definition's name on one line with an ellipsis; tapping shows it whole, and screen readers always get the full name.

`DatabaseTable` on phones: the header is the name, More and one search field (the search button and Enter apply). Filters, Sort by, Refresh (with the update time), Expand table and Page and rows (page jump and rows per page) are in More. Each row is a card (`role="list"` of `listitem`s) showing its row number and the first four visible columns as label and value side by side, with the grid's value formatting (NULL, empty string, long text); the whole card opens the row inspector (its button keeps the grid's name, "Inspect row N"). Sort by writes the same query state the desktop headings write. The paging bar (First/Previous/Next/Last and "1–25 of 32") is pinned and rests on the page bar; paging scrolls the new page's first card into view. The expanded (full-screen) table keeps the desktop grid.

## SQL text reader

`InspectionTextViewer` accepts `text`, `label`, optional `kind` (default `SQL`) and optional `preferenceKey` (default `sql`). Its compact toolbar keeps Find, Copy, Expand and More visible. Find reveals its field and match controls; More contains Wrap and Go to line. Top and Bottom stay at the footer. Code surfaces and highlights use semantic palette colors for both appearances.

Find searches the supplied definition only, highlighting up to 1,000 matches. Enter moves forward; Shift+Enter moves backward. Ctrl/Cmd+F while the reader has focus opens its Find field. Copy preserves the original text. If browser clipboard permission is unavailable, the reader tells the operator to select and copy the text.

Wrap preference is stored under `inspection.wrap.<preferenceKey>`. Do not reuse the SQL preference key for logs. Expanded rendering uses MUI's full-screen Dialog; state lives above the Dialog and scroll is restored when moving between surfaces. Escape closes it and returns focus to Expand after the transition. A short screen can scroll the control area instead of hiding the text or close action.

## Verification

Select affected consumer checks using `frontend/e2e/README.md`: database checks for SQL/table readers and log checks for log readers. Phone layout cases (cards on screen, Sort by, card opens its row, no nested vertical scroll, Load more) are in `database.spec.ts`, `inspection-pagination.spec.ts` and `logs.spec.ts`. The screenshot review (`playwright.visual.config.ts`) saves opened tables, log folders and archive folders at 390 and 375 pixels; set `VISUAL_SESSION=remote` to see a tunnel user's view. Shared sizing changes warrant representative narrow/desktop screenshots and checks for Back, Expand/Escape, long names, horizontal overflow and keyboard operation. A local text change does not require the entire matrix. Failure cases are listed at the top of each spec file.
