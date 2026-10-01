import { useSyncExternalStore } from 'react';

/**
 * Classifies a failed request so screens can tell a RobotControl answer from a
 * broken connection. Remote use goes through a Cloudflare tunnel: its error pages
 * (403 challenges, 502/52x) are HTML, not RobotControl JSON, and must never be read
 * as "wrong password" or "signed out".
 */
export type RequestErrorKind =
  | 'offline' // the device reports no network
  | 'unreachable' // no response at all (DNS, tunnel down, CORS on a proxy redirect)
  | 'timeout' // no answer in time; a write may still have completed
  | 'proxy' // a response that did not come from RobotControl
  | 'unauthorized' // RobotControl rejected the sign-in
  | 'local-only' // RobotControl allows this only on its own computer
  | 'forbidden'
  | 'conflict'
  | 'app'
  | 'cancelled';

const CONNECTION_KINDS = new Set<RequestErrorKind>(['offline', 'unreachable', 'timeout', 'proxy']);

/** RobotControl answers with FastAPI `{detail}` or ResponseFormatter `{error: {message}}`. */
export function isAppResponse(error: any): boolean {
  const data = error?.response?.data;
  return !!data && typeof data === 'object' && ('detail' in data || 'error' in data || 'success' in data);
}

export function appErrorMessage(error: any): string | undefined {
  const data = error?.response?.data;
  if (!isAppResponse(error)) return undefined;
  if (typeof data.detail === 'string') return data.detail;
  if (typeof data.error?.message === 'string') return data.error.message;
  if (typeof data.message === 'string') return data.message;
  return undefined;
}

export function classifyRequestError(error: any): RequestErrorKind {
  if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED' || error?.name === 'AbortError') return 'cancelled';
  if (error?.code === 'ECONNABORTED' || error?.code === 'ETIMEDOUT') return 'timeout';
  const response = error?.response;
  if (!response) return typeof navigator !== 'undefined' && navigator.onLine === false ? 'offline' : 'unreachable';
  if (!isAppResponse(error)) return 'proxy';
  if (response.status === 401) return 'unauthorized';
  // require_local_access (backend/api/dependencies.py) and the log-source rule word it this way.
  if (response.status === 403) return /local network access required|local session is required/i.test(appErrorMessage(error) ?? '') ? 'local-only' : 'forbidden';
  if (response.status === 409) return 'conflict';
  return 'app';
}

export const isConnectionProblem = (kind: RequestErrorKind) => CONNECTION_KINDS.has(kind);

/** RobotControl itself rejected the sign-in; a proxy page or outage never does. */
export const isSignInRejected = (error: any) => {
  const status = error?.response?.status;
  return (status === 401 || status === 403) && isAppResponse(error);
};

export function connectionMessage(error: any): string | undefined {
  switch (classifyRequestError(error)) {
    case 'offline': return 'This device is offline. Try again when it reconnects.';
    case 'unreachable': return "Can't reach RobotControl. Check the connection and try again.";
    case 'timeout': return 'RobotControl did not answer in time. It may still finish; refresh before trying again.';
    case 'proxy': return `The connection to RobotControl was interrupted${error?.response?.status ? ` (${error.response.status})` : ''}. Try again shortly.`;
    default: return undefined;
  }
}

/** RobotControl's own message, else a connection explanation, else the caller's fallback. */
export function requestErrorMessage(error: any, fallback: string): string {
  return appErrorMessage(error) ?? connectionMessage(error) ?? fallback;
}

// ---- Connection state: one owner (the api client) records outcomes; screens only read. ----

type ConnectionState = { online: boolean; failing: boolean; since: number | null };
let state: ConnectionState = { online: typeof navigator === 'undefined' ? true : navigator.onLine, failing: false, since: null };
const listeners = new Set<() => void>();
const set = (next: ConnectionState) => {
  if (next.online === state.online && next.failing === state.failing) return;
  state = next;
  listeners.forEach((listener) => listener());
};

export function recordRequestSuccess() {
  set({ online: true, failing: false, since: null });
}

export function recordRequestFailure(error: any) {
  if (isConnectionProblem(classifyRequestError(error))) set({ ...state, failing: true, since: state.since ?? Date.now() });
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => set({ ...state, online: true }));
  window.addEventListener('offline', () => set({ ...state, online: false, since: state.since ?? Date.now() }));
}

const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export const useConnectionState = () => useSyncExternalStore(subscribe, () => state, () => state);
