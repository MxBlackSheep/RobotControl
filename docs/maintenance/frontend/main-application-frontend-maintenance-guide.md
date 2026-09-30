# Frontend main application

The React shell: providers, routing, navigation, page layout, appearance, shared
dialogs and keyboard shortcuts. Read this before adding a page or changing anything
every page shares.

## Structure

- `main.tsx`: imports the bundled IBM Plex fonts (`@fontsource`, so offline lab PCs render
  the same), then `BrowserRouter` → `AppearanceProvider` → `App`.
- `App.tsx`: wraps the shell in `AuthProvider`. Signed out, it renders only `LoginPage`.
  Signed in, `AppShell` renders `AppSidebar`, `RobotAttentionBanner`, the lazily loaded routes
  (`loadComponent` in `utils/BundleOptimizer.ts` retries a failed chunk load), and the
  global dialogs: `MaintenanceDialog` (temporary API pause during a database restore),
  `ChangePasswordDialog` (opens when `user.must_reset`) and `KeyboardShortcutsHelp`.
- `components/navigation.tsx`: the single registry of pages, sections, URLs and UI
  permissions. The sidebar and the section tabs in `PageHeader` both read it. App keeps its
  own route guards as well; backend permissions still apply.

## Navigation and sections

`AppSidebar` is the dark module rail: 224px expanded, 64px collapsed, an overlay drawer
below 900px (opened from the menu button in the phone header). It lists modules
only; the account menu (Change password, About, Log out) and Appearance sit at its foot.
Collapsed, the account button shows the initial, with the name and role as a tooltip and
screen-reader text, so the signed-in user is always identifiable. Page titles name the
module; the selected tab names the section.
`useSidebarLayout` starts expanded from 1440px and remembers an explicit desktop choice in
`robotcontrol.sidebar.expanded`; without localStorage the choice lasts for the session.

Sections are URLs such as `/scheduling?section=methods`. `PageHeader` shows a module's
permitted sections as tabs (links, so Back/Forward and shared links work); pages read the
choice with `useModuleSection` or, for Scheduling, `useSchedulingSection`. Do not add another
tab bar for sections. Invalid or forbidden sections are replaced in history. `SectionPanel`
mounts a section on first visit and keeps its drafts and scroll for the page session, so a
retained panel that polls must take an `active` flag and stop its timer when hidden (CSS
hiding alone does not stop effects).

## Robot status and attention banner

`useRobotStatus` (in `hooks/useRobotStatus.ts`) is the shell's one owner of robot state: it
polls `GET /api/scheduling/status/queue` and `/status/scheduler` every 15 s through
`useSerialPolling` and publishes the result in `RobotStatusContext`. `RobotAttentionBanner`,
the rail's Scheduling badge, the Recovery tab badge, Overview and Maintenance's Right now
panel all read that context; nothing else polls for them. Scheduling keeps its own view.

- Both replies carry `manual_recovery`. `newerRecovery` keeps the higher `safety_revision`;
  unhealthy storage always wins (fail closed), and a reply without the field clears nothing.
- `robotAttention` names why runs are held: unhealthy storage, pending recoveries, or an
  acknowledged recovery whose queued jobs still wait for Resume (`resume_required`).
- There is no always-on status bar. The banner appears on every page only while runs are
  held, while status is older than two polls ("Robot status updated N s ago · Retry"), or
  when no read has succeeded ("Robot status unavailable"). A failed read keeps the last
  known hold visible. Scheduler, HxRun, camera and database state live on Overview.

Permission rules shown in the UI: Database Restore is admin **or** local; Database
Operations and Scheduling Methods are local-only; Notifications are admin-only;
RobotControl logs are for local users or remote administrators. Camera navigation never
starts or stops a live-view session.

## Overview

`pages/Dashboard.tsx` arranges the panels in `components/overview/`: Now running and Needs
attention (from the robot status context), Up next (active schedules by `next_run`),
Instrument health (scheduler, storage, HxRun from the context; SQL Server and camera from
one 60 s read that tolerates either source failing), Recent runs (last five executions) and
the Latest experiment card. Below the current run, Up next and Recent runs stack in the
main column; Instrument health and Latest experiment stack in a 360px supporting column.
Below 1000px of workspace width they become one column, without remounting panels.
This avoids an empty row under a short Up next panel. Each panel has its own error
boundary and Retry, so one failed read never blanks the page.

Now running shows elapsed time from the run log monitor's `launched_at` against the
schedule's `estimated_duration`, which the user typed and may be wrong. `runTiming` never
extrapolates: within the estimate the bar shows elapsed/estimate; past it the bar becomes
indeterminate and the text says "N min past the M min estimate". Unknown start or estimate
shows no bar. The queue's `launched_at` is offset-qualified ISO time, so Overview and
Maintenance derive the same elapsed duration in every browser timezone; the Started clock
uses the viewer's local timezone. When PyHSL supplies better estimates, change only the estimate source.

## Shared presentation

