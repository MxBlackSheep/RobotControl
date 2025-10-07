import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Collapse,
  IconButton,
  Grid,
  LinearProgress,
  Tooltip,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Stack,
  Divider
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
  Schedule as ScheduleIcon,
  PlayArrow as RunningIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import { useScheduling } from '../hooks/useScheduling';
import ErrorAlert from './ErrorAlert';

interface ExecutionHistoryProps {
  scheduleId?: string;
  maxHeight?: string;
}

interface ExecutionRecord {
  execution_id: string;
  schedule_id: string;
  experiment_name: string;
  status: string;
  status_formatted: string;
  start_time: string;
  end_time?: string;
  duration_seconds?: number;
  duration_formatted?: string;
  error_message?: string;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

interface ExecutionSummary {
  schedule_id: string;
  experiment_name: string;
  total_executions: number;
  successful_executions: number;
  failed_executions: number;
  success_rate: number;
  last_execution?: {
    execution_id: string;
    status: string;
    start_time: string;
    end_time?: string;
    duration_formatted?: string;
    error_message?: string;
  };
  next_scheduled_run?: string;
  average_duration?: number;
  average_duration_formatted?: string;
  last_7_days: {
    successful: number;
    failed: number;
    success_rate: number;
  };
}

const getStatusIcon = (status?: string) => {
  const normalizedStatus = typeof status === 'string' ? status.toLowerCase() : '';
  switch (normalizedStatus) {
    case 'success':
    case 'completed':
      return <SuccessIcon color="success" fontSize="small" />;
    case 'failed':
    case 'error':
      return <ErrorIcon color="error" fontSize="small" />;
    case 'running':
    case 'executing':
      return <RunningIcon color="primary" fontSize="small" />;
    case 'scheduled':
    case 'queued':
      return <ScheduleIcon color="info" fontSize="small" />;
    default:
      return <ScheduleIcon color="disabled" fontSize="small" />;
  }
};

const getStatusColor = (status?: string): 'success' | 'error' | 'warning' | 'info' | 'default' => {
  const normalizedStatus = typeof status === 'string' ? status.toLowerCase() : '';
  switch (normalizedStatus) {
    case 'success':
    case 'completed':
      return 'success';
    case 'failed':
    case 'error':
      return 'error';
    case 'running':
    case 'executing':
      return 'warning';
    case 'scheduled':
    case 'queued':
      return 'info';
    default:
      return 'default';
  }
};

export const ExecutionHistory: React.FC<ExecutionHistoryProps> = ({ 
  scheduleId, 
  maxHeight = '600px' 
}) => {
  const { actions } = useScheduling();
  const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
  const [summary, setSummary] = useState<ExecutionSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [limit, setLimit] = useState(50);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const loadExecutionHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const historyData = await actions.getExecutionHistory(scheduleId, limit);
      setExecutions(historyData || []);

      // Load summary for specific schedule
      if (scheduleId) {
        const summaryData = await actions.getScheduleExecutionSummary(scheduleId);
        setSummary(summaryData);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load execution history');
    } finally {
      setLoading(false);
    }
  };

  const toggleRowExpansion = (executionId: string) => {
    setExpandedRows(prev => {
      const newSet = new Set(prev);
      if (newSet.has(executionId)) {
        newSet.delete(executionId);
      } else {
        newSet.add(executionId);
      }
      return newSet;
    });
  };

