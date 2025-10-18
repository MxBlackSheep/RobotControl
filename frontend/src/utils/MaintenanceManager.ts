type Listener = (state: MaintenanceState) => void;

export interface MaintenanceState {
  active: boolean;
  expiresAt?: number;
  reason?: string;
}

let currentState: MaintenanceState = { active: false };
const listeners = new Set<Listener>();
let intervalHandle: ReturnType<typeof setInterval> | null = null;

const notifyListeners = () => {
  listeners.forEach((listener) => listener(currentState));
};

const stopInterval = () => {
  if (intervalHandle) {
    clearInterval(intervalHandle);
    intervalHandle = null;
  }
};

const startInterval = () => {
  if (intervalHandle) {
    return;
  }

  intervalHandle = setInterval(() => {
    if (!currentState.active || !currentState.expiresAt) {
      stopInterval();
      return;
    }

    if (Date.now() >= currentState.expiresAt) {
      clearMaintenance();
    } else {
      notifyListeners();
    }
  }, 1000);
};

const setState = (state: MaintenanceState) => {
  currentState = state;
  if (currentState.active) {
    startInterval();
  } else {
    stopInterval();
  }
  notifyListeners();
};

export const activateMaintenance = (durationMs: number, reason?: string) => {
  const expiresAt = Date.now() + Math.max(durationMs, 0);
  setState({
    active: true,
    expiresAt,
    reason,
  });
};

export const clearMaintenance = () => {
  if (!currentState.active) {
    return;
  }
  setState({ active: false });
};

export const isMaintenanceActive = (): boolean => currentState.active;

export const getMaintenanceRemainingMs = (): number => {
  if (!currentState.active || !currentState.expiresAt) {
    return 0;
  }
  return Math.max(currentState.expiresAt - Date.now(), 0);
};

export const getMaintenanceReason = (): string | undefined => currentState.reason;

export const subscribeToMaintenance = (listener: Listener): (() => void) => {
  listeners.add(listener);
  listener(currentState);
  return () => {
    listeners.delete(listener);
  };
};
