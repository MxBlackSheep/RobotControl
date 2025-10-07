/**
 * SystemStatus Component - Real-time system monitoring dashboard
 * Displays experiment status, system health metrics, and database connectivity
 */

import React, { useEffect, useState, useMemo, memo } from 'react';
import AccessibleStatusIndicator from './AccessibleStatusIndicator';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import LinearProgress from '@mui/material/LinearProgress';
import Chip from '@mui/material/Chip';
import LoadingSpinner from './LoadingSpinner';
import ErrorAlert from './ErrorAlert';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import ListItemIcon from '@mui/material/ListItemIcon';
import Divider from '@mui/material/Divider';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import {
  Refresh as RefreshIcon,
  Science as ExperimentIcon,
  Storage as DatabaseIcon,
  Wifi as ConnectionIcon,
  WifiOff as ConnectionOffIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import useMonitoring, { ExperimentData, SystemHealth, DatabaseStatus } from '../hooks/useMonitoring';

// Component props
interface SystemStatusProps {
  compact?: boolean; // For use in smaller spaces like dashboard widgets
  autoRefresh?: boolean; // Enable automatic refresh
  refreshInterval?: number; // Refresh interval in seconds
}

// Enhanced status mapping with accessibility features
const getAccessibleStatus = (status?: string) => {
  const normalizedStatus = (status ?? "unknown").toString().toUpperCase();
  
  switch (normalizedStatus) {
    case 'RUNNING':
    case 'CONNECTED':
    case 'ACTIVE':
      return {
        type: 'success' as const,
        animate: true,
        ariaLabel: `${status} - System is operating normally`
      };
    case 'COMPLETED':
    case 'OK':
      return {
        type: 'success' as const,
        animate: false,
        ariaLabel: `${status} - Operation completed successfully`
      };
    case 'FAILED':
    case 'ERROR':
    case 'OFFLINE':
      return {
        type: 'error' as const,
        animate: false,
        ariaLabel: `${status} - System error detected`
      };
    case 'PENDING':
    case 'DISCONNECTED':
    case 'WARNING':
      return {
        type: 'warning' as const,
        animate: false,
        ariaLabel: `${status} - Attention required`
      };
    case 'IDLE':
    case 'STANDBY':
      return {
        type: 'info' as const,
        animate: false,
        ariaLabel: `${status} - System ready`
      };
    default:
      return {
        type: 'neutral' as const,
        animate: false,
        ariaLabel: `Status: ${status}`
      };
  }
};

// Format bytes to human readable format
const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// Format timestamp to relative time
const formatRelativeTime = (timestamp: string): string => {
  const now = new Date();
  const time = new Date(timestamp);
  const diff = now.getTime() - time.getTime();
  const seconds = Math.floor(diff / 1000);
  
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
};

// Experiment Status Card
interface ExperimentStatusCardProps {
  experiments: ExperimentData[];
  compact?: boolean;
}

const ExperimentStatusCard: React.FC<ExperimentStatusCardProps> = memo(({ experiments, compact = false }) => {
  const runningExperiments = useMemo(() => 
    experiments.filter(exp => exp.status === 'RUNNING'), 
    [experiments]
  );
  const recentExperiments = useMemo(() => 
    experiments.slice(0, compact ? 3 : 5), 
    [experiments, compact]
  );

  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" mb={2}>
          <ExperimentIcon color="primary" sx={{ mr: 1 }} />
          <Typography variant="h6">
            Experiments
          </Typography>
          <Chip 
            label={`${runningExperiments.length} Running`}
            color={runningExperiments.length > 0 ? 'success' : 'default'}
            size="small"
            sx={{ ml: 'auto' }}
          />
        </Box>

        {experiments.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No experiment data available
          </Typography>
        ) : (
          <List dense={compact}>
            {recentExperiments.map((experiment, index) => (
              <React.Fragment key={experiment.id || index}>
                <ListItem>
                  <ListItemIcon>
                    <AccessibleStatusIndicator
                      status={getAccessibleStatus(experiment.status).type}
                      label={experiment.status}
                      variant="chip"
                      size="small"
                      animate={getAccessibleStatus(experiment.status).animate}
                      ariaLabel={getAccessibleStatus(experiment.status).ariaLabel}
                    />
                  </ListItemIcon>
                  <ListItemText
                    primary={experiment.method_name || 'Unknown Method'}
                    secondary={
                      <Box>
                        <Typography variant="caption" display="block">
                          Started: {experiment.start_time ? formatRelativeTime(experiment.start_time) : 'Unknown'}
                        </Typography>
                        {experiment.end_time && (
                          <Typography variant="caption" display="block">
                            Ended: {formatRelativeTime(experiment.end_time)}
                          </Typography>
                        )}
                        {experiment.progress !== undefined && (
                          <LinearProgress 
                            variant="determinate" 
                            value={experiment.progress} 
                            sx={{ mt: 1 }}
                          />
                        )}
                      </Box>
                    }
                  />
                </ListItem>
                {index < recentExperiments.length - 1 && <Divider />}
              </React.Fragment>
            ))}
          </List>
        )}
      </CardContent>
    </Card>
  );
});

// Database Status Card
interface DatabaseStatusCardProps {
  databaseStatus: DatabaseStatus | null;
  compact?: boolean;
}

