/**
 * The pause after a successful database restore: until it ends, the browser refuses its own
 * requests (services/api.ts) unless they carry X-Allow-Maintenance. One value owns it: the time
 * the pause ends. Each restore sets a new end time, so a dismissed dialog shows again.
 */
let expiresAt = 0;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach(listener => listener());

export const activateMaintenance = (durationMs: number) => {
  expiresAt = Date.now() + Math.max(durationMs, 0);
  notify();
};

export const clearMaintenance = () => {
  if (expiresAt === 0) return;
  expiresAt = 0;
  notify();
};

export const getMaintenanceExpiry = () => expiresAt;

export const isMaintenanceActive = () => Date.now() < expiresAt;

export const subscribeToMaintenance = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};
