# Frontend Main Application Maintenance Guide

## Shared page layout (September 2026)

`components/PageLayout.tsx` provides `PageContent` and `PageHeader` for authenticated pages. App owns the only outer gutter (16px small / 24px desktop), a 56px account header, and the single breadcrumb location. Do not add another outer MUI Container, Back row, or breadcrumb row inside a page. Put its title and actions in PageHeader; retain functional local tabs outside Scheduling.

Operational pages use all available width. Set `reading` on PageContent for explanatory/settings pages (960px maximum); the email settings card has its own 1000px limit. These limits do not constrain operational tables. PageContent is the named `workspace` CSS container: use its available width, rather than the whole browser width, for layouts that sit beside the sidebar.

Scheduling places Create schedule and Import methods beside its title and uses a compact scheduler-service strip. Its list/runtime columns stack below 1100px of content width. The method explorer switches to sequential folder/results views below 900px of its own width. MUI Dialog retains fixed title/actions with a scrolling body. Preserve input sizes and readable typography when adjusting spacing.

Validation: `PageLayout.test.tsx` checks heading/actions and section breadcrumbs; sidebar and scheduling component tests cover navigation and draft preservation. Browser review uses 390, 1280 and 1920px widths. The in-app browser does not apply zoom shortcuts: 640×360 checks equivalent layout space for 1280×720 at 200%, but is not a native browser-zoom test.

## Sidebar and section navigation

`components/navigation.tsx` is the shared source for desktop/mobile navigation and Scheduling sections. Keep existing route guards in App as well as navigation filtering. `AppSidebar` replaces the former MobileDrawer and top-level tabs: 240px expanded, 64px collapsed, overlay below 900px. `useSidebarLayout` defaults expanded at 1440px and remembers explicit desktop choices in `robotcontrol.sidebar.expanded`; unavailable localStorage still permits a session choice.

Scheduling uses `/scheduling?section=methods` (and schedules/calendar/history/archived/recovery/notifications). `useSchedulingSection` maps names to existing panel indices without remounting Scheduling on section changes. Invalid/inaccessible names are removed with history replacement; explicit navigation supports Back/Forward. Methods requires local access; Notifications requires admin. Use the shared section mapping for programmatic navigation. The recovery badge receives the latest Scheduling polling state through SchedulingNavigationContext; it does not add another poller.

MUI owns modal/menu Escape and focus. Global navigation shortcuts must not run while a modal is open. `AppSidebar.test.tsx` covers permissions, history, mobile behavior, stored preference and shortcut isolation.

## uv setup and verification

For a fresh Windows clone, use Node.js 24 with npm and run `npm --prefix frontend ci`, then `npm --prefix frontend run build`, from the repository root. Start the Python backend through `uv run --locked python backend/main.py --host 127.0.0.1 --port 8005 --no-browser`; it serves `frontend/dist`. Rebuild and re-embed assets before packaging the executable.

This guide explains the overall React shell: routing, theming, providers, and navigation. Use it whenever you change layout, add new pages, or adjust global providers. It spells everything out so you can’t get lost.

---

## 1. High-Level Architecture

- `frontend/src/main.tsx`  
  App entry point. Wraps `<App />` with React Router (`BrowserRouter`), Material UI theme provider, React Query client, and `react-hot-toast`.

- `frontend/src/App.tsx`  
  Defines the navigation shell. Handles authentication gating, top app bar, responsive sidebar, password change dialog, and route rendering via `<Routes>`.

- `frontend/src/theme.ts`  
  Central Material UI theme (palette, typography, component overrides). Imported by `main.tsx`.

- `frontend/src/utils/BundleOptimizer.ts` (`loadComponent`)  
  Lazy-load helper for page components (Database, Camera, Monitoring, etc.) to keep the initial bundle small.

- Shared UI components used globally:
  - `NavigationBreadcrumbs` – renders breadcrumb trail.
  - `AppSidebar` – shared expanded/collapsed/mobile navigation.
  - `SkipLink`, `KeyboardShortcutsHelp` – accessibility helpers.
  - `MaintenanceDialog` – warns users during backend database-restore windows (temporary API pause mode).
  - `ErrorAlert`, `SuccessAlert`, `ServerError` – modal notifications for state-changing flows (password change, delete confirmations). Dashboard-style status messages should use inline cards inside the relevant component.

