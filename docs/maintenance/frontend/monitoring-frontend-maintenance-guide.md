# Frontend Monitoring Maintenance Guide

Use this whenever you change the real-time monitoring dashboard or WebSocket logic. It explains how the React hook, components, and status banners fit together so you do not accidentally kill live telemetry.

---

## 1. High-Level Architecture

- `frontend/src/hooks/useMonitoring.ts`  
  Core hook. Opens the monitoring WebSocket, fetches REST fallbacks, and normalises data into a single `MonitoringData` object.

- `frontend/src/components/MonitoringDashboard.tsx`  
  Main dashboard cards (CPU/memory/disk usage, connection chips, manual refresh/reconnect buttons).

- `frontend/src/components/SystemStatus.tsx`  
  Secondary status panel with experiment summary, database info, and streaming status (used on Monitoring page and other dashboards).

- `frontend/src/pages/MonitoringPage.tsx`  
  Page wrapper. Renders `MonitoringDashboard` and `SystemStatus`, shows the user role chip.

- `frontend/src/utils/apiBase.ts` (`buildApiUrl`, `buildWsUrl`)  
  Converts relative paths into full HTTP/WS URLs so the hook works in dev and packaged modes.

**Rule of thumb:** Always fetch through `useMonitoring`. Components should never open their own WebSockets—otherwise you will spawn duplicate connections and double load the backend.

---

## 2. Data Flow Cheat Sheet

1. **Hook initialisation (`useMonitoring`)**  
   - If the user is authenticated (`token` from `AuthContext`), it tries to open `ws://…/api/monitoring/ws/general`.  
   - While the socket connects, it also calls REST fallbacks (`/api/monitoring/experiments`, `/api/monitoring/system-health`, `/api/camera/streaming/status`) to populate state.

2. **Incoming WebSocket messages**  
   - `type: "current_data"` → sets `monitoringData`, `experiments`, `systemHealth`, etc.  
   - `type: "experiments_update"` / `"system_health"` / `"database_performance"` → updates respective slices.  
   - `type: "pong"` → keeps connection metadata alive.

3. **Reconnection logic**  
   - The hook tracks `connectionRetries`. On failure it waits `RETRY_DELAY` (2s) and tries again up to `MAX_RETRIES` (5).  
   - After exhausting retries it stops auto-reconnecting; the dashboard exposes a manual “Reconnect” button.

4. **Manual refresh**  
   - `refreshData()` hits the REST endpoints again. Used when the socket is down or a user wants the latest stats immediately.

5. **Cleanup**  
   - On unmount (or when the token disappears) the hook closes the socket and clears polling intervals.

---

## 3. Key State Exposed by the Hook

- `monitoringData` – Combined payload (experiments, system health, database status, streaming status).  
- `experiments` – Normalised array of experiments with `id`, `method_name`, `status`, `progress`.  
- `systemHealth` – CPU/memory/disk metrics with timestamp.  
- `databaseStatus` – Connection info, server name, error message.  
- `streamingStatus` – Field derived from `/api/camera/streaming/status`.  
- `isConnected` – Boolean flag for WebSocket state.  
- `isLoading` – True during initial fetch or manual refresh.  
- `error` – String description of the latest failure.  
- `connectionRetries` – Number of reconnection attempts so the UI can show progress.

Actions returned by the hook:

- `connect()` / `disconnect()` – manual WebSocket control.  
- `refreshData()` – re-fetch REST data.  
- `resetError()` – clears `error` before retrying actions.

---

## 4. Working With the Dashboard Components

1. **Always pass the hook output directly.**  
   ```tsx
   const monitoring = useMonitoring();
   <MonitoringDashboard {...monitoring} />;
   ```
   `MonitoringDashboard` destructures what it needs; you don’t have to pick specific fields unless you only need a subset.

2. **Use memoisation carefully.** The dashboard memoises metric cards and status calculations (via `useMemo`). Keep that pattern if you add new cards to avoid unnecessary re-renders whenever the socket emits a frame.

3. **Render clear fallback states.**  
   - When `isLoading` is true, show `<LoadingSpinner />`.  
   - When `error` is set, display the inline warning cards baked into `MonitoringDashboard` / `SystemStatus` (headline + retry button). Reserve modal alerts for destructive actions only.

4. **Respect responsive design.** `MonitoringDashboard` and `SystemStatus` rely on MUI’s responsive props (`sx` with `{ xs: …, md: … }`). Mirror that style for new elements so the layout still works on tablets.

