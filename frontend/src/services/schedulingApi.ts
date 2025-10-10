import { AxiosError, isAxiosError } from 'axios';
import { api } from './api';
import {
  CreateScheduleRequest,
  UpdateScheduleRequest,
  ConflictCheckRequest,
  ScheduleListResponse,
  ScheduleCreateResponse,
  ScheduleResponse,
  CalendarDataResponse,
  ConflictCheckResponse,
  QueueStatusResponse,
  SchedulerServiceResponse,
  ScheduledExperiment,
  CalendarEvent,
  ConflictInfo,
  QueueStatus,
  HamiltonStatus,
  ManualRecoveryState,
  CreateScheduleFormData,
  RecoveryActionResponse,
  EvoYeastExperimentOption,
  NotificationContact,
  NotificationContactPayload,
  NotificationLogEntry,
  NotificationLogQuery,
  NotificationSettings,
  NotificationSettingsUpdatePayload,
} from '../types/scheduling';

const coerceNumber = (value: unknown, fallback = 0): number => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const coerceString = (value: unknown, fallback = ''): string => {
  if (value === null || value === undefined) {
    return fallback;
  }
  return String(value);
};

const coerceOptionalString = (value: unknown): string | null => {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  return String(value);
};

const serializeMaybeDate = (value?: Date | string | null): string | null => {
  if (!value) {
    return null;
  }
  if (value instanceof Date) {
    return value.toISOString();
  }
  return value;
};

export const normalizeSchedule = (raw: any): ScheduledExperiment => {
  const retryConfig = raw?.retry_config ?? {};
  return {
    schedule_id: coerceString(raw?.schedule_id),
    experiment_name: coerceString(raw?.experiment_name),
    experiment_path: coerceString(raw?.experiment_path),
    schedule_type: coerceString(raw?.schedule_type || 'once') as ScheduledExperiment['schedule_type'],
    interval_hours: raw?.interval_hours ?? null,
    start_time: raw?.start_time ?? null,
    estimated_duration: coerceNumber(raw?.estimated_duration, 0),
    created_by: coerceString(raw?.created_by || 'system'),
    created_at: coerceString(raw?.created_at || ''),
    updated_at: coerceString(raw?.updated_at || raw?.created_at || ''),
    is_active: Boolean(raw?.is_active ?? true),
    retry_config: {
      max_retries: coerceNumber(retryConfig.max_retries, 3),
      retry_delay_minutes: coerceNumber(retryConfig.retry_delay_minutes, 2),
      backoff_strategy: (retryConfig.backoff_strategy || 'linear') as 'linear' | 'exponential',
    },
    prerequisites: Array.isArray(raw?.prerequisites) ? raw.prerequisites : [],
    notification_contacts: Array.isArray(raw?.notification_contacts) ? raw.notification_contacts : [],
    failed_execution_count: coerceNumber(raw?.failed_execution_count, 0),
    recovery_required: Boolean(raw?.recovery_required),
    recovery_note: coerceOptionalString(raw?.recovery_note),
    recovery_marked_at: raw?.recovery_marked_at ?? null,
    recovery_marked_by: coerceOptionalString(raw?.recovery_marked_by),
    recovery_resolved_at: raw?.recovery_resolved_at ?? null,
    recovery_resolved_by: coerceOptionalString(raw?.recovery_resolved_by),
    next_run: raw?.next_run ?? raw?.start_time ?? null,
    last_run: raw?.last_run ?? null,
  };
};

const normalizeSchedules = (payload: unknown): ScheduledExperiment[] => {
  if (!Array.isArray(payload)) {
    return [];
  }
  return payload.map(normalizeSchedule);
};

const normalizeManualRecovery = (payload: unknown): ManualRecoveryState | null => {
  if (!payload || typeof payload !== 'object') {
    return null;
  }
  const data = payload as Record<string, unknown>;
  return {
    active: Boolean(data.active),
    note: coerceOptionalString(data.note),
    schedule_id: coerceOptionalString(data.schedule_id),
    experiment_name: coerceOptionalString(data.experiment_name),
    triggered_by: coerceOptionalString(data.triggered_by),
    triggered_at: coerceOptionalString(data.triggered_at),
    resolved_by: coerceOptionalString(data.resolved_by),
    resolved_at: coerceOptionalString(data.resolved_at),
  };
};

