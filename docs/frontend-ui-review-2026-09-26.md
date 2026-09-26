# Whole-application frontend review and design proposal

Reviewed 26 September 2026. This is a code-backed proposal, not an implemented redesign.
It covers the active routes and their nested sections, the supplied log screenshot,
and independent reviews/cross-review by two frontend specialists. No production
frontend or backend code changed during this review. Proposed dimensions and layout
targets below still require browser validation with representative data.

## Recommendation

Keep React and Material UI. Establish a shared application layout and four page
patterns: overview, inspection, spatial editing, and task/form. Give each pattern
clear rules for navigation, actions, scrolling, available space, selection and
mobile behavior. Add System/Light/Dark appearance through the same shared theme.

The previous work improved individual viewers but left the surrounding page
structure mostly intact. Functional E2E checks passed without proving that enough
space remained for the user's work. The next pass needs both workflow verification
and visual acceptance across the entire application.

## Confirmed causes in the current code

| Finding | Evidence | Consequence |
|---|---|---|
| The shared page layout only controls width and headings. | [PageLayout.tsx](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/components/PageLayout.tsx:3); [App.tsx](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/App.tsx:83) | Pages independently add headers, toolbars, cards and scroll areas. Consistent MUI components do not create a consistent workflow. |
| Logs stack several independent control areas above the text. | [LogSourceBrowser.tsx](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/components/LogSourceBrowser.tsx:333), [InspectionWorkspace.tsx](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/components/InspectionWorkspace.tsx:133), [LogReader.tsx](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/components/LogReader.tsx:379) | Shell breadcrumbs, page title, folder actions, folder breadcrumb, Hide files, filename, actions, Find and status all consume vertical space. In the supplied screenshot the text occupies roughly 36% of visible application height. This is an estimate from the screenshot, not a CSS measurement. |
| Database pagination omits first/last buttons. | [DatabaseTable.tsx](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/components/DatabaseTable.tsx:465), [database API](C:/Users/Hamilton/Desktop/RobotControl/backend/api/database.py:209) | Total count and arbitrary page requests already exist. This is primarily missing frontend navigation. |
| Maintenance explicitly uses a bounded reading layout. | [MaintenancePage.tsx](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/pages/MaintenancePage.tsx:113); PageContent caps it at 960px. | The single form floats in a large space. Increasing its width alone would stretch a small amount of content without making the task clearer. |
| Tip selection uses tiny mouse-only markers. | [TipTrackingPanel.tsx](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/components/labware/TipTrackingPanel.tsx:349) | Clickable 12×12 boxes have no native keyboard interaction; the full rack overview and permanent editing panel compete for attention. |
| Dark mode is blocked by explicit light styling. | [theme.ts](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/theme.ts:15), [main.tsx](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/main.tsx:30), InspectionTextViewer and TipTrackingPanel | Hardcoded black headings/alert text, light table/code surfaces, selection borders and highlights would survive a simple palette-mode toggle. |
| Responsive decisions use inconsistent reference widths. | Navigation uses viewport 900/1440px; InspectionWorkspace measures content width; Scheduling uses a container threshold while ScheduleList uses viewport width. | A narrow panel on a desktop can receive a dense desktop layout even when its actual content no longer fits. |
| Navigation and breadcrumb metadata have separate owners. | navigation.tsx and NavigationBreadcrumbs.tsx each describe routes/labels. | Future tabs can acquire inconsistent names or navigation rules; extend one authoritative registry. |
| Visited sections remain mounted. | [SectionPanel.tsx](C:/Users/Hamilton/Desktop/RobotControl/frontend/src/components/SectionPanel.tsx:2) | This preserves useful state. New layouts must explicitly distinguish visible content, retained drafts and background polling instead of unmounting everything to save space. |

There are also alternate/legacy implementations in the tree. App routes currently
use CameraPage and its imported archive component; CameraViewer, LiveCamerasTab,
LiveStreamingTab, TypedDatabaseTable/VirtualizedTable, BackupPage and
SystemConfigPage are not the active routed surfaces identified in this review.
Confirm all imports, tests and dynamic loading before consolidating or removing
them. Do not redesign an inactive component and assume the visible application changed.

## Shared application rules

### Navigation and headings

- Retain one primary navigation structure and the existing permission-aware section URLs.
- Expanded navigation on roomy screens, icon rail on smaller desktops, drawer on phones.
- Keep the current module and section discoverable. A compact section selector can live
  in the workspace heading when the navigation is collapsed; avoid another permanent
  full row of tabs beneath a breadcrumb and a second title.
