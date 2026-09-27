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
# Portable actions and reports (2026-09-27)

Before implementation, exercise these boundaries with disposable data:
- Upload/update/remove a package; reject traversal, binaries, duplicate identifiers,
  missing libraries and incompatible contracts. Failed updates preserve the active version.
- Anonymous/remote/non-admin callers cannot manage packages or change the database.
- Preview is bound to the user, package version and inputs; wrong confirmation,
  repeated execution, missing experiments and SQL failures cannot cause unintended writes.
- Busy/unknown robot state, unresolved recovery and unavailable safety storage block
  changes. Scheduler launch and a database change cannot overlap.
- Report output matches upstream values, parent/plate choices, columns and formatting;
  downloads are private, bounded workers reject excess work, expired files are removed.
- SMTP pending/sent/error records appear through HTTP and the screen. Manual/test/recovery
  emails are included. Partial refusal and log-storage failure must not resend accepted mail.
- A relocated executable installs and runs packages without a system Python or UV.