---

## 5. Common Maintenance Tasks

| Task | Where | Instructions |
|------|-------|--------------|
| Add a new system metric (e.g., GPU usage) | `useMonitoring` + `MonitoringDashboard` | Extend `system_health` in the backend, map the new field in the hook, and add a `ProgressCard` to display it. |
| Display experiment details | `MonitoringDashboard` or a new component | Use `monitoringData.experiments` to render a table/list. Include a fallback when the array is empty. |
| Show streaming service status | `SystemStatus` | The hook already exposes `streamingStatus`; render additional chips for `active_session_count`, etc. |
| Increase retry attempts | `useMonitoring` constants | Change `MAX_RETRIES` or `RETRY_DELAY`. Update the dashboard text so users know what to expect. |
| Link to specific pages from the dashboard | `MonitoringDashboard` buttons | Use `useNavigate()` in `MonitoringPage` and pass handlers down; on click, navigate to `/camera` or `/database`. |

---

## 6. Passive vs Active Messaging

- **Dashboard cards stay passive.** Errors in `MonitoringDashboard` and `SystemStatus` are rendered as inline warning cards with retry buttons. Follow the same design for any new widgets so the page does not pop a modal for status updates.
- **Reserve modals for state-changing actions.** Only confirmation-heavy actions (e.g., enabling maintenance mode) should open dialogs. Refresh/reconnect flows belong inside the card.
- **Reuse the shared styling.** Inline warnings use the red-outlined card (`borderColor: 'error.light', bgcolor: 'rgba(244, 67, 54, 0.08)'`). Keep that aesthetic for consistency.

---

## 7. Extending or Modifying Behaviour

### 6.1 Separate WebSocket channels
1. The hook currently connects to `/ws/general`. To support dedicated channels (e.g., `/ws/experiments`), add a parameter to the hook so callers can choose a channel.  
2. Update `getWebSocketUrl()` to include the channel.  
3. Adjust message parsing if the payload shape differs per channel.

### 6.2 Persist monitoring preferences
1. Store UI settings (e.g., preferred metric cards) in `localStorage` inside the hook or component.  
2. On mount, read the stored value and apply it to the component state (e.g., show/hide certain cards).

### 6.3 Integrate toast notifications for alerts
1. In the hook, when `systemHealth` crosses a threshold, call a toast (e.g., `toast.error('CPU > 95%')`).  
2. Debounce notifications so they don’t spam users (compare the previous value before showing a new toast).

---

## 8. Quick Reference

| Function / Component | Purpose | Notes |
|----------------------|---------|-------|
| `useMonitoring()` | Handles WebSocket + REST data | Requires access token; returns data + control actions. |
| `monitoring.connect()` | Reconnect WebSocket manually | Use when a user clicks "Reconnect". |
| `monitoring.refreshData()` | Fetch REST data | Safe to call even when WebSocket is active. |
| `MonitoringDashboard` | Shows core metrics | Expects the full hook return value as props. |
| `SystemStatus` | Compact status summary | Props allow toggling sections (`showExperiments`, `compact`, etc.). |
| `buildWsUrl('/api/monitoring/ws/general')` | Constructs WebSocket URL | Uses `window.location` to adapt to packaged builds. |

---

## 9. When Something Goes Wrong

1. **Dashboard stuck on “Loading…”**  
   - Check network tab for `/api/monitoring/system-health` and `/api/monitoring/experiments`. If they fail, the hook never sets `isLoading=false`. Display the error so the user can retry.

2. **WebSocket disconnects immediately**  
   - Browser console will show a close code. Confirm the backend websocket route is accessible and that the user has a valid token. If you changed the channel string, update `getWebSocketUrl`.

3. **Data updates but UI doesn’t**  
   - Ensure you call `setMonitoringData` or `setSystemHealth` inside the hook when new messages arrive. Missing `setState` calls leave the UI frozen.

4. **High CPU usage in the browser**  
   - Excessive re-renders usually mean you removed `useMemo` or `memo` wrappers. Restore them around heavy components (`ProgressCard`, derived metric arrays).

5. **Streaming status shows `null` forever**  
   - The hook swallows errors from `/api/camera/streaming/status`. Check logs for warnings (“Failed to parse streaming status response”). Fix the backend response shape or guard the UI to handle missing data.

Stick to this playbook and the monitoring dashboard will remain reliable, even under heavy load.
