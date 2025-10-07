import { useCallback, useEffect, useMemo, useState } from 'react';
import { AxiosError, isAxiosError } from 'axios';
import { schedulingAPI, schedulingService } from '../services/schedulingApi';
import {
  CalendarEvent,
  ConflictCheckRequest,
  ConflictInfo,
  CreateScheduleFormData,
  UpdateScheduleRequest,
  HamiltonStatus,
  QueueStatus,
  SchedulerServiceResponse,
  ScheduledExperiment,
  SchedulingOperationStatus,
  ManualRecoveryState,
} from '../types/scheduling';

const normalizeManualRecovery = (payload: unknown): ManualRecoveryState | null => {
  if (!payload || typeof payload !== 'object') {
    return null;
  }
  const data = payload as Record<string, unknown>;
  return {
    active: Boolean(data.active),
    note: typeof data.note === 'string' ? (data.note as string) : null,
    schedule_id: typeof data.schedule_id === 'string' ? (data.schedule_id as string) : null,
    experiment_name: typeof data.experiment_name === 'string' ? (data.experiment_name as string) : null,
    triggered_by: typeof data.triggered_by === 'string' ? (data.triggered_by as string) : null,
    triggered_at: typeof data.triggered_at === 'string' ? (data.triggered_at as string) : null,
    resolved_by: typeof data.resolved_by === 'string' ? (data.resolved_by as string) : null,
    resolved_at: typeof data.resolved_at === 'string' ? (data.resolved_at as string) : null,
  };
};

