/**
 * RobotControl Schedule List Component
 * 
 * Material-UI table component for displaying scheduled experiments with:
 * - Sortable columns by name, schedule type, duration, and next run
 * - Selection functionality for schedule operations
 * - Status indicators and conflict warnings
 * - Schedule details dialog
 * - Responsive design with loading states
 */

import React, { useState, useMemo } from 'react';
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Checkbox,
  Radio,
  IconButton,
  Tooltip,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  Button,
  Grid,
  Card,
  CardActionArea,
  CardContent,
  Divider,
  Stack,
  LinearProgress
} from '@mui/material';
import useTheme from '@mui/material/styles/useTheme';
import useMediaQuery from '@mui/material/useMediaQuery';
import {
  Info as InfoIcon,
  Refresh as RefreshIcon,
  Warning as WarningIcon,
  CheckCircle as CheckCircleIcon,
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  Schedule as ScheduleIcon,
  AccessTime as ClockIcon,
  Science as ExperimentIcon,
  Loop as IntervalIcon,
  Archive as ArchiveIcon,
  Delete as DeleteIcon
} from '@mui/icons-material';
import LoadingSpinner from './LoadingSpinner';
import ErrorAlert from './ErrorAlert';

import {
  ScheduledExperiment,
  ScheduleListProps,
  formatScheduleType,
  formatDuration,
  getNextExecutionTime
} from '../types/scheduling';

type ScheduleSortField = 'experiment_name' | 'schedule_type' | 'estimated_duration' | 'next_run' | 'created_at';
type ScheduleSortOrder = 'asc' | 'desc';

interface ScheduleSortOptions {
  field: ScheduleSortField;
  order: ScheduleSortOrder;
}

interface ScheduleDetailsDialogProps {
  schedule: ScheduledExperiment | null;
  open: boolean;
  onClose: () => void;
}

const formatPrerequisiteLabel = (value: string): string => {
  if (!value) {
    return value;
  }

  if (value.startsWith('EvoYeastExperiment:')) {
    const payload = value.replace('EvoYeastExperiment:', '');
    const [idPart, actionPart = 'set'] = payload.split('|', 2);
    const action = actionPart.trim().toLowerCase();
    const actionLabel = action === 'set' ? 'Reset others then activate' : 'No action';
    return `EvoYeast Experiment ${idPart.trim()} (${actionLabel})`;
  }

  return value;
};

