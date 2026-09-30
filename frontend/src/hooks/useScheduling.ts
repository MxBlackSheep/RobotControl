import { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { AxiosError, isAxiosError } from 'axios';
import { schedulingAPI, schedulingService, normalizeManualRecovery } from '../services/schedulingApi';
import {
  CalendarEvent,
  CreateScheduleFormData,
  UpdateScheduleRequest,
  HamiltonStatus,
  QueueStatus,
  SchedulerServiceResponse,
  ScheduledExperiment,
  SchedulingOperationStatus,
  ManualRecoveryState,
  NotificationContact,
  NotificationContactPayload,
  NotificationLogEntry,
  NotificationLogQuery,
  NotificationSettings,
  NotificationSettingsUpdatePayload,
} from '../types/scheduling';

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
  const [archivedSchedules, setArchivedSchedules] = useState<ScheduledExperiment[]>([]);
  const [selectedSchedule, setSelectedSchedule] = useState<ScheduledExperiment | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [archivedLoading, setArchivedLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [archivedError, setArchivedError] = useState<string | null>(null);
  const [archivedInitialized, setArchivedInitialized] = useState<boolean>(false);
  const [operationStatus, setOperationStatus] = useState<SchedulingOperationStatus>(
    SchedulingOperationStatus.Idle,
  );
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [hamiltonStatus, setHamiltonStatus] = useState<HamiltonStatus | null>(null);
  const [schedulerRunning, setSchedulerRunning] = useState<boolean>(false);
  const [manualRecovery, setManualRecovery] = useState<ManualRecoveryState | null>(null);
  // Status polls own their errors: the shared `error` belongs to schedule loads and edits.
  const [queueError, setQueueError] = useState<string | null>(null);
  const [schedulerError, setSchedulerError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState<boolean>(false);
  const [contacts, setContacts] = useState<NotificationContact[]>([]);
  const [notificationLogs, setNotificationLogs] = useState<NotificationLogEntry[]>([]);
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings | null>(null);
  const [notificationSettingsLoading, setNotificationSettingsLoading] = useState<boolean>(false);

  const sortContactsList = useCallback(
    (list: NotificationContact[]) =>
      [...list].sort((a, b) => {
        if (a.is_active !== b.is_active) {
          return a.is_active ? -1 : 1;
        }
        return a.display_name.localeCompare(b.display_name);
      }),
    [],
  );


  const loadSchedules = useCallback(
    async (activeOnly = false, focusScheduleId?: string | null): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Loading);
      setLoading(true);
      setError(null);
      try {
        const result = await schedulingService.getAllSchedules(activeOnly, false);
        if (result.error) {
          setError(result.error);
          setOperationStatus(SchedulingOperationStatus.Error);
          return;
        }

        const fetchedSchedules = result.schedules;
        setSchedules(fetchedSchedules);
        setCalendarEvents(
          fetchedSchedules
            .filter((schedule) => schedule.is_active && Boolean(schedule.next_run))
            .map((schedule) => ({
              event_id: `${schedule.schedule_id}-${schedule.next_run}`,
              schedule_id: schedule.schedule_id,
              title: schedule.experiment_name,
              description: schedule.experiment_path,
              start_time: schedule.next_run as string,
              end_time: schedule.next_run as string,
              event_type: 'scheduled',
              experiment_name: schedule.experiment_name,
              estimated_duration: schedule.estimated_duration,
              status: schedule.is_active ? 'scheduled' : 'inactive',
              created_by: schedule.created_by,
            })),
        );
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

  const loadArchivedSchedules = useCallback(async (): Promise<void> => {
    setArchivedLoading(true);
    setArchivedError(null);
    try {
      const result = await schedulingService.getArchivedSchedules();
      if (result.error) {
        setArchivedError(result.error);
        return;
      }
      setArchivedSchedules(result.schedules);
    } catch (err) {
      setArchivedError(extractErrorMessage(err));
    } finally {
      setArchivedLoading(false);
      setArchivedInitialized(true);
    }
  }, []);

  const createSchedule = useCallback(
    async (formData: CreateScheduleFormData): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Creating);
      setError(null);
      try {
        const result = await schedulingService.createSchedule(formData);
        if (result.error) {
          setOperationStatus(SchedulingOperationStatus.Error);
          throw new Error(result.error);
        }
        await loadSchedules(false, result.scheduleId);
      } catch (err) {
        const message = extractErrorMessage(err);
        setOperationStatus(SchedulingOperationStatus.Error);
        throw err instanceof Error ? err : new Error(message);
      }
    },
    [loadSchedules],
  );

  const updateSchedule = useCallback(
    async (scheduleId: string, request: UpdateScheduleRequest): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Updating);
      setError(null);
      const scheduleFromState = schedules.find((schedule) => schedule.schedule_id === scheduleId);
      const expected = request.expected_updated_at ?? scheduleFromState?.updated_at;
      const payload: UpdateScheduleRequest = expected
        ? { ...request, expected_updated_at: expected }
        : { ...request };
      try {
        const { data } = await schedulingAPI.updateSchedule(scheduleId, payload, {
          expectedUpdatedAt: expected,
        });
        if (!data.success) {
          const message = data.message || 'Failed to update schedule';
          setOperationStatus(SchedulingOperationStatus.Error);
          throw new Error(message);
        }
        await loadSchedules(false, scheduleId);
      } catch (err) {
        const message = extractErrorMessage(err);
        if (isAxiosError(err) && err.response?.status === 409) {
          await loadSchedules(false, scheduleId);
        }
        setOperationStatus(SchedulingOperationStatus.Error);
        throw err instanceof Error ? err : new Error(message);
      }
    },
    [loadSchedules, schedules],
  );

  const deleteSchedule = useCallback(
    async (schedule: ScheduledExperiment): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Deleting);
      setError(null);
      const expected = schedule.updated_at || null;
      try {
        const result = await schedulingService.deleteSchedule(schedule.schedule_id, expected || undefined);
        if (!result.success) {
          setError(result.error || 'Failed to delete schedule');
          setOperationStatus(SchedulingOperationStatus.Error);
          return;
        }
        await loadSchedules(false, null);
        await loadArchivedSchedules();
      } catch (err) {
        setError(extractErrorMessage(err));
        if (isAxiosError(err) && err.response?.status === 409) {
          await loadSchedules(false, null);
          await loadArchivedSchedules();
        }
        setOperationStatus(SchedulingOperationStatus.Error);
      }
    },
    [loadArchivedSchedules, loadSchedules],
  );

  const archiveSchedule = useCallback(
    async (schedule: ScheduledExperiment, archived: boolean): Promise<void> => {
      setOperationStatus(SchedulingOperationStatus.Updating);
      setError(null);
      try {
        const result = await schedulingService.archiveSchedule(schedule.schedule_id, archived, schedule.updated_at || undefined);
        if (result.error) {
          setError(result.error);
          setOperationStatus(SchedulingOperationStatus.Error);
          return;
        }
        await loadSchedules(false, archived ? null : schedule.schedule_id);
        await loadArchivedSchedules();
      } catch (err) {
        setError(extractErrorMessage(err));
        setOperationStatus(SchedulingOperationStatus.Error);
      }
    },
    [loadArchivedSchedules, loadSchedules],
  );

  const loadContacts = useCallback(
    async (includeInactive = true): Promise<{ contacts?: NotificationContact[]; error?: string }> => {
      try {
        const result = await schedulingService.getNotificationContacts(includeInactive);
        if (result.error) {
          setError(result.error);
          return { error: result.error };
        }
        setContacts(sortContactsList(result.contacts));
        return { contacts: result.contacts };
      } catch (err) {
        const message = extractErrorMessage(err);
        setError(message);
        return { error: message };
      }
    },
    [sortContactsList],
  );

  const loadNotificationSettings = useCallback(
    async (): Promise<{ settings?: NotificationSettings | null; error?: string }> => {
      setNotificationSettingsLoading(true);
      try {
        const result = await schedulingService.getNotificationSettings();
        if (result.error) {
          setError(result.error);
          return { error: result.error };
        }
        const settings = result.settings ?? null;
        setNotificationSettings(settings);
        return { settings };
      } finally {
        setNotificationSettingsLoading(false);
      }
    },
    [],
  );

  const updateNotificationSettings = useCallback(
    async (
      payload: NotificationSettingsUpdatePayload,
    ): Promise<{ settings?: NotificationSettings; error?: string }> => {
      setNotificationSettingsLoading(true);
      try {
        const result = await schedulingService.updateNotificationSettings(payload);
        if (result.error) {
          setError(result.error);
          return { error: result.error };
        }
        if (result.settings) {
          setNotificationSettings(result.settings);
        }
        return { settings: result.settings };
      } finally {
        setNotificationSettingsLoading(false);
      }
    },
    [],
  );

  const sendNotificationTestEmail = useCallback(
    (recipient: string) => schedulingService.sendNotificationTestEmail(recipient),
    [],
  );

  const createContact = useCallback(
    async (payload: NotificationContactPayload): Promise<{ contact?: NotificationContact; error?: string }> => {
      const result = await schedulingService.createNotificationContact(payload);
      if (!result.contact || result.error) {
        const message = result.error || 'Failed to create contact';
        setError(message);
        return { error: message };
      }
      setContacts((prev) => sortContactsList([...prev, result.contact!]));
      return { contact: result.contact };
    },
    [sortContactsList],
  );

  const updateContact = useCallback(
    async (
      contactId: string,
      payload: NotificationContactPayload,
    ): Promise<{ contact?: NotificationContact; error?: string }> => {
      const result = await schedulingService.updateNotificationContact(contactId, payload);
      if (!result.contact || result.error) {
        const message = result.error || 'Failed to update contact';
        setError(message);
        return { error: message };
      }
      setContacts((prev) =>
        sortContactsList(prev.map((contact) => (contact.contact_id === contactId ? result.contact! : contact))),
      );
      return { contact: result.contact };
    },
    [sortContactsList],
  );

  const deleteContact = useCallback(
    async (contactId: string): Promise<{ success: boolean; error?: string }> => {
      const result = await schedulingService.deleteNotificationContact(contactId);
      if (!result.success) {
        const message = result.error || 'Failed to delete contact';
        setError(message);
        return { success: false, error: message };
      }
      setContacts((prev) => prev.filter((contact) => contact.contact_id !== contactId));
      return { success: true };
    },
    [],
  );

  const notificationRead = useRef(0);
  const loadNotificationLogs = useCallback(
    async (
      params?: NotificationLogQuery & { limit?: number },
    ): Promise<{ logs?: NotificationLogEntry[]; error?: string }> => {
      const id = ++notificationRead.current;
      const result = await schedulingService.getNotificationLogs(params);
      if (id !== notificationRead.current) return {};
      if (result.error) {
        setError(result.error);
        return { error: result.error };
      }
      setNotificationLogs(result.logs);
      return { logs: result.logs };
    },
    [],
  );

  useEffect(() => {
    loadContacts(false);
  }, [loadContacts]);

  // Both status reads carry recovery state and run together, so answers can arrive out of
  // order. Older safety revisions cannot replace newer ones; request order only breaks
  // ties. Reopening Scheduling resets this history after a deliberate store restore.
  // Unhealthy storage reports a cached revision, so always show it (fail closed).
  const statusRequest = useRef(0);
  const appliedRecovery = useRef({ request: 0, revision: -1 });
  const applyManualRecovery = useCallback((request: number, value: ManualRecoveryState | null) => {
    const last = appliedRecovery.current;
    const revision = value?.safety_revision ?? -1;
    const unhealthy = value !== null && value.storage_healthy !== true;
    if (!unhealthy && (revision < last.revision || (revision === last.revision && request < last.request))) return;
    appliedRecovery.current = { request: Math.max(request, last.request), revision: Math.max(revision, last.revision) };
    setManualRecovery(value);
  }, []);

  const getQueueStatus = useCallback(async (): Promise<void> => {
    const request = ++statusRequest.current;
    try {
      const result = await schedulingService.getQueueStatus();
      if (result.error) {
        setQueueError(result.error);
        return;
      }
      setQueueError(null);
      setQueueStatus(result.queueStatus ?? null);
      setHamiltonStatus(result.hamiltonStatus ?? null);
      if (result.manualRecovery !== undefined) {
        applyManualRecovery(request, result.manualRecovery ?? null);
      }
    } catch (err) {
      setQueueError(extractErrorMessage(err));
    }
  }, [applyManualRecovery]);

  const getSchedulerStatus = useCallback(async (): Promise<void> => {
    const request = ++statusRequest.current;
    try {
      const { data } = await schedulingAPI.getSchedulerStatus();
      const payload = data as SchedulerServiceResponse;
      if (!payload.success) {
        setSchedulerError(payload.message || 'Failed to load scheduler status');
        return;
      }
      setSchedulerError(null);
      const statusPayload = (payload.data ?? {}) as { is_running?: boolean; status?: string };
      const derivedStatus =
        typeof statusPayload.is_running === 'boolean'
          ? statusPayload.is_running
          : (statusPayload.status ?? '').toLowerCase() === 'running';
      setSchedulerRunning(derivedStatus);
      if (Object.prototype.hasOwnProperty.call(payload.data ?? {}, 'manual_recovery')) {
        applyManualRecovery(request, normalizeManualRecovery(payload.data?.manual_recovery));
      }
    } catch (err) {
      setSchedulerError(extractErrorMessage(err));
    }
  }, [applyManualRecovery]);

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

  const selectSchedule = useCallback((schedule: ScheduledExperiment | null) => {
    setSelectedSchedule(schedule);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
    setArchivedError(null);
    if (operationStatus === SchedulingOperationStatus.Error) {
      setOperationStatus(SchedulingOperationStatus.Idle);
    }
  }, [operationStatus]);

  useEffect(() => {
    loadSchedules(false);
    loadArchivedSchedules();
    getQueueStatus();
    getSchedulerStatus();
    getCalendarData();
  }, [loadSchedules, loadArchivedSchedules, getQueueStatus, getSchedulerStatus, getCalendarData]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      getSchedulerStatus();
      getQueueStatus();
    }, 30000);
    return () => window.clearInterval(interval);
  }, [getQueueStatus, getSchedulerStatus]);

  const state = useMemo(
    () => ({
      schedules,
      archivedSchedules,
      selectedSchedule,
      operationStatus,
      loading,
      archivedLoading,
      error,
      archivedError,
      archivedInitialized,
      lastRefresh,
      calendarEvents,
      queueStatus,
      hamiltonStatus,
      schedulerRunning,
      manualRecovery,
      queueError,
      schedulerError,
      initialized,
      contacts,
      notificationLogs,
      notificationSettings,
      notificationSettingsLoading,
    }),
    [
      schedules,
      archivedSchedules,
      selectedSchedule,
      operationStatus,
      loading,
      archivedLoading,
      error,
      archivedError,
      archivedInitialized,
      lastRefresh,
      calendarEvents,
      queueStatus,
      hamiltonStatus,
      schedulerRunning,
      manualRecovery,
      queueError,
      schedulerError,
      initialized,
      contacts,
      notificationLogs,
      notificationSettings,
      notificationSettingsLoading,
    ],
  );

  const actions = useMemo(
    () => ({
      loadSchedules,
      loadArchivedSchedules,
      createSchedule,
      updateSchedule,
      deleteSchedule,
      archiveSchedule,
      loadContacts,
      createContact,
      updateContact,
      deleteContact,
      loadNotificationSettings,
      updateNotificationSettings,
      sendNotificationTestEmail,
      loadNotificationLogs,
      getQueueStatus,
      getSchedulerStatus,
      getCalendarData,
      getExecutionHistory,
      selectSchedule,
      clearError,
    }),
    [
      loadSchedules,
      loadArchivedSchedules,
      createSchedule,
      updateSchedule,
      deleteSchedule,
      archiveSchedule,
      loadContacts,
      createContact,
      updateContact,
      deleteContact,
      loadNotificationSettings,
      updateNotificationSettings,
      sendNotificationTestEmail,
      loadNotificationLogs,
      getQueueStatus,
      getSchedulerStatus,
      getCalendarData,
      getExecutionHistory,
      selectSchedule,
      clearError,
    ],
  );

  return { state, actions };
};

export { useScheduling };
export default useScheduling;

