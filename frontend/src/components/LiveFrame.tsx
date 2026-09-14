import React, { useEffect, useState, useSyncExternalStore } from 'react';
import { Box, BoxProps } from '@mui/material';

/** A single current image shared by normal/fullscreen views, with no history. */
export function createFrameStore() {
  let frame: string | null = null;
  let received: number | null = null;
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => frame,
    getLastReceived: () => received,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    set: (value: string | null) => {
      // Identical images still count as received frames; no scene-change detector.
      received = value ? performance.now() : null;
      if (value === frame) return;
      frame = value;
      listeners.forEach(listener => listener());
    },
  };
}

export function FrameFreshness({ store }: { store: FrameStore }) {
  const [label, setLabel] = useState('Waiting for frames');
  useEffect(() => {
    const refresh = () => {
      const last = store.getLastReceived();
      setLabel(last === null ? 'Waiting for frames' : performance.now() - last >= 10000
        ? 'Stale image — no new frames for 10 seconds' : 'Live view receiving frames');
    };
    refresh();
    const timer = setInterval(refresh, 1000);
    return () => clearInterval(timer);
  }, [store]);
  return <Box role="status" sx={{ position: 'absolute', bottom: 8, left: 8, right: 8, zIndex: 2,
    bgcolor: 'rgba(0,0,0,.8)', color: label.startsWith('Stale') ? '#ffcc80' : 'white',
    px: 1, py: .5, borderRadius: 1, pointerEvents: 'none' }}>{label}</Box>;
}

export type FrameStore = ReturnType<typeof createFrameStore>;

export default function LiveFrame({ store, ...props }: BoxProps<'img'> & { store: FrameStore }) {
  const source = useSyncExternalStore(store.subscribe, store.getSnapshot);
  return <Box component="img" {...props} src={source ?? undefined} />;
}
