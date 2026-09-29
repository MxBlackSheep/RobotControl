# Frontend main application

The React shell: providers, routing, navigation, page layout, appearance, shared
dialogs and keyboard shortcuts. Read this before adding a page or changing anything
every page shares.

## Structure

- `main.tsx`: `BrowserRouter` → `AppearanceProvider` → `App`.
- `App.tsx`: wraps the shell in `AuthProvider`. Signed out, it renders only `LoginPage`.
  Signed in, it renders the account header, `AppSidebar`, breadcrumbs, the lazily loaded
  routes (`loadComponent` in `utils/BundleOptimizer.ts` retries a failed chunk load), and
  the global dialogs: `MaintenanceDialog` (temporary API pause during a database restore),
  `ChangePasswordDialog` (opens when `user.must_reset`) and `KeyboardShortcutsHelp`.
- `components/navigation.tsx`: the single registry of pages, sections, URLs and UI
  permissions. The sidebar, breadcrumbs and section panels all read it. App keeps its own
  route guards as well; backend permissions still apply.

## Navigation and sections

`AppSidebar` is 240px expanded and 64px collapsed, and becomes an overlay below 900px.
`useSidebarLayout` starts expanded from 1440px and remembers an explicit desktop choice in
`robotcontrol.sidebar.expanded`; without localStorage the choice lasts for the session.

Sections are URLs such as `/scheduling?section=methods`. Use `useModuleSection`,
`moduleSectionUrl` and, for Scheduling, `useSchedulingSection`; do not add another tab
bar. Invalid or forbidden sections are replaced in history; explicit navigation supports
Back/Forward. `SectionPanel` mounts a section on first visit and keeps its drafts and
scroll for the page session, so a retained panel that polls must take an `active` flag
and stop its timer when hidden (CSS hiding alone does not stop effects). The Scheduling
recovery badge reads the page's existing polling state through
`SchedulingNavigationContext` instead of polling again.

Permission rules shown in the UI: Database Restore is admin **or** local; Database
Operations and Scheduling Methods are local-only; Notifications are admin-only;
RobotControl logs are for local users or remote administrators. Camera navigation never
starts or stops a live-view session.

## Page layout and appearance

`PageLayout.tsx` provides `PageContent` variants: `overview` (dashboards), `inspection`
(viewers), `spatial` (labware) and `task` (forms, capped at 1120px; `reading` is a legacy
alias). App owns the outer gutter (8/12/16px) and the 56px header. Use one `PageHeader`
and no extra Container or breadcrumb row.

`InspectionWorkspace` fills the remaining viewport height (320px minimum, then the page
scrolls) and switches between list and detail at 900px of content width; see the
inspection workspace guide. Spatial pages keep the equipment's physical order and
context; never derive coordinates from display names unless the backend defines that.

`AppearanceProvider` stores System/Light/Dark in `robotcontrol-appearance`, follows the
OS in System mode, syncs between tabs and falls back to memory if storage fails.
`index.html` sets the first background colour. Use the semantic palette from
`createAppTheme`; do not hardcode light surfaces or black text. Touch and narrow-screen
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
`AppSidebar.test.tsx` and `system-pages.spec.ts` cover navigation, help and dialog
isolation.

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
  console. Only Dashboard is imported eagerly.
- **Wrong sidebar item or section:** check the section name and permission filters in
  `navigation.tsx` and the `section` query parameter.
- **Mobile menu does not open:** the header's Open navigation button must update
  `mobileDrawerOpen`, and `AppSidebar` needs `open`/`onClose`.
- **Shortcuts do nothing:** App must call `useKeyboardNavigation({ enabled: isAuthenticated })`;
  an open dialog (including a stuck invisible one) disables them.