`PageLayout.tsx` also exports `PanelHeader` (panel title and optional actions, with the
parent owning surrounding spacing), `PanelLabel` (small uppercase status label), `DetailTitle`
(the selected item's name, 18px) and `EmptyPanel` (a plain "choose something" prompt, not
an alert). Panel titles use the theme `h6`. Refresh is always a labelled button. Times use
`utils/displayTime.ts` (`Today 14:30`, 24-hour). Execution statuses map to tones in
`components/scheduling/executionStatus.ts`, shared by Overview and History.

## Page layout and appearance

`PageLayout.tsx` provides `PageContent` variants: `overview` (dashboards, capped at
1440px), `inspection` (viewers, including Logs, using available width), `spatial`
(labware, using available width) and `task` (forms, capped at 1120px; `reading` is a
legacy alias). App owns the outer gutter (16/24/28px), the phone header (52px, below 900px) and
the sticky attention banner. Use one `PageHeader`: title and page actions share its
first row; section tabs have their own row below. Actions wrap on narrow screens. Do not add another page header.

The theme uses 4px control corners and 8px panel corners (`Card`, or `sx`
`borderRadius: 2`). Normal `CardContent` and the exported `panelPadding` use 16px
insets on phones and 24px from 600px; collection toolbars use a compact 16px inset.
Panel headings use `PanelHeader`/`h6`; uppercase `PanelLabel` identifies status
context and `DetailTitle` names the selected item. Parents own gaps, so a panel
header does not add a competing margin. Keep special spatial and reader layouts.
The spacing/grouping direction draws on [Carbon](https://carbondesignsystem.com/elements/spacing/overview/)
and [PatternFly card anatomy](https://www.patternfly.org/components/card/design-guidelines/),
implemented with the existing MUI components.

`InspectionWorkspace` fills the remaining viewport height (320px minimum, then the page
scrolls) and switches between list and detail at 900px of content width; see the
inspection workspace guide. Spatial pages keep the equipment's physical order and
context; never derive coordinates from display names unless the backend defines that.

`AppearanceProvider` stores System/Light/Dark in `robotcontrol-appearance`, follows the
OS in System mode, syncs between tabs and falls back to memory if storage fails.
`index.html` sets the first background colour. Use the semantic palette from
`createAppTheme`; do not hardcode light surfaces or black text. `palette.rail` colours the
sidebar, and `palette.tone` (running, completed, neutral, attention, fault) colours
`StatusChip`, the one status label for every screen; attention (amber) always means
someone must act. The approved design is linked from `docs/plans/2026-09-30-frontend-redesign.md`. Touch and narrow-screen
controls have 44px targets; full-screen dialogs bypass the normal dialog margins.

## Messages and dialogs

- Status on a page (lists, dashboards, failed reads) is an inline MUI `Alert` with any
  Retry beside it.
- The result of an action the user started (save failed, password changed, restore
  started) uses `StatusDialog`. The owner keeps a `StatusMessage | null` and clears it in
  `onClose`; an optional `action` adds a button such as Retry, and `autoCloseMs` suits
  success messages. Messages shown inside a dialog that is already open stay inline.
- Use MUI `Dialog` directly for everything else. It already traps focus, closes on
  Escape and returns focus; do not add a focus-trap wrapper.

Keep labels short and about the content or next action; put technical detail in
Details, More or diagnostics. Keep permission limits, errors, unsaved changes,
recording and recovery state visible, and never show unknown state as success.

## Keyboard shortcuts

`hooks/useKeyboardNavigation.ts` holds the only shortcut list: Alt+1…9 for the pages in
sidebar order, Ctrl+H, Ctrl+B, Ctrl+Shift+R, `/` to focus search, Escape to clear focus,
and `?` for the help dialog, which renders the same list. Shortcuts do nothing while a
MUI modal is open or (except Escape) while typing. To change a shortcut, edit that list.
`navigation.test.tsx` and `system-pages.spec.ts` cover navigation, help and dialog
isolation; `system-pages.spec.ts` also covers the attention banner's failure cases.

## Adding a page or section

1. Pick one `PageContent` variant and one owner for the page's requests.
2. Register the page or section in `navigation.tsx`, add its guarded route in App with
   `loadComponent`, and add a shortcut only if it belongs in the Alt+number list.
3. Put primary actions in `PageHeader` or the toolbar and secondary ones under More.
4. Decide what survives Back, resizing, expansion and switching sections.
5. Write the failure cases first (`frontend/e2e/scenarios.md`) and pick checks from
   `frontend/e2e/README.md` for the affected pages and widths.

## Troubleshooting

- **Blank page after login:** a route is missing or its component throws; check the
  console. Only the Overview page (`pages/Dashboard.tsx`) is imported eagerly.
- **Wrong sidebar item or section tab:** check the section name and permission filters in
  `navigation.tsx` and the `section` query parameter.
- **Mobile menu does not open:** the phone header's Open navigation button must update
  `mobileDrawerOpen`, and `AppSidebar` needs `open`/`onClose`.
- **Banner stuck on "Robot status unavailable":** open the two status URLs above; the reply
  must carry `data.queue`, `data.manual_recovery` (may be null) and a boolean
  `data.is_running`.
- **Shortcuts do nothing:** `AppShell` calls `useKeyboardNavigation`; an open dialog
  (including a stuck invisible one) disables them.
