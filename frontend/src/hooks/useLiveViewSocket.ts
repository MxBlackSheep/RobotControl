import { useCallback, useEffect, useRef, useState } from 'react';
import { isAxiosError } from 'axios';
import { api } from '@/services/api';
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

/** 'idle': this viewer has no live-view session. */
export type LiveViewState = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

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
 * Owns live view for this viewer: the session (create, release), its WebSocket, H.264 frames
 * decoded by WebCodecs, acknowledgements (the server keeps about one round trip of unacknowledged
 * frames in flight, so a slow link lowers the frame rate instead of queueing video), pause while
 * the tab is hidden, and automatic reconnection. Decoded frames are acknowledged at once (so the
 * window measures the link, not the playout delay), then go through the playout buffer to
 * `showFrame`, which takes ownership (the frame store closes them). Start, Stop, Reconnect and the
 * automatic retry share one session request at a time.
 */
export function useLiveViewSocket(showFrame: (frame: VideoFrame | null) => void) {
  const show = useRef(showFrame);
  show.current = showFrame;
  const [state, setState] = useState<LiveViewState>('idle');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  // Live view is H.264 only: a browser or page that cannot decode it gets this reason instead.
  const [unsupported, setUnsupported] = useState<string | null>(null);
  const session = useRef<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const decoding = useRef<Decoding | null>(null);
  // The newest sequence passed to the playout buffer or shown.
  const newestSequence = useRef(0);
  const [playout] = useState(() => createPlayout(frame => show.current(frame)));
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

  /** Closes the socket; the last image stays until a new one or Stop replaces it. */
  const detach = useCallback(() => {
    clearTimeout(retryTimer.current);
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
        else show.current(frame);
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

  const connect = (sessionId: string) => {
    wanted.current = true;
    detach();
    newestSequence.current = 0;
    const ws = new WebSocket(buildWsUrl(`/api/camera/streaming/video/${sessionId}`));
    ws.binaryType = 'arraybuffer';
    socket.current = ws;
    setState('connecting');
    ws.onopen = () => {
      if (socket.current !== ws) return;
      attempts.current = 0;
      setState('connected');
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
        if (message.type === 'error') setError(message.error || 'Streaming error');
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
      setState('disconnected');
      latest.current.scheduleReconnect();
    };
  };

  /** Runs one session request; returns undefined while another is in flight. */
  const exclusive = async <T,>(work: (signal: AbortSignal) => Promise<T>): Promise<T | undefined> => {
    if (request.current) return undefined;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    try {
      return await work(controller.signal);
    } finally {
      if (request.current === controller) {
        request.current = null;
        setBusy(false);
      }
    }
  };

  /** A 404 means the server has already ended the session. */
  const release = async (id: string) => {
    try {
      await api.delete(`/api/camera/streaming/session/${id}`);
      return true;
    } catch (cause) {
      return isAxiosError(cause) && cause.response?.status === 404;
    }
  };

  /** Creates a session and connects to it; the server's refusal reason (429, 503) is shown. */
  const open = async (signal: AbortSignal) => {
    try {
      const { data } = await api.post('/api/camera/streaming/session', undefined, { signal });
      if (signal.aborted) return false;
      session.current = data.data.session_id;
      setError('');
      connect(data.data.session_id);
      return true;
    } catch (cause) {
      if (signal.aborted) return false;
      const detail = isAxiosError(cause) ? cause.response?.data?.detail : undefined;
      setError(typeof detail === 'string' ? detail : 'Failed to create streaming session');
      return false;
    }
  };

  /** Replaces the session; the last image stays, marked stale, until new frames arrive. Until a
   * new session exists the old id is kept, so the next try releases it again (404 counts). */
  const replace = (signal: AbortSignal) => {
    const id = session.current;
    if (!id) return Promise.resolve(false);
    detach();
    return release(id).then(released => {
      if (released) return open(signal);
      setError('Could not release the previous live-view session. Retrying…');
      return false;
    });
  };

  const scheduleReconnect = () => {
    clearTimeout(retryTimer.current);
    if (!wanted.current) return;
    setState('reconnecting');
    if (!navigator.onLine) return; // the 'online' listener resumes
    const base = Math.min(RECONNECT_MAX_MS, 1000 * 2 ** attempts.current);
    attempts.current += 1;
    retryTimer.current = setTimeout(() => void latest.current.retry(), base * (0.75 + Math.random() * 0.5));
  };

  /** Manual Reconnect and the automatic retry: a failure keeps the back-off going. */
  const retry = async () => {
    if (!wanted.current || socket.current) return;
    const connected = await exclusive(replace);
    if (connected === false && wanted.current && !socket.current) scheduleReconnect();
  };

  // Timers and socket handlers call the current render's functions.
  const latest = useRef({ scheduleReconnect, retry });
  latest.current = { scheduleReconnect, retry };

  const start = () => {
    if (unsupported || session.current) return;
    void exclusive(open);
  };

  /** No reconnection and no image. A failed release keeps the session so Stop can be pressed again. */
  const stop = () => void exclusive(async () => {
    const id = session.current;
    if (!id) return;
    wanted.current = false;
    detach();
    show.current(null);
    if (await release(id)) {
      session.current = null;
      setState('idle');
      setError('');
    } else {
      setState('disconnected');
      setError('Failed to stop streaming session');
    }
  });

  const reconnect = () => {
    if (!session.current || request.current) return;
    wanted.current = true;
    attempts.current = 0;
    detach();
    void retry();
  };

  useEffect(() => {
    let current = true;
    void liveViewUnsupportedReason().then(reason => { if (current) setUnsupported(reason); });
    const visibility = () => {
      // Hidden: nothing is drawn. Visible: the server restarts at a keyframe after a gap.
      playout.clear();
      const ws = socket.current;
      if (ws) send(ws, document.visibilityState === 'hidden' ? 'pause' : 'resume');
    };
    const online = () => {
      if (wanted.current && !socket.current) {
        attempts.current = 0;
        latest.current.scheduleReconnect();
      }
    };
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('online', online);
    return () => {
      current = false;
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('online', online);
      wanted.current = false;
      request.current?.abort();
      detach();
      show.current(null);
    };
  }, [detach, playout]);

  return { state, error, busy, unsupported, start, stop, reconnect };
}