  const formatDateTime = (dateString?: string | null) => {
    if (!dateString) {
      return 'N/A';
    }
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) {
      return 'N/A';
    }
    return date.toLocaleString();
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  };

  useEffect(() => {
    loadExecutionHistory();
  }, [scheduleId, limit]);

  useEffect(() => {
    let intervalId: number | null = null;
    
    if (autoRefresh) {
      intervalId = setInterval(loadExecutionHistory, 30000); // Refresh every 30 seconds
    }
    
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [autoRefresh, scheduleId, limit]);

  return (
    <Box>
      {/* Summary Section */}
      {summary && (
        <Card sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Execution Summary: {summary.experiment_name}
            </Typography>
            
            <Grid container spacing={3}>
              {/* Success Rate */}
              <Grid item xs={12} sm={6} md={3}>
                <Box textAlign="center">
                  <Typography variant="h4" color="primary">
                    {summary.success_rate.toFixed(1)}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Success Rate
                  </Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={summary.success_rate} 
                    sx={{ mt: 1, height: 6, borderRadius: 3 }}
                    color={summary.success_rate > 80 ? 'success' : summary.success_rate > 60 ? 'warning' : 'error'}
                  />
                </Box>
              </Grid>

              {/* Total Executions */}
              <Grid item xs={12} sm={6} md={3}>
                <Box textAlign="center">
                  <Typography variant="h4" color="info.main">
                    {summary.total_executions}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Total Runs
                  </Typography>
                  <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
                    {summary.successful_executions} success, {summary.failed_executions} failed
                  </Typography>
                </Box>
              </Grid>

              {/* Last Execution */}
              <Grid item xs={12} sm={6} md={3}>
                <Box textAlign="center">
                  <Box display="flex" alignItems="center" justifyContent="center" mb={0.5}>
                    {summary.last_execution && getStatusIcon(summary.last_execution.status)}
                    <Typography variant="body1" sx={{ ml: 0.5 }}>
                      {summary.last_execution ? summary.last_execution.status : 'Never'}
                    </Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    Last Run
                  </Typography>
                  {summary.last_execution && (
                    <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
                      {formatDateTime(summary.last_execution.start_time)}
                    </Typography>
                  )}
                </Box>
              </Grid>

              {/* Average Duration */}
              <Grid item xs={12} sm={6} md={3}>
                <Box textAlign="center">
                  <Typography variant="h4" color="text.primary">
                    {summary.average_duration_formatted || 'N/A'}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Avg Duration
                  </Typography>
                  {summary.next_scheduled_run && (
                    <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
                      Next: {formatDateTime(summary.next_scheduled_run)}
                    </Typography>
                  )}
                </Box>
              </Grid>
            </Grid>

            {/* 7-Day Summary */}
            {summary.last_7_days && (
              <Box mt={2}>
                <Divider sx={{ mb: 2 }} />
                <Typography variant="subtitle2" gutterBottom>
                  Last 7 Days Performance
                </Typography>
                <Box display="flex" gap={2} alignItems="center">
                  <Chip 
                    icon={<SuccessIcon />}
                    label={`${summary.last_7_days.successful} Successful`}
                    color="success"
                    variant="outlined"
                    size="small"
                  />
                  <Chip 
                    icon={<ErrorIcon />}
                    label={`${summary.last_7_days.failed} Failed`}
                    color="error"
                    variant="outlined"
                    size="small"
                  />
                  <Typography variant="body2" color="text.secondary">
                    {summary.last_7_days.success_rate.toFixed(1)}% success rate
                  </Typography>
                </Box>
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      {/* Controls */}
      <Box display="flex" alignItems="center" gap={2} mb={2}>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Show Last</InputLabel>
          <Select
            value={limit}
            label="Show Last"
            onChange={(e) => setLimit(Number(e.target.value))}
          >
            <MenuItem value={25}>25 runs</MenuItem>
            <MenuItem value={50}>50 runs</MenuItem>
            <MenuItem value={100}>100 runs</MenuItem>
            <MenuItem value={200}>200 runs</MenuItem>
          </Select>
        </FormControl>

        <Tooltip title="Refresh execution history">
          <IconButton onClick={loadExecutionHistory} disabled={loading}>
            <RefreshIcon />
          </IconButton>
        </Tooltip>

        <Typography variant="body2" color="text.secondary" sx={{ ml: 'auto' }}>
          {executions.length} execution{executions.length !== 1 ? 's' : ''}
        </Typography>
      </Box>

      {/* Error Display */}
      {error && (
        <ErrorAlert
          message={error}
          severity="error"
          category="server"
          sx={{ mb: 2 }}
          retryable={true}
          onRetry={loadExecutionHistory}
          onClose={() => setError('')}
        />
      )}

      {/* Loading */}
      {loading && <LinearProgress sx={{ mb: 2 }} />}

      {/* Execution History Table */}
      <TableContainer 
        component={Paper} 
        sx={{ 
          maxHeight, 
          overflowY: 'auto',
          '& .MuiTableCell-root': { py: 1 }
        }}
      >
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell width="40px"></TableCell>
              <TableCell>Experiment</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Start Time</TableCell>
              <TableCell>Duration</TableCell>
              <TableCell>Retries</TableCell>
              <TableCell width="40px"></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {executions.length === 0 && !loading ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <Typography variant="body2" color="text.secondary" py={4}>
                    No execution history found
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              executions.map((execution) => (
                <React.Fragment key={execution.execution_id}>
                  <TableRow hover>
                    <TableCell>
                      {getStatusIcon(execution.status)}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontWeight="medium">
                        {execution.experiment_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        ID: {execution.schedule_id.substring(0, 8)}...
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={execution.status_formatted}
                        color={getStatusColor(execution.status)}
                        variant="outlined"
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatDateTime(execution.start_time)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {execution.duration_formatted || formatDuration(execution.duration_seconds) || 'N/A'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {execution.retry_count > 0 ? (
                        <Chip
                          label={`${execution.retry_count} retries`}
                          color="warning"
                          variant="outlined"
                          size="small"
                        />
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          None
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      {execution.error_message && (
                        <IconButton
                          size="small"
                          onClick={() => toggleRowExpansion(execution.execution_id)}
                        >
                          {expandedRows.has(execution.execution_id) ? 
                            <ExpandLessIcon /> : 
                            <ExpandMoreIcon />
                          }
                        </IconButton>
                      )}
                    </TableCell>
                  </TableRow>
                  
                  {/* Expanded Error Details */}
                  {execution.error_message && (
                    <TableRow>
                      <TableCell colSpan={7} sx={{ py: 0 }}>
                        <Collapse in={expandedRows.has(execution.execution_id)}>
                          <Box p={2} bgcolor="rgba(211, 47, 47, 0.04)">
                            <Typography variant="subtitle2" color="error" gutterBottom>
                              Error Details:
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {execution.error_message}
                            </Typography>
                            <Stack direction="row" spacing={2} mt={1}>
                              <Typography variant="caption" color="text.secondary">
                                Execution ID: {execution.execution_id}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                Updated: {formatDateTime(execution.updated_at)}
                              </Typography>
                            </Stack>
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};

export default ExecutionHistory;