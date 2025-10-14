/**
 * RobotControl Database Backup/Restore TypeScript Interfaces
 * 
 * Type definitions for database backup and restore functionality.
 * Mirrors the backend Python data models to ensure type safety across the full stack.
 */

// Core backup information interface
export interface BackupInfo {
  filename: string;
  description: string;
  timestamp: string;
  created_date: string;
  file_size: number;
  file_size_formatted: string;
  is_valid: boolean;
  database_name?: string | null;
  sql_server?: string | null;
}

// Backup operation result interface
export interface BackupResult {
  success: boolean;
  message: string;
  filename?: string | null;
  file_size?: number | null;
  duration_ms?: number | null;
  error_details?: string | null;
}

// Restore operation result interface
export interface RestoreResult {
  success: boolean;
  message: string;
  backup_filename: string;
  duration_ms?: number | null;
  warnings?: string[] | null;
  error_details?: string | null;
}

// Detailed backup information interface
export interface BackupDetails {
  filename: string;
  description: string;
  timestamp: string;
  created_date: string;
  file_size: number;
  file_size_formatted: string;
  database_name: string;
  sql_server: string;
  metadata: Record<string, any>;
  is_valid: boolean;
}

// Delete operation result interface
export interface DeleteBackupResult {
  success: boolean;
  message: string;
  files_deleted?: string[];
  errors?: string[];
}

// API Request types
export interface CreateBackupRequest {
  description: string;
}

// Standardized API response wrapper (to prevent axios response.data vs response.data.data issues)
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message: string;
  metadata?: Record<string, any>;
}

// API Response types for all endpoints
export interface BackupListResponse extends ApiResponse<BackupInfo[]> {
  metadata: {
    count: number;
  };
}

export interface BackupCreateResponse extends ApiResponse<BackupResult> {}

export interface BackupDetailsResponse extends ApiResponse<BackupDetails> {}

export interface RestoreResponse extends ApiResponse<RestoreResult> {}

export interface DeleteResponse extends ApiResponse<DeleteBackupResult> {}

// Backup service health status
export interface BackupHealthStatus {
  service_status: string;
  backup_directory: {
    path: string;
    exists: boolean;
    writable: boolean;
  };
  database_config: {
    server: string;
    database: string;
  };
  backup_count: number;
  last_check: string;
}

export interface BackupHealthResponse extends ApiResponse<BackupHealthStatus> {}

// Backup operation status for UI state management
export enum BackupOperationStatus {
  Idle = 'idle',
  Creating = 'creating',
  Restoring = 'restoring',
  Deleting = 'deleting',
  Loading = 'loading',
  Error = 'error'
}

// UI state interfaces
export interface BackupUIState {
  backups: BackupInfo[];
  selectedBackup: BackupInfo | null;
  operationStatus: BackupOperationStatus;
  loading: boolean;
  error: string | null;
  lastRefresh: Date | null;
}

// Form interfaces for backup operations
export interface CreateBackupFormData {
  description: string;
}

export interface RestoreConfirmationData {
  backup: BackupInfo;
  userConfirmed: boolean;
  acknowledged: boolean;
}

// Error handling interfaces
export interface BackupError {
  code: string;
  message: string;
  details?: string;
  timestamp: Date;
}

// Validation interfaces
export interface BackupValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

// Component prop interfaces
export interface BackupListProps {
  backups: BackupInfo[];
  selectedBackup: BackupInfo | null;
  onBackupSelect: (backup: BackupInfo | null) => void;
  onRefresh: () => void;
  loading?: boolean;
  error?: string | null;
}

export interface BackupActionsProps {
  selectedBackup: BackupInfo | null;
  onCreateBackup: (description: string) => void;
  onRestoreBackup: (backup: BackupInfo) => void;
  onDeleteBackup: (backup: BackupInfo) => void;
  operationStatus: BackupOperationStatus;
  disabled?: boolean;
}

export interface BackupDetailsDialogProps {
  backup: BackupDetails | null;
  open: boolean;
  onClose: () => void;
}

// Hook return types
export interface UseBackupReturn {
  state: BackupUIState;
  actions: {
    loadBackups: () => Promise<void>;
    createBackup: (description: string) => Promise<BackupResult>;
    restoreBackup: (filename: string) => Promise<RestoreResult>;
    deleteBackup: (filename: string) => Promise<DeleteBackupResult>;
    getBackupDetails: (filename: string) => Promise<BackupDetails | null>;
    clearError: () => void;
    selectBackup: (backup: BackupInfo | null) => void;
  };
}

// Constants for validation and UI
export const BACKUP_CONSTANTS = {
  MAX_DESCRIPTION_LENGTH: 1000,
  MIN_DESCRIPTION_LENGTH: 1,
  REFRESH_INTERVAL_MS: 30000, // 30 seconds
  ALLOWED_FILE_EXTENSIONS: ['.bak'],
  BACKUP_FILE_PATTERN: /^[a-zA-Z0-9_-]+_\d{8}_\d{6}\.bak$/,
} as const;

// Type guards for runtime type checking
export const isBackupInfo = (obj: any): obj is BackupInfo => {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    typeof obj.filename === 'string' &&
    typeof obj.description === 'string' &&
    typeof obj.timestamp === 'string' &&
    typeof obj.created_date === 'string' &&
    typeof obj.file_size === 'number' &&
    typeof obj.file_size_formatted === 'string' &&
    typeof obj.is_valid === 'boolean'
  );
};

export const isApiResponse = <T>(obj: any): obj is ApiResponse<T> => {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    typeof obj.success === 'boolean' &&
    'data' in obj &&
    typeof obj.message === 'string'
  );
};

// Utility types
export type BackupOperationType = 'create' | 'restore' | 'delete' | 'details';

export type BackupSortField = 'filename' | 'created_date' | 'file_size' | 'description';

export type BackupSortOrder = 'asc' | 'desc';

export interface BackupSortOptions {
  field: BackupSortField;
  order: BackupSortOrder;
}

// Date formatting utilities for backup timestamps
export const formatBackupDate = (isoString: string): string => {
  try {
    return new Date(isoString).toLocaleString();
  } catch {
    return 'Invalid Date';
  }
};

export const formatBackupTimestamp = (timestamp: string): string => {
  try {
    // Convert YYYYMMDD_HHMMSS format to readable date
    const year = timestamp.substring(0, 4);
    const month = timestamp.substring(4, 6);
    const day = timestamp.substring(6, 8);
    const hour = timestamp.substring(9, 11);
    const minute = timestamp.substring(11, 13);
    const second = timestamp.substring(13, 15);
    
    const date = new Date(`${year}-${month}-${day}T${hour}:${minute}:${second}`);
    return date.toLocaleString();
  } catch {
    return timestamp; // Return original if parsing fails
  }
};