**Rule of thumb:** All new pages should be registered in `App.tsx` (both the `Routes` block and, if appropriate, the shared navigation definitions). Ensure they sit inside `AuthProvider` so they can access user data.

---

## 2. Routing & Layout Lifecycle

1. **App bootstrap** (`main.tsx`):  
   - Creates a `QueryClient` (retry=2, no refetch on focus).  
   - Wraps `<App />` with providers in this order: `<QueryClientProvider>` → `<BrowserRouter>` → `<ThemeProvider>` → `<CssBaseline>` → `<App />` → `<Toaster>`.

2. **Authentication check** (`App.tsx`):  
   - `const { isAuthenticated, user, logout } = useAuth();`  
   - If `isAuthenticated` is false, return `<LoginPage />` immediately. The rest of the layout is hidden until login succeeds.

3. **Layout components** once authenticated:  
   - `AppBar` with user greeting, change password, logout buttons.  
   - Desktop navigation: `<AppSidebar>` linked to the shared route/section list.
   - Mobile navigation: the same AppSidebar rendered as an overlay drawer.
   - `Routes` inside `<Suspense fallback={<PageLoading />}>` so lazy pages show a spinner while loading.

4. **Route definitions**  
   - `'/'` → `Dashboard`  
  - `/database`, `/camera`, `/labware`, `/maintenance`, `/logfile`, `/system-status`, `/scheduling`, `/admin`, `/about` (lazy-loaded).  
   - Redirect unknown paths with `<Navigate to="/" />` as needed.

5. **Global dialogs**  
   - `MaintenanceDialog` listens for maintenance mode (via utilities).  
  - `ChangePasswordDialog` opens automatically if `user.must_reset`.  
   - `KeyboardShortcutsHelp` toggled via `useKeyboardShortcutsHelp`.

---

## 3. Key Providers & Hooks

- `AuthProvider` (from `context/AuthContext.tsx`) – wraps `<App />` in `main.tsx`. Every component uses `useAuth()` to read user info and tokens.
- `QueryClientProvider` – allows future components to use React Query. Currently most data still relies on custom hooks, but the provider is ready.
- `ThemeProvider` + `CssBaseline` – ensures consistent Material UI styling.
- `BrowserRouter` – handles routing. If you need hash routing (for environments without server support), swap it here.
- `useKeyboardNavigation` – enables keyboard shortcuts when authenticated (e.g., `Alt+1` to change tabs).

---

## 4. Working With Navigation

1. **Update the tab list** in `App.tsx`. The list is built dynamically based on `user.role`. Add entries to the `tabItems` array and ensure they map to actual routes.
2. **Route matching** uses `location.pathname`. When adding nested routes (e.g., `/scheduling/history`), update the fallback logic so the correct tab highlights (`startsWith` check).
3. **Mobile drawer** uses the same `tabItems`. Keep the data structure simple (label + path) so both navigation methods stay in sync.
4. **Breadcrumbs** – `NavigationBreadcrumbs` reads the current path. If you add deep nested routes, update its mapping table to show friendly names.
5. **Change password flow** – open the dialog with `setPasswordDialogOpen(true)`. Remember to close it on successful change or when the user cancels.

---

## 5. Common Maintenance Tasks

