import { createContext, useContext, useState } from 'react';
import { useSerialPolling } from './useSerialPolling';
import { schedulingAPI } from '../services/schedulingApi';
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

/** Runs that need an operator. Unhealthy scheduler storage counts: nothing can be dispatched safely. */
export function recoveryCount(status: RobotStatus | null) {
  const recovery = status?.recovery;
  if (!recovery) return 0;
  return recovery.pending_recoveries?.length || (recovery.active || recovery.storage_healthy === false ? 1 : 0);
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
      const schedulerRunning = schedulerResponse.data?.data?.is_running;
      // A reply without these fields must not read as "idle, no recovery".
      if (!queueData?.queue || !('manual_recovery' in queueData) || typeof schedulerRunning !== 'boolean') {
        throw new Error('Unexpected status reply');
      }
      return {
        schedulerRunning,
        running: Array.isArray(queueData.queue.running_job_details) ? queueData.queue.running_job_details : [],
        queued: Number(queueData.queue.queued_jobs) || 0,
        recovery: queueData.manual_recovery,
        receivedAt: Date.now(),
      };
    },
    // A failed read keeps the last known state, so an active recovery never disappears on error.
    onSuccess: setStatus,
  });
  return { status, error: polling.error, pending: polling.pending, refresh: () => { void polling.refresh(); } };
}
