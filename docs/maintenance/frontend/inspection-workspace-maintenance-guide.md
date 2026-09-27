# Inspection workspace

The Database and Logs viewers use the same small layout component. Camera keeps a specialized image viewport. All use the existing MUI theme, readable labels, and controls at least 44 pixels high.

## Layout component

Import the default `InspectionWorkspace` from `frontend/src/components/InspectionWorkspace.tsx`.

Pass these props:

- `label`: accessible name describing the workspace.
- `selector`: optional catalogue UI. Its root should use `display: flex`, `flexDirection: column`, `flex: 1` and `minHeight: 0`; its list should scroll independently.
- `selectorLabel`: the catalogue name, such as `Tables` or `Files`.
- `detailOpen` and `onBack`: the owning page controls whether the operator has opened an item on a narrow screen.
- `onDetailVisibilityChange`: optional notification of actual detail visibility. Use this for reader polling/leases; `detailOpen` alone is insufficient because resizing wide also reveals the detail.
- `children`: the detail viewer, with its own toolbar and footer.

The component measures the actual space below the page heading and above the application's bottom padding. A ResizeObserver updates it when the available width or header changes. Do not add another `65vh` height or subtract a guessed header height inside a viewer. A 320-pixel minimum lets controls remain usable in very short windows; the page can scroll in that case.

Below 900 pixels of **workspace width**, the catalogue and detail alternate. This is different from the browser width because the app sidebar takes some space. At wider widths the catalogue starts at 300 pixels and can be resized from 240–480 pixels using the divider (drag or Left/Right keys). Hide/Show is on the divider, so it consumes no content toolbar row. Both catalogue and detail remain mounted, so Back and resizing retain state. Selecting another table intentionally resets that table's query through its React key.

## SQL text reader

`InspectionTextViewer` accepts `text`, `label`, optional `kind` (default `SQL`) and optional `preferenceKey` (default `sql`). Its compact toolbar keeps Find, Copy, Expand and More visible. Find reveals its field and match controls; More contains Wrap and Go to line. Top and Bottom stay at the footer. Code surfaces and highlights use semantic palette colors for both appearances.

Find searches the supplied definition only, highlighting up to 1,000 matches. Enter moves forward; Shift+Enter moves backward. Ctrl/Cmd+F while the reader has focus opens its Find field. Copy preserves the original text. If browser clipboard permission is unavailable, the reader tells the operator to select and copy the text.

Wrap preference is stored under `inspection.wrap.<preferenceKey>`. Do not reuse the SQL preference key for logs. Expanded rendering uses MUI's full-screen Dialog; state lives above the Dialog and scroll is restored when moving between surfaces. Escape closes it and returns focus to Expand after the transition. A short screen can scroll the control area instead of hiding the text or close action.

## Verification

Select affected consumer checks using `frontend/e2e/README.md`: database checks for SQL/table readers and log checks for log readers. Shared sizing changes warrant representative narrow/desktop screenshots and checks for Back, Expand/Escape, long names, horizontal overflow and keyboard operation. A local text change does not require the entire matrix. Failure scenarios remain in `frontend/e2e/scenarios.md` and the module scenario files.