const normalizeNotificationContact = (payload: any): NotificationContact => ({
  contact_id: coerceString(payload?.contact_id),
  display_name: coerceString(payload?.display_name),
  email_address: coerceString(payload?.email_address),
  is_active: Boolean(payload?.is_active ?? true),
  created_at: coerceOptionalString(payload?.created_at),
  updated_at: coerceOptionalString(payload?.updated_at),
});


const normalizeNotificationSettings = (payload: any): NotificationSettings => ({
  host: coerceOptionalString(payload?.host),
  port: coerceNumber(payload?.port, 587),
  username: coerceOptionalString(payload?.username),
  sender: coerceOptionalString(payload?.sender),
  use_tls: payload?.use_tls === undefined ? true : Boolean(payload.use_tls),
  use_ssl: payload?.use_ssl === undefined ? false : Boolean(payload.use_ssl),
  has_password: Boolean(payload?.has_password),
  updated_at: coerceOptionalString(payload?.updated_at),
  updated_by: coerceOptionalString(payload?.updated_by),
  encryption_ready: payload?.encryption_ready === undefined ? undefined : Boolean(payload?.encryption_ready),
});

const normalizeNotificationLog = (payload: any): NotificationLogEntry => ({
  log_id: coerceString(payload?.log_id),
  schedule_id: coerceOptionalString(payload?.schedule_id),
  execution_id: coerceOptionalString(payload?.execution_id),
  event_type: coerceString(payload?.event_type),
  status: coerceString(payload?.status),
  subject: coerceOptionalString(payload?.subject),
  message: coerceOptionalString(payload?.message),
  recipients: Array.isArray(payload?.recipients) ? payload.recipients.map((value: unknown) => coerceString(value)) : [],
  attachments: Array.isArray(payload?.attachments) ? payload.attachments.map((value: unknown) => coerceString(value)) : [],
  error_message: coerceOptionalString(payload?.error_message),
  triggered_at: coerceOptionalString(payload?.triggered_at),
  processed_at: coerceOptionalString(payload?.processed_at),
  metadata:
    payload?.metadata && typeof payload.metadata === 'object'
      ? (payload.metadata as Record<string, unknown>)
      : null,
});

const normalizeCalendarEvents = (payload: unknown): CalendarEvent[] => {
  if (!Array.isArray(payload)) {
    return [];
  }
  return payload.map((event) => ({
    event_id: coerceString(event?.event_id ?? event?.id),
    schedule_id: coerceString(event?.schedule_id ?? event?.id),
    title: coerceString(event?.title ?? event?.experiment_name),
    description: coerceString(event?.description ?? ''),
    start_time: coerceString(event?.start_time ?? event?.start),
    end_time: coerceString(event?.end_time ?? event?.end),
    event_type: coerceString(event?.event_type ?? 'scheduled') as CalendarEvent['event_type'],
    experiment_name: coerceString(event?.experiment_name ?? event?.title),
    estimated_duration: coerceNumber(event?.estimated_duration, 0),
    status: coerceString(event?.status ?? 'scheduled'),
    created_by: coerceString(event?.created_by ?? 'system'),
  }));
};

const normalizeConflicts = (payload: unknown): Record<string, ConflictInfo[]> => {
  if (!payload || typeof payload !== 'object') {
    return {};
  }
  return Object.entries(payload as Record<string, unknown>).reduce<Record<string, ConflictInfo[]>>(
    (acc, [key, value]) => {
      if (Array.isArray(value)) {
        acc[key] = value as ConflictInfo[];
      }
      return acc;
    },
    {},
  );
};