const DatabaseStatusCard: React.FC<DatabaseStatusCardProps> = memo(({ databaseStatus, compact = false }) => {
  if (!databaseStatus) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <DatabaseIcon color="primary" sx={{ mr: 1 }} />
            <Typography variant="h6">Database</Typography>
            <AccessibleStatusIndicator
              status="warning"
              label="Unknown"
              variant="chip"
              size="small"
              sx={{ ml: 'auto' }}
              ariaLabel="Database status unknown - connection may be unavailable"
            />
          </Box>
          <Typography variant="body2" color="text.secondary">
            Database status unavailable
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const statusInfo = useMemo(() => ({
    color: databaseStatus.is_connected ? 'success' as const : 'error' as const,
    icon: databaseStatus.is_connected ? <CheckIcon /> : <ErrorIcon />,
    text: databaseStatus.is_connected ? 'Connected' : 'Disconnected',
  }), [databaseStatus.is_connected]);

  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" mb={2}>
          <DatabaseIcon color="primary" sx={{ mr: 1 }} />
          <Typography variant="h6">Database</Typography>
          <Chip 
            icon={statusInfo.icon}
            label={statusInfo.text}
            color={statusInfo.color}
            size="small"
            sx={{ ml: 'auto' }}
          />
        </Box>

        <Stack spacing={1}>
          <Box display="flex" justifyContent="space-between">
            <Typography variant="body2" color="text.secondary">Mode:</Typography>
            <Typography variant="body2">{databaseStatus.mode.toUpperCase()}</Typography>
          </Box>
          
          <Box display="flex" justifyContent="space-between">
            <Typography variant="body2" color="text.secondary">Database:</Typography>
            <Typography variant="body2">{databaseStatus.database_name}</Typography>
          </Box>
          
          <Box display="flex" justifyContent="space-between">
            <Typography variant="body2" color="text.secondary">Server:</Typography>
            <Typography variant="body2">{databaseStatus.server_name}</Typography>
          </Box>

          {databaseStatus.error_message && (
            <ErrorAlert
              message={databaseStatus.error_message}
              severity="error"
              category="server"
              compact={true}
              sx={{ mt: 1 }}
            />
          )}
        </Stack>
      </CardContent>
    </Card>
  );
});

// Main SystemStatus Component
const SystemStatus: React.FC<SystemStatusProps> = memo(({ 
  compact = false,
  autoRefresh = true,
  refreshInterval = 30,
}) => {
  const {
    experiments,
    systemHealth,
    databaseStatus,
    isConnected,
    isLoading,
    error,
    connectionRetries,
    refreshData,
    resetError,
    connect,
  } = useMonitoring();

  // Auto refresh timer
  useEffect(() => {
    if (autoRefresh && !isConnected) {
      const interval = setInterval(() => {
        refreshData();
      }, refreshInterval * 1000);

      return () => clearInterval(interval);
    }
  }, [autoRefresh, refreshInterval, isConnected, refreshData]);

  const handleRefresh = async () => {
    resetError();
    await refreshData();
  };

  const handleReconnect = () => {
    resetError();
    connect();
  };

  const lastUpdatedLabel = systemHealth?.timestamp ? `Updated ${formatRelativeTime(systemHealth.timestamp)}` : 'No recent metrics';

  // Memoized values for performance metrics
  return (
    <Box>
      {/* Header with connection status and refresh button */}
      <Box display="flex" alignItems="center" mb={2}>
        <Typography variant={compact ? "h6" : "h5"} component="h2" sx={{ flexGrow: 1 }}>
          System Status
        </Typography>
        
        <Box display="flex" alignItems="center" gap={1}>
          {/* Connection Status */}
          <Tooltip title={`WebSocket ${isConnected ? 'Connected' : 'Disconnected'}`}>
            {isConnected ? (
              <ConnectionIcon color="success" />
            ) : (
              <ConnectionOffIcon color="error" />
            )}
          </Tooltip>

          {/* Connection retries indicator */}
          {connectionRetries > 0 && (
            <Chip 
              label={`Retry ${connectionRetries}`}
              size="small"
              color="warning"
            />
          )}

          <Chip
            label={lastUpdatedLabel}
            size="small"
            variant="outlined"
          />

          {/* Refresh button */}
          <Tooltip title="Refresh Data">
            <IconButton 
              onClick={handleRefresh}
              disabled={isLoading}
              size="small"
            >
              {isLoading ? (
                <LoadingSpinner variant="inline" size="small" />
              ) : (
                <RefreshIcon />
              )}
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Error Alert */}
      {error && (
        <ErrorAlert
          message={error}
          severity="error"
          category="network"
          retryable={true}
          onRetry={handleReconnect}
          sx={{ mb: 2 }}
        />
      )}

      {/* Status Cards */}
      <Grid container spacing={compact ? 2 : 3}>
        {/* Experiments */}
        <Grid item xs={12} lg={compact ? 12 : 6}>
          <ExperimentStatusCard experiments={experiments} compact={compact} />
        </Grid>

        {/* Database Status */}
        <Grid item xs={12} lg={compact ? 12 : 6}>
          <DatabaseStatusCard databaseStatus={databaseStatus} compact={compact} />
        </Grid>
      </Grid>


    </Box>
  );
});

// Add display name for debugging
SystemStatus.displayName = 'SystemStatus';
ExperimentStatusCard.displayName = 'ExperimentStatusCard';
DatabaseStatusCard.displayName = 'DatabaseStatusCard';

export default SystemStatus;