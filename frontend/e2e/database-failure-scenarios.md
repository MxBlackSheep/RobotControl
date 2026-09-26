# Database inspection failure scenarios

Written before production changes for the September 2026 viewer work.

- A narrow screen puts the complete catalogue above the selected table or SQL; Back loses the current selection, search draft or scroll position.
- The table, toolbar or pagination exceeds the visible workspace; wide data makes the whole page scroll horizontally.
- Expand closes/reopens data requests, clears filters, resets SQL Find, or traps keyboard focus after Escape.
- A row inspector omits hidden columns, NULL, empty strings or long values; copy succeeds silently or reports success when the clipboard failed.
- Search applies on every keystroke, filtering ignores applied values, descending sort is lost, or older responses overwrite the current selection.
- A refresh failure clears useful data or presents old rows as a successful fresh response.
- Procedure parameters/metadata consume the definition area; mobile cannot reach SQL without scrolling past a tall list.
- SQL Find misses repeated matches, loses its term during expansion, or labels a partial search as a server-wide search.
- Empty procedure searches look broken; an item deleted by refresh remains presented as current.
- View-only actions accidentally call procedure execution or other mutation endpoints.

`database.spec.ts` checks these through the running application with synthetic read responses. Playwright retains screenshots and its HTML report as repeatable evidence. No unit tests are added.
