import { useEffect, useRef, useState } from 'react';
import { Box, BoxProps } from '@mui/material';

/**
 * The single current decoded frame shared by normal/fullscreen views, with no history. The store
 * owns it: replacing or clearing a frame closes the previous one (a decoder stalls when its
 * frames are not released).
 */
export function createFrameStore() {
  let frame: VideoFrame | null = null;
  let received: number | null = null;
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => frame,
    getLastReceived: () => received,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    set: (value: VideoFrame | null) => {
      // Identical images still count as received frames; no scene-change detector.
      received = value ? performance.now() : null;
      if (value === frame) return;
      const previous = frame;
      frame = value;
      // Listeners draw synchronously, so the previous frame is no longer needed afterwards.
      listeners.forEach(listener => listener());
      previous?.close();
    },
  };
}

export function FrameFreshness({ store, inline = false }: { store: FrameStore; inline?: boolean }) {
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
  return <Box role="status" sx={{ ...(inline ? { position: 'relative' } : { position: 'absolute', bottom: 8, left: 8, right: 8, zIndex: 2 }),
    bgcolor: inline ? 'transparent' : 'rgba(0,0,0,.8)',
    color: inline ? (label.startsWith('Stale') ? 'warning.dark' : 'text.secondary') : (label.startsWith('Stale') ? '#ffcc80' : 'white'),
    px: inline ? 0 : 1, py: .5, borderRadius: 1, pointerEvents: 'none', fontSize: '0.8125rem' }}>{label}</Box>;
}

export type FrameStore = ReturnType<typeof createFrameStore>;

/**
 * Draws the store's current frame on a canvas as each one arrives (no React render per frame).
 * `onDimensions` reports the frame size when it changes.
 */
export default function LiveFrame({ store, label, onDimensions, ...props }: BoxProps<'canvas'> & {
  store: FrameStore;
  label: string;
  onDimensions?: (width: number, height: number) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const reportDimensions = useRef(onDimensions);
  reportDimensions.current = onDimensions;
  useEffect(() => {
    const draw = () => {
      const frame = store.getSnapshot();
      const element = canvas.current;
      if (!frame || !element) return;
      const { displayWidth: width, displayHeight: height } = frame;
      if (element.width !== width || element.height !== height) {
        element.width = width;
        element.height = height;
        reportDimensions.current?.(width, height);
      }
      element.getContext('2d')?.drawImage(frame, 0, 0, width, height);
    };
    draw();
    return store.subscribe(draw);
  }, [store]);
  return <Box component="canvas" ref={canvas} role="img" aria-label={label} {...props} />;
}
