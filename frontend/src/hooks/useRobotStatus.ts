import { createContext, useContext, useState } from 'react';
import { useSerialPolling } from './useSerialPolling';
import { normalizeManualRecovery, schedulingAPI } from '../services/schedulingApi';
import type { ManualRecoveryState, RunningJobDetail } from '../types/scheduling';

export const ROBOT_STATUS_INTERVAL_MS = 15000;

export type RobotStatus = {
  schedulerRunning: boolean;
  running: RunningJobDetail[];
  queued: number;
  recovery: ManualRecoveryState | null;
  receivedAt: number;
};

export type RobotStatusState = { status: RobotStatus | null; error: string | null; pending: boolean; refresh: () => void };

export const RobotStatusContext = createContext<RobotStatusState>({ status: null, error: null, pending: false, refresh: () => {} });
export const useRobotStatusContext = () => useContext(RobotStatusContext);

const needsOperator = (value: ManualRecoveryState | null) =>
  !!value && (value.storage_healthy !== true || value.active || !!value.resume_required);

/**
 * Both status replies carry recovery state and are read concurrently, so either may be the
 * newer one. Unhealthy storage reports a cached revision, so it always wins (fail closed);
 * otherwise the higher safety revision wins, and a tie keeps the state that needs an operator.
 */
export function newerRecovery(a: ManualRecoveryState | null, b: ManualRecoveryState | null) {
  if (!a || !b) return a ?? b;
  const aUnhealthy = a.storage_healthy !== true, bUnhealthy = b.storage_healthy !== true;
  if (aUnhealthy !== bUnhealthy) return aUnhealthy ? a : b;
  const aRevision = a.safety_revision ?? -1, bRevision = b.safety_revision ?? -1;
  if (aRevision !== bRevision) return aRevision > bRevision ? a : b;
  return needsOperator(b) && !needsOperator(a) ? b : a;
}

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

/** One owner for the shell's robot state; Scheduling keeps its own revision-ordered view. */
export function useRobotStatus(identity: string | null): RobotStatusState {
  const [status, setStatus] = useState<RobotStatus | null>(null);
  const polling = useSerialPolling<RobotStatus>({
    identity,
    interval: ROBOT_STATUS_INTERVAL_MS,
    retryInterval: 10000,
    request: async () => {
      const [queueResponse, schedulerResponse] = await Promise.all([schedulingAPI.getQueueStatus(), schedulingAPI.getSchedulerStatus()]);
      const queueData = queueResponse.data?.data;
      const schedulerData = schedulerResponse.data?.data;
      const schedulerRunning = schedulerData?.is_running;
      // A reply without these fields must not read as "idle, no recovery".
      if (!queueData?.queue || !('manual_recovery' in queueData) || typeof schedulerRunning !== 'boolean') {
        throw new Error('Unexpected status reply');
      }
      const schedulerRecovery = schedulerData && 'manual_recovery' in schedulerData ? normalizeManualRecovery(schedulerData.manual_recovery) : null;
      return {
        schedulerRunning,
        running: Array.isArray(queueData.queue.running_job_details) ? queueData.queue.running_job_details : [],
        queued: Number(queueData.queue.queued_jobs) || 0,
        recovery: newerRecovery(normalizeManualRecovery(queueData.manual_recovery), schedulerRecovery),
        receivedAt: Date.now(),
      };
    },
    // A failed read keeps the last known state, so an active recovery never disappears on error.
    onSuccess: setStatus,
  });
  return { status, error: polling.error, pending: polling.pending, refresh: () => { void polling.refresh(); } };
}
