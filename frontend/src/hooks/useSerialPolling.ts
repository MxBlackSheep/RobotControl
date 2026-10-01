import { useCallback, useEffect, useRef, useState } from 'react';

// A response that never arrives would otherwise hold the single request slot
// forever: no further polls, Refresh disabled and a stale "connected" state.
const REQUEST_DEADLINE_MS = 20000;

/**
 * One request and timer per owner. Hidden tabs keep the same refresh policy (status must not
 * go stale on purpose), but browsers throttle their timers, so returning to the tab or
 * regaining the network refreshes at once instead of waiting for the next tick.
 */
export function useSerialPolling<T>(options: {
  request: (signal: AbortSignal) => Promise<T>;
  onSuccess: (value: T) => void;
  interval: number;
  retryInterval?: number;
  maxRetries?: number;
  enabled?: boolean;
  identity?: string | null;
  deadline?: number;
}) {
  const latest = useRef(options);
  latest.current = options;
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const controller = useRef<AbortController>();
  const flight = useRef<Promise<void>>();
  const generation = useRef(0);
  const running = useRef(false);
  const failures = useRef(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retries, setRetries] = useState(0);
  const [active, setActive] = useState(false);
  const [succeeded, setSucceeded] = useState(false);

  const refresh = useCallback((): Promise<void> => {
    if (flight.current) return flight.current;
    clearTimeout(timer.current);
    const epoch = generation.current;
    const abort = new AbortController();
    controller.current = abort;
    setPending(true);
    // stop() advances the generation, so it also discards this result.
    const current = () => epoch === generation.current;
    const request = latest.current.request;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    const expired = new Promise<never>((_, reject) => {
      deadline = setTimeout(() => {
        abort.abort();
        reject(new Error('Request timed out'));
      }, latest.current.deadline ?? REQUEST_DEADLINE_MS);
    });
    const operation = Promise.race([Promise.resolve().then(() => request(abort.signal)), expired])
      .then(value => {
        if (!current()) return;
        latest.current.onSuccess(value);
        setSucceeded(true);
        failures.current = 0;
        setRetries(0);
        setError(null);
      }).catch(cause => {
        if (!current()) return;
        failures.current += 1;
        setSucceeded(false);
        setRetries(failures.current);
        setError(cause instanceof Error ? cause.message : 'Request failed');
      }).finally(() => {
        clearTimeout(deadline);
        if (!current()) return;
        flight.current = undefined;
        controller.current = undefined;
        setPending(false);
        const config = latest.current;
        if (running.current && config.interval > 0 && failures.current < (config.maxRetries ?? Infinity)) {
          timer.current = setTimeout(() => { void refresh(); },
            failures.current ? (config.retryInterval ?? config.interval) : config.interval);
        }
      });
    flight.current = operation;
    return operation;
  }, []);

  const stop = useCallback(() => {
    running.current = false;
    setActive(false);
    setSucceeded(false);
    setPending(false);
    generation.current += 1;
    clearTimeout(timer.current);
    controller.current?.abort();
    controller.current = undefined;
    flight.current = undefined;
  }, []);

  const start = useCallback(() => {
    running.current = true;
    setActive(true);
    failures.current = 0;
    setRetries(0);
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (options.enabled !== false) start();
    return stop;
  }, [options.enabled, options.identity, start, stop]);

  useEffect(() => {
    // refresh() joins a request already in flight, so this never adds a second owner.
    const resume = () => { if (running.current && document.visibilityState === 'visible') void refresh(); };
    document.addEventListener('visibilitychange', resume);
    window.addEventListener('online', resume);
    return () => {
      document.removeEventListener('visibilitychange', resume);
      window.removeEventListener('online', resume);
    };
  }, [refresh]);

  useEffect(() => {
    clearTimeout(timer.current);
    if (running.current && !flight.current && options.interval > 0
        && failures.current < (options.maxRetries ?? Infinity)) {
      timer.current = setTimeout(() => { void refresh(); },
        failures.current ? (options.retryInterval ?? options.interval) : options.interval);
    }
  }, [options.interval, options.retryInterval, options.maxRetries, refresh]);

  const resetError = useCallback(() => setError(null), []);
  return { refresh, start, stop, pending, error, retries, active, succeeded, resetError };
}
