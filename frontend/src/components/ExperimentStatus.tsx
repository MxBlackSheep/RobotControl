/**
 * ExperimentStatus Component - Safe lazy-loaded experiment display
 * Shows latest experiment from Hamilton Vector database with graceful error handling
 */

import React, { useEffect, useState, memo, useCallback, useMemo } from 'react';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import Skeleton from '@mui/material/Skeleton';
import LoadingSpinner from './LoadingSpinner';
import ErrorAlert from './ErrorAlert';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Stack from '@mui/material/Stack';
import {
  Science as ExperimentIcon,
  Refresh as RefreshIcon,
  PlayArrow as RunningIcon,
  CheckCircle as CompletedIcon,
  Error as ErrorIcon,
  Pause as PausedIcon
} from '@mui/icons-material';
import { experimentsAPI } from '../services/api';

interface ExperimentData {
  run_guid: string;
  method_name: string;
  start_time: string | null;
  end_time: string | null;
  run_state: number;
}

interface ExperimentStatusProps {
  compact?: boolean;
  autoRefresh?: boolean;
  refreshInterval?: number; // in seconds
}

// Get appropriate icon, color, and accessibility indicators for run state
const getRunStateDisplay = (runState: string | number) => {
  const state = String(runState || 'UNKNOWN').toUpperCase();
  
  switch (state) {
    case 'RUNNING':
    case 'ACTIVE':
    case '1':
    case '2':
      return { 
        icon: <RunningIcon />, 
        color: 'success' as const, 
        label: 'Running',
        pattern: 'pulse',
        bgPattern: 'linear-gradient(45deg, rgba(46, 125, 50, 0.1) 25%, transparent 25%)',
        ariaLabel: 'Experiment is currently running'
      };
    case 'COMPLETED':
    case 'FINISHED':
    case '128':  // Hamilton completed state
    case '0':
      return { 
        icon: <CompletedIcon />, 
        color: 'info' as const, 
        label: 'Completed',
        pattern: 'solid',
        bgPattern: 'none',
        ariaLabel: 'Experiment completed successfully'
      };
    case 'FAILED':
    case 'ERROR':
    case '256':  // Hamilton error state
    case '-1':
      return { 
        icon: <ErrorIcon />, 
        color: 'error' as const, 
        label: 'Failed',
        pattern: 'striped',
        bgPattern: 'repeating-linear-gradient(45deg, rgba(198, 40, 40, 0.1), rgba(198, 40, 40, 0.1) 10px, transparent 10px, transparent 20px)',
        ariaLabel: 'Experiment failed with errors'
      };
    case 'PAUSED':
    case 'STOPPED':
      return { 
        icon: <PausedIcon />, 
        color: 'warning' as const, 
        label: 'Paused',
        pattern: 'dotted',
        bgPattern: 'radial-gradient(circle, rgba(239, 108, 0, 0.1) 2px, transparent 2px)',
        ariaLabel: 'Experiment is paused or stopped'
      };
    case 'ABORTED':
    case '64':   // Hamilton aborted state
      return { 
        icon: <ErrorIcon />, 
        color: 'warning' as const, 
        label: 'Aborted',
        pattern: 'dashed',
        bgPattern: 'repeating-linear-gradient(90deg, rgba(239, 108, 0, 0.1) 0px, rgba(239, 108, 0, 0.1) 8px, transparent 8px, transparent 16px)',
        ariaLabel: 'Experiment was aborted or cancelled'
      };
    default:
      return { 
        icon: <ExperimentIcon />, 
        color: 'default' as const, 
        label: `State ${state}`,
        pattern: 'none',
        bgPattern: 'none',
        ariaLabel: `Experiment status: ${state}`
      };
  }
};

// Format timestamp to readable format
const formatTimestamp = (timestamp: string | null): string => {
  if (!timestamp) return 'Unknown';
  
  try {
    const date = new Date(timestamp);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return 'Invalid date';
  }
};

// Calculate duration between start and end times
const calculateDuration = (startTime: string | null, endTime: string | null): string => {
  if (!startTime) return 'Unknown';
  
  try {
    const start = new Date(startTime);
    const end = endTime ? new Date(endTime) : new Date();
    const diffMs = end.getTime() - start.getTime();
    
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
    
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else {
      return `${minutes}m`;
    }
  } catch {
    return 'Unknown';
  }
};

