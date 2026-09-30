# Frontend redesign — brief (30 September 2026)

Approved design: [RobotControl Redesign Mock](https://claude.ai/artifact/BosxEuRcKRsc7YUxeWhDwo)
(20 artboards: nine modules on desktop and phone, plus the shared patterns sheet).
All work lands on the branch `redesign/instrument-panel`, one commit per verified step.

## User flow

- The robot's state is visible on every page: a status bar shows whether the
  scheduler is running, what is running now and whether a run needs recovery.
  Recovery links straight to Scheduling › Recovery.
- The sidebar lists modules only. A module's sections are tabs at the top of the
  page (`?section=` in the URL, unchanged), so Back/Forward and shared links keep working.
- Pages share one set of patterns: status chips, in-place errors that keep old data
  and say how old it is, empty states, a pinned unsaved-changes bar, and a
  confirmation that names the robot consequence.
- On phones the sidebar becomes a drawer, tabs scroll sideways, and two-column
  desktop layouts become a picker (table, file, rack) above the content.

## Data and state to retain

- Every existing draft protection stays: Labware and Scheduling pause refresh while
  editing, restore selections survive stale replies, maintenance reason drafts survive
  refresh.
- Scheduling recovery state stays ordered by `safety_revision`.
- Section choice stays in the URL; sidebar collapse stays in `localStorage`.
- Theme choice (System/Light/Dark) stays; every new surface has a dark variant.

## Safety constraints

- A failed or missing status read never looks like "all clear": the status bar shows
  "Status unavailable", not "Scheduler running" or "no recovery".
- Permission rules are unchanged: tabs are built from `allowedSections`, and the
  server still enforces every route.
- Robot-affecting actions keep their confirmations; no action gets easier to trigger.

## Build order

1. Theme tokens, bundled fonts (no internet needed), app shell: rail, status bar,
   section tabs in the page header, status chip.
2. Overview · 3. Scheduling · 4. Labware · 5. Camera · 6. Database · 7. Logs ·
8. Maintenance · 9. System status · 10. Admin.

Each step: failure cases in `frontend/e2e/scenarios.md` first, build, focused checks,
screenshots at phone/desktop, commit.

## Scope decision (30 September 2026): refactor only

This phase restyles each screen into the approved look and shared patterns without
adding features or removing existing ones. Each screen keeps its current content,
actions and permissions. Not built in this phase (they need new data or are new
features): the Overview cards beyond today's Dashboard content (Up next, Instrument
health, Recent runs, Needs attention), Maintenance's remaining-time estimate and "Right
now" summary, Logs' warning count and warning highlighting, declining a password reset
request, and "Next run" in the status bar. The step-1 status bar stays: it is the
recovery indicator the old sidebar already showed, now visible on every page.

## Acceptance

- Each screen matches its artboard at 1440x900 and 390x844, in light and dark.
- Existing browser checks for the affected area pass, or are changed only where the
  check itself asserted the old layout, with the reason in the commit.
- The shell works offline (no external font or script requests).