const normalizeQueueStatus = (payload: unknown): { queue?: QueueStatus; hamilton?: HamiltonStatus; manual_recovery?: ManualRecoveryState | null } => {
  if (!payload || typeof payload !== 'object') {
    return {};
  }
  const data = payload as { queue?: QueueStatus; hamilton?: HamiltonStatus; manual_recovery?: unknown };
  return {
    queue: data.queue,
    hamilton: data.hamilton,
    manual_recovery: normalizeManualRecovery(data.manual_recovery),
  };
};

const normalizeEvoYeastExperiments = (payload: unknown): EvoYeastExperimentOption[] => {
  if (!Array.isArray(payload)) {
    return [];
  }

  return payload.map((item) => {
    const experimentId = coerceString(item?.ExperimentID ?? item?.experiment_id);
    const userDefinedId = coerceOptionalString(item?.UserDefinedID ?? item?.user_defined_id);
    const note = coerceOptionalString(item?.Note ?? item?.note);
    const experimentName = coerceOptionalString(
      item?.ExperimentName ?? item?.experiment_name ?? userDefinedId ?? note,
    );

    return {
      experiment_id: experimentId,
      experiment_name: experimentName,
      user_defined_id: userDefinedId,
      note,
      scheduled_to_run: Boolean(item?.ScheduledToRun ?? item?.scheduled_to_run),
    };
  });
};

const parseAPIError = (error: unknown): string => {
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
  return 'Request failed';
};

export const schedulingAPI = {
  createSchedule: (data: CreateScheduleRequest) =>
    api.post<ScheduleCreateResponse>('/api/scheduling/create', data),

  getSchedules: (activeOnly = true) =>
    api.get<ScheduleListResponse>('/api/scheduling/list', { params: { active_only: activeOnly } }),

  getSchedule: (scheduleId: string) => api.get<ScheduleResponse>(`/api/scheduling/${scheduleId}`),

  updateSchedule: (scheduleId: string, data: UpdateScheduleRequest) =>
    api.put<ScheduleResponse>(`/api/scheduling/${scheduleId}`, data),

  deleteSchedule: (scheduleId: string) => api.delete<ScheduleResponse>(`/api/scheduling/${scheduleId}`),

  requireRecovery: (scheduleId: string, note?: string) =>
    api.post<RecoveryActionResponse>(`/api/scheduling/${scheduleId}/recovery/require`, note ? { note } : {}),

  resolveRecovery: (scheduleId: string, note?: string) =>
    api.post<RecoveryActionResponse>(`/api/scheduling/${scheduleId}/recovery/resolve`, note ? { note } : {}),

  getUpcomingSchedules: (hoursAhead = 48) =>
    api.get<ScheduleListResponse>('/api/scheduling/upcoming', { params: { hours_ahead: hoursAhead } }),

  getCalendarData: (startDate?: string, endDate?: string) =>
    api.get<CalendarDataResponse>(
      '/api/scheduling/calendar',
      {
        params: {
          ...(startDate ? { start_date: startDate } : {}),
          ...(endDate ? { end_date: endDate } : {}),
        },
      },
    ),

  getQueueStatus: () => api.get<QueueStatusResponse>('/api/scheduling/status/queue'),

  getSchedulerStatus: () => api.get<SchedulerServiceResponse>('/api/scheduling/status/scheduler'),

  checkConflicts: (request: ConflictCheckRequest) =>
    api.post<ConflictCheckResponse>('/api/scheduling/conflicts/check', request.experiments),

  startScheduler: () => api.post<SchedulerServiceResponse>('/api/scheduling/start-scheduler'),

  stopScheduler: () => api.post<SchedulerServiceResponse>('/api/scheduling/stop-scheduler'),

  getAvailableExperiments: (rescan = false) =>
    api.get('/api/scheduling/experiments/available', { params: { rescan } }),

  getAvailablePrerequisites: () => api.get('/api/scheduling/experiments/prerequisites'),

  getEvoYeastExperiments: (limit = 100) => api.get('/api/scheduling/experiments/evo-yeast', { params: { limit } }),

  importExperimentFiles: (files: any[]) => api.post('/api/scheduling/experiments/import-files', { files }),

  importExperimentFolder: (folderPath: string) =>
    api.post('/api/scheduling/experiments/import-folder', { folder_path: folderPath }),

  getExecutionHistory: (scheduleId?: string, limit = 50) =>
    api.get('/api/scheduling/executions/history', {
      params: {
        schedule_id: scheduleId,
        limit,
      },
    }),

  getScheduleExecutionSummary: (scheduleId: string) =>
    api.get(`/api/scheduling/executions/summary/${scheduleId}`),

  getRecentExecutions: (hours = 24) =>
    api.get('/api/scheduling/executions/recent', { params: { hours } }),

  getNotificationSettings: () =>
    api.get('/api/scheduling/notifications/settings'),

  updateNotificationSettings: (payload: Record<string, unknown>) =>
    api.put('/api/scheduling/notifications/settings', payload),

  getNotificationContacts: (includeInactive = true) =>
    api.get('/api/scheduling/contacts', { params: { include_inactive: includeInactive } }),

  createNotificationContact: (payload: NotificationContactPayload) =>
    api.post('/api/scheduling/contacts', payload),

  updateNotificationContact: (contactId: string, payload: NotificationContactPayload) =>
    api.put(`/api/scheduling/contacts/${contactId}`, payload),

  deleteNotificationContact: (contactId: string) =>
    api.delete(`/api/scheduling/contacts/${contactId}`),

  getNotificationLogs: (params?: NotificationLogQuery & { limit?: number }) =>
    api.get('/api/scheduling/notifications/logs', { params }),
};

