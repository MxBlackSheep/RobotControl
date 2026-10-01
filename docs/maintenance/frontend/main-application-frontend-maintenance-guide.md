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

## Design system A (instrument console)

Approved mock: https://claude.ai/artifact/ApKjN7njdXXfQpZ1RDqRhx (column A). Light and dark
share one structure; only the palette changes.

**Tokens** (`theme.ts`): everything is a multiple of 4px. `layout` holds the sizes: page
padding 24px (16px on phones), gutter 12px, panel inset 16px, panel header and list row
40px, touch row 44px, control 36px, rail 216px (64px collapsed), radius 4px. The palette
adds `surface` (header band, lines, track, label, control border), `attentionSurface` (hold
banner, attention panel, attention action) and a `dot` colour per status tone. Type scale:
page title 24/32, detail title 20/28, body 14/20 and 13/20, caption 12/16, panel label
11px uppercase. Pages never use their own spacing or colour numbers.

**Primitives** (`PageLayout.tsx`), which pages compose:
- `PageHeader`: title, section tabs and actions on one 40px row (tabs move to their own row
  and actions start at the page edge on phones).
- `PageGrid`: 12 columns with the 12px gutter; one column below md. Panels take `span`.
- `Panel`: 40px header band (`PanelLabel`, optional `headerExtra`, actions), body (16px inset
  unless `inset={false}` for lists), optional fixed 40px `footer`, `tone="attention"`.
  Panels in one grid row share its height. `label` gives a region name different from the
  visible title when a field inside would otherwise share it (Maintenance Reason).
- `ListRow`: a single-line 40px row with grid columns; rows that carry a second line
  (schedules, folders, recordings) are a fixed 56px.
- `StatusDot` (dot and label, for strips and compact rows), `StatusChip` (24px, for
  emphasis), `DetailTitle`, and `EmptyPanel` (a Details panel with a plain prompt, so both
  sides of a list/detail workspace start with the same band).

Times use `utils/displayTime.ts` (`Today 14:30`, `Mon 28 Sep 16:00`, 24-hour, fixed
three-letter names). Execution statuses map to tones in
`components/scheduling/executionStatus.ts`. Refresh is always a labelled button.

## Overview

`pages/Dashboard.tsx` follows the mock on `PageGrid`: the instrument strip (scheduler,
storage, SQL Server, HxRun, camera; 12 columns), Now running (8) beside Needs attention (4;
Now running takes 12 when nothing is held), Up next (6) beside Recent runs (6, both seven
single-line rows) and Latest experiment as one full-width row. On phones the strip and the
hold come first. Each panel has its own error boundary and Retry, so one failed read never
blanks the page. Now running shows elapsed time against the schedule's estimate; past the
estimate the bar stops claiming progress (see `runTiming`).

Row columns follow each panel's own width (`@container`), not the window: with the collapsed
rail at 900px the half-width lists are ~388px. Up next and Recent runs drop secondary columns
(repeat, then duration and start) before the name falls below ~150px. Latest experiment is one
row from 1000px of panel width; narrower, its ID and times wrap below the method name. Strip
cells wrap by their own text, so a long state moves to the next line instead of being clipped.

## Page layout and screenshot review

`PageContent` uses the full width on every screen (only `reading` keeps a 1120px measure),
so page edges never move between modules. App owns the page padding, the phone header
(52px, below 900px) and the sticky attention banner.

Styling changes are verified by screenshot review, not the behaviour suite:
`npx playwright test -c playwright.visual.config.ts` (from `frontend`) fills every screen
with fixed sample data and saves light and dark screenshots at 1440, 1280 and 390px to
`test-output/visual/latest`. `VISUAL_ROUTES`, `VISUAL_WIDTHS` and `VISUAL_MODES` narrow it.
It shares the behaviour suite's fixture server and `e2e/global-teardown.ts`, which removes the
fixture's temporary log folder when the run ends.

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
