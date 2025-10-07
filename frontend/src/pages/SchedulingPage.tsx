/**
 * PyRobot Experiment Scheduling Page
 * 
 * Dedicated page for experiment scheduling and management operations.
 * Provides full-page scheduling interface with:
 * - Page-level error boundaries and authentication
 * - Breadcrumb navigation following app patterns
 * - User and admin access control for different operations
 * - Comprehensive scheduling functionality
 * - Integration with main application navigation
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Button,
  Breadcrumbs,
  Link,
  Alert,
  Paper,
  Stack,
  Grid,
  Card,
  CardContent,
  Chip,
  Divider,
  Tab,
  Tabs,
  Badge
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Home as HomeIcon,
  Schedule as ScheduleIcon,
  Dashboard as DashboardIcon,
  PlayArrow as PlayArrowIcon,
  QueueMusic as QueueIcon,
  CalendarMonth as CalendarIcon,
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  FolderOpen as FolderIcon,
  Refresh as RefreshIcon,
  History as HistoryIcon,
  WarningAmber as WarningIcon
} from '@mui/icons-material';
import { useNavigate, Link as RouterLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Import scheduling components
import ScheduleList from '../components/ScheduleList';
import ScheduleActions from '../components/ScheduleActions';
import ImprovedScheduleForm from '../components/scheduling/ImprovedScheduleForm';
import FolderImportDialog from '../components/scheduling/FolderImportDialog';
import ExecutionHistory from '../components/ExecutionHistory';
import IntelligentStatusMonitor from '../components/IntelligentStatusMonitor';
import useScheduling from '../hooks/useScheduling';
import { formatDuration, formatExecutionStatus, ScheduledExperiment, CreateScheduleFormData } from '../types/scheduling';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => {
  return (
    <div role="tabpanel" hidden={value !== index}>
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
};

/**
 * SchedulingPage Component
 * 
 * Full-page interface for experiment scheduling operations.
 * Implements role-based access control and proper navigation patterns.
 */
const SchedulingPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [currentTab, setCurrentTab] = useState(0);
  const [improvedFormOpen, setImprovedFormOpen] = useState(false);
  const [folderImportOpen, setFolderImportOpen] = useState(false);
  const [scanning, setScanning] = useState(false);

  // Initialize scheduling hook
  const { state, actions } = useScheduling();

  const formatTimestamp = (value?: string | null): string => {
    if (!value) {
      return 'N/A';
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
  };

  const handleImprovedFormSubmit = async (data: any) => {
    const payload: CreateScheduleFormData = {
      experiment_name: data.experiment_name,
      experiment_path: data.experiment_path,
      schedule_type: data.schedule_type,
      interval_hours: data.schedule_type === 'interval' ? Number(data.interval_hours) : undefined,
      start_time: data.start_time ? new Date(data.start_time) : null,
      estimated_duration: Number(data.estimated_duration),
      is_active: data.is_active ?? true,
      max_retries: Number(data.max_retries ?? 0),
      retry_delay_minutes: Number(data.retry_delay_minutes ?? 0),
      backoff_strategy: data.backoff_strategy || 'linear',
      prerequisites: Array.isArray(data.prerequisites) ? data.prerequisites : [],
    };
    await actions.createSchedule(payload);
    await actions.loadSchedules(true);
  };

  const handleViewRecoverySchedule = async () => {
    const scheduleId = state.manualRecovery?.schedule_id;
    if (!scheduleId) {
      return;
    }
    await actions.loadSchedules(true, scheduleId);
    setCurrentTab(0);
  };

  const handleResolveManualRecovery = async () => {
    const scheduleId = state.manualRecovery?.schedule_id;
    if (!scheduleId) {
      window.alert('Manual recovery is active, but the originating schedule could not be identified.');
      return;
    }
    const noteInput = window.prompt('Optional note when resolving manual recovery', state.manualRecovery?.note || '');
    if (noteInput === null) {
      return;
    }
    const note = noteInput.trim() ? noteInput.trim() : undefined;
    await actions.resolveRecovery(scheduleId, note);
    await actions.getQueueStatus();
  };

  // Access control - users and admins can view, only admins can control scheduler service
  if (!user) {
    return (
      <Container maxWidth="md" sx={{ mt: 4 }}>
        <Alert severity="error" icon={<ScheduleIcon />}>
          <Typography variant="h6" gutterBottom>
            Authentication Required
          </Typography>
          <Typography variant="body2">
            Please log in to access experiment scheduling functionality.
          </Typography>
        </Alert>
      </Container>
    );
  }

  if (!['admin', 'user'].includes(user.role)) {
    return (
      <Container maxWidth="md" sx={{ mt: 4 }}>
        <Alert severity="error" icon={<ScheduleIcon />}>
          <Typography variant="h6" gutterBottom>
            Insufficient Permissions
          </Typography>
          <Typography variant="body2">
            Experiment scheduling requires user or administrator privileges. 
            Contact your system administrator for access.
          </Typography>
          <Box sx={{ mt: 2 }}>
            <Button
              startIcon={<ArrowBackIcon />}
              onClick={() => navigate('/')}
              variant="outlined"
            >
              Return to Dashboard
            </Button>
          </Box>
        </Alert>
      </Container>
    );
  }

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setCurrentTab(newValue);
  };

  // Status summary component
  const SchedulingStatusSummary: React.FC = () => {
    // Use the existing state from parent component instead of creating new hook instance

    return (
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1}>
                <ScheduleIcon color="primary" />
                <Box>
                  <Typography variant="h6">{state.schedules.length}</Typography>
                  <Typography variant="body2" color="textSecondary">
                    Total Schedules
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1}>
                <PlayArrowIcon color={state.schedulerRunning ? 'success' : 'disabled'} />
                <Box>
                  <Typography variant="h6">
                    {state.schedulerRunning ? 'Running' : 'Stopped'}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    Scheduler Status
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1}>
                <QueueIcon color={state.queueStatus ? 'info' : 'disabled'} />
                <Box>
                  <Typography variant="h6">
                    {state.queueStatus?.running_jobs || 0}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    Active Jobs
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1}>
                <CalendarIcon color={state.calendarEvents.length > 0 ? 'secondary' : 'disabled'} />
                <Box>
                  <Typography variant="h6">{state.calendarEvents.length}</Typography>
                  <Typography variant="body2" color="textSecondary">
                    Upcoming Events
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };

  // Calendar view component
  const CalendarView: React.FC = () => {
    const [calendarData, setCalendarData] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    
    const loadCalendarData = () => {
      setLoading(true);
      try {
        // Use existing schedules data instead of calling API again
        // Group schedules by date for calendar view
        const schedulesByDate = state.schedules
          .filter(schedule => schedule.next_run)
          .reduce((groups, schedule) => {
            const date = schedule.next_run ? new Date(schedule.next_run).toDateString() : 'No Date';
            if (!groups[date]) groups[date] = [];
            groups[date].push(schedule);
            return groups;
          }, {} as Record<string, ScheduledExperiment[]>);
        
        setCalendarData(Object.entries(schedulesByDate).sort((a, b) => 
          new Date(a[0]).getTime() - new Date(b[0]).getTime()
        ));
      } catch (error) {
        console.error('Failed to load calendar data:', error);
      } finally {
        setLoading(false);
      }
    };

    useEffect(() => {
      // Load calendar data when schedules change, but avoid infinite loops
      loadCalendarData();
    }, [state.schedules.length]); // Only re-run when the number of schedules changes

    if (loading) {
      return (
        <Box display="flex" justifyContent="center" p={3}>
          <Typography>Loading calendar data...</Typography>
        </Box>
      );
    }

    if (calendarData.length === 0) {
      return (
        <Alert severity="info">
          <Typography variant="h6" gutterBottom>
            No Upcoming Scheduled Experiments
          </Typography>
          <Typography variant="body2">
            Create new schedules to see them appear in the calendar view.
          </Typography>
        </Alert>
      );
    }

    return (
      <Box>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">
            Upcoming Schedule Calendar
          </Typography>
          <Button
            startIcon={<RefreshIcon />}
            onClick={loadCalendarData}
            size="small"
          >
            Refresh
          </Button>
        </Stack>
        
        <Grid container spacing={2}>
          {calendarData.map(([date, schedules]) => (
            <Grid item xs={12} md={6} key={date}>
              <Card>
                <CardContent>
                  <Typography variant="h6" color="primary" gutterBottom>
                    {new Date(date).toLocaleDateString('en-US', { 
                      weekday: 'long',
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric'
                    })}
                  </Typography>
                  
                  <Stack spacing={1}>
                    {schedules.map((schedule) => (
                      <Box
                        key={schedule.schedule_id}
                        sx={{
                          p: 1.5,
                          border: 1,
                          borderColor: 'divider',
                          borderRadius: 1,
                          backgroundColor: schedule.is_active ? 'action.hover' : 'action.disabled'
                        }}
                      >
                        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                          <Box flex={1}>
                            <Typography variant="subtitle2" fontWeight="bold">
                              {schedule.experiment_name}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {schedule.next_run 
                                ? new Date(schedule.next_run).toLocaleTimeString('en-US', { 
                                    hour: '2-digit', 
                                    minute: '2-digit' 
                                  })
                                : 'No scheduled time'
                              }
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              Duration: {formatDuration(schedule.estimated_duration)} | 
                              Type: {schedule.schedule_type}
                              {schedule.interval_hours && ` (${schedule.interval_hours}h)`}
                            </Typography>
                          </Box>
                          <Stack spacing={0.5}>
                            <Chip 
                              size="small"
                              label={schedule.is_active ? 'Active' : 'Inactive'} 
                              color={schedule.is_active ? 'success' : 'default'}
                            />
                            {schedule.prerequisites.length > 0 && (
                              <Chip 
                                size="small"
                                label={`${schedule.prerequisites.length} prereqs`}
                                variant="outlined"
                              />
                            )}
                          </Stack>
                        </Stack>
                      </Box>
                    ))}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
        
        <Alert severity="info" sx={{ mt: 2 }}>
          <Typography variant="body2">
            <strong>Calendar View:</strong> Showing {calendarData.reduce((total, [, schedules]) => total + schedules.length, 0)} 
            scheduled experiments across {calendarData.length} dates.
            Times shown are based on next_run calculations.
          </Typography>
        </Alert>
      </Box>
    );
  };

  // Queue status component
  const QueueStatus: React.FC = () => {
    const { queueStatus, hamiltonStatus } = state;

    if (!queueStatus) {
      return (
        <Alert severity="info">
          Queue status information is not available. The scheduler service may be stopped.
        </Alert>
      );
    }

    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Queue Information
              </Typography>
              <Stack spacing={1}>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Queued Jobs:</Typography>
                  <Typography variant="body2">{queueStatus.queue_size}</Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Running Jobs:</Typography>
                  <Typography variant="body2">{queueStatus.running_jobs}</Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Max Parallel:</Typography>
                  <Typography variant="body2">{queueStatus.max_parallel_jobs}</Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Capacity Available:</Typography>
                  <Chip 
                    label={queueStatus.capacity_available ? 'Yes' : 'No'} 
                    color={queueStatus.capacity_available ? 'success' : 'warning'}
                    size="small"
                  />
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          {/* Intelligent Status Monitor with 5-second refresh */}
          <IntelligentStatusMonitor 
            refreshInterval={5000}
            showLastUpdate={true}
            compact={false}
          />
        </Grid>
        {queueStatus.running_job_details.length > 0 && (
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Currently Running Jobs
                </Typography>
                <Stack spacing={1}>
                  {queueStatus.running_job_details.map((job, index) => (
                    <Box key={index} sx={{ p: 1, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Typography variant="body2" fontWeight="medium">
                          {job.experiment_name}
                        </Typography>
                        <Chip label={job.priority} size="small" />
                      </Stack>
                      <Typography variant="caption" color="textSecondary">
                        Queued: {new Date(job.queued_time).toLocaleString()} | Retries: {job.retry_count}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        )}
      </Grid>
    );
  };

  return (
    <Container maxWidth="xl" sx={{ mt: 2, mb: 4 }}>
      {/* Page Header with Navigation */}
      <Box sx={{ mb: 3 }}>
        {/* Navigation Controls */}
        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2 }}>
          <Button
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate(-1)}
            variant="outlined"
            size="small"
          >
            Back
          </Button>

          {/* Breadcrumb Navigation */}
          <Breadcrumbs aria-label="scheduling page breadcrumb">
            <Link
              component={RouterLink}
              to="/"
              underline="hover"
              color="inherit"
              sx={{ display: 'flex', alignItems: 'center' }}
            >
              <HomeIcon sx={{ mr: 0.5, fontSize: 18 }} />
              Dashboard
            </Link>
            <Typography
              color="text.primary"
              sx={{ display: 'flex', alignItems: 'center' }}
            >
              <ScheduleIcon sx={{ mr: 0.5, fontSize: 18 }} />
              Experiment Scheduling
            </Typography>
          </Breadcrumbs>
        </Stack>

        {/* Page Title */}
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700, mb: 1 }}>
          Experiment Scheduling
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Schedule, manage, and monitor automated experiment execution.
          Replace legacy VBS scripts with modern scheduling capabilities.
        </Typography>

        {/* Scheduler Control (Admin Only) */}
        {/* Status Summary */}
        <SchedulingStatusSummary />

        {/* Error Display */}
        {state.error && (
          <Alert severity="error" onClose={actions.clearError} sx={{ mb: 3 }}>
            {state.error}
          </Alert>
        )}
      </Box>

      {/* Main Content */}
      <Paper elevation={1}>
        {/* Navigation Tabs */}
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={currentTab} onChange={handleTabChange}>
            <Tab 
              label={
                <Stack direction="row" alignItems="center" spacing={1}>
                  <ScheduleIcon fontSize="small" />
                  <span>Schedules</span>
                </Stack>
              } 
            />
            <Tab 
              label={
                <Stack direction="row" alignItems="center" spacing={1}>
                  <WarningIcon fontSize="small" color={state.manualRecovery?.active ? 'error' : 'disabled'} />
                  <span>Manual Recovery</span>
                </Stack>
              } 
            />
            <Tab 
              label={
                <Stack direction="row" alignItems="center" spacing={1}>
                  <Badge 
                    badgeContent={state.queueStatus?.queue_size || 0} 
                    color={state.queueStatus?.queue_size > 0 ? "primary" : "default"}
                    max={99}
                  >
                    <QueueIcon fontSize="small" />
                  </Badge>
                  <span>Queue Status</span>
                </Stack>
              } 
            />
            <Tab 
              label={
                <Stack direction="row" alignItems="center" spacing={1}>
                  <CalendarIcon fontSize="small" />
                  <span>Calendar View</span>
                </Stack>
              } 
            />
            <Tab 
              label={
                <Stack direction="row" alignItems="center" spacing={1}>
                  <HistoryIcon fontSize="small" />
                  <span>Execution History</span>
                </Stack>
              } 
            />
          </Tabs>
        </Box>

        {/* Tab Panels */}
        <TabPanel value={currentTab} index={0}>
          <Grid container spacing={3}>
            <Grid item xs={12} lg={8}>
              <ScheduleList
                schedules={state.schedules}
                selectedSchedule={state.selectedSchedule}
                onScheduleSelect={actions.selectSchedule}
                onRefresh={() => actions.loadSchedules(true)}
                loading={state.loading}
                error={state.error}
                initialized={state.initialized}
              />
            </Grid>
            <Grid item xs={12} lg={4}>
              <Stack spacing={2}>
                {/* Action Buttons */}
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Actions
                    </Typography>
                    <Stack spacing={2}>
                      {/* Create New Schedule Button */}
                      <Button
                        variant="contained"
                        fullWidth
                        startIcon={<AddIcon />}
                        onClick={() => setImprovedFormOpen(true)}
                        disabled={state.loading}
                      >
                        Create New Schedule
                      </Button>
                      
                      {/* Import Experiments Button */}
                      <Button
                        variant="outlined"
                        fullWidth
                        startIcon={<FolderIcon />}
                        onClick={() => setFolderImportOpen(true)}
                        disabled={state.loading}
                      >
                        Import Experiments from Folder
                      </Button>

                      {/* Edit/Delete for selected schedule */}
                      {state.selectedSchedule && (
                        <>
                          <Divider />
                          <Typography variant="subtitle2" color="text.secondary">
                            Selected: {state.selectedSchedule.experiment_name}
                          </Typography>
                          <Button
                            variant="outlined"
                            fullWidth
                            startIcon={<EditIcon />}
                            onClick={() => {
                              // TODO: Open edit dialog with selected schedule
                              setImprovedFormOpen(true);
                            }}
                            disabled={state.loading}
                          >
                            Edit Schedule
                          </Button>
                          <Button
                            variant="outlined"
                            color="error"
                            fullWidth
                            startIcon={<DeleteIcon />}
                            onClick={() => {
                              if (window.confirm(`Delete schedule for ${state.selectedSchedule.experiment_name}?`)) {
                                actions.deleteSchedule(state.selectedSchedule.schedule_id);
                              }
                            }}
                            disabled={state.loading}
                          >
                            Delete Schedule
                          </Button>
                        </>
                      )}

                      {/* Auto-scan for experiments */}
                      <Divider />
                      <Typography variant="subtitle2" color="text.secondary">
                        Discovery
                      </Typography>
                      <Button
                        variant="outlined"
                        fullWidth
                        startIcon={<RefreshIcon />}
                        onClick={async () => {
                          try {
                            setScanning(true);
                            // Call API directly since it might not be in the hook yet
                            // Mock scan operation for now
                            console.log('Scan completed');
                          } catch (error) {
                            console.error('Scan failed:', error);
                          } finally {
                            setScanning(false);
                          }
                        }}
                        disabled={state.loading}
                      >
                        Scan Default Hamilton Paths
                      </Button>
                    </Stack>
                  </CardContent>
                </Card>

                {/* Operation Status */}
                {state.operationStatus && (
                  <Alert 
                    severity={'info'}
                  >
                    {state.operationStatus}
                  </Alert>
                )}
              </Stack>
            </Grid>
          </Grid>
        </TabPanel>

        <TabPanel value={currentTab} index={1}>
          <Stack spacing={2}>
            <Alert severity={state.manualRecovery?.active ? 'warning' : 'info'}>
              {state.manualRecovery?.active
                ? 'Manual recovery is required. Automatic scheduling is paused until it is resolved.'
                : 'No manual recovery is currently required.'}
            </Alert>
            {state.manualRecovery && (
              <Card>
                <CardContent>
                  <Stack spacing={1}>
                    <Typography variant="subtitle1">
                      Status: {state.manualRecovery.active ? 'Requires recovery' : 'Cleared'}
                    </Typography>
                    <Typography variant="body2">
                      <strong>Schedule ID:</strong> {state.manualRecovery.schedule_id || 'N/A'}
                    </Typography>
                    {state.manualRecovery.experiment_name && (
                      <Typography variant="body2">
                        <strong>Experiment:</strong> {state.manualRecovery.experiment_name}
                      </Typography>
                    )}
                    {state.manualRecovery.note && (
                      <Typography variant="body2">
                        <strong>Note:</strong> {state.manualRecovery.note}
                      </Typography>
                    )}
                    <Typography variant="body2">
                      <strong>Triggered by:</strong> {state.manualRecovery.triggered_by || 'N/A'}
                    </Typography>
                    <Typography variant="body2">
                      <strong>Triggered at:</strong> {formatTimestamp(state.manualRecovery.triggered_at)}
                    </Typography>
                    {state.manualRecovery.resolved_by && (
                      <Typography variant="body2">
                        <strong>Resolved by:</strong> {state.manualRecovery.resolved_by}
                      </Typography>
                    )}
                    {state.manualRecovery.resolved_at && (
                      <Typography variant="body2">
                        <strong>Resolved at:</strong> {formatTimestamp(state.manualRecovery.resolved_at)}
                      </Typography>
                    )}
                  </Stack>
                  <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
                    <Button
                      variant="outlined"
                      onClick={handleViewRecoverySchedule}
                      disabled={!state.manualRecovery.schedule_id}
                    >
                      View Schedule
                    </Button>
                    {state.manualRecovery.active && (
                      <Button
                        variant="contained"
                        color="primary"
                        onClick={handleResolveManualRecovery}
                      >
                        Resolve Manual Recovery
                      </Button>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            )}
          </Stack>
        </TabPanel>

        <TabPanel value={currentTab} index={2}>
          <QueueStatus />
        </TabPanel>

        <TabPanel value={currentTab} index={3}>
          <CalendarView />
        </TabPanel>

        <TabPanel value={currentTab} index={4}>
          <ExecutionHistory 
            scheduleId={state.selectedSchedule?.schedule_id}
            maxHeight="700px" 
          />
        </TabPanel>
      </Paper>

      {/* Footer Information */}
      <Box sx={{ mt: 3, p: 2, borderTop: 1, borderColor: 'divider' }}>
        <Typography variant="caption" color="text.secondary" component="div">
          <strong>Scheduling System:</strong> Replaces legacy VBS scripts with modern Python-based scheduling.
          All scheduling operations are logged and support role-based access control.
          Hamilton robot integration supports both real and mock execution modes for development.
        </Typography>
      </Box>

      {/* Improved Schedule Form Dialog */}
      <ImprovedScheduleForm
        open={improvedFormOpen}
        onClose={() => setImprovedFormOpen(false)}
        onSubmit={handleImprovedFormSubmit}
        mode="create"
      />

      {/* Folder Import Dialog */}
      <FolderImportDialog
        open={folderImportOpen}
        onClose={() => setFolderImportOpen(false)}
        onImportComplete={() => {
          // Experiments have been imported, they'll be available in the form now
          console.log('Experiments imported successfully');
        }}
      />
    </Container>
  );
};

export default SchedulingPage;