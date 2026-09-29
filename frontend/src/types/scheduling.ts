/**
 * RobotControl Scheduling TypeScript Interfaces
 * 
 * Type definitions for experiment scheduling functionality.
 * Mirrors the backend Python data models to ensure type safety across the full stack.
 */

// Core scheduling interfaces
export interface ScheduledExperiment {
  schedule_id: string;
  experiment_name: string;
  experiment_path: string;
  schedule_type: 'once' | 'hourly' | 'daily' | 'weekly' | 'interval';
  interval_hours?: number | null;
  start_time?: string | null; // ISO format
  estimated_duration: number; // minutes
  log_inactivity_threshold_minutes: number;
  created_by: string;
  created_at: string; // ISO format
  updated_at: string; // ISO format
  is_active: boolean;
  archived: boolean;
  timeout_config: TimeoutConfig;
  prerequisites: string[];
  notification_contacts: string[];
  recovery_required: boolean;
  recovery_note?: string | null;
  recovery_marked_at?: string | null;
  recovery_marked_by?: string | null;
  recovery_resolved_at?: string | null;
  recovery_resolved_by?: string | null;
  next_run?: string | null; // ISO format
  last_run?: string | null; // ISO format
}

export interface TimeoutConfig {
  timeout_minutes: number | null;
  action: 'continue' | 'run_cleanup_and_terminate';
  cleanup_experiment_name?: string | null;
  cleanup_experiment_path?: string | null;
}

export interface JobExecution {
  execution_id: string;
  schedule_id: string;
  experiment_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  started_at?: string | null; // ISO format
  completed_at?: string | null; // ISO format
  duration_seconds?: number | null;
  exit_code?: number | null;
  error_message?: string | null;
  hamilton_command?: string | null;
  retry_count: number;
  created_at: string; // ISO format
}

export interface CalendarEvent {
  event_id: string;
  schedule_id: string;
  title: string;
  description: string;
  start_time: string; // ISO format
  end_time: string; // ISO format
  event_type: 'scheduled' | 'running' | 'completed' | 'failed';
  experiment_name: string;
  estimated_duration: number;
  status: string;
  created_by: string;
}

// Conflict detection interfaces
export interface ConflictInfo {
  conflict_type: 'time_overlap' | 'resource_conflict' | 'hamilton_busy' | 'dependency_conflict';
  conflicting_schedule_ids: string[];
  message: string;
  suggested_resolution: string;
  alternative_times: string[]; // ISO format
  severity: 'low' | 'medium' | 'high' | 'critical';
}

export interface ConflictCheckRequest {
  experiments: Array<{
    schedule_id?: string;
    experiment_name: string;
    experiment_path?: string;
    schedule_type?: string;
    start_time?: string; // ISO format
    estimated_duration?: number;
  }>;
}

// Manual recovery state
export interface PendingRecovery {
  schedule_id: string | null;
  experiment_name?: string | null;
  note?: string | null;
  triggered_by?: string | null;
  triggered_at?: string | null;
  schedule_missing: boolean;
  archived: boolean;
}

export interface ManualRecoveryState {
  safety_revision?: number;
  resume_required?: boolean;
  pending_recoveries?: PendingRecovery[];
  schedule_missing?: boolean;
  storage_healthy?: boolean;
  storage_error?: string | null;
  resume_block_reason?: string | null;
  active: boolean;
  note?: string | null;
  schedule_id?: string | null;
  experiment_name?: string | null;
  triggered_by?: string | null;
  triggered_at?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
}

