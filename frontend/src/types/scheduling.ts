/** Scheduling types: the server's replies and the requests the page sends. */

/** A database package's preparation step as requested by the form: tool and inputs only. */
export interface PreparationStep {
  tool_id: string;
  inputs: Record<string, unknown>;
}

/** The step as saved: the server pins the package version, file hash and connection. */
export interface PinnedPreparation extends PreparationStep {
  package_id: string;
  tool_name?: string;
  package_version: string;
  attached_by?: string;
  attached_at?: string;
}

/** Derived on read: ready, or the package/connection changed (needs_review), or it is gone. */
export type PreparationState = 'ready' | 'needs_review' | 'missing' | 'invalid' | 'unknown';
export type ScheduleMode = 'real' | 'simulation' | 'test';
/** Test exists only for PyHSL protocols that list it. */
export const SCHEDULE_MODE_LABELS: Record<ScheduleMode, string> = { simulation: 'Simulation', test: 'Test', real: 'Real' };
export type ScheduleRunner = 'venus' | 'pyhsl';
export const RUNNER_LABELS: Record<ScheduleRunner, string> = { venus: 'VENUS', pyhsl: 'PyHSL' };
export type ScheduleType = 'once' | 'interval' | 'daily' | 'weekly';
/** The late-start action. */
export type TimeoutAction = 'continue' | 'run_cleanup_and_terminate';

export interface ScheduledExperiment {
  schedule_id: string;
  experiment_name: string;
  experiment_path: string;
  schedule_type: ScheduleType;
  interval_hours?: number | null;
  start_time?: string | null; // ISO format
  estimated_duration: number; // minutes
  log_inactivity_threshold_minutes: number;
  mode: ScheduleMode;
  runner: ScheduleRunner;
  protocol_id?: string | null;
  parameters?: Record<string, unknown>;
  created_by: string;
  created_at: string; // ISO format
  updated_at: string; // ISO format
  is_active: boolean;
  archived: boolean;
  timeout_config: TimeoutConfig;
  /** Retired adapter tokens, kept until an administrator reviews them. */
  prerequisites: string[];
  preparation?: PinnedPreparation | null;
  preparation_state?: PreparationState;
  notification_contacts: string[];
  recovery_required: boolean;
  recovery_note?: string | null;
  recovery_marked_at?: string | null;
  recovery_marked_by?: string | null;
  recovery_resolved_at?: string | null;
  recovery_resolved_by?: string | null;
  next_run?: string | null; // ISO format
  last_run?: string | null; // ISO format
  /** Set when the stored record fails its check: it never runs until it is edited or deleted. */
  review_reason?: string | null;
}

export interface TimeoutConfig {
  timeout_minutes: number | null;
  action: TimeoutAction;
  cleanup_experiment_name?: string | null;
  cleanup_experiment_path?: string | null;
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

export interface RunningJobDetail {
  schedule_id: string;
  experiment_name: string;
  experiment_path?: string | null;
  runner?: ScheduleRunner | null;
  protocol_id?: string | null;
  estimated_duration?: number | null; // minutes, entered by the user
  priority: string;
  queued_time: string; // ISO format
  retry_count: number;
  waiting_reason?: string | null;
  monitoring?: {
    state: 'waiting' | 'monitoring' | 'log_inactive' | 'monitoring_unavailable' | 'terminal';
    run_state?: string | null;
    raw_run_state?: string | null;
    run_guid?: string | null;
    launched_at?: string | null; // offset-qualified ISO time when HxRun was launched
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
  schedule_type: ScheduleType;
  interval_hours?: number;
  start_time?: string; // ISO format
  estimated_duration: number;
  log_inactivity_threshold_minutes?: number;
  mode?: ScheduleMode;
  runner?: ScheduleRunner;
  protocol_id?: string;
  parameters?: Record<string, unknown>;
  is_active?: boolean;
  timeout_config?: Partial<TimeoutConfig>;
  /** Omitted: the saved step stays. null removes it. Only a local administrator may change it. */
  preparation?: PreparationStep | null;
  notification_contacts?: string[];
}

/** The version the edit opened is the conflict check: a newer saved version answers 409. */
export type UpdateScheduleRequest = Partial<CreateScheduleRequest> & { expected_updated_at?: string };

/** What the schedule form edits; buildScheduleRequest turns it into the create or update body. */
export interface ScheduleFormValues {
  experiment_name: string;
  experiment_path: string;
  schedule_type: ScheduleType;
  interval_hours: number;
  /** The datetime-local input's text, or null for none. */
  start_time: string | null;
  estimated_duration: number;
  log_inactivity_threshold_minutes: number;
  mode: ScheduleMode;
  runner: ScheduleRunner;
  protocol_id?: string;
  parameters?: Record<string, unknown>;
  is_active: boolean;
  timeout_minutes: number | null;
  timeout_action: TimeoutAction;
  timeout_cleanup_experiment_name: string | null;
  timeout_cleanup_experiment_path: string | null;
  /** Undefined until a local administrator changes the database step; then sent (null removes it). */
  preparation?: PreparationStep | null;
  notification_contacts: string[];
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


export interface QueueStatusResponse extends ApiResponse<{
  /** The scheduler service. */
  is_running: boolean;
  queue: QueueStatus;
  hamilton: HamiltonStatus;
  manual_recovery: ManualRecoveryState | null;
}> {}

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
