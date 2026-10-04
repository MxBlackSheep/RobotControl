import { useCallback, useEffect, useRef, useState } from 'react';
import { buildWsUrl } from '@/utils/apiBase';

/** backend/services/streaming_session.py FRAME_HEADER: <BIdHHB (version, sequence, time, width, height, flags). */
const HEADER_BYTES = 18;
const FRAME_VERSION = 2;
const FLAG_KEYFRAME = 1;
/** backend/services/h264_encoder.py encodes H.264 Constrained Baseline; level 3.1 covers 640×480. */
const H264_CODEC = 'avc1.42E01F';
const RECONNECT_MAX_MS = 30_000;
// streaming_session.py ends a session silent for 75 s; Cloudflare closes idle sockets at ~100 s.
const KEEPALIVE_MS = 30_000;
/**
 * Show frames evenly spaced by their capture times instead of as they arrive: a long link
 * delivers them in bursts (freeze, then a quick catch-up). Costs the recent jitter in delay, at
 * most MAX_DELAY_MS. false shows each frame as soon as it is decoded, as before October 2026.
 */
const PLAYOUT_BUFFER = true;
const JITTER_FRAMES = 90; // 6 s at 15 fps
const MAX_DELAY_MS = 300;
// Share of the gap to the target delay closed per frame: up within about a second, down over
// several, so one quiet second does not undo the delay a bursty link needs.
const DELAY_RISE = 0.1;
const DELAY_FALL = 0.02;
const MAX_HELD = 8;
// Held frames pin the decoder's output buffers. Hardware decoders have small fixed pools and stall
// when they run out, so with the buffer live view asks for software decoding first (640×480
// Constrained Baseline is a few ms a frame); a browser that refuses it uses the default.
const DECODER_CONFIGS: VideoDecoderConfig[] = [
  ...(PLAYOUT_BUFFER ? [{ codec: H264_CODEC, optimizeForLatency: true, hardwareAcceleration: 'prefer-software' as const }] : []),
  { codec: H264_CODEC, optimizeForLatency: true },
];
/** The first of DECODER_CONFIGS this browser supports, chosen by liveViewUnsupportedReason. */
let decoderConfig = DECODER_CONFIGS[DECODER_CONFIGS.length - 1];

export type LiveViewState = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

/**
 * A decoder for one socket and frame size; `received` is the newest sequence given to it and
 * `captured` the capture times (Unix ms) of frames it has not output yet.
 */
type Decoding = { decoder: VideoDecoder; size: string; received: number; captured: Map<number, number> };

/**
 * Holds decoded frames until capture time + offset + delay. The offset is the smallest
 * (arrival − capture) over the last JITTER_FRAMES, so server/browser clock skew cancels; the delay
 * follows the p95 of the arrival jitter above it, clamped to MAX_DELAY_MS. A frame already past
 * its time is shown at once, so none waits longer than the delay. On each animation frame only
 * the newest due frame is shown; older due ones are closed unshown. Every held frame is closed
 * exactly once, by `show`'s owner or here.
 */
function createPlayout(show: (frame: VideoFrame) => void) {
  let held: { frame: VideoFrame; captured: number }[] = [];
  let transits: number[] = [];
  let delay = 0;
  let offset = 0; // capture time (Unix ms) + offset = performance.now() at which to show
  let animation = 0;
  const play = () => {
    animation = 0;
    const now = performance.now();
    let due: VideoFrame | undefined;
    while (held.length && held[0].captured + offset <= now) {
      due?.close();
      due = held.shift()!.frame;
    }
    if (due) show(due);
    if (held.length) animation = requestAnimationFrame(play);
  };
  return {
    push(frame: VideoFrame, captured: number) {
      transits.push(performance.now() - captured);
      if (transits.length > JITTER_FRAMES) transits.shift();
      const minimum = Math.min(...transits);
      const jitter = transits.map(transit => transit - minimum).sort((a, b) => a - b);
      const target = Math.min(MAX_DELAY_MS, jitter[Math.floor(0.95 * (jitter.length - 1))]);
      delay += (target - delay) * (target > delay ? DELAY_RISE : DELAY_FALL);
      offset = minimum + delay;
      held.push({ frame, captured });
      while (held.length > MAX_HELD) held.shift()!.frame.close();
      cancelAnimationFrame(animation);
      play();
    },
    /** Pause, resume, a new socket or decoder: drop held frames and start the estimates again. */
    clear() {
      cancelAnimationFrame(animation);
      animation = 0;
      held.forEach(({ frame }) => frame.close());
      held = [];
      transits = [];
      delay = offset = 0;
    },
  };
}

