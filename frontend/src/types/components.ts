/**
 * Component TypeScript Interfaces - Comprehensive type definitions
 * 
 * Centralized type definitions for all PyRobot components
 * Provides type safety, better IntelliSense, and developer experience
 */

import React from 'react';
import { SxProps, Theme } from '@mui/material/styles';

// =====================================
// Base Component Interfaces
// =====================================

/** Base props that most components should have */
export interface BaseComponentProps {
  /** Component className for styling */
  className?: string;
  /** Material-UI sx prop for custom styling */
  sx?: SxProps<Theme>;
  /** Component children */
  children?: React.ReactNode;
  /** Component ID for testing/accessibility */
  id?: string;
  /** Data test ID for testing */
  'data-testid'?: string;
}

/** Props for components with loading states */
export interface LoadingComponentProps extends BaseComponentProps {
  loading?: boolean;
  loadingMessage?: string;
  loadingVariant?: 'spinner' | 'skeleton' | 'linear' | 'fullscreen';
}

/** Props for components with error handling */
export interface ErrorComponentProps extends BaseComponentProps {
  error?: string | null;
  onError?: (error: string) => void;
  onRetry?: () => void;
  retryable?: boolean;
}

/** Combined props for components with loading and error states */
export interface AsyncComponentProps extends LoadingComponentProps, ErrorComponentProps {}

// =====================================
// Data Model Interfaces
// =====================================

/** Database-related interfaces */
export namespace Database {
  export interface TableInfo {
    name: string;
    schema: string;
    row_count: number;
    is_important?: boolean;
    created_date?: string;
    modified_date?: string;
  }

  export interface ConnectionStatus {
    connected: boolean;
    database: string;
    server: string;
    mode: 'primary' | 'secondary' | 'mock';
    error_message?: string;
  }

  export interface TableData {
    columns: string[];
    data: any[][];
    total_rows: number;
    page?: number;
    page_size?: number;
  }

  export interface QueryResult {
    success: boolean;
    data?: TableData;
    error?: string;
    execution_time_ms?: number;
  }
}

/** Camera-related interfaces */
export namespace Camera {
  export interface CameraInfo {
    id: string;
    name: string;
    url: string;
    status: 'online' | 'offline' | 'error';
    resolution: string;
    fps: number;
    last_frame_time?: string;
    error_message?: string;
  }

  export interface VideoFile {
    filename: string;
    timestamp: string;
    size_bytes: number;
    duration?: number;
    path?: string;
  }

  export interface ExperimentFolder {
    folder_name: string;
    video_count: number;
    total_size_bytes: number;
    creation_time: string;
    videos: VideoFile[];
  }

  export interface StreamingSession {
    session_id: string;
    camera_id: string;
    camera_name: string;
    client_count: number;
    bandwidth_mbps: number;
    start_time: string;
    status: 'active' | 'starting' | 'stopping' | 'error';
  }

  export interface StreamingStatus {
    enabled: boolean;
    active_session_count: number;
    max_sessions: number;
    total_bandwidth_mbps: number;
    resource_usage_percent: number;
    sessions: StreamingSession[];
  }

  export interface SystemStatus {
    storage_info?: {
      total_space_gb: number;
      used_space_gb: number;
      available_space_gb: number;
    };
    paths?: {
      rolling_clips: string;
      experiments: string;
    };
  }
}

/** Scheduling-related interfaces */
export namespace Scheduling {
  export interface Schedule {
    id: string;
    name: string;
    experiment_name: string;
    start_time: string;
    end_time?: string;
    interval_minutes?: number;
    repeat_count: number;
    is_recurring: boolean;
    enabled: boolean;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
    description?: string;
    priority: 'low' | 'medium' | 'high';
    max_retries: number;
    retry_delay_minutes: number;
    created_at: string;
    updated_at: string;
    next_run_time?: string;
    last_run_time?: string;
  }

  export interface ExecutionRecord {
    execution_id: string;
    schedule_id: string;
    experiment_name: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    status_formatted: string;
    start_time: string;
    end_time?: string;
    duration_seconds?: number;
    error_message?: string;
    retry_count: number;
  }

  export interface SchedulerStatus {
    running: boolean;
    active_schedules: number;
    pending_executions: number;
    last_heartbeat?: string;
    uptime_seconds?: number;
  }
}

/** User and authentication interfaces */
export namespace Auth {
  export interface User {
    id: string;
    username: string;
    role: 'admin' | 'user' | 'hamilton';
    email?: string;
    created_at: string;
    last_login?: string;
    active: boolean;
  }

  export interface LoginCredentials {
    username: string;
    password: string;
  }

  export interface AuthContextValue {
    user: User | null;
    token: string | null;
    isAuthenticated: boolean;
    login: (username: string, password: string) => Promise<void>;
    logout: () => void;
    loading: boolean;
  }
}

/** System monitoring interfaces */
export namespace Monitoring {
  export interface SystemHealth {
    timestamp: string;
    cpu_percent: number;
    memory_percent: number;
    memory_used_gb: number;
    memory_total_gb: number;
    disk_percent: number;
    disk_used_gb: number;
    disk_total_gb: number;
  }