const extractErrorMessage = (error: unknown): string => {
  if (isAxiosError(error)) {
    const axiosError = error as AxiosError<any>;
    const message = axiosError.response?.data?.message || axiosError.response?.data?.detail;
    if (typeof message === 'string' && message.trim()) {
      return message;
    }
    if (axiosError.message) {
      return axiosError.message;
    }
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return 'Unexpected error occurred';
};

const useScheduling = () => {
  const [schedules, setSchedules] = useState<ScheduledExperiment[]>([]);
  const [selectedSchedule, setSelectedSchedule] = useState<ScheduledExperiment | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [operationStatus, setOperationStatus] = useState<SchedulingOperationStatus>(
    SchedulingOperationStatus.Idle,
  );
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [hamiltonStatus, setHamiltonStatus] = useState<HamiltonStatus | null>(null);
  const [schedulerRunning, setSchedulerRunning] = useState<boolean>(false);
  const [manualRecovery, setManualRecovery] = useState<ManualRecoveryState | null>(null);
  const [initialized, setInitialized] = useState<boolean>(false);


  const loadSchedules = useCallback(
    async (activeOnly = true, focusScheduleId?: string | null): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Loading);
      setLoading(true);
      setError(null);
      try {
        const result = await schedulingService.getAllSchedules(activeOnly);
        if (result.error) {
          setError(result.error);
          setOperationStatus(SchedulingOperationStatus.Error);
          return;
        }

        const fetchedSchedules = result.schedules;
        setSchedules(fetchedSchedules);
        setLastRefresh(new Date());
        setSelectedSchedule((previous) => {
          if (focusScheduleId === null) {
            return null;
          }
          if (focusScheduleId) {
            return (
              fetchedSchedules.find((schedule) => schedule.schedule_id === focusScheduleId) || null
            );
          }
          if (!previous) {
            return null;
          }
          return (
            fetchedSchedules.find((schedule) => schedule.schedule_id === previous.schedule_id) ||
            null
          );
        });
        setOperationStatus(SchedulingOperationStatus.Idle);
      } catch (err) {
        setError(extractErrorMessage(err));
        setOperationStatus(SchedulingOperationStatus.Error);
      } finally {
        setLoading(false);
        setInitialized(true);
      }
    },
    [],
  );

  const createSchedule = useCallback(
    async (formData: CreateScheduleFormData): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Creating);
      setError(null);
      try {
        const result = await schedulingService.createSchedule(formData);
        if (result.error) {
          setError(result.error);
          setOperationStatus(SchedulingOperationStatus.Error);
          return;
        }
        await loadSchedules(true, result.scheduleId);
      } catch (err) {
        setError(extractErrorMessage(err));
        setOperationStatus(SchedulingOperationStatus.Error);
      }
    },
    [loadSchedules],
  );

  const updateSchedule = useCallback(
    async (scheduleId: string, request: UpdateScheduleRequest): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Updating);
      setError(null);
      try {
        const { data } = await schedulingAPI.updateSchedule(scheduleId, request);
        if (!data.success) {
          setError(data.message || 'Failed to update schedule');
          setOperationStatus(SchedulingOperationStatus.Error);
          return;
        }
        await loadSchedules(true, scheduleId);
      } catch (err) {
        setError(extractErrorMessage(err));
        setOperationStatus(SchedulingOperationStatus.Error);
      }
    },
    [loadSchedules],
  );

  const deleteSchedule = useCallback(
    async (scheduleId: string): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Deleting);
      setError(null);
      try {
        const result = await schedulingService.deleteSchedule(scheduleId);
        if (!result.success) {
          setError(result.error || 'Failed to delete schedule');
          setOperationStatus(SchedulingOperationStatus.Error);
          return;
        }
        await loadSchedules(true, null);
      } catch (err) {
        setError(extractErrorMessage(err));
        setOperationStatus(SchedulingOperationStatus.Error);
      }
    },
    [loadSchedules],
  );

  const requireRecovery = useCallback(
    async (scheduleId: string, note?: string): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Updating);
      setError(null);
      try {
        const result = await schedulingService.requireRecovery(scheduleId, note);
        if (result.error) {
          setError(result.error);
          setOperationStatus(SchedulingOperationStatus.Error);
          return;
        }
        if (result.manualRecovery !== undefined) {
          setManualRecovery(result.manualRecovery ?? null);
        }
        const focusId = result.schedule?.schedule_id ?? scheduleId;
        await loadSchedules(true, focusId);
      } catch (err) {
        setError(extractErrorMessage(err));
        setOperationStatus(SchedulingOperationStatus.Error);
      }
    },
    [loadSchedules],
  );

  const resolveRecovery = useCallback(
    async (scheduleId: string, note?: string): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Updating);
      setError(null);
      try {
        const result = await schedulingService.resolveRecovery(scheduleId, note);
        if (result.error) {
          setError(result.error);
          setOperationStatus(SchedulingOperationStatus.Error);
          return;
        }
        if (result.manualRecovery !== undefined) {
          setManualRecovery(result.manualRecovery ?? null);
        }
        const focusId = result.schedule?.schedule_id ?? scheduleId;
        await loadSchedules(true, focusId);
      } catch (err) {
        setError(extractErrorMessage(err));
        setOperationStatus(SchedulingOperationStatus.Error);
      }
    },
    [loadSchedules],
  );

  const getQueueStatus = useCallback(async (): Promise<void> => {
    try {
      const result = await schedulingService.getQueueStatus();
      if (result.error) {
        setError(result.error);
        return;
      }
      setQueueStatus(result.queueStatus ?? null);
      setHamiltonStatus(result.hamiltonStatus ?? null);
      if (result.manualRecovery !== undefined) {
        setManualRecovery(result.manualRecovery ?? null);
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }, []);

  const getSchedulerStatus = useCallback(async (): Promise<void> => {
    try {
      const { data } = await schedulingAPI.getSchedulerStatus();
      const payload = data as SchedulerServiceResponse;
      if (!payload.success) {
        setError(payload.message || 'Failed to load scheduler status');
        return;
      }
      setSchedulerRunning((payload.data?.status || '').toLowerCase() === 'running');
      if (Object.prototype.hasOwnProperty.call(payload.data ?? {}, 'manual_recovery')) {
        setManualRecovery(normalizeManualRecovery(payload.data?.manual_recovery));
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }, []);

  const getCalendarData = useCallback(
    async (startDate?: Date, endDate?: Date): Promise<{ events: CalendarEvent[]; error?: string }> => {
      const result = await schedulingService.getCalendarData(startDate, endDate);
      if (!result.error) {
        setCalendarEvents(result.events);
      }
      return result;
    },
    [],
  );

  const checkConflicts = useCallback(
    async (
      request: ConflictCheckRequest,
    ): Promise<{ conflicts: Record<string, ConflictInfo[]>; error?: string }> =>
      schedulingService.checkConflicts(request),
    [],
  );

  const getExecutionHistory = useCallback(
    async (scheduleId?: string, limit = 50): Promise<any[]> => {
      try {
        const { data } = await schedulingAPI.getExecutionHistory(scheduleId, limit);
        if (!data.success) {
          throw new Error(data.message || 'Failed to load execution history');
        }
        return (data.data as any[]) ?? [];
      } catch (err) {
        throw new Error(extractErrorMessage(err));
      }
    },
    [],
  );

  const getScheduleExecutionSummary = useCallback(
    async (scheduleId: string): Promise<any> => {
      try {
        const { data } = await schedulingAPI.getScheduleExecutionSummary(scheduleId);
        if (!data.success) {
          throw new Error(data.message || 'Failed to load execution summary');
        }
        return data.data;
      } catch (err) {
        throw new Error(extractErrorMessage(err));
      }
    },
    [],
  );

  const selectSchedule = useCallback((schedule: ScheduledExperiment | null) => {
    setSelectedSchedule(schedule);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
    if (operationStatus === SchedulingOperationStatus.Error) {
      setOperationStatus(SchedulingOperationStatus.Idle);
    }
  }, [operationStatus]);

  useEffect(() => {
    loadSchedules(true);
    getQueueStatus();
    getSchedulerStatus();
  }, [loadSchedules, getQueueStatus, getSchedulerStatus]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      getSchedulerStatus();
    }, 30000);
    return () => window.clearInterval(interval);
  }, [getSchedulerStatus]);

  const state = useMemo(
    () => ({
      schedules,
      selectedSchedule,
      operationStatus,
      loading,
      error,
      lastRefresh,
      calendarEvents,
      queueStatus,
      hamiltonStatus,
      schedulerRunning,
      manualRecovery,
      initialized,
    }),
    [
      schedules,
      selectedSchedule,
      operationStatus,
      loading,
      error,
      lastRefresh,
      calendarEvents,
      queueStatus,
      hamiltonStatus,
      schedulerRunning,
      manualRecovery,
      initialized,
    ],
  );

  const actions = useMemo(
    () => ({
      loadSchedules,
      createSchedule,
      updateSchedule,
      deleteSchedule,
      requireRecovery,
      resolveRecovery,
      getQueueStatus,
      getSchedulerStatus,
      getCalendarData,
      checkConflicts,
      getExecutionHistory,
      getScheduleExecutionSummary,
      selectSchedule,
      clearError,
    }),
    [
      loadSchedules,
      createSchedule,
      updateSchedule,
      deleteSchedule,
      requireRecovery,
      resolveRecovery,
      getQueueStatus,
      getSchedulerStatus,
      getCalendarData,
      checkConflicts,
      getExecutionHistory,
      getScheduleExecutionSummary,
      selectSchedule,
      clearError,
    ],
  );

  return { state, actions };
};

export { useScheduling };
export default useScheduling;