export const UNSUPPORTED_BROWSER = "This browser can't show live view; use Chrome/Edge 94+, Safari 16.4+ or Firefox 130+.";
export const INSECURE_PAGE = "Live view needs a secure connection. Open RobotControl through its https:// address, or on the RobotControl computer.";

/** Live view is H.264 only (no image fallback). Returns why this page cannot show it, or null. */
export async function liveViewUnsupportedReason(): Promise<string | null> {
  // WebCodecs exists only on secure pages (HTTPS, or localhost on the RobotControl computer).
  if (!window.isSecureContext) return INSECURE_PAGE;
  if (typeof VideoDecoder === 'undefined') return UNSUPPORTED_BROWSER;
  for (const config of DECODER_CONFIGS) {
    try {
      if ((await VideoDecoder.isConfigSupported(config)).supported) {
        decoderConfig = config;
        return null;
      }
    } catch {
      /* Try the next configuration. */
    }
  }
  return UNSUPPORTED_BROWSER;
}

/**
 * Owns the live-view WebSocket: H.264 frames decoded by WebCodecs, acknowledgements (the server
 * keeps about one round trip of unacknowledged frames in flight, so a slow link lowers the frame
 * rate instead of queueing video), pause while the tab is hidden, and automatic reconnection. The page owns the
 * session API: `reconnect` creates a new session and calls `connect`; it returns whether that
 * worked. Decoded frames are acknowledged at once (so the window measures the link, not the
 * playout delay), then go through the playout buffer to `showFrame`, which takes ownership (the
 * frame store closes them).
 */
