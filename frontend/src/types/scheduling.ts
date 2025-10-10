/**
 * PyRobot Scheduling TypeScript Interfaces
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
  created_by: string;
  created_at: string; // ISO format
  updated_at: string; // ISO format
  is_active: boolean;
  retry_config: RetryConfig;
  prerequisites: string[];
  notification_contacts: string[];
  failed_execution_count?: number;
  recovery_required: boolean;
  recovery_note?: string | null;
  recovery_marked_at?: string | null;
  recovery_marked_by?: string | null;
  recovery_resolved_at?: string | null;
  recovery_resolved_by?: string | null;
  next_run?: string | null; // ISO format
  last_run?: string | null; // ISO format
}

export interface RetryConfig {
  max_retries: number;
  retry_delay_minutes: number;
  backoff_strategy: 'linear' | 'exponential';
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
export interface ManualRecoveryState {
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
}

export interface NotificationSettingsUpdatePayload {
  host: string;
  port: number;
  username?: string | null;
  sender: string;
  use_tls: boolean;
  use_ssl: boolean;
  password?: string | null;
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
  running_jobs: number;
  max_parallel_jobs: number;
  capacity_available: boolean;
  running_job_details: RunningJobDetail[];
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
  is_active?: boolean;
  retry_config?: {
    max_retries?: number;
    retry_delay_minutes?: number;
    backoff_strategy?: 'linear' | 'exponential';
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
  is_active?: boolean;
  retry_config?: {
    max_retries?: number;
    retry_delay_minutes?: number;
    backoff_strategy?: 'linear' | 'exponential';
  };
  prerequisites?: string[];
  notification_contacts?: string[];
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
  selectedSchedule: ScheduledExperiment | null;
  operationStatus: SchedulingOperationStatus;
  loading: boolean;
  error: string | null;
  lastRefresh: Date | null;
  calendarEvents: CalendarEvent[];
  queueStatus: QueueStatus | null;
  hamiltonStatus: HamiltonStatus | null;
  schedulerRunning: boolean;
  manualRecovery: ManualRecoveryState | null;
  initialized: boolean;
}

// Form interfaces
export interface CreateScheduleFormData {
  experiment_name: string;
  experiment_path: string;
  schedule_type: 'once' | 'hourly' | 'daily' | 'weekly' | 'interval';
  interval_hours?: number;
  start_time?: Date | null;
  estimated_duration: number;
  is_active: boolean;
  max_retries: number;
  retry_delay_minutes: number;
  backoff_strategy: 'linear' | 'exponential';
  prerequisites: string[];
  notification_contacts: string[];
}

export interface EditScheduleFormData extends CreateScheduleFormData {
  schedule_id: string;
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
  loading?: boolean;
  error?: string | null;
  initialized: boolean;
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

export interface CalendarViewProps {
  events: CalendarEvent[];
  settings: CalendarViewSettings;
  onSettingsChange: (settings: CalendarViewSettings) => void;
  onEventClick: (event: CalendarEvent) => void;
  loading?: boolean;
}

export interface QueueMonitorProps {
  queueStatus: QueueStatus | null;
  hamiltonStatus: HamiltonStatus | null;
  onRefresh: () => void;
  loading?: boolean;
}

export interface ConflictDetectorProps {
  onCheckConflicts: (experiments: ConflictCheckRequest) => void;
  conflicts: Record<string, ConflictInfo[]> | null;
  loading?: boolean;
}

// Hook return types
export interface UseSchedulingReturn {
  state: SchedulingUIState;
  actions: {
    loadSchedules: (activeOnly?: boolean, focusScheduleId?: string | null) => Promise<void>;
    createSchedule: (data: CreateScheduleFormData) => Promise<void>;
    updateSchedule: (scheduleId: string, data: UpdateScheduleRequest) => Promise<void>;
    deleteSchedule: (scheduleId: string) => Promise<void>;
    requireRecovery: (scheduleId: string, note?: string) => Promise<void>;
    resolveRecovery: (scheduleId: string, note?: string) => Promise<void>;
    getQueueStatus: () => Promise<void>;
    getSchedulerStatus: () => Promise<void>;
    getCalendarData: (startDate?: Date, endDate?: Date) => Promise<{ events: CalendarEvent[]; error?: string }>;
    checkConflicts: (request: ConflictCheckRequest) => Promise<{ conflicts: Record<string, ConflictInfo[]>; error?: string }>;
    getExecutionHistory: (scheduleId?: string, limit?: number) => Promise<any[]>;
    getScheduleExecutionSummary: (scheduleId: string) => Promise<any>;
    selectSchedule: (schedule: ScheduledExperiment | null) => void;
    clearError: () => void;
  };
}

export interface UseCalendarReturn {
  events: CalendarEvent[];
  settings: CalendarViewSettings;
  loading: boolean;
  error: string | null;
  actions: {
    loadCalendarData: (startDate?: Date, endDate?: Date) => Promise<void>;
    updateSettings: (settings: Partial<CalendarViewSettings>) => void;
    refresh: () => Promise<void>;
  };
}

// Constants and validation
export const SCHEDULING_CONSTANTS = {
  MIN_ESTIMATED_DURATION: 1, // minutes
  MAX_ESTIMATED_DURATION: 1440, // 24 hours
  MIN_INTERVAL_HOURS: 1,
  MAX_INTERVAL_HOURS: 168, // 1 week
  MAX_RETRY_ATTEMPTS: 10,
  MIN_RETRY_DELAY: 1, // minutes
  MAX_RETRY_DELAY: 1440, // 24 hours
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

export const BACKOFF_STRATEGY_OPTIONS = [
  { value: 'linear' as const, label: 'Linear (Fixed Delay)' },
  { value: 'exponential' as const, label: 'Exponential (Growing Delay)' },
] as const;

// Type guards for runtime type checking
export const isScheduledExperiment = (obj: any): obj is ScheduledExperiment => {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    typeof obj.schedule_id === 'string' &&
    typeof obj.experiment_name === 'string' &&
    typeof obj.experiment_path === 'string' &&
    typeof obj.schedule_type === 'string' &&
    typeof obj.estimated_duration === 'number' &&
    typeof obj.created_by === 'string' &&
    typeof obj.created_at === 'string' &&
    typeof obj.updated_at === 'string' &&
    typeof obj.is_active === 'boolean' &&
    typeof obj.retry_config === 'object' &&
    Array.isArray(obj.prerequisites) &&
    typeof obj.recovery_required === 'boolean'
  );
};

export const isCalendarEvent = (obj: any): obj is CalendarEvent => {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    typeof obj.event_id === 'string' &&
    typeof obj.schedule_id === 'string' &&
    typeof obj.title === 'string' &&
    typeof obj.start_time === 'string' &&
    typeof obj.end_time === 'string' &&
    typeof obj.event_type === 'string' &&
    typeof obj.experiment_name === 'string' &&
    typeof obj.estimated_duration === 'number'
  );
};

export const isJobExecution = (obj: any): obj is JobExecution => {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    typeof obj.execution_id === 'string' &&
    typeof obj.schedule_id === 'string' &&
    typeof obj.experiment_name === 'string' &&
    typeof obj.status === 'string' &&
    typeof obj.retry_count === 'number' &&
    typeof obj.created_at === 'string'
  );
};

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

export const formatExecutionStatus = (status: string): { text: string; color: string } => {
  switch (status.toLowerCase()) {
    case 'pending':
      return { text: 'Pending', color: '#f59e0b' }; // amber
    case 'running':
      return { text: 'Running', color: '#3b82f6' }; // blue
    case 'completed':
      return { text: 'Completed', color: '#10b981' }; // emerald
    case 'failed':
      return { text: 'Failed', color: '#ef4444' }; // red
    case 'cancelled':
      return { text: 'Cancelled', color: '#6b7280' }; // gray
    default:
      return { text: status, color: '#6b7280' };
  }
};

export const getNextExecutionTime = (schedule: ScheduledExperiment): Date | null => {
  if (schedule.recovery_required) return null;

  const reference = schedule.next_run ?? schedule.start_time;
  if (!reference) return null;

  const parsed = new Date(reference);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  if (schedule.schedule_type === "interval" && schedule.interval_hours) {
    const intervalMs = schedule.interval_hours * 60 * 60 * 1000;
    if (intervalMs <= 0) {
      return null;
    }

    const nowMs = Date.now();
    const startMs = parsed.getTime();
    if (startMs > nowMs) {
      return parsed;
    }

    const intervalsElapsed = Math.floor((nowMs - startMs) / intervalMs) + 1;
    const nextMs = startMs + intervalsElapsed * intervalMs;
    return new Date(nextMs);
  }

  return parsed > new Date() ? parsed : null;
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
  
  if (data.max_retries < 0 || data.max_retries > SCHEDULING_CONSTANTS.MAX_RETRY_ATTEMPTS) {
    errors.push(`Max retries must be between 0 and ${SCHEDULING_CONSTANTS.MAX_RETRY_ATTEMPTS}`);
  }
  
  if (data.retry_delay_minutes < SCHEDULING_CONSTANTS.MIN_RETRY_DELAY || 
      data.retry_delay_minutes > SCHEDULING_CONSTANTS.MAX_RETRY_DELAY) {
    errors.push(`Retry delay must be between ${SCHEDULING_CONSTANTS.MIN_RETRY_DELAY} and ${SCHEDULING_CONSTANTS.MAX_RETRY_DELAY} minutes`);
  }
  
  return errors;
};
