# RobotControl engineering guidance

Python/FastAPI backend and React/TypeScript/MUI frontend for Hamilton robots,
cameras, scheduling and monitoring. Use PowerShell 7 on Windows and `rg` for search.

## Start from the user’s job

Before editing, read the affected code and state the observable outcome, the
constraints and what could go wrong. Separate measured facts from assumptions.
For example: “Show all racks in their physical order; resizing must not lose
unsaved tip changes.” A proposed component or framework is not the requirement.

Choose the simplest mechanism that meets those needs. Prefer existing platform,
React and CSS behavior. Add state, abstractions, dependencies or configuration
only for a concrete requirement or demonstrated failure; explain the cost they
remove. Do not build for hypothetical future tabs or features.

- Keep one owner for each request, timer and editable state. Derive values instead
  of storing multiple copies that need synchronization.
- Share code when callers have the same behavior and reason to change. Similar
  appearance alone is not enough: a physical rack map and a file list may need
  different layouts.
- Keep functions and names direct. Comments explain a constraint or decision,
  rather than restating the code. Avoid names such as Improved/New/Manager when
  a domain name says what the code does.
- For a local refactor, find every caller, preserve its contract and remove the
  replaced path. Briefly explain the approach and proceed within the request.
  Propose a separate change when it crosses modules or changes behavior.
- File length is a review signal, not a reason for a rewrite. Split by an actual
  responsibility or change boundary; do not add layers merely to shorten files.
- Keep permission checks, robot safety gates, data integrity and protection from
  late responses. Simplification must preserve these guarantees.

## Match verification to the change

Name the relevant failure cases before changing behavior. A short note in the
existing scenario file or task is enough; do not create a new document per tweak.
Prefer browser/HTTP E2E checks for user workflows and integration. Do not add unit
tests after writing production code. Existing focused tests may be run; if an
isolated check is necessary, describe its failures before implementation.

| Change | Normal verification |
| --- | --- |
| Documentation or comments | Review accuracy, paths and diff; no app build or browser suite. |
| Local layout or wording | Build changed frontend code; inspect affected view and relevant width boundary. Use an existing focused browser check where useful. |
| Drafts, Save, polling or permissions | Focused workflow checks, including the relevant failure/recovery and state-preservation cases. |
| Shared navigation, theme or cross-module contract | Check affected consumers; broaden to the full suite when the impact warrants it. |
| Scheduler, hardware, storage or deployment behavior | Verify the affected safety/recovery paths with disposable data; package/hardware checks where the boundary requires them. |

Use representative sizes plus the breakpoint implicated in a bug. A 4K sizing
change warrants 4K; a label correction does not require every viewport. Add a
regression only for behavior that can plausibly break, not to mirror implementation.
Reuse existing fixtures; avoid another copy of the same rack IDs or API contract.

Stop after the relevant checks pass. Repeat or broaden only for new changes,
a failure, an unresolved risk or an explicit acceptance requirement. Investigate
timeouts before increasing them; preserve the failure and state what the new
bound means. A pass count alone does not establish visual quality or real-hardware
correctness.

Every E2E run should be repeatable: record command, code/build identity, fixture
source, outcome and relevant evidence. Keep useful screenshots and failure traces;
full successful traces are opt-in for releases/investigations. Keep one current
report, preserve referenced release evidence and useful failures, and remove
owned disposable processes/data. Do not copy every entire report after each edit
or delete old release evidence without an explicit retention decision.

See [frontend/e2e/README.md](frontend/e2e/README.md) for commands and limits.

## Builds and delivery

For changed frontend code on Windows, run `npm --prefix frontend run build` before
final verification. Run it again only if inputs changed. Do not reinstall packages
unless setting up the workspace or dependency inputs changed.

Embed and compile once a Windows candidate is needed, after relevant checks pass:
`uv run --locked python build_scripts/embed_resources.py`, then
`uv run --locked --group build python build_scripts/pyinstaller_build.py --output-dir dist/<new-candidate>`.
Use a fresh candidate directory and verify the packaged boundary. Documentation,
review and test-only changes do not require an executable rebuild. On WSL, make
changes but leave Windows compilation to Windows and report that limit.

Commit related changes together; preserve unrelated working edits. A candidate
and its verification record must identify the code/build actually exercised.

## Communication and collaboration

Explain the user-visible result first, then the reason or trade-off. Use ordinary
words and a concrete before/after usage case. For example: “Before, Refresh could
replace tips you had just edited. Now, editing pauses refresh until you finish.”
Use an analogy only when it shortens the explanation. Avoid process jargon,
invented labels, repetitive test counters and narration of routine tool calls.

Before implementation, briefly explain what you found and the intended change.
Progress updates should report a finding, decision, blocker or meaningful stage.
Finish with what changed, what was checked and any material limit. When manual
help is essential, give the exact action and what happens next. Keep UI wording
short; put engineering explanation in maintenance documentation.

Work as one agent by default. Delegate only when explicitly requested for the
current work; previous specialist assignments are not a standing requirement.
The earlier frontend specialist assignments are retired.

## Where information belongs

- This file: current engineering rules, tracked with the repository.
- `docs/maintenance/frontend` and `docs/maintenance/backend`: current module
  behavior, key files and troubleshooting. Update only the guides affected.
- `frontend/e2e`: executable browser checks and their module failure scenarios.
- `docs/implementation-notes.md`: prepend a concise record of meaningful changes;
  link evidence rather than copying a test transcript.
- `docs/*review*.md` and `docs/plans`: dated findings/proposals, not standing rules.
- `recovery/`, `build/`, `dist/`: local evidence/build outputs, not source guidance.

Write for a competent maintainer unfamiliar with this module. Define necessary
terms and show the relevant command/path. Avoid duplicate policy, per-change
folder trees and wholesale reorganizations without a concrete navigation benefit.