  export interface ExperimentData {
    id: string;
    method_name: string;
    start_time: string;
    end_time?: string;
    status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'PENDING';
    progress?: number;
    plate_ids?: string[];
  }

  export interface MonitoringData {
    experiments: ExperimentData[];
    system_health: SystemHealth;
    database_status: Database.ConnectionStatus;
    camera_status?: Camera.CameraInfo[];
    scheduler_status?: Scheduling.SchedulerStatus;
  }
}

// =====================================
// Component-Specific Props Interfaces
// =====================================

/** Database components */
export namespace DatabaseComponents {
  export interface DatabaseTableProps extends AsyncComponentProps {
    tableName: string;
    maxHeight?: string | number;
    pageSize?: number;
    virtualizeThreshold?: number;
    onRowClick?: (row: any, index: number) => void;
    onCellClick?: (value: any, column: string, row: any, index: number) => void;
  }

  export interface DatabasePageProps extends BaseComponentProps {
    autoRefresh?: boolean;
    refreshInterval?: number;
  }

  export interface StoredProceduresProps extends ErrorComponentProps {
    maxHeight?: string | number;
  }
}

/** Camera components */
export namespace CameraComponents {
  export interface LiveCamerasTabProps extends AsyncComponentProps {
    cameras: Camera.CameraInfo[];
    onRefresh: () => void;
    onShowStatus: () => void;
    onCameraSettings?: (camera: Camera.CameraInfo) => void;
  }

  export interface VideoArchiveTabProps extends AsyncComponentProps {
    experimentFolders: Camera.ExperimentFolder[];
    onRefresh: () => void;
    onDownloadVideo: (filename: string) => void;
    onDeleteVideo?: (filename: string) => void;
  }

  export interface LiveStreamingTabProps extends AsyncComponentProps {
    streamingStatus: Camera.StreamingStatus | null;
    onRefresh: () => void;
    onStartSession: (cameraId: string) => Promise<void>;
    onStopSession: (sessionId: string) => Promise<void>;
    availableCameras?: Array<{ id: string; name: string }>;
  }

  export interface CameraViewerProps extends AsyncComponentProps {
    camera: Camera.CameraInfo;
    autoRefresh?: boolean;
    showControls?: boolean;
  }
}

/** Scheduling components */
export namespace SchedulingComponents {
  export interface ScheduleListProps extends AsyncComponentProps {
    schedules: Scheduling.Schedule[];
    onEdit?: (schedule: Scheduling.Schedule) => void;
    onDelete?: (scheduleId: string) => void;
    onToggleEnabled?: (scheduleId: string, enabled: boolean) => void;
    onExecuteNow?: (scheduleId: string) => void;
    sortBy?: keyof Scheduling.Schedule;
    sortDirection?: 'asc' | 'desc';
  }

  export interface ScheduleFormProps extends BaseComponentProps {
    initialData?: Partial<Scheduling.Schedule>;
    onSubmit: (data: Partial<Scheduling.Schedule>) => Promise<void>;
    onCancel: () => void;
    mode: 'create' | 'edit';
  }

  export interface ExecutionHistoryProps extends AsyncComponentProps {
    scheduleId?: string;
    maxHeight?: string;
    pageSize?: number;
    onViewDetails?: (execution: Scheduling.ExecutionRecord) => void;
  }
}

/** Form and dialog components */
export namespace FormComponents {
  export interface FormFieldProps<T = any> extends BaseComponentProps {
    name: string;
    label: string;
    value: T;
    onChange: (value: T) => void;
    onBlur?: () => void;
    error?: string;
    required?: boolean;
    disabled?: boolean;
    helperText?: string;
    placeholder?: string;
  }

  export interface DialogProps extends BaseComponentProps {
    open: boolean;
    onClose: () => void;
    title?: string;
    maxWidth?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | false;
    fullWidth?: boolean;
    fullScreen?: boolean;
    disableEscapeKeyDown?: boolean;
    disableBackdropClick?: boolean;
  }

  export interface ConfirmationDialogProps extends DialogProps {
    message: string;
    confirmText?: string;
    cancelText?: string;
    severity?: 'info' | 'warning' | 'error' | 'success';
    onConfirm: () => void;
    confirmColor?: 'primary' | 'secondary' | 'error' | 'warning';
  }
}

/** Navigation and layout components */
export namespace LayoutComponents {
  export interface TabPanelProps extends BaseComponentProps {
    index: number;
    value: number;
  }

  export interface PageHeaderProps extends BaseComponentProps {
    title: string;
    subtitle?: string;
    icon?: React.ReactNode;
    actions?: React.ReactNode;
    breadcrumbs?: Array<{ label: string; href?: string }>;
  }

  export interface SidebarProps extends BaseComponentProps {
    open: boolean;
    onClose: () => void;
    items: Array<{
      label: string;
      path: string;
      icon?: React.ReactNode;
      disabled?: boolean;
    }>;
    currentPath: string;
  }
}

