import React, { useSyncExternalStore } from 'react';
import { Box, BoxProps } from '@mui/material';

/** A single current image shared by normal/fullscreen views, with no history. */
export function createFrameStore() {
  let frame: string | null = null;
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => frame,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    set: (value: string | null) => {
      if (value === frame) return;
      frame = value;
      listeners.forEach(listener => listener());
    },
  };
}

export type FrameStore = ReturnType<typeof createFrameStore>;

export default function LiveFrame({ store, ...props }: BoxProps<'img'> & { store: FrameStore }) {
  const source = useSyncExternalStore(store.subscribe, store.getSnapshot);
  return <Box component="img" {...props} src={source ?? undefined} />;
}