| Task | Where | Steps |
|------|-------|-------|
| Add a new page (e.g., “Reports”) | `App.tsx`, navigation helpers | Create `frontend/src/pages/ReportsPage.tsx`, add `const ReportsPage = loadComponent(() => import('./pages/ReportsPage'));`, add a `<Route>` and tab item, then update `MobileDrawer.tsx`, `NavigationBreadcrumbs.tsx`, and keyboard shortcut/help mappings if it should be globally navigable. |
| Tune LogFile page behavior | `frontend/src/pages/LogFilePage.tsx` & `frontend/src/services/logFileApi.ts` | Keep it read-only. `.zip` should open archive browsing mode; `.gz` should preview directly. |
| Tune HxRun Maintenance page behavior | `frontend/src/pages/MaintenancePage.tsx` & `frontend/src/services/hxrunMaintenanceApi.ts` | Keep this page separate from `MaintenanceDialog`; this page controls persistent HxRun blocking, not temporary DB restore windows. |
| Change the theme colors | `frontend/src/theme.ts` | Edit `palette.primary`, `secondary`, typography, etc. Rebuild so Material UI picks up the change. |
| Show maintenance banner globally | `App.tsx` | Use `<MaintenanceDialog />` (already included). If you need a static banner, add it under the AppBar conditioned on maintenance state. |
| Modify keyboard shortcuts | `frontend/src/components/KeyboardShortcutsHelp.tsx` & `useKeyboardNavigation` | Update the hook to include/exclude keybindings. Update the help dialog text. |
| Update footer or global announcements | Create a component (e.g., `<GlobalFooter />`) and render it at the bottom of `<App />` before closing the main `<Box>`. |

---

## 6. Passive vs Active Messaging

- **Passive surfaces** (dashboards, list views) should render inline warning cards with retry buttons. Keep messages inside the component and avoid popping modals for status updates.
- **Active flows** (password changes, destructive deletes) go through `ErrorAlert` / confirmation dialogs. These modals provide titles and explicit actions.
- **Consistency** – Reuse the shared red warning card styling (`borderColor: 'error.light', bgcolor: 'rgba(244, 67, 54, 0.08)'`) whenever you add a new passive warning.

---

## 7. Extending or Modifying Behaviour

### 6.1 Add route guards
1. Wrap restricted routes with a component that checks `user.role`.  
2. For example, define `<AdminRoute element={<AdminPage />} />` that returns `<Navigate to="/" />` if `user.role !== 'admin'`.  
3. Use it in the route definition:  
   ```jsx
   <Route path="/admin" element={<AdminRoute element={<AdminPage />} />} />
   ```

### 6.2 Support dark/light mode toggle
1. Store a theme preference in `localStorage` or React context.  
2. Update `theme.ts` to export both a light and dark theme.  
3. In `main.tsx`, wrap `<ThemeProvider>` with your own `ThemeModeProvider` that switches between the two.

### 6.3 Replace React Router with HashRouter (if hosting as static files)
1. Swap `BrowserRouter` for `HashRouter` in `main.tsx`.  
2. Adjust `buildApiUrl` if necessary (hash-based URLs may cause extra slashes).  
3. Confirm navigation works in the packaged app and in dev mode.

---

## 8. Quick Reference

| Piece | Purpose | Notes |
|-------|---------|-------|
| `main.tsx` | Entry point | Sets up providers and renders `<App />`. |
| `App.tsx` | Shell + routes | Guards on auth, builds navigation, includes global dialogs. |
| `loadComponent` | Lazy loader | Wraps `React.lazy` + `Suspense` for code splitting. |
| `MobileDrawer` | Mobile navigation | Controlled by `mobileDrawerOpen` state in `App.tsx`. |
| `MaintenanceDialog` | Maintenance alerts | Automatically shows when maintenance window is active. |
| `ChangePasswordDialog` | Force password update | Opens on login if `user.must_reset`. |

---

## 8. When Something Goes Wrong

1. **Blank page after login**  
   - Likely forgot to add a `<Route>` for the landing page or the route component throws an error. Check the console for stack traces. Ensure `Dashboard` is imported via `loadComponent`.

2. **Tabs highlight the wrong page**  
   - Update the `tabValue` computation. Nested paths require the `startsWith` check to match the parent tab.

3. **Mobile menu doesn’t open**  
   - Ensure `MobileMenuButton` calls `setMobileDrawerOpen(true)` and that `<MobileDrawer>` receives `open` and `onClose` props. MUI drawers are picky—leave them mounted outside the `<Toolbar>` like the current layout.

4. **Keyboard shortcuts not working**  
   - Check that `useKeyboardNavigation({ enabled: isAuthenticated })` is still called. If you changed provider order, make sure the hook still lives inside `AuthProvider`.

5. **Theme changes don’t apply**  
   - After editing `theme.ts`, restart Vite (or rebuild the packaged app). Material UI caches the theme; hot module reload usually works but not during some production builds.

Stick to this playbook and the main shell will stay tidy, predictable, and easy to extend.