const ScheduleDetailsDialog: React.FC<ScheduleDetailsDialogProps> = ({
  schedule,
  open,
  onClose
}) => {
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'));

  if (!schedule) return null;

  const nextRun = getNextExecutionTime(schedule);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullScreen={fullScreen} fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <ScheduleIcon color="primary" />
          <Typography variant="h6">Schedule Details</Typography>
        </Stack>
      </DialogTitle>
      <DialogContent sx={{ px: { xs: 2, sm: 3 } }}>
        <Grid container spacing={2}>
          {/* Basic Information */}
          <Grid item xs={12}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Experiment Information
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Experiment Name
                    </Typography>
                    <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                      {schedule.experiment_name}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Schedule ID
                    </Typography>
                    <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                      {schedule.schedule_id}
                    </Typography>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="body2" color="textSecondary">
                      Experiment Path
                    </Typography>
                    <Typography variant="body1" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                      {schedule.experiment_path}
                    </Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          {/* Prerequisites */}
          <Grid item xs={12}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Prerequisites
                </Typography>
                {schedule.prerequisites && schedule.prerequisites.length > 0 ? (
                  <Stack spacing={1}>
                    {schedule.prerequisites.map((prerequisite, index) => (
                      <Chip
                        key={index}
                        label={formatPrerequisiteLabel(prerequisite)}
                        size="small"
                        variant="outlined"
                      />
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No prerequisites configured
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Metadata */}
          <Grid item xs={12}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Metadata
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Created By
                    </Typography>
                    <Typography variant="body1">
                      {schedule.created_by}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Created At
                    </Typography>
                    <Typography variant="body1">
                      {new Date(schedule.created_at).toLocaleString()}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Last Updated
                    </Typography>
                    <Typography variant="body1">
                      {new Date(schedule.updated_at).toLocaleString()}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Archived
                    </Typography>
                    <Typography variant="body1">
                      {schedule.archived ? 'Yes' : 'No'}
                    </Typography>
                  </Grid>
                  {schedule.last_run && (
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        Last Run
                      </Typography>
                      <Typography variant="body1">
                        {new Date(schedule.last_run).toLocaleString()}
                      </Typography>
                    </Grid>
                  )}
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          {/* Schedule Configuration */}
          <Grid item xs={12}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Schedule Configuration
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Schedule Type
                    </Typography>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Typography variant="body1">
                        {formatScheduleType(schedule.schedule_type, schedule.interval_hours)}
                      </Typography>
                      {schedule.schedule_type === 'interval' && <IntervalIcon fontSize="small" />}
                    </Stack>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Estimated Duration
                    </Typography>
                    <Typography variant="body1">
                      {formatDuration(schedule.estimated_duration)}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Status
                    </Typography>
                    <Chip
                      icon={schedule.is_active ? <PlayIcon /> : <PauseIcon />}
                      label={schedule.is_active ? 'Active' : 'Inactive'}
                      color={schedule.is_active ? 'success' : 'default'}
                      size="small"
                    />
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Next Run
                    </Typography>
                    <Typography variant="body1">
                      {nextRun ? nextRun.toLocaleString() : 'Not scheduled'}
                    </Typography>
                  </Grid>
                  {schedule.start_time && (
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        Start Time
                      </Typography>
                      <Typography variant="body1">
                        {new Date(schedule.start_time).toLocaleString()}
                      </Typography>
                    </Grid>
                  )}
                </Grid>
              </CardContent>
            </Card>
          </Grid>

        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="primary">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
};

const ScheduleList: React.FC<ScheduleListProps> = ({
  schedules,
  selectedSchedule,
  onScheduleSelect,
  onRefresh,
  onDeleteSchedule,
  loading = false,
  error = null,
  initialized = false,
  archivedView = false,
}) => {
  const [sortOptions, setSortOptions] = useState<ScheduleSortOptions>({
    field: 'next_run',
    order: 'asc'
  });
  const [detailsDialog, setDetailsDialog] = useState({
    open: false,
    schedule: null as ScheduledExperiment | null
  });
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  // Sort schedules
  const sortedSchedules = useMemo(() => {
    const sorted = [...schedules].sort((a, b) => {
      let aValue: any;
      let bValue: any;

      switch (sortOptions.field) {
        case 'next_run':
          aValue = getNextExecutionTime(a)?.getTime() || 0;
          bValue = getNextExecutionTime(b)?.getTime() || 0;
          break;
        case 'created_at':
          aValue = new Date(a.created_at).getTime();
          bValue = new Date(b.created_at).getTime();
          break;
        case 'estimated_duration':
          aValue = a.estimated_duration;
          bValue = b.estimated_duration;
          break;
        default:
          aValue = String(a[sortOptions.field]).toLowerCase();
          bValue = String(b[sortOptions.field]).toLowerCase();
      }

      if (sortOptions.order === 'asc') {
        return aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      } else {
        return aValue > bValue ? -1 : aValue < bValue ? 1 : 0;
      }
    });
    return sorted;
  }, [schedules, sortOptions]);

  const handleSort = (field: ScheduleSortField) => {
    setSortOptions(prev => ({
      field,
      order: prev.field === field && prev.order === 'asc' ? 'desc' : 'asc'
    }));
  };

  const handleRowClick = (schedule: ScheduledExperiment) => {
    const newSelection = selectedSchedule?.schedule_id === schedule.schedule_id ? null : schedule;
    onScheduleSelect(newSelection);
  };

  const handleViewDetails = (schedule: ScheduledExperiment) => {
    setDetailsDialog({
      open: true,
      schedule
    });
  };

  const handleDeleteClick = (event: React.MouseEvent, schedule: ScheduledExperiment) => {
    event.stopPropagation();
    if (onDeleteSchedule) {
      onDeleteSchedule(schedule);
    }
  };

  const renderStatusIcon = (schedule: ScheduledExperiment) => {
    if (schedule.recovery_required) {
      return (
        <Tooltip title="Manual recovery required">
          <WarningIcon color="warning" fontSize="small" />
        </Tooltip>
      );
    }

    if (schedule.archived) {
      return (
        <Tooltip title="Schedule is archived">
          <ArchiveIcon color="disabled" fontSize="small" />
        </Tooltip>
      );
    }

    if (!schedule.is_active) {
      return (
        <Tooltip title="Schedule is inactive">
          <PauseIcon color="disabled" fontSize="small" />
        </Tooltip>
      );
    }

    const nextRun = getNextExecutionTime(schedule);
    if (!nextRun) {
      return (
        <Tooltip title="No next execution scheduled">
          <WarningIcon color="warning" fontSize="small" />
        </Tooltip>
      );
    }

    return (
      <Tooltip title="Schedule is active">
        <PlayIcon color="success" fontSize="small" />
      </Tooltip>
    );
  };

  const renderScheduleTypeChip = (schedule: ScheduledExperiment) => {
    const getTypeColor = (type: string) => {
      switch (type) {
        case 'once': return 'default';
        case 'interval': return 'primary';
        case 'daily': return 'secondary';
        case 'weekly': return 'info';
        default: return 'default';
      }
    };

    return (
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Chip
          label={formatScheduleType(schedule.schedule_type, schedule.interval_hours)}
          color={getTypeColor(schedule.schedule_type)}
          size="small"
          variant="outlined"
        />
        {schedule.recovery_required && (
          <Chip
            label="Recovery Needed"
            color="error"
            size="small"
          />
        )}
        {schedule.archived && (
          <Chip
            label="Archived"
            color="default"
            size="small"
            variant="outlined"
          />
        )}
      </Stack>
    );
  };

  const renderPrerequisitesPreview = (schedule: ScheduledExperiment) => {
    if (!schedule.prerequisites || schedule.prerequisites.length === 0) {
      return null;
    }

    const previewItems = schedule.prerequisites.slice(0, 2);

    return (
      <Stack direction="row" spacing={0.5} flexWrap="wrap">
        {previewItems.map((item, index) => (
          <Chip
            key={`${schedule.schedule_id}-pr-${index}`}
            label={formatPrerequisiteLabel(item)}
            size="small"
            variant="outlined"
          />
        ))}
        {schedule.prerequisites.length > previewItems.length && (
          <Chip
            label={`+${schedule.prerequisites.length - previewItems.length}`}
            size="small"
            variant="outlined"
          />
        )}
      </Stack>
    );
  };

  const renderMobileScheduleCards = () => {
    if (sortedSchedules.length === 0) {
      return (
        <Box sx={{ p: 2 }}>
          <Card variant="outlined">
            <CardContent>
              <Stack alignItems="center" spacing={2}>
                <ExperimentIcon color="disabled" sx={{ fontSize: 48 }} />
          <Typography color="textSecondary">
            {archivedView ? 'No archived schedules found' : 'No scheduled experiments found'}
          </Typography>
              </Stack>
            </CardContent>
          </Card>
        </Box>
      );
    }

    return (
      <Box sx={{ p: 2 }}>
        <Stack spacing={2}>
          {sortedSchedules.map((schedule) => {
            const selected = selectedSchedule?.schedule_id === schedule.schedule_id;
            const nextRun = getNextExecutionTime(schedule);

            return (
              <Card
                key={schedule.schedule_id}
                variant="outlined"
                sx={{
                  borderColor: selected ? 'primary.main' : 'divider',
                  boxShadow: selected ? (theme) => `0 0 0 1px ${theme.palette.primary.main}` : 'none',
                  transition: 'box-shadow 0.2s ease'
                }}
              >
                <CardActionArea
                  onClick={() => handleRowClick(schedule)}
                  sx={{ p: 2 }}
                >
                  <Stack spacing={1.5}>
                    <Stack
                      direction="row"
                      alignItems="flex-start"
                      justifyContent="space-between"
                      spacing={1}
                      flexWrap="wrap"
                      rowGap={1}
                    >
                      <Stack direction="row" spacing={1} alignItems="center">
                        {renderStatusIcon(schedule)}
                        <Typography
                          variant="subtitle1"
                          fontWeight={600}
                          sx={{ wordBreak: 'break-word' }}
                        >
                          {schedule.experiment_name}
                        </Typography>
                      </Stack>
                      {renderScheduleTypeChip(schedule)}
                    </Stack>

                    <Stack spacing={0.5}>
                      <Typography variant="body2" color="textSecondary">
                        Created by {schedule.created_by}
                      </Typography>
                      <Typography variant="body2">
                        Est. duration: {formatDuration(schedule.estimated_duration)}
                      </Typography>
                      <Typography variant="body2">
                        Next run: {nextRun ? nextRun.toLocaleString() : 'Not scheduled'}
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        Created: {new Date(schedule.created_at).toLocaleString()}
                      </Typography>
                    </Stack>

                    {renderPrerequisitesPreview(schedule)}
                  </Stack>
                </CardActionArea>
                <Divider />
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ px: 2, py: 1, flexWrap: 'wrap', rowGap: 1 }}
            >
              <Typography variant="caption" color="textSecondary">
                ID: {schedule.schedule_id}
              </Typography>
              <Stack direction="row" spacing={1}>
                {archivedView && onDeleteSchedule && (
                  <Button
                    size="small"
                    color="error"
                    startIcon={<DeleteIcon fontSize="small" />}
                    onClick={(event) => handleDeleteClick(event, schedule)}
                  >
                    Delete
                  </Button>
                )}
                <Button
                  size="small"
                  startIcon={<InfoIcon fontSize="small" />}
                  onClick={(event) => {
                    event.stopPropagation();
                    handleViewDetails(schedule);
                  }}
                >
                  Details
                </Button>
              </Stack>
            </Stack>
          </Card>
        );
      })}
    </Stack>
      </Box>
    );
  };

  const renderTableHeader = () => {
    const columns = [
      { field: 'experiment_name' as ScheduleSortField, label: 'Experiment Name', width: '25%' },
      { field: 'schedule_type' as ScheduleSortField, label: 'Schedule Type', width: '15%' },
      { field: 'estimated_duration' as ScheduleSortField, label: 'Duration', width: '12%' },
      { field: 'next_run' as ScheduleSortField, label: 'Next Run', width: '20%' },
      { field: 'created_at' as ScheduleSortField, label: 'Created', width: '18%' },
    ];

    return (
      <TableHead>
        <TableRow>
          <TableCell padding="checkbox" width="5%">
            Status
          </TableCell>
          {columns.map((column) => (
            <TableCell key={column.field} width={column.width}>
              <TableSortLabel
                active={sortOptions.field === column.field}
                direction={sortOptions.field === column.field ? sortOptions.order : 'asc'}
                onClick={() => handleSort(column.field)}
              >
                {column.label}
              </TableSortLabel>
            </TableCell>
          ))}
          <TableCell width="5%">Actions</TableCell>
        </TableRow>
      </TableHead>
    );
  };

  if (!initialized) {
    const loadingMessage = archivedView
      ? 'Loading archived schedules...'
      : 'Loading scheduled experiments...';
    return (
      <LoadingSpinner
        variant="spinner"
        message={loadingMessage}
        minHeight={300}
      />
    );
  }

  const showInlineProgress = loading && schedules.length > 0;

  if (error) {
    return (
      <Paper
        elevation={0}
        sx={{
          p: { xs: 3, md: 3.5 },
          borderRadius: 2,
          border: 1,
          borderColor: 'error.light',
          bgcolor: 'rgba(244, 67, 54, 0.04)'
        }}
      >
        <Stack spacing={2}>
          <Typography variant="h6" color="error.main">
            {error}
          </Typography>
          <Box>
            <Button
              variant="contained"
              color="error"
              onClick={() => onRefresh()}
              startIcon={<RefreshIcon />}
            >
              Try again
            </Button>
          </Box>
        </Stack>
      </Paper>
    );
  }

  if (schedules.length === 0) {
    return (
      <Paper
        elevation={0}
        sx={{
          p: { xs: 3, md: 3.5 },
          textAlign: 'center',
          borderRadius: 2,
          border: 1,
          borderColor: 'divider'
        }}
      >
        <Typography variant="h6" gutterBottom>
          {archivedView ? 'No archived schedules yet' : 'No scheduled experiments yet'}
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {archivedView
            ? 'Archived schedules will appear here once you archive existing experiments.'
            : 'Create a schedule to see it listed here.'}
        </Typography>
        <Button variant="outlined" onClick={onRefresh} startIcon={<RefreshIcon />}>
          Refresh
        </Button>
      </Paper>
    );
  }

  return (
    <>
      <Paper
        elevation={1}
        sx={{
          display: 'flex',
          flexDirection: 'column',
          overflow: isMobile ? 'visible' : 'hidden',
          borderRadius: 2,
          border: 1,
          borderColor: 'divider',
          bgcolor: 'background.paper'
        }}
      >
        {/* Header */}
        <Box
          sx={{
            px: { xs: 2.25, md: 3 },
            py: { xs: 1.75, md: 2 },
            borderBottom: 1,
            borderColor: 'divider'
          }}
        >
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems={isMobile ? 'flex-start' : 'center'}
            spacing={isMobile ? 1 : 2}
            flexWrap="wrap"
            rowGap={1}
          >
            <Typography variant="h6" sx={{ fontSize: { xs: '1rem', sm: '1.1rem' } }}>
              {archivedView ? 'Archived Schedules' : 'Scheduled Experiments'} ({schedules.length})
            </Typography>
            <Button
              startIcon={<RefreshIcon />}
              onClick={onRefresh}
              variant="outlined"
              size="small"
              sx={{
                width: { xs: '100%', sm: 'auto' },
                mt: { xs: 1, sm: 0 }
              }}
            >
              Refresh
            </Button>
          </Stack>
        </Box>

        {showInlineProgress && <LinearProgress color="primary" />}

        {isMobile ? (
          renderMobileScheduleCards()
        ) : (
          <TableContainer
            sx={{
              maxHeight: { xs: 360, md: 520 },
              overflowY: 'auto'
            }}
          >
            <Table stickyHeader>
              {renderTableHeader()}
              <TableBody>
                {sortedSchedules.length === 0 ? (
                  <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                    <Stack alignItems="center" spacing={2}>
                      <ExperimentIcon color="disabled" sx={{ fontSize: 48 }} />
                      <Typography color="textSecondary">
                        {archivedView ? 'No archived schedules found' : 'No scheduled experiments found'}
                        </Typography>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ) : (
                  sortedSchedules.map((schedule) => {
                    const nextRun = getNextExecutionTime(schedule);
                    return (
                      <TableRow
                        key={schedule.schedule_id}
                        hover
                        selected={selectedSchedule?.schedule_id === schedule.schedule_id}
                        onClick={() => handleRowClick(schedule)}
                        sx={{ cursor: 'pointer' }}
                      >
                        <TableCell padding="checkbox">
                          <Stack direction="row" alignItems="center" spacing={1}>
                            <Radio
                              checked={selectedSchedule?.schedule_id === schedule.schedule_id}
                              onChange={() => handleRowClick(schedule)}
                              size="small"
                            />
                            {renderStatusIcon(schedule)}
                          </Stack>
                        </TableCell>
                        
                        <TableCell>
                          <Stack spacing={0.5}>
                            <Typography variant="body2" sx={{ fontWeight: 'medium' }}>
                              {schedule.experiment_name}
                            </Typography>
                            <Typography variant="caption" color="textSecondary">
                              by {schedule.created_by}
                            </Typography>
                          </Stack>
                        </TableCell>
                        
                        <TableCell>
                          {renderScheduleTypeChip(schedule)}
                        </TableCell>
                        
                        <TableCell>
                          <Stack direction="row" alignItems="center" spacing={0.5}>
                            <ClockIcon fontSize="small" color="disabled" />
                            <Typography variant="body2">
                              {formatDuration(schedule.estimated_duration)}
                            </Typography>
                          </Stack>
                        </TableCell>
                        
                        <TableCell>
                          <Stack spacing={0.5}>
                            <Typography variant="body2">
                              {nextRun ? nextRun.toLocaleDateString() : 'Not scheduled'}
                            </Typography>
                            {nextRun && (
                              <Typography variant="caption" color="textSecondary">
                                {nextRun.toLocaleTimeString()}
                              </Typography>
                            )}
                          </Stack>
                        </TableCell>
                        
                        <TableCell>
                          <Typography variant="body2">
                            {new Date(schedule.created_at).toLocaleDateString()}
                          </Typography>
                        </TableCell>
                        
                        <TableCell>
                          <IconButton
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleViewDetails(schedule);
                            }}
                          >
                            <InfoIcon fontSize="small" />
                          </IconButton>
                          {archivedView && onDeleteSchedule && (
                            <Tooltip title="Delete archived schedule">
                              <IconButton
                                size="small"
                                color="error"
                                onClick={(e) => handleDeleteClick(e, schedule)}
                                sx={{ ml: 0.5 }}
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>

      {/* Details Dialog */}
      <ScheduleDetailsDialog
        schedule={detailsDialog.schedule}
        open={detailsDialog.open}
        onClose={() => setDetailsDialog(prev => ({ ...prev, open: false }))}
      />
    </>
  );
};

export default ScheduleList;
export { ScheduleDetailsDialog };
export type { ScheduleDetailsDialogProps };