const ExperimentStatus: React.FC<ExperimentStatusProps> = memo(({
  compact = false,
  autoRefresh = true,
  refreshInterval = 60 // 60 seconds default
}) => {
  const [experiment, setExperiment] = useState<ExperimentData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const loadExperiment = useCallback(async () => {
    try {
      setError('');
      
      // Check if user is authenticated
      const token = localStorage.getItem('access_token');
      if (!token) {
        setError('Please log in to view experiment data');
        setLoading(false);
        return;
      }
      
      console.log('Making API call to experiments/latest...');
      const response = await experimentsAPI.getLatest();
      console.log('Raw response:', response);
      console.log('Response data:', response.data);
      
      if (response.data && response.data.success && response.data.data) {
        setExperiment(response.data.data);
        setLastUpdate(new Date());
        console.log('✅ Experiment loaded successfully:', response.data.data);
      } else if (response.data && response.data.success && !response.data.data) {
        // No experiments found - valid state
        setExperiment(null);
        setLastUpdate(new Date());
        console.log('ℹ️ No experiments found');
      } else {
        // API returned error
        console.log('❌ API returned error:', response.data);
        setError(response.data?.error || 'Failed to load experiment data');
      }
    } catch (err: any) {
      // Handle specific error types
      console.error('🚨 ExperimentStatus error:', err);
      console.error('Error details:', {
        message: err.message,
        status: err.response?.status,
        data: err.response?.data
      });
      
      if (err.response?.status === 403 || err.response?.status === 401) {
        setError('Authentication required - please log in');
      } else if (err.response?.status === 404) {
        setError('Experiment service not available');
      } else if (err.name === 'TimeoutError' || err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        setError('Database connection timeout - check database status');
      } else if (err.code === 'ECONNREFUSED' || err.code === 'ENOTFOUND') {
        setError('Backend service unavailable');
      } else {
        // Network or other error - fail gracefully
        setError('Experiment data temporarily unavailable');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load with delay (non-blocking for dashboard)
  useEffect(() => {
    const timer = setTimeout(() => {
      loadExperiment();
    }, 3000); // 3 second delay to let authentication complete first

    return () => clearTimeout(timer);
  }, []);

  // Auto refresh timer
  useEffect(() => {
    if (!autoRefresh || loading || error) return;

    const interval = setInterval(() => {
      loadExperiment();
    }, refreshInterval * 1000);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, loading, error]);

  const handleRefresh = () => {
    setLoading(true);
    loadExperiment();
  };

  // Loading state
  if (loading) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <ExperimentIcon color="primary" sx={{ mr: 1 }} />
            <Typography variant="h6">Latest Experiment</Typography>
            <Box sx={{ ml: 'auto' }}>
              <LoadingSpinner variant="inline" size="small" />
            </Box>
          </Box>
          <Stack spacing={1}>
            <Skeleton variant="text" width="80%" />
            <Skeleton variant="text" width="60%" />
            <Skeleton variant="rectangular" height={24} width="40%" />
          </Stack>
        </CardContent>
      </Card>
    );
  }

  // Error state
  if (error) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <ExperimentIcon color="primary" sx={{ mr: 1 }} />
            <Typography variant="h6">Latest Experiment</Typography>
            <Tooltip title="Retry">
              <IconButton onClick={handleRefresh} size="small" sx={{ ml: 'auto' }}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
          <ErrorAlert
            message={error}
            severity="warning"
            category="client"
            compact={true}
            sx={{ py: 1 }}
          />
        </CardContent>
      </Card>
    );
  }

  // No experiment state
  if (!experiment) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <ExperimentIcon color="primary" sx={{ mr: 1 }} />
            <Typography variant="h6">Latest Experiment</Typography>
            <Tooltip title="Refresh">
              <IconButton onClick={handleRefresh} size="small" sx={{ ml: 'auto' }}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
          <Typography variant="body2" color="text.secondary">
            No experiments found
          </Typography>
          {lastUpdate && (
            <Typography variant="caption" color="text.secondary">
              Last checked: {lastUpdate.toLocaleTimeString()}
            </Typography>
          )}
        </CardContent>
      </Card>
    );
  }

  // Success state - display experiment
  const stateDisplay = getRunStateDisplay(experiment.run_state);
  const duration = calculateDuration(experiment.start_time, experiment.end_time);

  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" mb={2}>
          <ExperimentIcon color="primary" sx={{ mr: 1 }} />
          <Typography variant="h6">Latest Experiment</Typography>
          <Chip
            icon={stateDisplay.icon}
            label={stateDisplay.label}
            color={stateDisplay.color}
            size="small"
            sx={{ 
              ml: 'auto', 
              mr: 1,
              background: stateDisplay.bgPattern,
              // Add pulse animation for running experiments
              animation: stateDisplay.pattern === 'pulse' ? 'pulse 2s infinite' : 'none',
              '@keyframes pulse': {
                '0%': { opacity: 1 },
                '50%': { opacity: 0.7 },
                '100%': { opacity: 1 }
              }
            }}
            aria-label={stateDisplay.ariaLabel}
          />
          <Tooltip title="Refresh">
            <IconButton onClick={handleRefresh} size="small">
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Box>

        <Stack spacing={compact ? 1 : 2}>
          <Box>
            <Typography variant="subtitle1" fontWeight="medium">
              {experiment.method_name ? 
                experiment.method_name.split('\\').pop()?.replace('.hsl', '') || 'Unknown Method'
                : 'Unknown Method'
              }
            </Typography>
            <Typography variant="caption" color="text.secondary">
              ID: {experiment.run_guid?.substring(0, 8) || 'Unknown'}
            </Typography>
          </Box>

          <Box display="flex" justifyContent="space-between" flexWrap="wrap" gap={1}>
            <Box>
              <Typography variant="body2" color="text.secondary">
                Started
              </Typography>
              <Typography variant="body2">
                {formatTimestamp(experiment.start_time)}
              </Typography>
            </Box>

            {experiment.end_time && (
              <Box>
                <Typography variant="body2" color="text.secondary">
                  Ended
                </Typography>
                <Typography variant="body2">
                  {formatTimestamp(experiment.end_time)}
                </Typography>
              </Box>
            )}

            <Box>
              <Typography variant="body2" color="text.secondary">
                Duration
              </Typography>
              <Typography variant="body2">
                {duration}
              </Typography>
            </Box>
          </Box>

          {lastUpdate && (
            <Typography variant="caption" color="text.secondary" textAlign="right">
              Updated: {lastUpdate.toLocaleTimeString()}
            </Typography>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
});

// Add display name for debugging
ExperimentStatus.displayName = 'ExperimentStatus';

export default ExperimentStatus;