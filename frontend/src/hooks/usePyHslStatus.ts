import { useState } from 'react';
import { api } from '../services/api';
import { useSerialPolling } from './useSerialPolling';
import type { StatusTone } from '../theme';

export type PyHslRun = {
  run_id: string; protocol: string; status: string; mode: string | null;
  completed_count: number | null; error: string | null; origin: string | null; created_at: string;
};

export type PyHslStatus = {
  state: 'running' | 'not_running' | 'unknown';
  reason: string;
  checked_at: string | null;
  run: PyHslRun | null;
  reviews: { known: boolean; blocked: boolean; run_ids: string[] };
};

/** The backend's stored reading; a failed read clears it, so old data never reads as current. */
export function usePyHslStatus() {
  const [status, setStatus] = useState<PyHslStatus | null>(null);
  const polling = useSerialPolling<PyHslStatus>({
    interval: 15000,
    request: async () => (await api.get('/api/pyhsl/status')).data,
    onSuccess: setStatus,
  });
  return polling.error ? null : status;
}

/** The PyHSL run of an execution history row, when it has one. */
export function pyhslRunId(record: { pyhsl?: unknown }): string | null {
  let receipt = record.pyhsl;
  if (typeof receipt === 'string') {
    try { receipt = JSON.parse(receipt); } catch { return null; }
  }
  const id = (receipt as { run_id?: unknown } | null | undefined)?.run_id;
  return typeof id === 'string' ? id : null;
}

/** Run Control's state for the instrument strip. Unknown is never healthy. */
export function pyhslState(status: PyHslStatus | null): [string, StatusTone] {
  if (status?.reviews.blocked) return ['Review needed', 'attention'];
  if (!status || status.state === 'unknown') return ['Unknown', 'neutral'];
  if (status.state === 'not_running') return ['Not running', 'neutral'];
  if (status.run) return ['Running', 'running'];
  return status.reviews.known ? ['Idle', 'completed'] : ['Unknown', 'neutral'];
}
