import { useEffect, useState } from 'react';
import { useSerialPolling } from '../../hooks/useSerialPolling';

/** Keep the last good snapshot; hidden pages and unsaved edits suspend reads. */
export function useLabwareSnapshot<T extends { auto_refresh_ms: number }>(read: () => Promise<T>, active: boolean, paused: boolean, validate: (value: T) => boolean) {
  const [snapshot, setSnapshot] = useState<T | null>(null);
  useEffect(() => {
    if (!paused) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [paused]);
  const polling = useSerialPolling({
    request: async () => {
      try {
        const value = await read();
        if (!validate(value)) throw new Error('Labware data unavailable. Retry.');
        return value;
      }
      catch (cause: any) { throw new Error(cause?.response?.data?.error?.message || cause?.response?.data?.message || cause?.message || 'Unable to load labware.'); }
    },
    onSuccess: setSnapshot,
    interval: Math.max(1000, snapshot?.auto_refresh_ms || 15000),
    enabled: active && !paused,
  });
  return { snapshot, setSnapshot, ...polling };
}
