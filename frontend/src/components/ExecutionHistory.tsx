import React, { useState, useEffect, useMemo } from 'react';
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
  LinearProgress,
  Tooltip,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Stack,
  Divider,
  TextField,
  Switch,
  FormControlLabel
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
  experiment_path?: string | null;
  status: string;
  status_display?: string;
  start_time?: string | null;
  end_time?: string | null;
  duration_minutes?: number | null;
  calculated_duration_minutes?: number | null;
  duration_seconds?: number | null;
  error_message?: string | null;
  retry_count: number;
  created_at?: string | null;
  updated_at?: string | null;
  archived_at?: string | null;
}

type FilterOption = { label: string; value: string };

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [limit, setLimit] = useState(50);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [experimentFilter, setExperimentFilter] = useState<string>('all');
  const [methodFilter, setMethodFilter] = useState<string>('all');
  const [executionFilter, setExecutionFilter] = useState<string>('all');
  const [search, setSearch] = useState<string>('');

  const loadExecutionHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const historyData = await actions.getExecutionHistory(undefined, limit);
      const normalised = Array.isArray(historyData) ? historyData.map((record) => {
        const execution: ExecutionRecord = {
          execution_id: record.execution_id,
          schedule_id: record.schedule_id,
          experiment_name: record.experiment_name || 'Unknown Experiment',
          experiment_path: record.experiment_path,
          status: record.status,
          status_display: record.status_display || record.status_formatted,
          start_time: record.start_time,
          end_time: record.end_time,
          duration_minutes: record.duration_minutes,
          calculated_duration_minutes: record.calculated_duration_minutes,
          duration_seconds: record.duration_seconds,
          error_message: record.error_message,
          retry_count: record.retry_count ?? 0,
          created_at: record.created_at,
          updated_at: record.updated_at,
          archived_at: record.archived_at,
        };
        return execution;
      }) : [];

      // Deduplicate executions when archive + live return same ID
      const dedupedMap = normalised.reduce((acc, execution) => {
        if (!acc.has(execution.execution_id)) {
          acc.set(execution.execution_id, execution);
        } else {
          const existing = acc.get(execution.execution_id)!;
          // Prefer non-archived entry when choosing between duplicates
          if (existing.archived_at && !execution.archived_at) {
            acc.set(execution.execution_id, execution);
          }
        }
        return acc;
      }, new Map<string, ExecutionRecord>());

      setExecutions(Array.from(dedupedMap.values()));
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

  useEffect(() => {
    loadExecutionHistory();
  }, [limit]);

  useEffect(() => {
    if (scheduleId) {
      setExperimentFilter(scheduleId);
    } else {
      setExperimentFilter('all');
    }
  }, [scheduleId]);

  useEffect(() => {
    let intervalId: number | null = null;
    
    if (autoRefresh) {
      intervalId = setInterval(loadExecutionHistory, 30000); // Refresh every 30 seconds
    }
    
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [autoRefresh, scheduleId, limit]);

  const experimentOptions: FilterOption[] = useMemo(() => {
    const unique = new Map<string, { name: string }>();
    executions.forEach((execution) => {
      if (!execution.schedule_id) {
        return;
      }
      if (!unique.has(execution.schedule_id)) {
        unique.set(execution.schedule_id, { name: execution.experiment_name });
      }
    });

    return [
      { label: 'All experiments', value: 'all' },
      ...Array.from(unique.entries()).map(([scheduleId, meta]) => {
        const safeName = (meta.name || 'Untitled').trim();
        const shortId = scheduleId ? scheduleId.substring(0, 8) : 'unknown';
        return {
          value: scheduleId,
          label: `${safeName} · ${shortId}`,
        };
      }),
    ];
  }, [executions]);

  const methodOptions: FilterOption[] = useMemo(() => {
    const extractMethod = (path?: string | null): string | null => {
      if (!path) return null;
      const segments = path.split(/[\\/]/);
      const tail = segments[segments.length - 1];
      if (!tail) return null;
      return tail.replace(/\.[^.]+$/, '');
    };

    const unique = new Set<string>();
    executions.forEach((execution) => {
      const method = extractMethod(execution.experiment_path);
      if (method) {
        unique.add(method);
      }
    });

    return [
      { label: 'All methods', value: 'all' },
      ...Array.from(unique).sort().map((value) => ({ label: value, value })),
    ];
  }, [executions]);

  const executionOptions: FilterOption[] = useMemo(() => {
    return [
      { label: 'All executions', value: 'all' },
      ...executions.slice(0, 200).map((execution) => ({
        label: execution.execution_id,
        value: execution.execution_id,
      })),
    ];
  }, [executions]);

  const filteredExecutions = useMemo(() => {
    return executions.filter((execution) => {
      if (experimentFilter !== 'all' && execution.schedule_id !== experimentFilter) {
        return false;
      }

      if (methodFilter !== 'all') {
        const path = execution.experiment_path || '';
        const normalizedPath = path.toLowerCase();
        if (!normalizedPath.includes(methodFilter.toLowerCase())) {
          return false;
        }
      }

      if (executionFilter !== 'all' && execution.execution_id !== executionFilter) {
        return false;
      }

      if (search.trim()) {
        const haystack = [
          execution.execution_id,
          execution.experiment_name,
          execution.experiment_path,
          execution.status_display || execution.status,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();

        if (!haystack.includes(search.trim().toLowerCase())) {
          return false;
        }
      }

      return true;
    });
  }, [executions, experimentFilter, methodFilter, executionFilter, search]);

  const formatDurationDisplay = (execution: ExecutionRecord) => {
    const { duration_minutes, calculated_duration_minutes, duration_seconds } = execution;
    if (duration_seconds && duration_seconds > 0) {
      return `${Math.round(duration_seconds)}s`;
    }

    const minutes = calculated_duration_minutes ?? duration_minutes ?? null;
    if (minutes === null || minutes === undefined || Number.isNaN(minutes)) {
      return 'N/A';
    }

    if (minutes >= 60) {
      const hours = Math.floor(minutes / 60);
      const mins = Math.round(minutes % 60);
      if (mins === 0) {
        return `${hours}h`;
      }
      return `${hours}h ${mins}m`;
    }

    if (minutes >= 1) {
      return `${Math.round(minutes)}m`;
    }

    const secondsFromMinutes = Math.round(minutes * 60);
    if (secondsFromMinutes > 0) {
      return `${secondsFromMinutes}s`;
    }

    if (execution.start_time && execution.end_time) {
      const start = new Date(execution.start_time).getTime();
      const end = new Date(execution.end_time).getTime();
      if (!Number.isNaN(start) && !Number.isNaN(end) && end > start) {
        const durationSeconds = Math.round((end - start) / 1000);
        if (durationSeconds >= 60) {
          const mins = Math.floor(durationSeconds / 60);
          const secs = durationSeconds % 60;
          if (mins >= 60) {
            const hours = Math.floor(mins / 60);
            const remainingMinutes = mins % 60;
            return remainingMinutes === 0 ? `${hours}h` : `${hours}h ${remainingMinutes}m`;
          }
          return secs === 0 ? `${mins}m` : `${mins}m ${secs}s`;
        }
        if (durationSeconds > 0) {
          return `${durationSeconds}s`;
        }
      }
    }

    return 'N/A';
  };

  const statusLabel = (execution: ExecutionRecord) =>
    execution.status_display || execution.status?.replace(/_/g, ' ') || 'Unknown';

  return (
    <Box>
      <Card sx={{ mb: 2, px: { xs: 2, sm: 3 }, py: { xs: 2, sm: 2.5 } }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ xs: 'stretch', md: 'center' }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexGrow={1}>
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel>Experiment</InputLabel>
              <Select
                value={experimentFilter}
                label="Experiment"
                onChange={(event) => setExperimentFilter(event.target.value)}
              >
                {experimentOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel>Method</InputLabel>
              <Select
                value={methodFilter}
                label="Method"
                onChange={(event) => setMethodFilter(event.target.value)}
              >
                {methodOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel>Execution ID</InputLabel>
              <Select
                value={executionFilter}
                label="Execution ID"
                onChange={(event) => setExecutionFilter(event.target.value)}
              >
                {executionOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
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

            <TextField
              size="small"
              placeholder="Search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />

            <Tooltip title="Refresh execution history">
              <IconButton onClick={loadExecutionHistory} disabled={loading}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Stack>
        </Stack>

        <Divider sx={{ my: 2 }} />

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ xs: 'flex-start', sm: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            Showing {filteredExecutions.length} of {executions.length} executions
          </Typography>

          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={autoRefresh}
                onChange={(event) => setAutoRefresh(event.target.checked)}
              />
            }
            label="Auto refresh"
          />
        </Stack>
      </Card>

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
            {filteredExecutions.length === 0 && !loading ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <Typography variant="body2" color="text.secondary" py={4}>
                    No execution history found
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              filteredExecutions.map((execution) => (
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
                      {execution.archived_at && (
                        <Chip
                          size="small"
                          label="Archived"
                          color="default"
                          variant="outlined"
                          sx={{ mt: 0.5 }}
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={statusLabel(execution)}
                        color={getStatusColor(execution.status)}
                        variant="outlined"
                        size="small"
                        icon={getStatusIcon(execution.status)}
                        sx={{
                          '& .MuiChip-icon': { fontSize: '1rem' },
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatDateTime(execution.start_time)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatDurationDisplay(execution)}
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
