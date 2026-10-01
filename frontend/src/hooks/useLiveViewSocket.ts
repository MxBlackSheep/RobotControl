import { useCallback, useEffect, useRef } from 'react';
import { buildWsUrl } from '@/utils/apiBase';

/** backend/services/streaming_session.py FRAME_HEADER: <BIdHH (version, sequence, time, width, height). */
const HEADER_BYTES = 17;
const FRAME_VERSION = 1;
const RECONNECT_MAX_MS = 30_000;

export type LiveViewState = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

/**
 * Owns the live-view WebSocket: binary frames, acknowledgements (the server sends at most two
 * unacknowledged frames, so a slow tunnel lowers the frame rate instead of queueing video),
 * pause while the tab is hidden, and automatic reconnection. The page owns the session API:
 * `reconnect` creates a new session and calls `connect`; it returns whether that worked.
 */
export function useLiveViewSocket(options: {
  showFrame: (url: string | null) => void;
  onState: (state: LiveViewState) => void;
  onError: (message: string) => void;
  reconnect: () => Promise<boolean>;
}) {
  const latest = useRef(options);
  latest.current = options;
  const socket = useRef<WebSocket | null>(null);
  const shownUrl = useRef<string | null>(null);
  const shownSequence = useRef(0);
  // The viewer wants live view: false after Stop or unmount, so nothing reconnects then.
  const wanted = useRef(false);
  const retryTimer = useRef<ReturnType<typeof setTimeout>>();
  const attempts = useRef(0);

  const send = (ws: WebSocket, type: string, parameters: Record<string, unknown> = {}) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type, parameters }));
  };

  const replaceFrame = useCallback((url: string | null) => {
    const previous = shownUrl.current;
    shownUrl.current = url;
    latest.current.showFrame(url);
    // The image element switches to the new URL first; release the old one afterwards.
    if (previous) setTimeout(() => URL.revokeObjectURL(previous), 1000);
  }, []);

  const detach = useCallback(() => {
    const ws = socket.current;
    socket.current = null;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
      ws.close();
    }
  }, []);

  const receiveFrame = async (ws: WebSocket, buffer: ArrayBuffer) => {
    if (buffer.byteLength <= HEADER_BYTES) return;
    const header = new DataView(buffer);
    if (header.getUint8(0) !== FRAME_VERSION) return;
    const sequence = header.getUint32(1, true);
    const url = URL.createObjectURL(new Blob([buffer.slice(HEADER_BYTES)], { type: 'image/jpeg' }));
    try {
      // Decode off-screen so the visible image never shows a half-loaded frame.
      const image = new Image();
      image.src = url;
      await image.decode();
    } catch {
      URL.revokeObjectURL(url);
      send(ws, 'ack', { sequence });
      return;
    }
    send(ws, 'ack', { sequence });
    // Frames from a replaced socket, or older than the one shown, are dropped.
    if (socket.current !== ws || sequence <= shownSequence.current) {
      URL.revokeObjectURL(url);
      return;
    }
    shownSequence.current = sequence;
    replaceFrame(url);
  };

  const scheduleReconnect = useCallback(() => {
    clearTimeout(retryTimer.current);
    if (!wanted.current) return;
    latest.current.onState('reconnecting');
    if (!navigator.onLine) return; // the 'online' listener resumes
    const base = Math.min(RECONNECT_MAX_MS, 1000 * 2 ** attempts.current);
    attempts.current += 1;
    retryTimer.current = setTimeout(async () => {
      if (!wanted.current || socket.current) return;
      const connected = await latest.current.reconnect();
      if (!connected && wanted.current && !socket.current) scheduleReconnect();
    }, base * (0.75 + Math.random() * 0.5));
  }, []);

  const connect = useCallback((sessionId: string) => {
    wanted.current = true;
    clearTimeout(retryTimer.current);
    detach();
    shownSequence.current = 0;
    const ws = new WebSocket(buildWsUrl(`/api/camera/streaming/video/${sessionId}`));
    ws.binaryType = 'arraybuffer';
    socket.current = ws;
    latest.current.onState('connecting');
    ws.onopen = () => {
      if (socket.current !== ws) return;
      attempts.current = 0;
      latest.current.onState('connected');
      if (document.visibilityState === 'hidden') send(ws, 'pause');
    };
    ws.onmessage = (event) => {
      if (socket.current !== ws) return;
      if (event.data instanceof ArrayBuffer) {
        void receiveFrame(ws, event.data);
        return;
      }
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'error') latest.current.onError(message.error || 'Streaming error');
      } catch {
        /* Status messages are informational. */
      }
    };
    ws.onclose = () => {
      if (socket.current !== ws) return;
      socket.current = null;
      // Keep the last image: its freshness label turns stale while reconnecting.
      latest.current.onState('disconnected');
      scheduleReconnect();
    };
  }, [detach, scheduleReconnect]);

  /** Close the socket but keep the last image (a manual reconnect replaces the session). */
  const close = useCallback(() => {
    clearTimeout(retryTimer.current);
    detach();
  }, [detach]);

  /** The viewer stopped live view: no reconnection, no image. */
  const stop = useCallback(() => {
    wanted.current = false;
    close();
    replaceFrame(null);
  }, [close, replaceFrame]);

  useEffect(() => {
    const visibility = () => {
      const ws = socket.current;
      if (ws) send(ws, document.visibilityState === 'hidden' ? 'pause' : 'resume');
    };
    const online = () => {
      if (wanted.current && !socket.current) {
        attempts.current = 0;
        scheduleReconnect();
      }
    };
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('online', online);
    return () => {
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('online', online);
      stop();
    };
  }, [scheduleReconnect, stop]);

  return { connect, close, stop };
}