/** Shared UI components */
export namespace SharedComponents {
  export interface LoadingSpinnerProps extends BaseComponentProps {
    variant?: 'spinner' | 'skeleton' | 'linear' | 'inline' | 'fullscreen';
    size?: 'small' | 'medium' | 'large' | number;
    message?: string;
    color?: 'primary' | 'secondary' | 'inherit';
    thickness?: number;
    minHeight?: string | number;
  }

  export interface ErrorAlertProps extends BaseComponentProps {
    message: string;
    severity?: 'error' | 'warning' | 'info' | 'success';
    category?: 'network' | 'authentication' | 'authorization' | 'validation' | 'server' | 'client' | 'timeout' | 'unknown';
    title?: string;
    closable?: boolean;
    retryable?: boolean;
    onRetry?: () => void | Promise<void>;
    onClose?: () => void;
    actions?: React.ReactNode;
    detailed?: boolean;
    details?: string;
    autoHideDuration?: number;
    fullWidth?: boolean;
    compact?: boolean;
    retrying?: boolean;
  }

  export interface StatusChipProps extends BaseComponentProps {
    status: string;
    variant?: 'filled' | 'outlined';
    size?: 'small' | 'medium';
    colorMapping?: Record<string, 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'>;
  }

  export interface DataTableProps<T = any> extends AsyncComponentProps {
    data: T[];
    columns: Array<{
      key: keyof T;
      label: string;
      width?: number;
      align?: 'left' | 'center' | 'right';
      sortable?: boolean;
      render?: (value: any, row: T, index: number) => React.ReactNode;
    }>;
    rowHeight?: number;
    height?: number;
    virtualized?: boolean;
    onRowClick?: (row: T, index: number) => void;
    onCellClick?: (value: any, column: keyof T, row: T, index: number) => void;
    onSort?: (column: keyof T, direction: 'asc' | 'desc') => void;
    sortColumn?: keyof T;
    sortDirection?: 'asc' | 'desc';
    stickyHeader?: boolean;
    pageSize?: number;
    currentPage?: number;
    totalCount?: number;
    onPageChange?: (page: number) => void;
  }
}

// =====================================
// Event Handler Types
// =====================================

/** Common event handler types */
export type ClickHandler = (event: React.MouseEvent) => void;
export type ChangeHandler<T = string> = (value: T) => void;
export type SubmitHandler<T = any> = (data: T) => Promise<void> | void;
export type ValidationHandler<T = any> = (data: T) => Promise<Record<string, string> | null> | Record<string, string> | null;

/** Async operation handlers */
export type AsyncOperation<T = void> = () => Promise<T>;
export type AsyncOperationWithData<TInput, TOutput = void> = (data: TInput) => Promise<TOutput>;

// =====================================
// Utility Types
// =====================================

/** Make all properties optional */
export type PartialBy<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

/** Make all properties required */
export type RequiredBy<T, K extends keyof T> = T & Required<Pick<T, K>>;

/** Extract component props type */
export type ComponentProps<T> = T extends React.ComponentType<infer P> ? P : never;

/** API response wrapper type */
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
  metadata?: {
    page?: number;
    pageSize?: number;
    total?: number;
    hasNext?: boolean;
    hasPrev?: boolean;
  };
};

/** Generic list response */
export interface ListResponse<T> extends ApiResponse<T[]> {
  metadata: {
    total: number;
    page: number;
    pageSize: number;
    hasNext: boolean;
    hasPrev: boolean;
  };
}

// =====================================
// Theme and Style Types
// =====================================

/** Custom theme extensions */
export interface CustomTheme extends Theme {
  custom?: {
    status: {
      success: string;
      warning: string;
      error: string;
      info: string;
    };
    spacing: {
      xs: number;
      sm: number;
      md: number;
      lg: number;
      xl: number;
    };
  };
}

/** Responsive props helper */
export type ResponsiveStyleValue<T> = T | { xs?: T; sm?: T; md?: T; lg?: T; xl?: T };

// =====================================
// Validation and Runtime Types
// =====================================

/** Runtime validation schema */
export type ValidationSchema<T> = {
  [K in keyof T]?: {
    required?: boolean;
    type?: 'string' | 'number' | 'boolean' | 'array' | 'object' | 'function';
    minLength?: number;
    maxLength?: number;
    min?: number;
    max?: number;
    pattern?: RegExp;
    custom?: (value: T[K]) => string | null;
  };
}

/** Form validation result */
export interface ValidationResult {
  isValid: boolean;
  errors: Record<string, string>;
}

// =====================================
// Export commonly used type unions
// =====================================

export type ComponentSize = 'small' | 'medium' | 'large';
export type ComponentVariant = 'filled' | 'outlined' | 'standard';
export type ComponentColor = 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning';
export type ComponentStatus = 'idle' | 'loading' | 'success' | 'error';
export type SortDirection = 'asc' | 'desc';
export type UserRole = 'admin' | 'user' | 'hamilton';
export type DatabaseMode = 'primary' | 'secondary' | 'mock';
export type CameraStatus = 'online' | 'offline' | 'error';
export type ScheduleStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type ExecutionStatus = 'pending' | 'running' | 'completed' | 'failed';
export type Priority = 'low' | 'medium' | 'high';