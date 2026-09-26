# Frontend Main Application Maintenance Guide

## Shared page layout and appearance (September 2026)

`PageLayout.tsx` supplies four PageContent variants: overview for dashboards,
inspection for viewers, spatial for labware and task for forms. The task variant
(and legacy `reading`) caps width at 1120px. Other variants use the available
content width. PageContent is the named `workspace` CSS container. App owns the
outer gutter (8px phone, 12px small desktop, 16px large desktop) and 56px account
header. Use one PageHeader; avoid another outer Container or breadcrumb row.

InspectionWorkspace allocates remaining viewport height, with a 320px minimum
that permits page scrolling on short screens. Collection/detail views switch at
900px of actual content width. The desktop selector starts at 300px, can resize
from 240–480px with dragging or arrow keys, and collapses from its divider. Keep
both sides mounted to preserve selection, scroll and drafts. Forms and overview
pages scroll as documents; they do not need to fill the window vertically.

Spatial pages need the equipment's geometry, not a mandatory list/detail layout.
Tip tracking keeps Col A and Col B and the configured rack order visible in its
deck overview, with a larger editor for accurate input. Preserve physical context
when narrowing the screen; use an overview and return path rather than stacking
or sorting physical columns. Never derive equipment coordinates from display
names unless the backend contract explicitly defines that mapping.

`AppearanceProvider` wraps the application and login. Its System/Light/Dark menu
stores `robotcontrol-appearance`, follows OS changes in System mode and syncs
between browser tabs. Storage failure falls back to an in-memory preference.
`index.html` sets the initial background before React mounts. `createAppTheme`
supplies semantic light/dark colors; do not hardcode light gray card surfaces or
black text. Theme changes update existing components without remounting them.
Desktop buttons remain compact; touch/coarse-pointer and narrow-screen controls
have 44px targets. Full-screen dialogs must bypass ordinary dialog margins.

Visible labels should identify content or the next action. Keep technical details
in Details, More or diagnostics. Keep permission limits, errors, unsaved changes,
recording and recovery state visible. Never replace unknown state with success.

### Adding a future page or tab

1. Choose one PageContent pattern and a single owner for its requests.
2. Register route/section labels and permissions in `navigation.tsx`, then add the
   guarded route to App. Breadcrumbs read the same registry.
3. Put primary actions in PageHeader or the content toolbar. Move secondary actions
   to More; retain a visible Find button when its field is collapsed.
4. State what persists through Back, resize, expansion and visited sections. Pass
   explicit active state to retained panels when requests should stop; hiding a
   component with CSS alone does not stop its effects.
5. Use semantic palette colors, labelled controls, keyboard operation and focus
   restoration. Do not shrink text or touch targets to make a layout fit.
6. Record failures before implementation and extend the browser E2E matrix. Save
   screenshots/traces for 320/390px phones and 1280/1920px desktops, light/dark,
   short screens and browser zoom. See `frontend/e2e/README.md`.

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
  Theme factory (palette, typography, component overrides), used by AppearanceProvider.

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
   - Wraps `<App />` with providers in this order: `<QueryClientProvider>` → `<BrowserRouter>` → `<AppearanceProvider>` (ThemeProvider, CssBaseline and Toaster) → `<App />`.

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

- `AuthProvider` (from `context/AuthContext.tsx`) – wraps AppContent inside `App.tsx`. Every component uses `useAuth()` to read user info and tokens.
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
| Add a new page (e.g., “Reports”) | `App.tsx`, navigation helpers | Create `frontend/src/pages/ReportsPage.tsx`, add `const ReportsPage = loadComponent(() => import('./pages/ReportsPage'));`, add its guarded `<Route>` and `navigation.tsx` entry, then update shortcut/help mappings if globally navigable. Breadcrumbs and AppSidebar use the shared registry. |
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
- **Consistency** – Use the shared MUI Alert and semantic palette colors for passive warnings in both appearances.

---

## 7. Extending or Modifying Behaviour

### 6.1 Add route guards
1. Wrap restricted routes with a component that checks `user.role`.  
2. For example, define `<AdminRoute element={<AdminPage />} />` that returns `<Navigate to="/" />` if `user.role !== 'admin'`.  
3. Use it in the route definition:  
   ```jsx
   <Route path="/admin" element={<AdminRoute element={<AdminPage />} />} />
   ```

### 6.2 Extend appearance
Use the existing `AppearanceProvider`, `AppearanceControl` and `createAppTheme`.
Do not create a second theme provider or preference key. Test System mode, explicit
Light/Dark, storage failure, reload and retained page state before adding options.

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
| `AppSidebar` | Desktop rail and mobile drawer | Uses `mobileDrawerOpen` and the shared navigation registry. |
| `MaintenanceDialog` | Maintenance alerts | Automatically shows when maintenance window is active. |
| `ChangePasswordDialog` | Force password update | Opens on login if `user.must_reset`. |

---

## 8. When Something Goes Wrong

1. **Blank page after login**  
   - Likely forgot to add a `<Route>` for the landing page or the route component throws an error. Check the console for stack traces. Dashboard is eagerly imported; other routes use `loadComponent`.

2. **Tabs highlight the wrong page**  
   - Check the section name and permission filtering in `navigation.tsx`, and the `section` query parameter.

3. **Mobile menu doesn’t open**  
   - Ensure the labelled Open navigation IconButton updates `mobileDrawerOpen`, and AppSidebar receives `open` and `onClose`.

4. **Keyboard shortcuts not working**  
   - Check that `useKeyboardNavigation({ enabled: isAuthenticated })` is still called. If you changed provider order, make sure the hook still lives inside `AuthProvider`.

5. **Theme changes don’t apply**  
   - After editing `theme.ts`, restart Vite (or rebuild the packaged app). Material UI caches the theme; hot module reload usually works but not during some production builds.

Stick to this playbook and the main shell will stay tidy, predictable, and easy to extend.


### September 2026: shared section navigation

`components/navigation.tsx` is the source of section names, URLs and UI permissions. Use `useModuleSection` and `moduleSectionUrl`; do not add another horizontal page tab bar. The sidebar supports expanded links, rail menus and mobile navigation. `SectionPanel` mounts on first visit and retains drafts/scroll within the page session. Components that poll must take an active flag and suspend their timer when hidden. Camera navigation never starts/stops a session. Database Restore remains admin **or** local; Operations remain local-only; RobotControl logs allow authenticated local users or remote administrators. Backend permissions still apply.
