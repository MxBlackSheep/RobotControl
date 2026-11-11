import { api } from './api';
import { requestErrorMessage } from './requestError';
import { coalesceRead } from '../utils/coalesceRead';
import {
  ApiResponse,
  CreateScheduleRequest,
  UpdateScheduleRequest,
  ScheduleListResponse,
  ScheduleCreateResponse,
  ScheduleResponse,
  QueueStatusResponse,
  ScheduledExperiment,
  ScheduleFormValues,
  ManualRecoveryState,
  NotificationContact,
  NotificationContactPayload,
  NotificationLogEntry,
  NotificationLogQuery,
  NotificationSettings,
  NotificationSettingsUpdatePayload,
  NotificationTestEmailResponse,
  MethodPathPreview,
  MethodPathChange,
  LibraryMethod,
  HostMethodDirectory,
  MethodImportSelection,
  MethodImportPreview,
  MethodImportResult,
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

export const normalizeSchedule = (raw: any): ScheduledExperiment => {
  const timeoutConfig = raw?.timeout_config ?? {};
  const timeoutMinutesRaw = timeoutConfig.timeout_minutes;
  const timeoutMinutes =
    timeoutMinutesRaw === null || timeoutMinutesRaw === undefined || timeoutMinutesRaw === ''
      ? null
      : coerceNumber(timeoutMinutesRaw, 0);
  return {
    schedule_id: coerceString(raw?.schedule_id),
    experiment_name: coerceString(raw?.experiment_name),
    experiment_path: coerceString(raw?.experiment_path),
    schedule_type: coerceString(raw?.schedule_type || 'once') as ScheduledExperiment['schedule_type'],
    interval_hours: raw?.interval_hours ?? null,
    start_time: raw?.start_time ?? null,
    estimated_duration: coerceNumber(raw?.estimated_duration, 0),
    log_inactivity_threshold_minutes: coerceNumber(raw?.log_inactivity_threshold_minutes, 3),
    mode: coerceString(raw?.mode || 'real') as ScheduledExperiment['mode'],
    runner: raw?.runner === 'pyhsl' ? 'pyhsl' : 'venus',
    protocol_id: raw?.protocol_id ?? null,
    parameters: raw?.parameters ?? {},
    created_by: coerceString(raw?.created_by || 'system'),
    created_at: coerceString(raw?.created_at || ''),
    updated_at: coerceString(raw?.updated_at || raw?.created_at || ''),
    is_active: Boolean(raw?.is_active ?? true),
    archived: Boolean(raw?.archived ?? false),
    timeout_config: {
      timeout_minutes: timeoutMinutes,
      action:
        timeoutConfig.action === 'run_cleanup_and_terminate'
          ? 'run_cleanup_and_terminate'
          : 'continue',
      cleanup_experiment_name: coerceOptionalString(timeoutConfig.cleanup_experiment_name),
      cleanup_experiment_path: coerceOptionalString(timeoutConfig.cleanup_experiment_path),
    },
    prerequisites: Array.isArray(raw?.prerequisites) ? raw.prerequisites : [],
    preparation: raw?.preparation && typeof raw.preparation === 'object' ? raw.preparation : null,
    // An unrecognised state is shown as unknown, never as ready.
    preparation_state: raw?.preparation
      ? (['ready', 'needs_review', 'missing', 'invalid'].includes(raw?.preparation_state) ? raw.preparation_state : 'unknown')
      : undefined,
    notification_contacts: Array.isArray(raw?.notification_contacts) ? raw.notification_contacts : [],
    recovery_required: Boolean(raw?.recovery_required),
    recovery_note: coerceOptionalString(raw?.recovery_note),
    recovery_marked_at: raw?.recovery_marked_at ?? null,
    recovery_marked_by: coerceOptionalString(raw?.recovery_marked_by),
    recovery_resolved_at: raw?.recovery_resolved_at ?? null,
    recovery_resolved_by: coerceOptionalString(raw?.recovery_resolved_by),
    // Only the server's times: start_time is not a next run.
    next_run: raw?.next_run ?? null,
    last_run: raw?.last_run ?? null,
    review_reason: coerceOptionalString(raw?.review_reason),
  };
};

const normalizeSchedules = (payload: unknown): ScheduledExperiment[] => {
  if (!Array.isArray(payload)) {
    return [];
  }
  return payload.map(normalizeSchedule);
};

export const normalizeManualRecovery = (payload: unknown): ManualRecoveryState | null => {
  if (!payload || typeof payload !== 'object') {
    return null;
  }
  const data = payload as Record<string, unknown>;
  return {
    active: Boolean(data.active),
    safety_revision: typeof data.safety_revision === 'number' ? data.safety_revision : undefined,
    resume_required: Boolean(data.resume_required),
    pending_recoveries: Array.isArray(data.pending_recoveries) ? data.pending_recoveries as import('../types/scheduling').PendingRecovery[] : [],
    schedule_missing: Boolean(data.schedule_missing),
    storage_healthy: data.storage_healthy === true,
    storage_error: coerceOptionalString(data.storage_error),
    resume_block_reason: coerceOptionalString(data.resume_block_reason),
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
  manual_recovery_recipients: Array.isArray(payload?.manual_recovery_recipients)
    ? payload.manual_recovery_recipients.map((value: unknown) => coerceString(value))
    : [],
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

/** One call: the reply's data, or the server's message (else `failure`) as `error`; never throws. */
async function call<T>(request: Promise<{ data: ApiResponse<T> }>, failure: string): Promise<{ data?: T; error?: string }> {
  try {
    const { data } = await request;
    return data.success ? { data: data.data } : { error: data.message || failure };
  } catch (error) {
    return { error: requestErrorMessage(error, failure) };
  }
}

export const schedulingAPI = {
  createSchedule: (data: CreateScheduleRequest) =>
    api.post<ScheduleCreateResponse>('/api/scheduling/create', data),

  getSchedules: (activeOnly = true, archivedOnly = false) =>
    api.get<ScheduleListResponse>('/api/scheduling/list', {
      params: { active_only: activeOnly, archived_only: archivedOnly },
    }),

  updateSchedule: (scheduleId: string, data: UpdateScheduleRequest) =>
    api.put<ScheduleResponse>(`/api/scheduling/${scheduleId}`, data),

  deleteSchedule: (scheduleId: string, options?: { expectedUpdatedAt?: string | null }) => {
    const expected = options?.expectedUpdatedAt ?? undefined;
    const config = expected ? { headers: { 'If-Unmodified-Since': expected } } : undefined;
    return api.delete<ScheduleResponse>(`/api/scheduling/${scheduleId}`, config);
  },

  archiveSchedule: (scheduleId: string, archived: boolean, expectedUpdatedAt?: string) =>
    api.post<ScheduleResponse>(`/api/scheduling/${scheduleId}/archive`, { archived, expected_updated_at: expectedUpdatedAt }),

  getQueueStatus: () => coalesceRead(`queue:${localStorage.getItem('access_token')}`, () => api.get<QueueStatusResponse>('/api/scheduling/status/queue')),

  getAvailableExperiments: () =>
    api.get('/api/scheduling/experiments/available'),

  previewExperimentImport: (selection: MethodImportSelection) =>
    api.post<ApiResponse<MethodImportPreview>>('/api/scheduling/experiments/import-preview', selection, { timeout: 60000 }),

  browseMethodFolders: (path?: string) =>
    api.get<ApiResponse<HostMethodDirectory>>('/api/scheduling/experiments/browse', { params: { path }, timeout: 15000 }),

  getMethodLibrary: () => api.get<ApiResponse<{ methods: LibraryMethod[] }>>('/api/scheduling/experiments/library'),
  checkMethodPaths: (method_ids: string[]) => api.post<ApiResponse<{ outcomes: { method_id: string; success: boolean; reason?: string }[] }>>('/api/scheduling/experiments/library/check', { method_ids }, { timeout: 60000 }),
  archiveMethod: (method_id: string, archived: boolean, expected_revision: number) =>
    api.patch(`/api/scheduling/experiments/library/${encodeURIComponent(method_id)}`, { archived, expected_revision }),
  previewMethodPath: (method_id: string, new_path: string) =>
    api.post<ApiResponse<MethodPathPreview>>(`/api/scheduling/experiments/library/${encodeURIComponent(method_id)}/path-preview`, { new_path }, { timeout: 30000 }),
  changeMethodPath: (method_id: string, payload: MethodPathChange) =>
    api.post<ApiResponse<{ updated_schedule_ids: string[] }>>(`/api/scheduling/experiments/library/${encodeURIComponent(method_id)}/change-path`, payload, { timeout: 30000 }),

  importExperimentFolder: (folderPath: string, relativePaths?: string[]) =>
    api.post<ApiResponse<MethodImportResult>>('/api/scheduling/experiments/import-folder',
      { folder_path: folderPath, relative_paths: relativePaths }, { timeout: 60000 }),

  getExecutionHistory: (scheduleId?: string, limit = 50, signal?: AbortSignal) =>
    api.get('/api/scheduling/executions/history', {
      signal,
      params: {
        schedule_id: scheduleId,
        limit,
      },
    }),

  getNotificationSettings: () =>
    api.get('/api/scheduling/notifications/settings'),

  updateNotificationSettings: (payload: Record<string, unknown>) =>
    api.put('/api/scheduling/notifications/settings', payload),

  sendNotificationTestEmail: (recipient: string) =>
    api.post('/api/scheduling/notifications/settings/test', { recipient }, { timeout: 60000 }),

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

/** The create body; an update sends it with the opened version. The start time is read at the browser's offset. */
export const buildScheduleRequest = (values: ScheduleFormValues): CreateScheduleRequest => ({
  experiment_name: values.experiment_name,
  experiment_path: values.experiment_path,
  runner: values.runner,
  ...(values.runner === 'pyhsl' ? { protocol_id: values.protocol_id, parameters: values.parameters } : {}),
  schedule_type: values.schedule_type,
  interval_hours: values.schedule_type === 'interval' ? Number(values.interval_hours) : undefined,
  start_time: values.start_time ? new Date(values.start_time).toISOString() : undefined,
  estimated_duration: Number(values.estimated_duration),
  log_inactivity_threshold_minutes: Number(values.log_inactivity_threshold_minutes),
  mode: values.mode,
  is_active: values.is_active,
  timeout_config: {
    timeout_minutes: values.timeout_minutes === null ? null : Number(values.timeout_minutes),
    action: values.timeout_action,
    cleanup_experiment_name: values.timeout_action === 'run_cleanup_and_terminate' ? values.timeout_cleanup_experiment_name : null,
    cleanup_experiment_path: values.timeout_action === 'run_cleanup_and_terminate' ? values.timeout_cleanup_experiment_path : null,
  },
  ...(values.preparation !== undefined ? { preparation: values.preparation } : {}),
  notification_contacts: values.notification_contacts,
});

export const schedulingService = {
  async getAllSchedules(activeOnly = true, archivedOnly = false): Promise<{ schedules: ScheduledExperiment[]; error?: string }> {
    const { data, error } = await call(schedulingAPI.getSchedules(activeOnly, archivedOnly), 'Failed to load schedules');
    return { schedules: normalizeSchedules(data), error };
  },

  getArchivedSchedules() {
    return this.getAllSchedules(false, true);
  },

  async createSchedule(values: ScheduleFormValues): Promise<{ scheduleId?: string; error?: string }> {
    const { data, error } = await call(schedulingAPI.createSchedule(buildScheduleRequest(values)), 'Failed to create schedule');
    return { scheduleId: data?.schedule_id, error };
  },

  async deleteSchedule(scheduleId: string, expectedUpdatedAt?: string): Promise<{ error?: string }> {
    return call(schedulingAPI.deleteSchedule(scheduleId, { expectedUpdatedAt }), 'Failed to delete schedule');
  },

  async archiveSchedule(scheduleId: string, archived: boolean, expectedUpdatedAt?: string): Promise<{ error?: string }> {
    return call(schedulingAPI.archiveSchedule(scheduleId, archived, expectedUpdatedAt), 'Failed to update archive state');
  },

  async getNotificationSettings(): Promise<{ settings?: NotificationSettings; error?: string }> {
    const { data, error } = await call(schedulingAPI.getNotificationSettings(), 'Failed to load notification settings');
    return error ? { error } : { settings: normalizeNotificationSettings(data) };
  },

  async updateNotificationSettings(payload: NotificationSettingsUpdatePayload): Promise<{ settings?: NotificationSettings; error?: string }> {
    const request: Record<string, unknown> = {
      host: payload.host,
      port: payload.port,
      sender: payload.sender,
      use_tls: payload.use_tls,
      use_ssl: payload.use_ssl,
      manual_recovery_recipients: payload.manual_recovery_recipients,
    };
    if (payload.username !== undefined) {
      request.username = payload.username;
    }
    if (Object.prototype.hasOwnProperty.call(payload, 'password')) {
      request.password = payload.password;
    }
    const { data, error } = await call(schedulingAPI.updateNotificationSettings(request), 'Failed to update notification settings');
    return error ? { error } : { settings: normalizeNotificationSettings(data) };
  },

  async sendNotificationTestEmail(recipient: string): Promise<{ success: boolean; recipient?: string; warning?: string; error?: string }> {
    const { data, error } = await call<NotificationTestEmailResponse & { warning?: string }>(
      schedulingAPI.sendNotificationTestEmail(recipient), 'Failed to send test email');
    if (error) return { success: false, error };
    return { success: true, recipient: coerceString(data?.recipient, recipient), warning: data?.warning || undefined };
  },

  async getNotificationContacts(includeInactive = true): Promise<{ contacts: NotificationContact[]; error?: string }> {
    const { data, error } = await call<unknown[]>(schedulingAPI.getNotificationContacts(includeInactive), 'Failed to load contacts');
    return { contacts: Array.isArray(data) ? data.map(normalizeNotificationContact) : [], error };
  },

  async createNotificationContact(payload: NotificationContactPayload): Promise<{ contact?: NotificationContact; error?: string }> {
    const { data, error } = await call(schedulingAPI.createNotificationContact(payload), 'Failed to create contact');
    return error || !data ? { error: error || 'Failed to create contact' } : { contact: normalizeNotificationContact(data) };
  },

  async updateNotificationContact(contactId: string, payload: NotificationContactPayload): Promise<{ contact?: NotificationContact; error?: string }> {
    const { data, error } = await call(schedulingAPI.updateNotificationContact(contactId, payload), 'Failed to update contact');
    return error || !data ? { error: error || 'Failed to update contact' } : { contact: normalizeNotificationContact(data) };
  },

  async deleteNotificationContact(contactId: string): Promise<{ success: boolean; error?: string }> {
    const { error } = await call(schedulingAPI.deleteNotificationContact(contactId), 'Failed to delete contact');
    return { success: !error, error };
  },

  async getNotificationLogs(params?: NotificationLogQuery & { limit?: number }): Promise<{ logs: NotificationLogEntry[]; error?: string }> {
    const { data, error } = await call<unknown[]>(schedulingAPI.getNotificationLogs(params), 'Failed to load notification logs');
    return { logs: Array.isArray(data) ? data.map(normalizeNotificationLog) : [], error };
  },
};