export function useLiveViewSocket(options: {
  showFrame: (frame: VideoFrame | null) => void;
  onState: (state: LiveViewState) => void;
  onError: (message: string) => void;
  reconnect: () => Promise<boolean>;
}) {
  const latest = useRef(options);
  latest.current = options;
  const socket = useRef<WebSocket | null>(null);
  const decoding = useRef<Decoding | null>(null);
  // The newest sequence passed to the playout buffer or shown.
  const newestSequence = useRef(0);
  const [playout] = useState(() => createPlayout(frame => latest.current.showFrame(frame)));
  // The viewer wants live view: false after Stop or unmount, so nothing reconnects then.
  const wanted = useRef(false);
  const retryTimer = useRef<ReturnType<typeof setTimeout>>();
  const keepaliveTimer = useRef<ReturnType<typeof setInterval>>();
  const attempts = useRef(0);

  const send = (ws: WebSocket, type: string, parameters: Record<string, unknown> = {}) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type, parameters }));
  };

  const closeDecoder = useCallback(() => {
    const current = decoding.current;
    decoding.current = null;
    if (current && current.decoder.state !== 'closed') current.decoder.close();
    playout.clear();
  }, [playout]);

  const detach = useCallback(() => {
    clearInterval(keepaliveTimer.current);
    closeDecoder();
    const ws = socket.current;
    socket.current = null;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
      ws.close();
    }
  }, [closeDecoder]);

  /** Acknowledgements are cumulative: "this frame and every earlier one". */
  const openDecoder = (ws: WebSocket, size: string): Decoding => {
    const entry: Decoding = { decoder: null as unknown as VideoDecoder, size, received: 0, captured: new Map() };
    entry.decoder = new VideoDecoder({
      output: (frame) => {
        const sequence = frame.timestamp;
        send(ws, 'ack', { sequence });
        const captured = entry.captured.get(sequence);
        for (const key of entry.captured.keys()) {
          if (key > sequence) break;
          entry.captured.delete(key);
        }
        // Frames from a replaced socket or decoder, or older than the newest one, are dropped.
        if (socket.current !== ws || decoding.current !== entry || sequence <= newestSequence.current) {
          frame.close();
          return;
        }
        newestSequence.current = sequence;
        if (PLAYOUT_BUFFER && captured !== undefined) playout.push(frame, captured);
        else latest.current.showFrame(frame);
      },
      error: () => {
        // The decoder has closed itself. Acknowledge what it held so the server keeps sending;
        // the next keyframe starts a new decoder.
        send(ws, 'ack', { sequence: entry.received });
        if (decoding.current === entry) {
          decoding.current = null;
          playout.clear();
        }
      },
    });
    entry.decoder.configure(decoderConfig);
    return entry;
  };

  const receiveFrame = (ws: WebSocket, buffer: ArrayBuffer) => {
    if (buffer.byteLength <= HEADER_BYTES) return;
    const header = new DataView(buffer);
    if (header.getUint8(0) !== FRAME_VERSION) return;
    const sequence = header.getUint32(1, true);
    const size = `${header.getUint16(13, true)}x${header.getUint16(15, true)}`;
    const keyframe = (header.getUint8(17) & FLAG_KEYFRAME) !== 0;
    let current = decoding.current;
    if (keyframe && current && current.size !== size) {
      closeDecoder(); // A new frame size starts a fresh decoder at this keyframe.
      current = null;
    }
    if (!current) {
      if (!keyframe) {
        send(ws, 'ack', { sequence }); // A delta frame needs the frames before it: skip it.
        return;
      }
      current = decoding.current = openDecoder(ws, size);
    }
    current.received = sequence;
    current.captured.set(sequence, header.getFloat64(5, true) * 1000);
    try {
      current.decoder.decode(new EncodedVideoChunk({ type: keyframe ? 'key' : 'delta', timestamp: sequence,
        data: new Uint8Array(buffer, HEADER_BYTES) }));
    } catch {
      send(ws, 'ack', { sequence });
      closeDecoder();
    }
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
    newestSequence.current = 0;
    const ws = new WebSocket(buildWsUrl(`/api/camera/streaming/video/${sessionId}`));
    ws.binaryType = 'arraybuffer';
    socket.current = ws;
    latest.current.onState('connecting');
    ws.onopen = () => {
      if (socket.current !== ws) return;
      attempts.current = 0;
      latest.current.onState('connected');
      if (document.visibilityState === 'hidden') send(ws, 'pause');
      // Also while paused: proves this browser is still there and keeps the tunnel open.
      clearInterval(keepaliveTimer.current);
      keepaliveTimer.current = setInterval(() => send(ws, 'keepalive'), KEEPALIVE_MS);
    };
    ws.onmessage = (event) => {
      if (socket.current !== ws) return;
      if (event.data instanceof ArrayBuffer) {
        receiveFrame(ws, event.data);
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
      clearInterval(keepaliveTimer.current);
      closeDecoder();
      // Keep the last image: its freshness label turns stale while reconnecting.
      latest.current.onState('disconnected');
      scheduleReconnect();
    };
  }, [detach, closeDecoder, scheduleReconnect]);

  /** Close the socket but keep the last image (a manual reconnect replaces the session). */
  const close = useCallback(() => {
    clearTimeout(retryTimer.current);
    detach();
  }, [detach]);

  /** The viewer stopped live view: no reconnection, no image. */
  const stop = useCallback(() => {
    wanted.current = false;
    close();
    latest.current.showFrame(null);
  }, [close]);

  useEffect(() => {
    const visibility = () => {
      // Hidden: nothing is drawn. Visible: the server restarts at a keyframe after a gap.
      playout.clear();
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
  }, [scheduleReconnect, stop, playout]);

  return { connect, close, stop };
}
