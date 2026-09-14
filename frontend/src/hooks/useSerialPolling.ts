import { useCallback, useEffect, useRef, useState } from 'react';

/** One request and timer per owner. Visibility never changes the refresh policy. */
export function useSerialPolling<T>(options: {
  request: (signal: AbortSignal) => Promise<T>;
  onSuccess: (value: T) => void;
  interval: number;
  retryInterval?: number;
  maxRetries?: number;
  enabled?: boolean;
  identity?: string | null;
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

  const refresh = useCallback((): Promise<void> => {
    if (flight.current) return flight.current;
    clearTimeout(timer.current);
    const epoch = generation.current;
    const abort = new AbortController();
    controller.current = abort;
    setPending(true);
    const current = () => epoch === generation.current && !abort.signal.aborted;
    const request = latest.current.request;
    const operation = Promise.resolve().then(() => request(abort.signal))
      .then(value => {
        if (!current()) return;
        latest.current.onSuccess(value);
        failures.current = 0;
        setRetries(0);
        setError(null);
      }).catch(cause => {
        if (!current()) return;
        failures.current += 1;
        setRetries(failures.current);
        setError(cause instanceof Error ? cause.message : 'Request failed');
      }).finally(() => {
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
    clearTimeout(timer.current);
    if (running.current && !flight.current && options.interval > 0
        && failures.current < (options.maxRetries ?? Infinity)) {
      timer.current = setTimeout(() => { void refresh(); },
        failures.current ? (options.retryInterval ?? options.interval) : options.interval);
    }
  }, [options.interval, options.retryInterval, options.maxRetries, refresh]);

  const resetError = useCallback(() => setError(null), []);
  return { refresh, start, stop, pending, error, retries, active, resetError };
}