const buildScheduleRequest = (data: CreateScheduleFormData): CreateScheduleRequest => ({
  experiment_name: data.experiment_name,
  experiment_path: data.experiment_path,
  schedule_type: data.schedule_type,
  interval_hours: data.schedule_type === 'interval' ? data.interval_hours : undefined,
  start_time: serializeMaybeDate(data.start_time),
  estimated_duration: data.estimated_duration,
  is_active: data.is_active,
  retry_config: {
    max_retries: data.max_retries,
    retry_delay_minutes: data.retry_delay_minutes,
    backoff_strategy: data.backoff_strategy,
  },
  prerequisites: data.prerequisites,
  notification_contacts: data.notification_contacts,
});

export const schedulingService = {
  async getAllSchedules(activeOnly = true): Promise<{ schedules: ScheduledExperiment[]; error?: string }> {
    try {
      const { data } = await schedulingAPI.getSchedules(activeOnly);
      if (!data.success) {
        return { schedules: [], error: data.message || 'Failed to load schedules' };
      }
      return { schedules: normalizeSchedules(data.data) };
    } catch (error) {
      return { schedules: [], error: parseAPIError(error) };
    }
  },

  async createSchedule(data: CreateScheduleFormData): Promise<{ scheduleId?: string; error?: string }> {
    try {
      const payload = buildScheduleRequest(data);
      const { data: response } = await schedulingAPI.createSchedule(payload);
      if (!response.success) {
        return { error: response.message || 'Failed to create schedule' };
      }
      return { scheduleId: response.data?.schedule_id };
    } catch (error) {
      return { error: parseAPIError(error) };
    }
  },

  async updateSchedule(
    scheduleId: string,
    data: CreateScheduleFormData,
  ): Promise<{ schedule?: ScheduledExperiment; error?: string }> {
    try {
      const payload: UpdateScheduleRequest = buildScheduleRequest(data);
      const { data: response } = await schedulingAPI.updateSchedule(scheduleId, payload);
      if (!response.success || !response.data) {
        return { error: response.message || 'Failed to update schedule' };
      }
      return { schedule: normalizeSchedule(response.data) };
    } catch (error) {
      return { error: parseAPIError(error) };
    }
  },

  async deleteSchedule(scheduleId: string): Promise<{ success: boolean; error?: string }> {
    try {
      const { data } = await schedulingAPI.deleteSchedule(scheduleId);
      if (!data.success) {
        return { success: false, error: data.message || 'Failed to delete schedule' };
      }
      return { success: true };
    } catch (error) {
      return { success: false, error: parseAPIError(error) };
    }
  },

  async getNotificationSettings(): Promise<{ settings?: NotificationSettings; error?: string }> {
    try {
      const { data } = await schedulingAPI.getNotificationSettings();
      if (!data.success) {
        return { error: data.message || 'Failed to load notification settings' };
      }
      return { settings: normalizeNotificationSettings(data.data) };
    } catch (error) {
      return { error: parseAPIError(error) };
    }
  },

  async updateNotificationSettings(
    payload: NotificationSettingsUpdatePayload,
  ): Promise<{ settings?: NotificationSettings; error?: string }> {
    try {
      const request: Record<string, unknown> = {
        host: payload.host,
        port: payload.port,
        sender: payload.sender,
        use_tls: payload.use_tls,
        use_ssl: payload.use_ssl,
      };
      if (payload.username !== undefined) {
        request.username = payload.username;
      }
      if (Object.prototype.hasOwnProperty.call(payload, 'password')) {
        request.password = payload.password;
      }
      const { data } = await schedulingAPI.updateNotificationSettings(request);
      if (!data.success) {
        return { error: data.message || 'Failed to update notification settings' };
      }
      return { settings: normalizeNotificationSettings(data.data) };
    } catch (error) {
      return { error: parseAPIError(error) };
    }
  },

  async getNotificationContacts(includeInactive = true): Promise<{ contacts: NotificationContact[]; error?: string }> {
    try {
      const { data } = await schedulingAPI.getNotificationContacts(includeInactive);
      if (!data.success) {
        return { contacts: [], error: data.message || 'Failed to load contacts' };
      }
      const contacts = Array.isArray(data.data) ? data.data.map(normalizeNotificationContact) : [];
      return { contacts };
    } catch (error) {
      return { contacts: [], error: parseAPIError(error) };
    }
  },

  async createNotificationContact(
    payload: NotificationContactPayload,
  ): Promise<{ contact?: NotificationContact; error?: string }> {
    try {
      const { data } = await schedulingAPI.createNotificationContact(payload);
      if (!data.success || !data.data) {
        return { error: data.message || 'Failed to create contact' };
      }
      return { contact: normalizeNotificationContact(data.data) };
    } catch (error) {
      return { error: parseAPIError(error) };
    }
  },

  async updateNotificationContact(
    contactId: string,
    payload: NotificationContactPayload,
  ): Promise<{ contact?: NotificationContact; error?: string }> {
    try {
      const { data } = await schedulingAPI.updateNotificationContact(contactId, payload);
      if (!data.success || !data.data) {
        return { error: data.message || 'Failed to update contact' };
      }
      return { contact: normalizeNotificationContact(data.data) };
    } catch (error) {
      return { error: parseAPIError(error) };
    }
  },

  async deleteNotificationContact(contactId: string): Promise<{ success: boolean; error?: string }> {
    try {
      const { data } = await schedulingAPI.deleteNotificationContact(contactId);
      if (!data.success) {
        return { success: false, error: data.message || 'Failed to delete contact' };
      }
      return { success: true };
    } catch (error) {
      return { success: false, error: parseAPIError(error) };
    }
  },

  async getNotificationLogs(
    params?: NotificationLogQuery & { limit?: number },
  ): Promise<{ logs: NotificationLogEntry[]; error?: string }> {
    try {
      const { data } = await schedulingAPI.getNotificationLogs(params);
      if (!data.success) {
        return { logs: [], error: data.message || 'Failed to load notification logs' };
      }
      const logs = Array.isArray(data.data) ? data.data.map(normalizeNotificationLog) : [];
      return { logs };
    } catch (error) {
      return { logs: [], error: parseAPIError(error) };
    }
  },

  async requireRecovery(
    scheduleId: string,
    note?: string,
  ): Promise<{ schedule?: ScheduledExperiment; manualRecovery?: ManualRecoveryState | null; error?: string }> {
    try {
      const { data } = await schedulingAPI.requireRecovery(scheduleId, note);
      if (!data.success || !data.data) {
        return { error: data.message || 'Failed to mark recovery requirement' };
      }
      const schedulePayload = data.data?.schedule;
      const manualState = normalizeManualRecovery(data.data?.manual_recovery);
      return {
        schedule: schedulePayload ? normalizeSchedule(schedulePayload) : undefined,
        manualRecovery: manualState ?? null,
      };
    } catch (error) {
      return { error: parseAPIError(error) };
    }
  },

  async resolveRecovery(
    scheduleId: string,
    note?: string,
  ): Promise<{ schedule?: ScheduledExperiment; manualRecovery?: ManualRecoveryState | null; error?: string }> {
    try {
      const { data } = await schedulingAPI.resolveRecovery(scheduleId, note);
      if (!data.success || !data.data) {
        return { error: data.message || 'Failed to resolve recovery' };
      }
      const schedulePayload = data.data?.schedule;
      const manualState = normalizeManualRecovery(data.data?.manual_recovery);
      return {
        schedule: schedulePayload ? normalizeSchedule(schedulePayload) : undefined,
        manualRecovery: manualState ?? null,
      };
    } catch (error) {
      return { error: parseAPIError(error) };
    }
  },

  async getCalendarData(
    startDate?: Date,
    endDate?: Date,
  ): Promise<{ events: CalendarEvent[]; error?: string }> {
    try {
      const { data } = await schedulingAPI.getCalendarData(
        startDate ? startDate.toISOString() : undefined,
        endDate ? endDate.toISOString() : undefined,
      );
      if (!data.success) {
        return { events: [], error: data.message || 'Failed to load calendar' };
      }
      return { events: normalizeCalendarEvents(data.data) };
    } catch (error) {
      return { events: [], error: parseAPIError(error) };
    }
  },

  async checkConflicts(
    request: ConflictCheckRequest,
  ): Promise<{ conflicts: Record<string, ConflictInfo[]>; error?: string }> {
    try {
      const { data } = await schedulingAPI.checkConflicts(request);
      if (!data.success) {
        return { conflicts: {}, error: data.message || 'Failed to check conflicts' };
      }
      return { conflicts: normalizeConflicts(data.data) };
    } catch (error) {
      return { conflicts: {}, error: parseAPIError(error) };
    }
  },

  async getQueueStatus(): Promise<{
    queueStatus?: QueueStatus;
    hamiltonStatus?: HamiltonStatus;
    manualRecovery?: ManualRecoveryState | null;
    error?: string;
  }> {
    try {
      const { data } = await schedulingAPI.getQueueStatus();
      if (!data.success) {
        return { error: data.message || 'Failed to load queue status' };
      }
      const { queue, hamilton, manual_recovery } = normalizeQueueStatus(data.data);
      return { queueStatus: queue, hamiltonStatus: hamilton, manualRecovery: manual_recovery ?? null };
    } catch (error) {
      return { error: parseAPIError(error) };
    }
  },

  async controlScheduler(action: 'start' | 'stop'): Promise<{ success: boolean; status?: string; manualRecovery?: ManualRecoveryState | null; error?: string }> {
    try {
      const { data } = action === 'start'
        ? await schedulingAPI.startScheduler()
        : await schedulingAPI.stopScheduler();
      if (!data.success) {
        return { success: false, error: data.message || 'Scheduler command failed' };
      }
      const manualState = normalizeManualRecovery(data.data?.manual_recovery);
      return { success: true, status: data.data?.status, manualRecovery: manualState ?? null };
    } catch (error) {
      return { success: false, error: parseAPIError(error) };
    }
  },
  async getEvoYeastExperiments(limit = 100): Promise<{ experiments: EvoYeastExperimentOption[]; error?: string }> {
    try {
      const { data } = await schedulingAPI.getEvoYeastExperiments(limit);
      if (!data.success) {
        return { experiments: [], error: data.message || 'Failed to load EvoYeast experiments' };
      }
      return { experiments: normalizeEvoYeastExperiments(data.data?.experiments) };
    } catch (error) {
      return { experiments: [], error: parseAPIError(error) };
    }
  },

};