- Use one workspace heading with primary actions. A pane title should identify its
  selected file/table/rack, without repeating the page description.
- Give filenames and paths available width; show full values through an accessible
  details/popover interaction. Do not let long titles push the content far downscreen.

### Space and scrolling

- Let the shell allocate available height through flex/grid. Inspection content fills
  the remaining space; children should not each subtract their own guessed header height.
- Each workspace has a deliberate main scroll area. Side lists can scroll separately;
  avoid nested page/card/table scrollbars unless the interaction requires them.
- Forms and dashboards use document scrolling. They need not behave like editors.
- On short screens, at high browser zoom, or with a phone keyboard open, controls
  must remain reachable through scrolling. Do not lock every page to a fixed viewport.
- Resizable/collapsible collection panels should have sensible minimum widths and a
  keyboard-operable divider. Extra-wide monitors can show useful context alongside
  content; prose and form inputs should retain readable line lengths.

### Actions and density

- Use a compact primary toolbar with one prominent next action. Secondary actions go
  into More; show applicable selection actions when something is selected.
- Keep Find discoverable as a button/keyboard action even when its input is collapsed.
- Prefer compact controls for mouse use and comfortable controls for touch. Preserve
  approximately 44px touch targets; do not solve density by shrinking all text or controls.
- Offer an explicit Comfortable/Compact preference if necessary, distinct from theme.
  Use content width and pointer capability, not a blanket assumption that a phone is
  the only touch device or that a desktop panel is always wide.
- Important errors, permission limits, unsaved changes, recording and recovery state
  stay visible. Debug metadata and routine explanations can be disclosed on demand.

### State and data confidence

- Layout, expansion, theme and density changes preserve the selected resource,
  filters, page, scroll, focus, drafts and existing camera session.
- Browser Back restores the preceding view. Leaving an edit workflow must account for
  unsaved changes. Harmless preferences may persist per browser; sensitive content and
  authentication data do not belong in a new general-purpose UI preference store.
- Show loading, fresh, stale, unknown, empty and failed as distinct states. Unknown
  maintenance or camera state must never appear as a reassuring success state.
- Retain previous data on failed refresh with its displayed query/time. Do not label
  old data with the newly requested page or filter as though the request succeeded.
- Establish one polling owner per shared dataset, with explicit visibility rules.
  Presentation changes must not trigger hardware commands, saves or extra stream starts.

## Four reusable page patterns

| Pattern | Desktop | Narrow windows and phones | Current uses |
|---|---|---|---|
| Overview | Prioritized summary with relevant detail arranged in a responsive grid. | Status and next action first, followed by one column of detail. | Dashboard, System Status, calendar summaries. |
| Inspection | Collection/filter pane beside a dominant viewer; optional details only when useful and space permits. | Collection or selected content, with Back and retained position. | Tables, procedures, logs, video archive, schedules/history, account lists. |
| Spatial editing | Overview/map plus selected-object editor and persistent pending-change summary. | Select a rack/position, then use a comfortably sized editor; retain an overview route. | Tip tracking, Cytomat; live camera uses a specialized image viewport with a contextual controls panel. |
| Task/form | Bounded input width, clear consequence/status and one primary action; contextual material alongside only when useful. | Linear task with reachable actions and full-screen editing when appropriate. | Maintenance, restore/operations, schedule forms, notifications, account editing, About and Login. |

These are composable patterns, not four rigid screens. Scheduling can use inspection
for the list and task/form for editing. A future page declares its pattern, actions,
permissions, scroll owner, retained state and background activity policy. Keep
business logic in the modules rather than putting every feature into one giant
generic page component.

## Proposed changes by module and section

