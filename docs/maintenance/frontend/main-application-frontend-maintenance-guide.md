# Frontend Main Application Maintenance Guide

This guide explains the overall React shell: routing, theming, providers, and navigation. Use it whenever you change layout, add new pages, or adjust global providers. It spells everything out so you can’t get lost.

---

## 1. High-Level Architecture

- `frontend/src/main.tsx`  
  App entry point. Wraps `<App />` with React Router (`BrowserRouter`), Material UI theme provider, React Query client, and `react-hot-toast`.

- `frontend/src/App.tsx`  
  Defines the navigation shell. Handles authentication gating, top app bar, tabs, mobile drawer, password change dialog, and route rendering via `<Routes>`.

- `frontend/src/theme.ts`  
  Central Material UI theme (palette, typography, component overrides). Imported by `main.tsx`.

- `frontend/src/utils/BundleOptimizer.ts` (`loadComponent`)  
  Lazy-load helper for page components (Database, Camera, Monitoring, etc.) to keep the initial bundle small.

- Shared UI components used globally:
  - `NavigationBreadcrumbs` – renders breadcrumb trail.
  - `MobileDrawer` – collapsible nav on small screens.
  - `SkipLink`, `KeyboardShortcutsHelp` – accessibility helpers.
  - `MaintenanceDialog` – warns users during backend maintenance windows.

**Rule of thumb:** All new pages should be registered in `App.tsx` (both the `Routes` block and, if appropriate, the navigation tabs). Ensure they sit inside `AuthProvider` so they can access user data.

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
   - Desktop navigation: `<Tabs>` linked to the route list.  
   - Mobile navigation: `<MobileDrawer>`, toggled by `MobileMenuButton`.  
   - `Routes` inside `<Suspense fallback={<PageLoading />}>` so lazy pages show a spinner while loading.

4. **Route definitions**  
   - `'/'` → `Dashboard`  
   - `/database`, `/camera`, `/system-status`, `/scheduling`, `/admin`, `/about` (lazy-loaded).  
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
| Add a new page (e.g., “Reports”) | `App.tsx`, `BundleOptimizer.ts` | Create `frontend/src/pages/ReportsPage.tsx`, add `const ReportsPage = loadComponent(() => import('./pages/ReportsPage'));`, add a `<Route>` and tab item. |
| Change the theme colors | `frontend/src/theme.ts` | Edit `palette.primary`, `secondary`, typography, etc. Rebuild so Material UI picks up the change. |
| Show maintenance banner globally | `App.tsx` | Use `<MaintenanceDialog />` (already included). If you need a static banner, add it under the AppBar conditioned on maintenance state. |
| Modify keyboard shortcuts | `frontend/src/components/KeyboardShortcutsHelp.tsx` & `useKeyboardNavigation` | Update the hook to include/exclude keybindings. Update the help dialog text. |
| Update footer or global announcements | Create a component (e.g., `<GlobalFooter />`) and render it at the bottom of `<App />` before closing the main `<Box>`. |

---

## 6. Extending or Modifying Behaviour

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

## 7. Quick Reference

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

