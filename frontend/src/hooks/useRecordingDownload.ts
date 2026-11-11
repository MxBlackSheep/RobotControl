import { useCallback, useEffect, useRef, useState } from 'react';
import { attemptTokenRefresh } from '@/services/api';
import { buildApiUrl } from '@/utils/apiBase';

export interface DownloadProgress { filename: string; received: number; total: number | null; retrying: boolean }

const MAX_ATTEMPTS = 5;
const RETRY_BASE_MS = 1200;
const RETRY_MAX_MS = 8000;

/** A failure that another attempt cannot fix. */
class DownloadRefused extends Error {}

const refusal = (status: number) => status === 404 ? 'Recording not found on server. It may have been moved or deleted.'
  : status === 401 || status === 403 ? 'You are not authorized to download this recording.'
  : 'Download request is invalid and cannot be retried automatically.';

/** Resolves after `ms`, or at once when the download is cancelled. */
const pause = (ms: number, signal: AbortSignal) => new Promise<void>(resolve => {
  const timer = window.setTimeout(resolve, ms);
  signal.addEventListener('abort', () => { window.clearTimeout(timer); resolve(); }, { once: true });
});

/** Streamed with fetch for progress and resume, so an expired sign-in is renewed here once per request. */
async function request(filename: string, from: number, signal: AbortSignal) {
  // no-store: the resume below is this hook's, not the browser cache's.
  const send = (token: string | null) => fetch(buildApiUrl(`/api/camera/recording/${filename}`), {
    cache: 'no-store', signal, headers: { Authorization: `Bearer ${token}`, ...(from > 0 && { Range: `bytes=${from}-` }) },
  });
  const response = await send(localStorage.getItem('access_token'));
  if (response.status !== 401) return response;
  const renewed = await attemptTokenRefresh().catch(() => null);
  return renewed ? send(renewed) : response;
}

/**
 * Downloads one recording at a time. A dropped connection resumes from the received byte with
 * `Range` (five attempts, 1.2 to 8 s apart); bytes stay in memory and are saved only when the file
 * is complete. One AbortController is both Cancel and the request signal; leaving the page cancels.
 */
export function useRecordingDownload() {
  const [progress, setProgress] = useState<DownloadProgress | null>(null);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const start = useCallback(async (filename: string) => {
    if (controller.current) return;
    const abort = new AbortController();
    controller.current = abort;
    setError('');
    const chunks: Uint8Array[] = [];
    let received = 0, total: number | null = null, type = 'application/octet-stream';
    const show = (retrying = false) => setProgress({ filename, received, total, retrying });
    show();
    try {
      for (let attempt = 1; ; attempt += 1) {
        try {
          const response = await request(filename, received, abort.signal);
          if (!response.ok) {
            if (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429) {
              throw new DownloadRefused(refusal(response.status));
            }
            throw new Error(`Download request failed (${response.status})`);
          }
          type = response.headers.get('Content-Type') || type;
          if (response.status === 206) {
            const range = /^bytes (\d+)-\d+\/(\d+)$/.exec(response.headers.get('Content-Range') ?? '');
            if (!range || Number(range[1]) !== received) throw new DownloadRefused('Server resume offset mismatch');
            total = Number(range[2]);
          } else {
            // A full answer, also to a Range request: start again from the first byte.
            chunks.length = 0;
            received = 0;
            const length = Number(response.headers.get('Content-Length'));
            total = response.headers.has('Content-Length') && Number.isFinite(length) ? length : null;
          }
          const reader = response.body!.getReader();
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            chunks.push(value);
            received += value.length;
            show();
          }
          if (total !== null && received < total) throw new Error('Download incomplete');
          break;
        } catch (cause) {
          // The connection dropped after the last byte: the file is complete.
          if (total !== null && received === total && !abort.signal.aborted) break;
          if (abort.signal.aborted || cause instanceof DownloadRefused || attempt >= MAX_ATTEMPTS) throw cause;
          show(true);
          await pause(Math.min(RETRY_BASE_MS * 2 ** (attempt - 1), RETRY_MAX_MS), abort.signal);
          if (abort.signal.aborted) return;
        }
      }
      if (!received) throw new Error('No data was received');
      // A fetch body never yields SharedArrayBuffer chunks; the DOM typing only allows for them.
      const url = URL.createObjectURL(new Blob(chunks as BlobPart[], { type }));
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : 'Download failed');
    } finally {
      controller.current = null;
      setProgress(null);
    }
  }, []);

  const cancel = useCallback(() => controller.current?.abort(), []);
  return { progress, error, clearError: () => setError(''), start, cancel };
}