| Module/sections | Recommended design |
|---|---|
| Dashboard | Make current experiment, attention-required conditions and the next useful action prominent using existing data. Avoid stretching one compact widget across an ultra-wide screen or adding decorative statistics. |
| Database: tables | Keep the grid and full-row inspector. Add First/Previous/Next/Last, page X of Y and an optional Go to page field. Preserve search/sort/export and handle changing counts and failed page requests. |
| Database: procedures/functions | Retain the clean catalogue and SQL/Parameters/Details structure. Add Top/Bottom or Go to line for a long definition; definitions are continuous text, not paginated result sets. |
| Database: restore/operations | Use clear task steps and a bounded form. Keep local/admin restrictions and consequential actions explicit. Avoid mixing these controls into the read-only inspection toolbar. |
| Logs: all sources | Move folder actions, folder breadcrumb, filename search and sort into the file pane. Put Hide files in its header, not a dedicated row. The reader gets one compact filename/action toolbar, an on-demand Find row and a slim section/status footer. Keep section navigation separate from file-list pagination, preserve captured-version and Follow semantics, and offer optional Focus/Expand. Normal viewing must already provide adequate space. |
| Scheduling: schedules/methods | List/detail workspace. Selection reveals relevant actions beside the list on desktop or in a reachable phone panel. Keep queue/run/recovery status visible and distinguish immediate commands from editing. |
| Scheduling: calendar/history/archive | Calendar on roomy screens; agenda on phones. Shared compact filter bar and list/detail history, with row details instead of permanently wide metadata. |
| Scheduling: recovery/notifications | Recovery is a guided task with explicit blockers and acknowledgement. Notification contacts/settings use form layouts; delivery logs use inspection. Preserve the safety semantics of Resume and destructive actions. |
| Camera: live/archive | Retain Fit/Fill/zoom and session behavior. Apply the shared toolbar and status conventions. Archive should use folder/file navigation on phones, with a dominant playback viewer on desktop; remove fixed indents and brittle fixed-height wrapping rows. |
| Labware: tips | Begin with family and compact rack summaries. Select a rack to get a readable map, coordinates and context-specific Tip/Column/Rack actions. Keep an overview mode useful on large screens. On phones use a larger selected-rack view or accessible position list; do not try to make every rack's tiny dot directly editable at once. Show pending count and Save/Discard near the work; place Reset in a clearly labelled separate flow. |
| Labware: Cytomat | Keep the location/plate relationship easy to scan, with filtering if data volume warrants it. Inspect/edit the selected location instead of rendering a permanent editor in every row. Preserve batch updates and a visible pending-change bar. |
| Maintenance | Lead with verified HxRun state and consequences. Use an intentional task layout: current state/audit information and the bounded reason/action form. Show the applicable action clearly, such as Enter maintenance or Allow HxRun launches. A large monitor need not be filled with stretched inputs or invented panels; use extra width for real context when present. |
| System Status | Organize existing telemetry into a useful overview with detail on demand. Share refresh/freshness state for common data. Avoid independent widgets presenting conflicting update times for the same system. |
| Admin: accounts/reset requests | Resource list with contextual edit/review flow. Phone summaries and a dedicated editor; desktop table with restrained row actions. Keep destructive changes explicit. Local SQLite health/repair currently appears beneath both account sections; give it its own authorized section instead of mixing account work and storage repair. |
| About/Login/password dialogs | Bounded readable surfaces, consistent theme and focus handling. These are appropriately narrow; verify keyboard appearance and long validation text rather than forcing full-width layouts. |

## Last-page navigation details

I interpret the SQL request as database table-result pagination. The backend already
accepts a page number and returns total_count. MUI v5 TablePagination exposes
showFirstButton/showLastButton; a labelled page jump would be a small additional
control. Last must apply to the current filtered/sorted result, not to an unrelated
unfiltered count. Empty results, shrinking totals, aborts and failed requests need
explicit handling. Large OFFSET queries can still cost more on SQL Server; verify
representative tables without replacing the existing backend query strategy by guesswork.

## Dark mode design

Provide System (default), Light and Dark in an Appearance setting reachable from
the account menu and login screen. Store the preference locally and apply it before
the main UI paints. System follows OS changes; an explicit choice takes precedence.
Switch appearance without remounting pages or changing live operations.

Use semantic theme colors for page/panel/raised surfaces, primary/secondary text,
dividers, hover/selection/focus, status and pending changes, code/log backgrounds and
search highlights. Update dialogs, menus, tooltips, notifications/toasts, table
headers, empty/error states and labware markers as well as the page background.
Camera/video pixels remain untouched. Preserve status meaning with labels/shapes,
not just a color mapping.

This is supported by the installed MUI v5 theme APIs; a library migration is not a
prerequisite. Existing contrast comments are not sufficient validation: for example,
theme.ts describes white on warning #ef6c00 as 4.56:1, but calculating sRGB relative
luminance gives approximately 3.08:1. Test actual rendered normal-text, focus,
selection and disabled states for both themes rather than trusting the comments.

## Behavior issues to resolve with the redesign

1. **Unknown maintenance state looks safe.** MaintenancePage uses state?.enabled to
   choose a success-colored "Disabled (HxRun allowed)" label after an initial load
   error. Preserve unknown/unavailable until the backend has returned a state.
