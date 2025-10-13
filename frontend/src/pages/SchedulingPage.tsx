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

import React, { useState, useEffect, useCallback, useMemo } from 'react';
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
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  CircularProgress
} from '@mui/material';
import useTheme from '@mui/material/styles/useTheme';
import useMediaQuery from '@mui/material/useMediaQuery';
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
  WarningAmber as WarningIcon,
  Email as EmailIcon
} from '@mui/icons-material';
import { useNavigate, Link as RouterLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Import scheduling components
import ScheduleList from '../components/ScheduleList';
import ImprovedScheduleForm from '../components/scheduling/ImprovedScheduleForm';
import NotificationContactsPanel from '../components/scheduling/NotificationContactsPanel';
import NotificationEmailSettingsPanel from '../components/scheduling/NotificationEmailSettingsPanel';
import FolderImportDialog from '../components/scheduling/FolderImportDialog';
import ExecutionHistory from '../components/ExecutionHistory';
import useScheduling from '../hooks/useScheduling';
import { formatDuration, formatExecutionStatus, ScheduledExperiment, CreateScheduleFormData, UpdateScheduleRequest } from '../types/scheduling';

type ScheduleFormValues = Partial<{
  experiment_name: string;
  experiment_path: string;
  schedule_type: 'once' | 'interval' | 'daily' | 'weekly';
  interval_hours: number;
  start_time: string | null;
  estimated_duration: number;
  prerequisites: string[];
  is_active: boolean;
  max_retries: number;
  retry_delay_minutes: number;
  backoff_strategy: 'linear' | 'exponential';
  notification_contacts: string[];
}>;

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => {
  return (
    <div role="tabpanel" hidden={value !== index}>
        {value === index && (
          <Box sx={{ py: { xs: 3, md: 4 }, px: { xs: 1.75, md: 3.75 } }}>
            {children}
          </Box>
        )}
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
  const [scheduleFormMode, setScheduleFormMode] = useState<'create' | 'edit'>('create');
  const [scheduleFormInitialData, setScheduleFormInitialData] = useState<ScheduleFormValues>({});
  const [editingScheduleId, setEditingScheduleId] = useState<string | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [logsLoaded, setLogsLoaded] = useState(false);
  const [logScheduleFilter, setLogScheduleFilter] = useState('');
  const [logStatusFilter, setLogStatusFilter] = useState<'all' | 'sent' | 'pending' | 'error'>('all');
  const [notificationsTab, setNotificationsTab] = useState(0);
  const [contactsRequested, setContactsRequested] = useState(false);
  const [emailSettingsRequested, setEmailSettingsRequested] = useState(false);

  // Initialize scheduling hook
  const { state, actions } = useScheduling();
  const theme = useTheme();
  const isSmallScreen = useMediaQuery(theme.breakpoints.down('sm'));
  const cardPadding = { xs: 2.75, md: 4 };
  const tabPadding = { xs: 1.75, md: 2.75 };

  const formatTimestamp = (value?: string | null): string => {
    if (!value) {
      return 'N/A';
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
  };

  const formatStartTimeForInput = (iso?: string | null): string => {
    if (!iso) {
      return '';
    }
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
      return '';
    }
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 16);
  };

  const handleScheduleFormSubmit = async (data: any) => {
    if (scheduleFormMode === 'edit' && editingScheduleId) {
      const updatePayload: UpdateScheduleRequest = {
        experiment_name: data.experiment_name,
        experiment_path: data.experiment_path,
        schedule_type: data.schedule_type,
        interval_hours: data.schedule_type === 'interval' ? Number(data.interval_hours) : undefined,
        start_time: data.start_time ? new Date(data.start_time).toISOString() : undefined,
        estimated_duration: Number(data.estimated_duration),
        is_active: data.is_active ?? true,
        retry_config: {
          max_retries: Number(data.max_retries ?? 0),
          retry_delay_minutes: Number(data.retry_delay_minutes ?? 0),
          backoff_strategy: data.backoff_strategy || 'linear',
        },
        prerequisites: Array.isArray(data.prerequisites) ? data.prerequisites : [],
        notification_contacts: Array.isArray(data.notification_contacts) ? data.notification_contacts : [],
        expected_updated_at: state.selectedSchedule?.updated_at || undefined,
      };
      await actions.updateSchedule(editingScheduleId, updatePayload);
      await actions.loadSchedules(true, editingScheduleId);
    } else {
      const createPayload: CreateScheduleFormData = {
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
        notification_contacts: Array.isArray(data.notification_contacts) ? data.notification_contacts : [],
      };
      await actions.createSchedule(createPayload);
      await actions.loadSchedules(true);
    }
  };

  const handleScheduleFormClose = () => {
    setImprovedFormOpen(false);
    setScheduleFormMode('create');
    setScheduleFormInitialData({ notification_contacts: [] });
    setEditingScheduleId(null);
  };

  const handleOpenCreateForm = () => {
    setScheduleFormMode('create');
    setScheduleFormInitialData({ notification_contacts: [] });
    setEditingScheduleId(null);
    setImprovedFormOpen(true);
  };

  const handleOpenEditForm = () => {
    const selected = state.selectedSchedule;
    if (!selected) {
      return;
    }

    setScheduleFormMode('edit');
    setEditingScheduleId(selected.schedule_id);
    const allowedTypes: Array<'once' | 'interval' | 'daily' | 'weekly'> = ['once', 'interval', 'daily', 'weekly'];
    const scheduleType = allowedTypes.includes(selected.schedule_type as any)
      ? (selected.schedule_type as 'once' | 'interval' | 'daily' | 'weekly')
      : 'once';
    setScheduleFormInitialData({
      experiment_name: selected.experiment_name,
      experiment_path: selected.experiment_path,
      schedule_type: scheduleType,
      interval_hours: selected.interval_hours ?? undefined,
      start_time: selected.start_time ? formatStartTimeForInput(selected.start_time) : null,
      estimated_duration: selected.estimated_duration,
      is_active: selected.is_active,
      max_retries: selected.retry_config?.max_retries ?? 3,
      retry_delay_minutes: selected.retry_config?.retry_delay_minutes ?? 2,
    backoff_strategy: selected.retry_config?.backoff_strategy ?? 'linear',
    prerequisites: selected.prerequisites ?? [],
    notification_contacts: selected.notification_contacts ?? [],
  });
  setImprovedFormOpen(true);
};

  const handleLogsRefresh = useCallback(async () => {
    if (user?.role !== 'admin') {
      return;
    }
    setLogsLoading(true);
    setLogsError(null);

    const params: Record<string, string | number> = { limit: 50 };
    const trimmedSchedule = logScheduleFilter.trim();
    if (trimmedSchedule) {
      params.schedule_id = trimmedSchedule;
    }
    if (logStatusFilter !== 'all') {
      params.status = logStatusFilter;
    }

    const result = await actions.loadNotificationLogs(params);
    if (result?.error) {
      setLogsError(result.error);
    }
    setLogsLoading(false);
    setLogsLoaded(true);
  }, [actions.loadNotificationLogs, logScheduleFilter, logStatusFilter, user?.role]);

  const applyLogFilters = useCallback(() => {
    setLogsLoaded(false);
    handleLogsRefresh();
  }, [handleLogsRefresh]);

  const resetLogFilters = useCallback(() => {
    setLogScheduleFilter('');
    setLogStatusFilter('all');
    setLogsLoaded(false);
  }, []);

  const openNotificationsTab = useCallback(() => {
    setCurrentTab(4);
  }, []);

  useEffect(() => {
    if (user?.role !== 'admin') {
      return;
    }
    if (currentTab !== 4 || notificationsTab !== 0) {
      return;
    }
    if (!contactsRequested) {
      setContactsRequested(true);
      actions.loadContacts(true);
    }
  }, [user?.role, currentTab, notificationsTab, contactsRequested, actions]);

  useEffect(() => {
    if (user?.role !== 'admin') {
      return;
    }
    if (currentTab !== 4 || notificationsTab !== 1) {
      return;
    }
    if (!logsLoaded && !logsLoading) {
      handleLogsRefresh();
    }
  }, [user?.role, currentTab, notificationsTab, logsLoaded, logsLoading, handleLogsRefresh]);

  useEffect(() => {
    if (user?.role !== 'admin') {
      return;
    }
    if (currentTab !== 4 || notificationsTab !== 2) {
      return;
    }
    if (!emailSettingsRequested) {
      setEmailSettingsRequested(true);
      actions.loadNotificationSettings();
    }
  }, [user?.role, currentTab, notificationsTab, emailSettingsRequested, actions]);

  const latestNotificationForSelectedSchedule = useMemo(() => {
    if (!state.selectedSchedule || !state.notificationLogs.length) {
      return null;
    }
    const scheduleId = state.selectedSchedule.schedule_id;
    let latest = null;
    let latestTime = -Infinity;
    for (const log of state.notificationLogs) {
      if (log.schedule_id !== scheduleId) {
        continue;
      }
      const timestamp = log.triggered_at ? new Date(log.triggered_at).getTime() : -Infinity;
      if (!Number.isNaN(timestamp) && timestamp > latestTime) {
        latest = log;
        latestTime = timestamp;
      }
    }
    return latest;
  }, [state.selectedSchedule, state.notificationLogs]);

  const getLogStatusColor = useCallback(
    (status?: string): 'default' | 'success' | 'warning' | 'error' | 'info' => {
      switch ((status || '').toLowerCase()) {
        case 'sent':
          return 'success';
        case 'pending':
          return 'warning';
        case 'error':
          return 'error';
        default:
          return 'default';
      }
    },
    [],
  );

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

  const handleNotificationsTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setNotificationsTab(newValue);
  };

  // Status summary component
  const SchedulingStatusSummary: React.FC = () => {
    // Use the existing state from parent component instead of creating new hook instance

    return (
      <Grid container spacing={{ xs: 2, md: 2.5 }} sx={{ mb: { xs: 2.5, md: 3 } }}>
        <Grid item xs={12} md={3}>
          <Card sx={{ borderRadius: 2, height: '100%' }}>
            <CardContent sx={{ p: cardPadding }}>
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
          <Card sx={{ borderRadius: 2, height: '100%' }}>
            <CardContent sx={{ p: cardPadding }}>
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
          <Card sx={{ borderRadius: 2, height: '100%' }}>
            <CardContent sx={{ p: cardPadding }}>
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
          <Card sx={{ borderRadius: 2, height: '100%' }}>
            <CardContent sx={{ p: cardPadding }}>
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
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          justifyContent="space-between"
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          spacing={1.5}
          sx={{ mb: { xs: 2.5, md: 3 } }}
        >
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            Upcoming Schedule Calendar
          </Typography>
          <Button
            startIcon={<RefreshIcon />}
            onClick={loadCalendarData}
            size="small"
            sx={{ alignSelf: { xs: 'flex-start', sm: 'center' } }}
          >
            Refresh
          </Button>
        </Stack>
        
        <Grid container spacing={{ xs: 2.5, md: 3 }}>
          {calendarData.map(([date, schedules]) => (
            <Grid item xs={12} md={6} key={date}>
              <Card sx={{ borderRadius: 2, height: '100%' }}>
                <CardContent sx={{ p: cardPadding }}>
                  <Typography variant="h6" color="primary" gutterBottom>
                    {new Date(date).toLocaleDateString('en-US', { 
                      weekday: 'long',
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric'
                    })}
                  </Typography>

                  <Stack spacing={1.5}>
                    {schedules.map((schedule) => (
                      <Box
                        key={schedule.schedule_id}
                        sx={{
                          p: 1.75,
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
        
        <Alert severity="info" sx={{ mt: { xs: 2.5, md: 3 } }}>
          <Typography variant="body2">
            <strong>Calendar View:</strong> Showing {calendarData.reduce((total, [, schedules]) => total + schedules.length, 0)} 
            scheduled experiments across {calendarData.length} dates.
            Times shown are based on next_run calculations.
          </Typography>
        </Alert>
      </Box>
    );
  };

  return (
    <Container
      maxWidth="xl"
      sx={{
        mt: { xs: 1.5, md: 2 },
        mb: { xs: 3.5, md: 5 },
        px: { xs: 2.5, md: 4 },
        py: { xs: 3, md: 4 }
      }}
    >
      {/* Page Header with Navigation */}
      <Box sx={{ mb: { xs: 3, md: 4 } }}>
        {/* Navigation Controls */}
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          spacing={2}
          sx={{ mb: { xs: 2.5, md: 3 } }}
        >
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
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          Experiment Scheduling
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mt: { xs: 1.5, md: 2 } }}>
          Schedule, manage, and monitor automated experiment execution.
          Replace legacy VBS scripts with modern scheduling capabilities.
        </Typography>

        {/* Status Summary */}
        <Box sx={{ mt: { xs: 3, md: 4 } }}>
          <SchedulingStatusSummary />
        </Box>

        {/* Error Display */}
        {state.error && (
          <Alert severity="error" onClose={actions.clearError} sx={{ mb: 3 }}>
            {state.error}
          </Alert>
        )}
      </Box>

      {/* Main Content */}
      <Paper elevation={1} sx={{ borderRadius: 2, overflow: 'hidden' }}>
        {/* Navigation Tabs */}
        <Box
          sx={{
            borderBottom: 1,
            borderColor: 'divider',
            overflowX: 'auto',
            px: { xs: 1.5, md: 2.5 },
            py: 1,
            bgcolor: 'background.paper'
          }}
        >
          <Tabs
            value={currentTab}
            onChange={handleTabChange}
            variant="scrollable"
            scrollButtons="auto"
            allowScrollButtonsMobile
            aria-label="scheduling tabs"
            sx={{
              minHeight: { xs: 44, md: 48 },
              '& .MuiTabs-flexContainer': {
                columnGap: { xs: 0.5, md: 1 }
              },
              '& .MuiTabs-indicator': {
                height: 3,
                borderRadius: 2
              }
            }}
          >
            <Tab 
              label={
                <Stack direction="row" alignItems="center" spacing={isSmallScreen ? 1 : 1.25}>
                  <ScheduleIcon fontSize="small" />
                  <Typography component="span" variant="body2">
                    Schedules
                  </Typography>
                </Stack>
              }
              sx={{
                minHeight: 0,
                py: { xs: 1, md: 1.25 },
                px: tabPadding
              }}
            />
            <Tab 
              label={
                <Stack direction="row" alignItems="center" spacing={isSmallScreen ? 1 : 1.25}>
                  <WarningIcon fontSize="small" color={state.manualRecovery?.active ? 'error' : 'disabled'} />
                  <Typography component="span" variant="body2">
                    {isSmallScreen ? 'Recovery' : 'Manual Recovery'}
                  </Typography>
                </Stack>
              }
              sx={{
                minHeight: 0,
                py: { xs: 1, md: 1.25 },
                px: tabPadding
              }}
            />
            <Tab 
              label={
                <Stack direction="row" alignItems="center" spacing={isSmallScreen ? 1 : 1.25}>
                  <CalendarIcon fontSize="small" />
                  <Typography component="span" variant="body2">
                    {isSmallScreen ? 'Calendar' : 'Calendar View'}
                  </Typography>
                </Stack>
              }
              sx={{
                minHeight: 0,
                py: { xs: 1, md: 1.25 },
                px: tabPadding
              }}
            />
            <Tab 
              label={
                <Stack direction="row" alignItems="center" spacing={isSmallScreen ? 1 : 1.25}>
                  <HistoryIcon fontSize="small" />
                  <Typography component="span" variant="body2">
                    {isSmallScreen ? 'History' : 'Execution History'}
                  </Typography>
                </Stack>
              }
              sx={{
                minHeight: 0,
                py: { xs: 1, md: 1.25 },
                px: tabPadding
              }}
            />
            {user?.role === 'admin' && (
              <Tab 
                label={
                  <Stack direction="row" alignItems="center" spacing={isSmallScreen ? 1 : 1.25}>
                    <EmailIcon fontSize="small" />
                    <Typography component="span" variant="body2">
                      Notifications
                    </Typography>
                  </Stack>
                }
                sx={{
                  minHeight: 0,
                  py: { xs: 1, md: 1.25 },
                  px: tabPadding
                }}
              />
            )}
          </Tabs>
        </Box>

        {/* Tab Panels */}
        <TabPanel value={currentTab} index={0}>
          <Grid container spacing={{ xs: 3, lg: 3.5 }}>
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
              <Stack spacing={2.5}>
                {/* Action Buttons */}
                <Card sx={{ borderRadius: 2 }}>
                  <CardContent sx={{ p: cardPadding }}>
                    <Typography variant="h6" gutterBottom>
                      Actions
                    </Typography>
                    <Stack spacing={2}>
                      {/* Create New Schedule Button */}
                      <Button
                        variant="contained"
                        fullWidth
                        startIcon={<AddIcon />}
                        onClick={handleOpenCreateForm}
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
                            onClick={handleOpenEditForm}
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
                                actions.deleteSchedule(state.selectedSchedule);
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

                {user?.role === 'admin' && state.selectedSchedule && (
                  <Card sx={{ borderRadius: 2 }}>
                    <CardContent sx={{ p: cardPadding }}>
                      <Typography variant="h6" gutterBottom>
                        Latest Notification
                      </Typography>
                      {latestNotificationForSelectedSchedule ? (
                        <Stack spacing={1.5}>
                          <Stack direction="row" spacing={1} alignItems="center">
                            <Chip
                              label={latestNotificationForSelectedSchedule.status || 'unknown'}
                              color={getLogStatusColor(latestNotificationForSelectedSchedule.status)}
                              size="small"
                            />
                            <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                              {latestNotificationForSelectedSchedule.event_type?.replace(/_/g, ' ') || 'event'}
                            </Typography>
                          </Stack>
                          <Typography variant="body2" color="text.secondary">
                            Sent: {formatTimestamp(latestNotificationForSelectedSchedule.triggered_at)}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            Recipients: {latestNotificationForSelectedSchedule.recipients.length ? latestNotificationForSelectedSchedule.recipients.join(', ') : 'N/A'}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            Attachments: {latestNotificationForSelectedSchedule.attachments.length ? `${latestNotificationForSelectedSchedule.attachments.length} file${latestNotificationForSelectedSchedule.attachments.length > 1 ? 's' : ''}` : 'N/A'}
                          </Typography>
                          {latestNotificationForSelectedSchedule.error_message && (
                            <Alert severity="error" variant="outlined">
                              {latestNotificationForSelectedSchedule.error_message}
                            </Alert>
                          )}
                          <Button onClick={openNotificationsTab} size="small">
                            View notification history
                          </Button>
                        </Stack>
                      ) : (
                        <Stack spacing={1.5}>
                          <Typography variant="body2" color="text.secondary">
                            No notifications recorded for this schedule yet.
                          </Typography>
                          <Button onClick={openNotificationsTab} size="small">
                            Configure notifications
                          </Button>
                        </Stack>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Operation Status */}
                {state.operationStatus && (
                  <Alert 
                    severity={'info'}
                    sx={{ borderRadius: 2 }}
                  >
                    {state.operationStatus}
                  </Alert>
                )}
              </Stack>
            </Grid>
          </Grid>
        </TabPanel>

        <TabPanel value={currentTab} index={1}>
          <Stack spacing={2.5}>
            <Alert severity={state.manualRecovery?.active ? 'warning' : 'info'}>
              {state.manualRecovery?.active
                ? 'Manual recovery is required. Automatic scheduling is paused until it is resolved.'
                : 'No manual recovery is currently required.'}
            </Alert>
            {state.manualRecovery && (
              <Card sx={{ borderRadius: 2 }}>
                <CardContent sx={{ p: cardPadding }}>
                  <Stack spacing={1.25}>
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
          <CalendarView />
        </TabPanel>

        <TabPanel value={currentTab} index={3}>
          <ExecutionHistory 
            scheduleId={state.selectedSchedule?.schedule_id}
            maxHeight="700px" 
          />
        </TabPanel>

        {user?.role === 'admin' && (
          <TabPanel value={currentTab} index={4}>
            <Stack spacing={3}>
              <Box sx={{ borderBottom: 1, borderColor: 'divider', px: { xs: 0.5, md: 1 } }}>
                <Tabs
                  value={notificationsTab}
                  onChange={handleNotificationsTabChange}
                  variant="scrollable"
                  scrollButtons="auto"
                  allowScrollButtonsMobile
                  aria-label="notification configuration tabs"
                  sx={{
                    minHeight: { xs: 42, md: 46 },
                    '& .MuiTabs-indicator': {
                      height: 3,
                      borderRadius: 2,
                    },
                  }}
                >
                  <Tab label="Contacts" sx={{ minHeight: 0 }} />
                  <Tab label="Delivery Logs" sx={{ minHeight: 0 }} />
                  <Tab label="Email Settings" sx={{ minHeight: 0 }} />
                </Tabs>
              </Box>

              {notificationsTab === 0 && (
                <NotificationContactsPanel
                  contacts={state.contacts}
                  onRefresh={(includeInactive) => actions.loadContacts(includeInactive)}
                  onCreate={actions.createContact}
                  onUpdate={actions.updateContact}
                  onDelete={actions.deleteContact}
                />
              )}

              {notificationsTab === 1 && (
                <Card sx={{ borderRadius: 2 }}>
                  <CardContent sx={{ p: cardPadding }}>
                    <Stack
                      direction={{ xs: 'column', md: 'row' }}
                      spacing={2}
                      alignItems={{ xs: 'stretch', md: 'flex-end' }}
                      sx={{ mb: 2 }}
                    >
                      <TextField
                        label="Schedule filter"
                        value={logScheduleFilter}
                        onChange={(event) => setLogScheduleFilter(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault();
                            applyLogFilters();
                          }
                        }}
                        size="small"
                        sx={{ minWidth: { xs: '100%', md: 220 } }}
                        placeholder="Schedule ID"
                      />
                      <FormControl size="small" sx={{ minWidth: 160 }}>
                        <InputLabel id="log-status-label">Status</InputLabel>
                        <Select
                          labelId="log-status-label"
                          label="Status"
                          value={logStatusFilter}
                          onChange={(event) => setLogStatusFilter(event.target.value as typeof logStatusFilter)}
                        >
                          <MenuItem value="all">All statuses</MenuItem>
                          <MenuItem value="sent">Sent</MenuItem>
                          <MenuItem value="pending">Pending</MenuItem>
                          <MenuItem value="error">Error</MenuItem>
                        </Select>
                      </FormControl>
                      <Stack direction="row" spacing={1}>
                        <Button variant="contained" size="small" onClick={applyLogFilters} disabled={logsLoading}>
                          Apply
                        </Button>
                        <Button
                          variant="text"
                          size="small"
                          onClick={resetLogFilters}
                          disabled={logsLoading || (logScheduleFilter === '' && logStatusFilter === 'all')}
                        >
                          Reset
                        </Button>
                      </Stack>
                      <Button
                        variant="outlined"
                        size="small"
                        startIcon={<RefreshIcon />}
                        onClick={handleLogsRefresh}
                        disabled={logsLoading}
                      >
                        Refresh
                      </Button>
                    </Stack>

                    {logsError && (
                      <Alert severity="error" sx={{ mb: 2 }}>
                        {logsError}
                      </Alert>
                    )}

                    {logsLoading && state.notificationLogs.length === 0 ? (
                      <Box display="flex" justifyContent="center" py={4}>
                        <CircularProgress size={32} />
                      </Box>
                    ) : state.notificationLogs.length === 0 ? (
                      <Typography variant="body2" color="text.secondary">
                        No notification events recorded yet.
                      </Typography>
                    ) : (
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Timestamp</TableCell>
                            <TableCell>Schedule</TableCell>
                            <TableCell>Event</TableCell>
                            <TableCell>Status</TableCell>
                            <TableCell>Recipients</TableCell>
                            <TableCell>Attachments</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {state.notificationLogs.map((log) => (
                            <TableRow key={log.log_id} hover>
                              <TableCell>{formatTimestamp(log.triggered_at)}</TableCell>
                              <TableCell>{log.schedule_id || 'N/A'}</TableCell>
                              <TableCell>{(log.event_type || 'event').replace(/_/g, ' ')}</TableCell>
                              <TableCell>
                                <Chip
                                  label={log.status || 'unknown'}
                                  color={getLogStatusColor(log.status)}
                                  size="small"
                                />
                              </TableCell>
                              <TableCell>
                                {log.recipients.length ? log.recipients.join(', ') : 'N/A'}
                                {log.error_message && (
                                  <Typography variant="caption" color="error" display="block">
                                    {log.error_message}
                                  </Typography>
                                )}
                              </TableCell>
                              <TableCell>
                                {log.attachments.length
                                  ? `${log.attachments.length} file${log.attachments.length > 1 ? 's' : ''}`
                                  : 'N/A'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                  </CardContent>
                </Card>
              )}

              {notificationsTab === 2 && (
              <NotificationEmailSettingsPanel
                  settings={state.notificationSettings}
                  loading={state.notificationSettingsLoading}
                  onRefresh={actions.loadNotificationSettings}
                  onSave={actions.updateNotificationSettings}
                  onSendTest={actions.sendNotificationTestEmail}
                  contacts={state.contacts}
                />
              )}
            </Stack>
          </TabPanel>
        )}
      </Paper>

      {/* Improved Schedule Form Dialog */}
      <ImprovedScheduleForm
        open={improvedFormOpen}
        onClose={handleScheduleFormClose}
        onSubmit={handleScheduleFormSubmit}
        initialData={scheduleFormInitialData}
        mode={scheduleFormMode}
        contacts={state.contacts}
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