export interface NotificationContact {
  contact_id: string;
  display_name: string;
  email_address: string;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface NotificationSettings {
  host: string | null;
  port: number;
  username: string | null;
  sender: string | null;
  use_tls: boolean;
  use_ssl: boolean;
  has_password: boolean;
  updated_at?: string | null;
  updated_by?: string | null;
  manual_recovery_recipients: string[];
}

export interface MethodImportSelection {
  folder_path: string;
  relative_paths?: string[];
}

export interface HostMethodDirectory {
  current_path: string | null;
  parent_path: string | null;
  drives: string[];
  shortcuts: string[];
  breadcrumbs: { name: string; path: string }[];
  folders: { name: string; path: string; linked: boolean }[];
  methods: { name: string; path: string }[];
}

export interface MethodImportRow {
  archived?: boolean;
  name: string;
  relative_path: string;
  path: string | null;
  size?: number | null;
  last_modified?: string | null;
  action?: 'new' | 'update' | 'invalid';
  status?: 'added' | 'updated' | 'failed';
  reason?: string | null;
}

export type MethodPathStatus = 'available' | 'missing' | 'inaccessible' | 'invalid' | 'not_checked';
export interface MethodReference {
  schedule_id: string; experiment_name: string; role: 'primary' | 'cleanup';
  is_active: boolean; archived: boolean; busy: boolean; updated_at: string;
}
export interface LibraryMethod {
  method_id: string; method_name: string; file_path: string; containing_folder: string;
  source_folder: string | null; imported_at: string; imported_by: string; revision: number;
  archived: boolean; path_status: MethodPathStatus; last_checked_at: string | null;
  validation_reason: string | null; references: MethodReference[]; schedule_count: number; duplicate_path: boolean;
}

export interface MethodPathPreview {
  method_id: string; expected_revision: number; old_path: string; new_path: string; references: MethodReference[];
}
export interface MethodPathChange {
  new_path: string; expected_revision: number;
  references: { schedule_id: string; role: 'primary' | 'cleanup'; expected_updated_at: string }[];
}

export interface MethodImportPreview {
  folder: string;
  total_found: number;
  methods: MethodImportRow[];
}

export interface MethodImportResult {
  success: boolean;
  total_found: number;
  new_methods: number;
  updated_methods: number;
  failed_methods: number;
  methods: MethodImportRow[];
  errors: string[];
}

export interface NotificationSettingsUpdatePayload {
  host: string;
  port: number;
  username?: string | null;
  sender: string;
  use_tls: boolean;
  use_ssl: boolean;
  password?: string | null;
  manual_recovery_recipients: string[];
}

export interface NotificationTestEmailResponse {
  recipient: string;
}
export interface NotificationLogEntry {
  log_id: string;
  schedule_id?: string | null;
  execution_id?: string | null;
  event_type: string;
  status: string;
  subject?: string | null;
  message?: string | null;
  recipients: string[];
  attachments: string[];
  error_message?: string | null;
  triggered_at?: string | null;
  processed_at?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface NotificationContactPayload {
  display_name: string;
  email_address: string;
  is_active?: boolean;
}

export interface NotificationLogQuery {
  schedule_id?: string;
  event_type?: string;
  status?: string;
}

// Queue management interfaces
export interface QueueStatus {
  queue_size: number;
  queued_jobs: number;
  running_jobs: number;
  max_parallel_jobs: number;
  capacity_available: boolean;
  running_job_details: RunningJobDetail[];
  queued_job_details: RunningJobDetail[];
  execution_windows: ExecutionWindow[];
  hamilton_available: boolean;
}

export interface EvoYeastExperimentOption {
  experiment_id: string;
  experiment_name?: string | null;
  user_defined_id?: string | null;
  note?: string | null;
  scheduled_to_run?: boolean;
}

export interface RunningJobDetail {
  schedule_id: string;
  experiment_name: string;
  priority: string;
  queued_time: string; // ISO format
  retry_count: number;
  waiting_reason?: string | null;
  monitoring?: {
    state: 'waiting' | 'monitoring' | 'log_inactive' | 'monitoring_unavailable' | 'terminal';
    run_state?: string | null;
    raw_run_state?: string | null;
    run_guid?: string | null;
    trace_filename?: string | null;
    last_activity_at?: string | null;
    observed_at?: string | null;
    inactivity_seconds: number;
    threshold_minutes: number;
    reason?: string | null;
  } | null;
}

export interface ExecutionWindow {
  schedule_id: string;
  experiment_name: string;
  start_time: string; // ISO format
  end_time: string; // ISO format
  is_running: boolean;
}

// Hamilton process monitoring
export interface HamiltonStatus {
  is_running: boolean;
  process_count: number;
  availability: 'available' | 'busy' | 'unknown';
  last_check: string; // ISO format
}

// API Request types
export interface CreateScheduleRequest {
  experiment_name: string;
  experiment_path: string;
  schedule_type: 'once' | 'hourly' | 'daily' | 'weekly' | 'interval';
  interval_hours?: number;
  start_time?: string; // ISO format
  estimated_duration: number;
  log_inactivity_threshold_minutes?: number;
  is_active?: boolean;
  timeout_config?: {
    timeout_minutes?: number | null;
    action?: 'continue' | 'run_cleanup_and_terminate';
    cleanup_experiment_name?: string | null;
    cleanup_experiment_path?: string | null;
  };
  prerequisites?: string[];
  notification_contacts?: string[];
}

export interface UpdateScheduleRequest {
  experiment_name?: string;
  experiment_path?: string;
  schedule_type?: 'once' | 'hourly' | 'daily' | 'weekly' | 'interval';
  interval_hours?: number;
  start_time?: string; // ISO format
  estimated_duration?: number;
  log_inactivity_threshold_minutes?: number;
  is_active?: boolean;
  timeout_config?: {
    timeout_minutes?: number | null;
    action?: 'continue' | 'run_cleanup_and_terminate';
    cleanup_experiment_name?: string | null;
    cleanup_experiment_path?: string | null;
  };
  prerequisites?: string[];
  notification_contacts?: string[];
  expected_updated_at?: string;
}

// API Response types using standardized wrapper
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message: string;
  metadata?: Record<string, any>;
}

export interface ScheduleListResponse extends ApiResponse<ScheduledExperiment[]> {
  metadata: {
    count: number;
    active_only: boolean;
    archived_only: boolean;
  };
}

export interface ScheduleCreateResponse extends ApiResponse<{
  schedule_id: string;
  experiment_name: string;
  next_execution: string | null;
}> {}

export interface ScheduleResponse extends ApiResponse<ScheduledExperiment> {}

export interface RecoveryActionResponse extends ApiResponse<{
  schedule: ScheduledExperiment;
  manual_recovery: ManualRecoveryState | null;
}> {}


export interface CalendarDataResponse extends ApiResponse<CalendarEvent[]> {
  metadata: {
    start_date: string;
    end_date: string;
    event_count: number;
  };
}

export interface ConflictCheckResponse extends ApiResponse<Record<string, ConflictInfo[]>> {
  metadata: {
    experiments_analyzed: number;
    conflicts_found: number;
  };
}

export interface QueueStatusResponse extends ApiResponse<{
  queue: QueueStatus;
  hamilton: HamiltonStatus;
  manual_recovery: ManualRecoveryState | null;
}> {}

export interface SchedulerServiceResponse extends ApiResponse<{
  status: 'running' | 'stopped';
  manual_recovery?: ManualRecoveryState | null;
}> {}

// UI state management
export enum SchedulingOperationStatus {
  Idle = 'idle',
  Creating = 'creating',
  Updating = 'updating',
  Deleting = 'deleting',
  Loading = 'loading',
  Starting = 'starting',
  Stopping = 'stopping',
  Error = 'error'
}

export interface SchedulingUIState {
  schedules: ScheduledExperiment[];
  archivedSchedules: ScheduledExperiment[];
  selectedSchedule: ScheduledExperiment | null;
  operationStatus: SchedulingOperationStatus;
  loading: boolean;
  archivedLoading: boolean;
  error: string | null;
  archivedError: string | null;
  lastRefresh: Date | null;
  calendarEvents: CalendarEvent[];
  queueStatus: QueueStatus | null;
  hamiltonStatus: HamiltonStatus | null;
  schedulerRunning: boolean;
  manualRecovery: ManualRecoveryState | null;
  initialized: boolean;
  archivedInitialized: boolean;
}

// Form interfaces
export interface CreateScheduleFormData {
  experiment_name: string;
  experiment_path: string;
  schedule_type: 'once' | 'hourly' | 'daily' | 'weekly' | 'interval';
  interval_hours?: number;
  start_time?: Date | null;
  estimated_duration: number;
  log_inactivity_threshold_minutes: number;
  is_active: boolean;
  timeout_minutes?: number | null;
  timeout_action: 'continue' | 'run_cleanup_and_terminate';
  timeout_cleanup_experiment_name?: string | null;
  timeout_cleanup_experiment_path?: string | null;
  prerequisites: string[];
  notification_contacts: string[];
}

export interface CalendarViewSettings {
  view_type: 'day' | 'week' | 'month';
  start_date: Date;
  end_date: Date;
  show_completed: boolean;
  show_failed: boolean;
}

// Component prop interfaces
export interface ScheduleListProps {
  schedules: ScheduledExperiment[];
  selectedSchedule: ScheduledExperiment | null;
  onScheduleSelect: (schedule: ScheduledExperiment | null) => void;
  onRefresh: () => void;
  onDeleteSchedule?: (schedule: ScheduledExperiment) => void;
  loading?: boolean;
  error?: string | null;
  initialized: boolean;
  archivedView?: boolean;
}

export interface ScheduleActionsProps {
  selectedSchedule: ScheduledExperiment | null;
  onCreateSchedule: (data: CreateScheduleFormData) => Promise<void>;
  onUpdateSchedule: (scheduleId: string, data: UpdateScheduleRequest) => Promise<void>;
  onDeleteSchedule: (schedule: ScheduledExperiment) => Promise<void>;
  onRequireRecovery: (scheduleId: string, note?: string) => Promise<void>;
  onResolveRecovery: (scheduleId: string, note?: string) => Promise<void>;
  operationStatus: SchedulingOperationStatus;
  disabled?: boolean;
}
// Constants and validation
export const SCHEDULING_CONSTANTS = {
  MIN_ESTIMATED_DURATION: 1, // minutes
  MAX_ESTIMATED_DURATION: 1440, // 24 hours
  MIN_INTERVAL_HOURS: 1,
  MAX_INTERVAL_HOURS: 168, // 1 week
  MIN_TIMEOUT_MINUTES: 1,
  MAX_TIMEOUT_MINUTES: 10080, // 7 days
  CALENDAR_DEFAULT_HOURS_AHEAD: 48,
  CALENDAR_MAX_HOURS_AHEAD: 168, // 1 week
  REFRESH_INTERVAL_MS: 30000, // 30 seconds
  EXPERIMENT_NAME_MAX_LENGTH: 255,
  EXPERIMENT_PATH_MAX_LENGTH: 500,
} as const;

export const SCHEDULE_TYPE_OPTIONS = [
  { value: 'once' as const, label: 'Run Once' },
  { value: 'interval' as const, label: 'Interval (Hours)' },
  { value: 'daily' as const, label: 'Daily' },
  { value: 'weekly' as const, label: 'Weekly' },
] as const;
// Utility functions
export const formatScheduleType = (scheduleType: string, intervalHours?: number): string => {
  switch (scheduleType) {
    case 'once':
      return 'Run Once';
    case 'interval':
      if (!intervalHours) {
        return 'Interval';
      }
      const totalMinutes = Math.round(intervalHours * 60);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;

      if (hours === 0) {
        const minuteLabel = minutes === 1 ? 'minute' : 'minutes';
        return `Every ${minutes} ${minuteLabel}`;
      }
      if (minutes === 0) {
        return `Every ${hours} ${hours === 1 ? 'hour' : 'hours'}`;
      }
      return `Every ${hours}h ${minutes}m`;
    case 'daily':
      return 'Daily';
    case 'weekly':
      return 'Weekly';
    case 'hourly':
      return 'Hourly';
    default:
      return scheduleType;
  }
};

export const formatDuration = (minutes: number): string => {
  if (minutes < 60) {
    return `${minutes} min`;
  }
  
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  
  if (remainingMinutes === 0) {
    return `${hours} hr`;
  }
  
  return `${hours}h ${remainingMinutes}m`;
};

export const getNextExecutionTime = (schedule: ScheduledExperiment): Date | null => {
  const reference = schedule.next_run ?? schedule.start_time;
  if (!reference) return null;

  const parsed = new Date(reference);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
};

// Validation functions
export const validateScheduleFormData = (data: CreateScheduleFormData): string[] => {
  const errors: string[] = [];
  
  if (!data.experiment_name.trim()) {
    errors.push('Experiment name is required');
  }
  
  if (data.experiment_name.length > SCHEDULING_CONSTANTS.EXPERIMENT_NAME_MAX_LENGTH) {
    errors.push(`Experiment name must be ${SCHEDULING_CONSTANTS.EXPERIMENT_NAME_MAX_LENGTH} characters or less`);
  }
  
  if (!data.experiment_path.trim()) {
    errors.push('Experiment path is required');
  }
  
  if (data.experiment_path.length > SCHEDULING_CONSTANTS.EXPERIMENT_PATH_MAX_LENGTH) {
    errors.push(`Experiment path must be ${SCHEDULING_CONSTANTS.EXPERIMENT_PATH_MAX_LENGTH} characters or less`);
  }
  
  if (!Number.isInteger(data.log_inactivity_threshold_minutes) || data.log_inactivity_threshold_minutes <= 0) {
    errors.push('Log inactivity threshold must be a positive whole number of minutes');
  }
  if (data.estimated_duration < SCHEDULING_CONSTANTS.MIN_ESTIMATED_DURATION || 
      data.estimated_duration > SCHEDULING_CONSTANTS.MAX_ESTIMATED_DURATION) {
    errors.push(`Estimated duration must be between ${SCHEDULING_CONSTANTS.MIN_ESTIMATED_DURATION} and ${SCHEDULING_CONSTANTS.MAX_ESTIMATED_DURATION} minutes`);
  }
  
  if (data.schedule_type === 'interval') {
    if (!data.interval_hours || data.interval_hours <= 0) {
      errors.push('Interval must be greater than 0 minutes');
    } else if (data.interval_hours > SCHEDULING_CONSTANTS.MAX_INTERVAL_HOURS) {
      errors.push(`Interval must be ${SCHEDULING_CONSTANTS.MAX_INTERVAL_HOURS} hours or less`);
    }
  }

  if (data.start_time && data.start_time.getTime() < Date.now()) {
    errors.push('Start time cannot be in the past');
  }

  if (data.timeout_minutes !== undefined && data.timeout_minutes !== null) {
    if (
      data.timeout_minutes < SCHEDULING_CONSTANTS.MIN_TIMEOUT_MINUTES ||
      data.timeout_minutes > SCHEDULING_CONSTANTS.MAX_TIMEOUT_MINUTES
    ) {
      errors.push(
        `Timeout must be between ${SCHEDULING_CONSTANTS.MIN_TIMEOUT_MINUTES} and ${SCHEDULING_CONSTANTS.MAX_TIMEOUT_MINUTES} minutes`,
      );
    }
  }

  if (data.timeout_action === 'run_cleanup_and_terminate' && !data.timeout_cleanup_experiment_path?.trim()) {
    errors.push('Cleanup method is required for "Run cleanup and terminate" timeout action');
  }
  
  return errors;
};