2. **Pending tip edits can disappear during Save.** TipTrackingPanel.savePending
   captures the current batch, awaits it, then clears the entire family's pending
   map. Edit actions remain usable during that request. Lock editing during save or
   remove only the acknowledged changes while retaining newer edits.
3. **Initial labware failures look empty.** TipTrackingPanel's missing-family return
   and CytomatPanel's no-rows return precede their normal error alerts. Report
   failure/retry distinctly from a successful empty result.
4. **Failed pagination can mislabel retained rows.** DatabaseTable keeps prior rows
   when a new request fails, but row numbers and pagination use the new query.page.
   Track requested and displayed queries separately, or restore the displayed query.
5. **Monitoring has separate polling owners.** MonitoringDashboard and SystemStatus
   each use useMonitoring. Check shared data ownership and refresh behavior before
   composing them into a new overview; styling alone will not synchronize them.

These are code-reviewed scenarios, not newly reproduced live failures. The supplied
log screenshot is visual evidence; the rest needs targeted browser fixtures before
implementation and verification afterward.

## Acceptance and delivery sequence

1. Agree on the common shell, four patterns, light/dark tokens and action hierarchy.
   Use realistic long filenames, loaded racks and stale/error states in representative
   Logs, Labware and Maintenance designs before applying them across the application.
2. Write browser failure scenarios for the behavior issues above. Implement the
   shared theme/layout foundations and the three representative pages, plus table
   navigation. Preserve APIs, permissions, polling, draft and streaming behavior.
3. Apply the reviewed patterns to every active route/section and modal. Confirm the
   legacy-component import map before consolidating duplicate code.
4. Run browser workflows and visual checks in System/Light/Dark at 1280×720,
   1920×1080, a large-monitor CSS viewport, 320/390px phones and landscape, including
   200% zoom and a 320px-equivalent reflow check. Physical screen resolution alone
   is insufficient: record CSS viewport and OS/browser scaling.
5. Inspect phone keyboard behavior, keyboard-only navigation, selected-rack targets,
   long content, stale/error/loading/empty states, draft retention, page jump failures,
   resize/theme changes and camera request counts. Retain reports/screenshots/traces.
6. Build/embed/package and verify the candidate in a relocated folder for VM testing.

Proposed measurable design goal: at 1280×720 in the default log-reading state,
allocate at least 60% of available application height to readable log content,
without requiring Expand. This is an acceptance target, not a hardcoded CSS height;
visible errors, opened Find and accessibility settings may legitimately change it.
On phones the selected-content workflow must stay usable with touch and the keyboard,
without placing a full file catalogue above the reader. Forms should have deliberate
widths and helpful context; there is no universal target to fill every blank area.

## Professional guidance informing the proposal

- [IBM Carbon data tables](https://carbondesignsystem.com/components/data-table/usage/):
  coordinated row/toolbar density, clear selection actions and secondary overflow.
- [IBM Carbon pagination](https://carbondesignsystem.com/components/pagination/usage/):
  consistent paging and direct navigation for large collections.
- [AWS Cloudscape resource views](https://cloudscape.design/patterns/resource-management/view/):
  collection/detail views with optional contextual panels.
- [Material UI v5 dark mode](https://v5.mui.com/material-ui/customization/dark-mode/):
  custom mode-specific palettes, a theme provider and system preference support.
- [Material UI v5 TablePagination](https://v5.mui.com/material-ui/api/table-pagination/):
  existing first/last-page controls in the installed component family.
- [PatternFly primary/detail](https://www.patternfly.org/patterns/primary-detail/design-guidelines/):
  context-preserving collection/detail navigation adapted to narrow screens.
- [Carbon forms](https://carbondesignsystem.com/patterns/forms-pattern/):
  task-focused forms, progressive disclosure and appropriate surfaces for complex input.
- [Grafana dashboard guidance](https://grafana.com/docs/grafana-cloud/learn-and-build/visualizations/dashboards/build-dashboards/best-practices/):
  organize monitoring around the operational question and progress from summary to detail.
- [W3C reflow guidance](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html):
  narrow/zoomed layouts and scoped exceptions for genuinely two-dimensional content.
- [W3C target sizing](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
  and [contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html):
  check actual interaction geometry and rendered color pairs.

These are references for adapting proven patterns to RobotControl. They do not imply
that importing another design system or copying a desktop console wholesale would
solve this application's phone workflows.
