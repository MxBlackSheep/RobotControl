# Engineering review — 27 September 2026

## Judgment

The concerns are valid. The main problem is that the process does not distinguish
small, reversible presentation changes from changes that can lose data or control
hardware. More checks are useful only when they answer a relevant question.

This was a targeted review of repository guidance, recent verification evidence,
Labware state/layout, shared polling, page loading, scheduling structure and the
browser harness. It is not a full correctness or security audit.

## Findings and decisions

| Finding | Evidence | Decision |
| --- | --- | --- |
| Build instructions are too broad. | The former root guidance required Windows build/compile after changes without distinguishing documentation, local edits and releases. | Build changed frontend code before verification; embed/package when delivering a candidate or checking deployment behavior. No executable build for documentation/test-only edits. |
| Routine instructions encourage excessive verification. | The old browser README led with the full suite and repeated release histories. The main-page guide prescribed a full screen/theme/zoom matrix for future pages; the Maintenance guide requested all browser tests. | Select tests by changed behavior and affected consumers. Keep broad runs available for shared changes and release acceptance. |
| Evidence handling adds avoidable work. | Playwright retained traces and screenshots for every successful test. Prior iterations copied complete report folders. | Default to failure-trace retention, opt into full traces when needed. Keep existing visual screenshots and release evidence. This reduces retained data; it does not eliminate trace capture cost during a run. |
| Current rules are not reproducible across checkouts. | `.gitignore` excluded the existing root `AGENTS.md`; Git did not track it. | Track the project rules. Keep the machine-wide Codex instructions unchanged; this repository now spells out proportional E2E scope. |
| Documentation mixes current operation with history. | The browser README contains successive Spatial/Rack/Quiet/Full-workspace revisions, while several scenario documents overlap. | Make the run guide current and add a small documentation index. Existing scenario/history files remain referenced; avoid a mass move that breaks useful links. |
| “Simplicity” is not defined operationally. | Former guidance said “make code easy-to-understand” but provided no choice criteria. | Require an observable user outcome, real constraints and a reason for each extra abstraction/state owner. Preserve safety and data guarantees. |
| Communication is too process-heavy. | Recent updates often counted test progress and described implementation mechanisms before their practical effect. | Explain the result and a specific usage case first. Report decisions/blockers instead of routine execution. A passing test total is supporting evidence, not the headline. |

The latest 100-case run took about 6.2 minutes and was explicitly requested by the
approved release plan. It was not inherently wrong. Requiring that same run for
every subsequent spacing or documentation edit would be disproportionate. The
first Labware run also caught real geometry faults: keep that useful coverage.

## Code observations for future changes

- **Keep the late-response protection.** `useLabwareSnapshot` and
  `useSerialPolling` invalidate an old read when editing begins. Without it, a
  refresh can replace a tip state the operator just changed. This is justified
  complexity, like keeping a latch on a door that must not swing open.
- **Reduce unused options before adding more.** In
  `frontend/src/utils/BundleOptimizer.ts`, `fallback` is declared but not read;
  `DefaultLoadingFallback`, `ComponentLoadError` and `preloadComponent` have no
  callers under `frontend/src`. The used `loadComponent` does have callers and
  retries imports. On the next related change, remove unused surface after a
  caller check; do not replace it with another loading framework.
- **Keep fixture contracts consistent.** Real rack IDs and similar snapshot data
  appear in layout, native-zoom and packaged checks. When changing that contract,
  share the stable data through a small fixture file; keep each test's failure
  behavior local. A universal fixture factory would add complexity of its own.
- **Review responsibility before splitting files.** `SchedulingPage.tsx` combines
  several workflows, and scheduling API/storage files are large. Size alone is
  not proof of a defect. Extract a coherent responsibility when a real scheduling
  change needs it; do not restructure the scheduler during a layout task.

No runtime behavior, safety gate, API or test case was removed in this review.
The existing frontend/backend module folders remain appropriate. The earlier
frontend specialists have no active work and are not part of the default workflow.

## Practical difference

| User request | Proportionate response |
| --- | --- |
| “This toolbar wastes space.” | Adjust the relevant layout, build it and inspect the affected desktop/narrow boundary. Reuse the focused sizing check. |
| “Save loses my tip changes.” | Reproduce the loss; check failure, late refresh, Undo and successful Save. Use disposable inventory. |
| “Change when a scheduled robot run resumes.” | Establish the safety/recovery rules first; exercise the affected scheduler boundary and relevant real deployment behavior. |
| “Clarify the maintenance guide.” | Review the text, links and diff. No browser suite or Windows candidate. |

Guidance is centralized in [AGENTS.md](../AGENTS.md). Commands live in the
[browser run guide](../frontend/e2e/README.md). Changes to guidance/configuration
are checked by reviewing links/diffs and loading Playwright's case list; the
previous release report is preserved, and no new application build is needed.
