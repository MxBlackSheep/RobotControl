import { createContext, useContext, useState } from 'react';
import { useSerialPolling } from './useSerialPolling';
import { normalizeManualRecovery, schedulingAPI } from '../services/schedulingApi';
import { requestErrorMessage } from '../services/requestError';
import type { ManualRecoveryState, RunningJobDetail } from '../types/scheduling';

export const ROBOT_STATUS_INTERVAL_MS = 15000;

export type RobotStatus = {
  schedulerRunning: boolean;
  /** HxRun process seen on this PC; null when the reply did not say. */
  hamiltonRunning: boolean | null;
  running: RunningJobDetail[];
  queued: number;
  /** Queued runs with why each waits (waiting_reason). */
  queuedJobs: RunningJobDetail[];
  recovery: ManualRecoveryState | null;
  receivedAt: number;
};

export type RobotStatusState = { status: RobotStatus | null; error: string | null; pending: boolean; refresh: () => Promise<void> };

export const RobotStatusContext = createContext<RobotStatusState>({ status: null, error: null, pending: false, refresh: async () => {} });
export const useRobotStatusContext = () => useContext(RobotStatusContext);

export type RobotAttention = { kind: 'storage' | 'recovery' | 'resume'; count: number; label: string };

/** Why the scheduler is holding runs for an operator, or null when nothing is held. */
export function robotAttention(status: RobotStatus | null): RobotAttention | null {
  const recovery = status?.recovery;
  if (!recovery) return null;
  if (recovery.storage_healthy === false) return { kind: 'storage', count: 1, label: 'Scheduler storage needs attention' };
  const pending = recovery.pending_recoveries?.length || (recovery.active ? 1 : 0);
  if (pending) return { kind: 'recovery', count: pending, label: `${pending} ${pending === 1 ? 'run needs' : 'runs need'} recovery` };
  if (recovery.resume_required) return { kind: 'resume', count: 1, label: 'Queued jobs paused until Resume' };
  return null;
}

/** The one owner of the robot status read; every page, Scheduling included, reads its context. */
export function useRobotStatus(identity: string | null): RobotStatusState {
  const [status, setStatus] = useState<RobotStatus | null>(null);
  const polling = useSerialPolling<RobotStatus>({
    identity,
    interval: ROBOT_STATUS_INTERVAL_MS,
    retryInterval: 10000,
    request: async () => {
      const reply = await schedulingAPI.getQueueStatus().then(response => response.data?.data,
        error => { throw new Error(requestErrorMessage(error, 'Status read failed')); });
      // A reply without these fields must not read as "idle, no recovery".
      if (!reply?.queue || !('manual_recovery' in reply) || typeof reply.is_running !== 'boolean') {
        throw new Error('Unexpected status reply');
      }
      return {
        schedulerRunning: reply.is_running,
        hamiltonRunning: typeof reply.hamilton?.is_running === 'boolean' ? reply.hamilton.is_running : null,
        running: Array.isArray(reply.queue.running_job_details) ? reply.queue.running_job_details : [],
        queued: Number(reply.queue.queued_jobs) || 0,
        queuedJobs: Array.isArray(reply.queue.queued_job_details) ? reply.queue.queued_job_details : [],
        recovery: normalizeManualRecovery(reply.manual_recovery),
        receivedAt: Date.now(),
      };
    },
    // A failed read keeps the last known state, so an active recovery never disappears on error.
    onSuccess: setStatus,
  });
  return { status, error: polling.error, pending: polling.pending, refresh: polling.refresh };
}
