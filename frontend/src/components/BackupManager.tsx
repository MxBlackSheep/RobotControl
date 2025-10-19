/**
 * RobotControl Database Backup Manager Component
 * 
 * Main component combining BackupListComponent and BackupActions for complete
 * backup management functionality. Handles state management, API operations,
 * error handling, and user notifications.
 * 
 * Key Features:
 * - Unified backup list and action interface
 * - Real-time operation status tracking
 * - Comprehensive error handling with user-friendly messages  
 * - Automatic backup list refreshing
 * - Isolated failure mode (backup issues don't break other features)
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Typography,
  Paper,
  Divider,
  Stack,
  IconButton,
  Tooltip,
  CircularProgress,
  Card,
  CardContent
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  Storage as StorageIcon,
  Warning as WarningIcon,
  CheckCircle as CheckCircleIcon,
  Info as InfoIcon
} from '@mui/icons-material';

import BackupListComponent from './BackupListComponent';
import BackupActions from './BackupActions';
import ErrorAlert, { ServerError } from './ErrorAlert';
import { backupAPI, BackupApiError } from '../services/backupApi';
import {
  BackupInfo,
  BackupOperationStatus,
  BackupUIState,
  BackupResult,
  RestoreResult,
  DeleteBackupResult,
  BACKUP_CONSTANTS
} from '../types/backup';

interface BackupManagerProps {
  // Optional callbacks for parent components
  onBackupCreated?: (result: BackupResult) => void;
  onBackupRestored?: (result: RestoreResult) => void;
  onBackupDeleted?: (result: DeleteBackupResult) => void;
  onError?: (error: string) => void;
  
  // UI configuration
  autoRefresh?: boolean;
  refreshInterval?: number;
  showHealthStatus?: boolean;
}

interface NotificationState {
  open: boolean;
  message: string;
  severity: 'success' | 'error' | 'warning' | 'info';
  duration?: number;
}

const BackupManager: React.FC<BackupManagerProps> = ({
  onBackupCreated,
  onBackupRestored,
  onBackupDeleted,
  onError,
  autoRefresh = true,
  refreshInterval = BACKUP_CONSTANTS.REFRESH_INTERVAL_MS,
  showHealthStatus = true
}) => {
  // Main backup state
  const [state, setState] = useState<BackupUIState>({
    backups: [],
    selectedBackup: null,
    operationStatus: BackupOperationStatus.Idle,
    loading: true, // Start with loading true to fetch initial data
    error: null,
    lastRefresh: null
  });

  // Notification state for user feedback
  const [notification, setNotification] = useState<NotificationState>({
    open: false,
    message: '',
    severity: 'info'
  });
  const notificationTitles: Record<NotificationState['severity'], string> = {
    success: 'Success',
    error: 'Error',
    warning: 'Warning',
    info: 'Notification'
  };

  // Health status (if enabled)
  const [healthStatus, setHealthStatus] = useState<{
    loading: boolean;
    healthy: boolean;
    message: string;
  }>({
    loading: false,
    healthy: true,
    message: ''
  });

  /**
   * Show notification to user
   * CRITICAL: Always show user feedback for operations to avoid silent failures
   */
  const showNotification = useCallback((
    message: string, 
    severity: NotificationState['severity'] = 'info',
    duration?: number
  ) => {
    setNotification({
      open: true,
      message,
      severity,
      duration
    });
  }, []);

  /**
   * Update backup state safely
   */
  const updateState = useCallback((updates: Partial<BackupUIState>) => {
    setState(prevState => ({ ...prevState, ...updates }));
  }, []);

  /**
   * Clear error state
   */
  const clearError = useCallback(() => {
    updateState({ error: null });
  }, [updateState]);

  /**
   * Load backup list from API
   * CRITICAL: Proper error handling to prevent component crashes
   */
  const loadBackups = useCallback(async (options?: { quiet?: boolean }) => {
    const quiet = options?.quiet ?? false;
    try {
      updateState({ loading: true, error: null });
      
      // Use the backupAPI client which handles axios response format issues correctly
      const backupsData = await backupAPI.listBackups();
      
      updateState({
        backups: backupsData,
        loading: false,
        lastRefresh: new Date(),
        error: null
      });

      // Show success message only if this was a manual refresh
      if (!quiet && (!autoRefresh || state.lastRefresh !== null)) {
        showNotification(`Loaded ${backupsData.length} backup(s)`, 'success', 2000);
      }

    } catch (error) {
      const errorMessage = error instanceof BackupApiError 
        ? error.message 
        : 'Failed to load backup list';

      updateState({
        loading: false,
        error: errorMessage
      });

      showNotification(errorMessage, 'error', 5000);
      
      // Report error to parent if callback provided
      if (onError) {
        onError(errorMessage);
      }
    }
  }, [autoRefresh, state.lastRefresh, updateState, showNotification, onError]);

  /**
   * Create new backup
   * CRITICAL: Handle API response format correctly (response.data not response.data.data)
   */
  const handleCreateBackup = useCallback(async (description: string) => {
    try {
      updateState({ operationStatus: BackupOperationStatus.Creating });
      
      // Use the backupAPI client which properly handles response format
      const result = await backupAPI.createBackup(description);
      
      updateState({ operationStatus: BackupOperationStatus.Idle });

      if (result.success) {
        showNotification(
          `Backup created successfully: ${result.filename}`,
          'success',
          5000
        );

        // Refresh backup list to show new backup
        await loadBackups({ quiet: true });

        // Notify parent component
        if (onBackupCreated) {
          onBackupCreated(result);
        }
      } else {
        throw new Error(result.message || 'Backup creation failed');
      }

    } catch (error) {
      const errorMessage = error instanceof BackupApiError 
        ? error.message 
        : 'Failed to create backup';

      updateState({ 
        operationStatus: BackupOperationStatus.Error,
        error: errorMessage
      });

      showNotification(errorMessage, 'error', 7000);

      if (onError) {
        onError(errorMessage);
      }

      // Reset status after error display
      setTimeout(() => {
        updateState({ operationStatus: BackupOperationStatus.Idle });
      }, 3000);
    }
  }, [updateState, showNotification, loadBackups, onBackupCreated, onError]);

  /**
   * Restore from backup
   * CRITICAL: Handle database unavailability gracefully
   */
  const handleRestoreBackup = useCallback(async (backup: BackupInfo) => {
    try {
      updateState({ operationStatus: BackupOperationStatus.Restoring });
      
      // Use the backupAPI client which handles response format correctly
      const result = await backupAPI.restoreBackup(backup.filename);
      
      updateState({ operationStatus: BackupOperationStatus.Idle });

      if (result.success) {
        showNotification(
          `Database restored successfully from ${backup.filename}`,
          'success',
          7000
        );

        // Clear selection after successful restore
        updateState({ selectedBackup: null });

        // Notify parent component
        if (onBackupRestored) {
          onBackupRestored(result);
        }
      } else {
        throw new Error(result.message || 'Database restore failed');
      }

    } catch (error) {
      const errorMessage = error instanceof BackupApiError 
        ? error.message 
        : 'Failed to restore database';

      updateState({ 
        operationStatus: BackupOperationStatus.Error,
        error: errorMessage
      });

      showNotification(errorMessage, 'error', 10000);

      if (onError) {
        onError(errorMessage);
      }

      // Reset status after error display
      setTimeout(() => {
        updateState({ operationStatus: BackupOperationStatus.Idle });
      }, 3000);
    }
  }, [updateState, showNotification, onBackupRestored, onError]);

  /**
   * Delete backup
   */
  const handleDeleteBackup = useCallback(async (backup: BackupInfo) => {
    try {
      updateState({ operationStatus: BackupOperationStatus.Deleting });
      
      // Use the backupAPI client which handles response format correctly
      const result = await backupAPI.deleteBackup(backup.filename);
      
      updateState({ 
        operationStatus: BackupOperationStatus.Idle,
        selectedBackup: null // Clear selection
      });

      if (result.success) {
        showNotification(
          `Backup ${backup.filename} deleted successfully`,
          'success',
          5000
        );

        // Refresh backup list to remove deleted backup
        await loadBackups({ quiet: true });

        // Notify parent component
        if (onBackupDeleted) {
          onBackupDeleted(result);
        }
      } else {
        throw new Error(result.message || 'Backup deletion failed');
      }

    } catch (error) {
      const errorMessage = error instanceof BackupApiError 
        ? error.message 
        : 'Failed to delete backup';

      updateState({ 
        operationStatus: BackupOperationStatus.Error,
        error: errorMessage
      });

      showNotification(errorMessage, 'error', 7000);

      if (onError) {
        onError(errorMessage);
      }

      // Reset status after error display
      setTimeout(() => {
        updateState({ operationStatus: BackupOperationStatus.Idle });
      }, 3000);
    }
  }, [updateState, showNotification, loadBackups, onBackupDeleted, onError]);

  /**
   * Handle backup selection
   */
  const handleBackupSelect = useCallback((backup: BackupInfo | null) => {
    updateState({ selectedBackup: backup });
  }, [updateState]);

  /**
   * Load health status if enabled
   */
  const loadHealthStatus = useCallback(async () => {
    if (!showHealthStatus) return;

    try {
      setHealthStatus(prev => ({ ...prev, loading: true }));
      
      const health = await backupAPI.getHealthStatus();
      
      setHealthStatus({
        loading: false,
        healthy: health.service_status === 'healthy',
        message: health.service_status === 'healthy' 
          ? `${health.backup_count} backups available`
          : health.service_status
      });

    } catch (error) {
      setHealthStatus({
        loading: false,
        healthy: false,
        message: 'Health check failed'
      });
    }
  }, [showHealthStatus]);

  /**
   * Manual refresh trigger
   */
  const handleManualRefresh = useCallback(async () => {
    await Promise.all([
      loadBackups(),
      loadHealthStatus()
    ]);
  }, [loadBackups, loadHealthStatus]);

  /**
   * Initialize component - load initial data
   */
  useEffect(() => {
    const initialize = async () => {
      await Promise.all([
        loadBackups(),
        loadHealthStatus()
      ]);
    };

    initialize();
  }, []); // Run once on mount

  /**
   * Setup auto-refresh if enabled
   */
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      // Only auto-refresh if not currently performing operations
      if (state.operationStatus === BackupOperationStatus.Idle) {
        loadBackups();
      }
    }, refreshInterval);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, state.operationStatus, loadBackups]);

  /**
   * Render health status indicator
   */
  const renderHealthStatus = () => {
    if (!showHealthStatus) return null;

    return (
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent sx={{ py: 1.5 }}>
          <Stack direction="row" alignItems="center" spacing={2}>
            {healthStatus.loading ? (
              <CircularProgress size={16} />
            ) : healthStatus.healthy ? (
              <CheckCircleIcon color="success" fontSize="small" />
            ) : (
              <WarningIcon color="warning" fontSize="small" />
            )}
            
            <Typography variant="body2" color="textSecondary">
              Backup Service: {healthStatus.message}
            </Typography>
            
            {state.lastRefresh && (
              <Typography variant="caption" color="textSecondary" sx={{ ml: 'auto' }}>
                Last updated: {state.lastRefresh.toLocaleTimeString()}
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>
    );
  };

  return (
    <Box sx={{ width: '100%' }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
        <Stack direction="row" alignItems="center" spacing={2}>
          <StorageIcon color="primary" sx={{ fontSize: 32 }} />
          <Typography variant="h4" component="h1">
            Database Backup Manager
          </Typography>
        </Stack>

        <Tooltip title="Refresh backup list and health status">
          <IconButton 
            onClick={handleManualRefresh} 
            disabled={state.loading}
            size="large"
          >
            <RefreshIcon />
          </IconButton>
        </Tooltip>
      </Stack>

      {/* Health Status */}
      {renderHealthStatus()}

      {/* Error Alert */}
      {state.error && (
          <ServerError
            title="Backup Operation Error"
            message={state.error}
            onClose={clearError}
            onRetry={handleManualRefresh}
          />
      )}

      {/* Main Content */}
      <Paper elevation={2} sx={{ overflow: 'hidden' }}>
        {/* Backup Actions */}
        <Box sx={{ p: 3, pb: 2 }}>
          <Typography variant="h6" gutterBottom>
            Backup Operations
          </Typography>
          <BackupActions
            selectedBackup={state.selectedBackup}
            onCreateBackup={handleCreateBackup}
            onRestoreBackup={handleRestoreBackup}
            onDeleteBackup={handleDeleteBackup}
            operationStatus={state.operationStatus}
            disabled={state.loading || state.operationStatus !== BackupOperationStatus.Idle}
          />
        </Box>

        <Divider />

        {/* Backup List */}
        <Box sx={{ p: 3, pt: 2 }}>
          <BackupListComponent
            backups={state.backups}
            selectedBackup={state.selectedBackup}
            onBackupSelect={handleBackupSelect}
            onRefresh={loadBackups}
            loading={state.loading}
            error={state.error}
            selectionMode="single"
            showActions={true}
          />
        </Box>
      </Paper>

      {/* Notifications */}
      {notification.open && (
        <ErrorAlert
          severity={notification.severity}
          title={notificationTitles[notification.severity]}
          message={notification.message}
          autoHideDuration={notification.duration || 6000}
          retryable={false}
          onClose={() => setNotification(prev => ({ ...prev, open: false }))}
        />
      )}
    </Box>
  );
};

export default BackupManager;
export type { BackupManagerProps };
