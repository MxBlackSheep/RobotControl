import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Stack,
  Chip,
  LinearProgress,
  Tooltip,
  IconButton,
  Badge
} from '@mui/material';
import {
  Computer as HamiltonIcon,
  Schedule as SchedulerIcon,
  QueueMusic as QueueIcon,
  Refresh as RefreshIcon,
  CheckCircle as OnlineIcon,
  Error as OfflineIcon,
  Warning as WarningIcon
} from '@mui/icons-material';
import { useIntelligentStatusMonitor } from '../hooks/useIntelligentStatusMonitor';

interface IntelligentStatusMonitorProps {
  compact?: boolean;
  refreshInterval?: number; // in milliseconds
  showLastUpdate?: boolean;
  enabled?: boolean;
}

export const IntelligentStatusMonitor: React.FC<IntelligentStatusMonitorProps> = ({
  compact = false,
  refreshInterval = 5000, // 5 seconds default
  showLastUpdate = true,
  enabled = true
}) => {
  const {
    queueStatus,
    hamiltonStatus,
    schedulerStatus,
    loading,
    error,
    lastUpdate,
    refreshStatus,
    clearError,
    isMonitoring
  } = useIntelligentStatusMonitor({ refreshInterval, enabled });

  const formatLastUpdate = (date: Date | null) => {
    if (!date) return 'Never';
    const now = new Date();
    const diff = Math.floor((now.getTime() - date.getTime()) / 1000);
    
    if (diff < 10) return 'Just now';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return date.toLocaleTimeString();
  };

  const getHamiltonStatusColor = () => {
    if (!hamiltonStatus) return 'default';
    if (hamiltonStatus.availability === 'available' && hamiltonStatus.process_count === 0) return 'success';
    if (hamiltonStatus.availability === 'busy') return 'warning';
    return 'error';
  };

  const getHamiltonStatusIcon = () => {
    const color = getHamiltonStatusColor();
    if (color === 'success') return <OnlineIcon color="success" fontSize="small" />;
    if (color === 'warning') return <WarningIcon color="warning" fontSize="small" />;
    return <OfflineIcon color="error" fontSize="small" />;
  };

  const getSchedulerStatusColor = () => {
    if (!schedulerStatus) return 'default';
    if (schedulerStatus.is_running && schedulerStatus.thread_alive) return 'success';
    return 'error';
  };

  if (compact) {
    return (
      <Stack direction="row" spacing={1} alignItems="center">
        {/* Hamilton Status - Compact */}
        <Tooltip title={`Hamilton: ${hamiltonStatus?.availability || 'Unknown'} (${hamiltonStatus?.process_count || 0} processes)`}>
          <Chip
            icon={getHamiltonStatusIcon()}
            label={hamiltonStatus?.availability || 'Unknown'}
            color={getHamiltonStatusColor()}
            size="small"
            variant="outlined"
          />
        </Tooltip>

        {/* Queue Status - Compact */}
        {queueStatus && (
          <Tooltip title={`Queue: ${queueStatus.running_jobs} running, ${queueStatus.queued_jobs} queued`}>
            <Badge badgeContent={queueStatus.queued_jobs} color="primary">
              <QueueIcon fontSize="small" color={queueStatus.running_jobs > 0 ? 'primary' : 'disabled'} />
            </Badge>
          </Tooltip>
        )}

        {/* Scheduler Status - Compact */}
        <Tooltip title={`Scheduler: ${schedulerStatus?.is_running ? 'Running' : 'Stopped'}`}>
          <SchedulerIcon 
            fontSize="small" 
            color={getSchedulerStatusColor() === 'success' ? 'success' : 'error'} 
          />
        </Tooltip>

        {/* Refresh Button */}
        <Tooltip title={`Last update: ${formatLastUpdate(lastUpdate)}`}>
          <IconButton size="small" onClick={refreshStatus} disabled={loading}>
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    );
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
          <Typography variant="h6" component="h3">
            System Status
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            {showLastUpdate && (
              <Typography variant="caption" color="text.secondary">
                {formatLastUpdate(lastUpdate)}
              </Typography>
            )}
            <Tooltip title={isMonitoring ? `Auto-refresh every ${refreshInterval / 1000}s` : 'Monitoring disabled'}>
              <IconButton size="small" onClick={refreshStatus} disabled={loading}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>

        {loading && <LinearProgress sx={{ mb: 2 }} />}

        {error && (
          <Box mb={2}>
            <Typography variant="body2" color="error">
              {error}
            </Typography>
          </Box>
        )}

        <Stack spacing={2}>
          {/* Hamilton Robot Status */}
          <Box>
            <Stack direction="row" alignItems="center" spacing={1} mb={1}>
              <HamiltonIcon fontSize="small" />
              <Typography variant="subtitle2">Hamilton Robot</Typography>
            </Stack>
            {hamiltonStatus ? (
              <Stack direction="row" spacing={1} alignItems="center">
                {getHamiltonStatusIcon()}
                <Chip
                  label={hamiltonStatus.availability}
                  color={getHamiltonStatusColor()}
                  variant="outlined"
                  size="small"
                />
                <Typography variant="body2" color="text.secondary">
                  {hamiltonStatus.process_count} processes
                </Typography>
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Status unavailable
              </Typography>
            )}
          </Box>

          {/* Queue Status */}
          <Box>
            <Stack direction="row" alignItems="center" spacing={1} mb={1}>
              <QueueIcon fontSize="small" />
              <Typography variant="subtitle2">Execution Queue</Typography>
            </Stack>
            {queueStatus ? (
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip
                  label={`${queueStatus.running_jobs} Running`}
                  color={queueStatus.running_jobs > 0 ? 'primary' : 'default'}
                  variant="outlined"
                  size="small"
                />
                <Chip
                  label={`${queueStatus.queued_jobs} Queued`}
                  color={queueStatus.queued_jobs > 0 ? 'warning' : 'default'}
                  variant="outlined"
                  size="small"
                />
                <Typography variant="body2" color="text.secondary">
                  {queueStatus.completed_jobs} completed, {queueStatus.failed_jobs} failed
                </Typography>
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Queue status unavailable
              </Typography>
            )}
          </Box>

          {/* Scheduler Status */}
          <Box>
            <Stack direction="row" alignItems="center" spacing={1} mb={1}>
              <SchedulerIcon fontSize="small" />
              <Typography variant="subtitle2">Scheduler Engine</Typography>
            </Stack>
            {schedulerStatus ? (
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip
                  label={schedulerStatus.is_running ? 'Running' : 'Stopped'}
                  color={getSchedulerStatusColor()}
                  variant="outlined"
                  size="small"
                />
                <Typography variant="body2" color="text.secondary">
                  {schedulerStatus.active_schedules_count} schedules, {schedulerStatus.running_jobs_count} running
                </Typography>
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Scheduler status unavailable
              </Typography>
            )}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
};

export default IntelligentStatusMonitor;