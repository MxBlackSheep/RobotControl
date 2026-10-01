import { DetailTitle, EmptyPanel, ListRow, PageContent, PageHeader, Panel, PanelLabel } from '../components/PageLayout';
import { useSchedulingSection, isLocalUser } from '../components/navigation';
/**
 * RobotControl Experiment Scheduling Page
 *
 * Dedicated page for experiment scheduling and management operations.
 * Provides full-page scheduling interface with:
 * - Page-level error boundaries and authentication
 * - Breadcrumb navigation following app patterns
 * - User and admin access control for different operations
 * - Comprehensive scheduling functionality
 * - Integration with main application navigation
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Box,
  Typography,
  Button,
  Alert,
  Stack,
  Grid,
  Card,
  CardContent,
  Tab,
  Tabs,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Table,
  TableContainer,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  CircularProgress
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  FolderOpen as FolderIcon,
  Refresh as RefreshIcon,
  History as HistoryIcon,
  Archive as ArchiveIcon
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Import scheduling components
import ScheduleList from '../components/ScheduleList';
import ScheduleCollection, { repeatLabel, scheduleState } from '../components/scheduling/ScheduleCollection';
import StatusChip from '../components/StatusChip';
import { fontMono, layout, StatusTone } from '../theme';
import WarningAmber from '@mui/icons-material/WarningAmber';
import InspectionWorkspace from '../components/InspectionWorkspace';
import SectionPanel from '../components/SectionPanel';
import RecoverySafetyPanel from '../components/scheduling/RecoverySafetyPanel';
import ImprovedScheduleForm from '../components/scheduling/ImprovedScheduleForm';
import NotificationContactsPanel from '../components/scheduling/NotificationContactsPanel';
import NotificationEmailSettingsPanel from '../components/scheduling/NotificationEmailSettingsPanel';
import FolderImportDialog from '../components/scheduling/FolderImportDialog';
import MethodLibraryPanel from '../components/scheduling/MethodLibraryPanel';
import MethodPathDialog from '../components/scheduling/MethodPathDialog';
import { LibraryMethod } from '../types/scheduling';
import ExecutionHistory from '../components/ExecutionHistory';
import useScheduling from '../hooks/useScheduling';
import { formatDuration, ScheduledExperiment, CreateScheduleFormData, UpdateScheduleRequest, SchedulingOperationStatus } from '../types/scheduling';
import StatusDialog from '../components/StatusDialog';
import { DeleteConfirmationDialog } from '../components/ScheduleActions';

type ScheduleFormValues = Partial<{
  experiment_name: string;
  experiment_path: string;
  schedule_type: 'once' | 'interval' | 'daily' | 'weekly';
  interval_hours: number;
  start_time: string | null;
  estimated_duration: number;
  log_inactivity_threshold_minutes: number;
  prerequisites: string[];
  is_active: boolean;
  timeout_minutes: number | null;
  timeout_action: 'continue' | 'run_cleanup_and_terminate';
  timeout_cleanup_experiment_name: string | null;
  timeout_cleanup_experiment_path: string | null;
  notification_contacts: string[];
}>;

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => {
  return (
    <SectionPanel active={value === index}>
        {(
          <Box sx={{ minWidth: 0 }}>
            {children}
          </Box>
        )}
      </SectionPanel>
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
  const [currentTab, setCurrentTab] = useSchedulingSection(user);
  const [improvedFormOpen, setImprovedFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [queueDetailsOpen, setQueueDetailsOpen] = useState(false);
  const [catalogueVersion, setCatalogueVersion] = useState(0);
  const [methodToRelink, setMethodToRelink] = useState<LibraryMethod | null>(null);
  const [folderImportOpen, setFolderImportOpen] = useState(false);
  const [scheduleFormMode, setScheduleFormMode] = useState<'create' | 'edit'>('create');
  const [scheduleFormInitialData, setScheduleFormInitialData] = useState<ScheduleFormValues>({});
  const [editingVersion, setEditingVersion] = useState<string | undefined>();
  const [editingScheduleId, setEditingScheduleId] = useState<string | null>(null);
  // Captured when the edit form opens, like its initial data.
  const [editingPreparation, setEditingPreparation] = useState<Pick<ScheduledExperiment, 'preparation' | 'preparation_state'>>({});
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [logScheduleFilter, setLogScheduleFilter] = useState('');
  const [logStatusFilter, setLogStatusFilter] = useState<'all' | 'sent' | 'pending' | 'error' | 'partial' | 'unknown' | 'cancelled'>('all');
  const [appliedLogFilters, setAppliedLogFilters] = useState({ schedule: '', status: 'all' });
  const [notificationsTab, setNotificationsTab] = useState(0);
  const [contactsRequested, setContactsRequested] = useState(false);
  const [emailSettingsRequested, setEmailSettingsRequested] = useState(false);

  // Initialize scheduling hook
  const { state, actions } = useScheduling();
  const cardPadding = { xs: 2, md: 2 };
  const isLocalSession = isLocalUser(user);
  const isLocalClient = isLocalSession;

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
        log_inactivity_threshold_minutes: Number(data.log_inactivity_threshold_minutes ?? 3),
        is_active: data.is_active ?? true,
        timeout_config: {
          timeout_minutes:
            data.timeout_minutes === null || data.timeout_minutes === undefined
              ? null
              : Number(data.timeout_minutes),
          action: data.timeout_action || 'continue',
          cleanup_experiment_name:
            data.timeout_action === 'run_cleanup_and_terminate'
              ? data.timeout_cleanup_experiment_name ?? null
              : null,
          cleanup_experiment_path:
            data.timeout_action === 'run_cleanup_and_terminate'
              ? data.timeout_cleanup_experiment_path ?? null
              : null,
        },
        prerequisites: Array.isArray(data.prerequisites) ? data.prerequisites : [],
        ...(data.preparation !== undefined ? { preparation: data.preparation } : {}),
        notification_contacts: Array.isArray(data.notification_contacts) ? data.notification_contacts : [],
        expected_updated_at: editingVersion,
      };
      await actions.updateSchedule(editingScheduleId, updatePayload);
    } else {
      const createPayload: CreateScheduleFormData = {
        experiment_name: data.experiment_name,
        experiment_path: data.experiment_path,
        schedule_type: data.schedule_type,
        interval_hours: data.schedule_type === 'interval' ? Number(data.interval_hours) : undefined,
        start_time: data.start_time ? new Date(data.start_time) : null,
        estimated_duration: Number(data.estimated_duration),
        log_inactivity_threshold_minutes: Number(data.log_inactivity_threshold_minutes ?? 3),
        is_active: data.is_active ?? true,
        timeout_minutes:
          data.timeout_minutes === null || data.timeout_minutes === undefined
            ? null
            : Number(data.timeout_minutes),
        timeout_action: data.timeout_action || 'continue',
        timeout_cleanup_experiment_name:
          data.timeout_action === 'run_cleanup_and_terminate'
            ? data.timeout_cleanup_experiment_name ?? null
            : null,
        timeout_cleanup_experiment_path:
          data.timeout_action === 'run_cleanup_and_terminate'
            ? data.timeout_cleanup_experiment_path ?? null
            : null,
        prerequisites: Array.isArray(data.prerequisites) ? data.prerequisites : [],
        preparation: data.preparation,
        notification_contacts: Array.isArray(data.notification_contacts) ? data.notification_contacts : [],
      };
      await actions.createSchedule(createPayload);
    }
  };

  const handleScheduleFormClose = () => {
    setImprovedFormOpen(false);
    setScheduleFormMode('create');
    setScheduleFormInitialData({ notification_contacts: [] });
    setEditingScheduleId(null);
    setEditingPreparation({});
  };

  const handleOpenCreateForm = () => {
    setScheduleFormMode('create');
    setScheduleFormInitialData({ notification_contacts: [] });
    setEditingScheduleId(null);
    setEditingPreparation({});
    setImprovedFormOpen(true);
  };

  const handleOpenEditForm = () => {
    const selected = state.selectedSchedule;
    if (!selected) {
      return;
    }

    setScheduleFormMode('edit');
    setEditingScheduleId(selected.schedule_id);
    setEditingPreparation({ preparation: selected.preparation ?? null, preparation_state: selected.preparation_state });
    setEditingVersion(selected.updated_at || undefined);
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
      log_inactivity_threshold_minutes: selected.log_inactivity_threshold_minutes,
      is_active: selected.is_active,
      timeout_minutes: selected.timeout_config?.timeout_minutes ?? null,
      timeout_action: selected.timeout_config?.action ?? 'continue',
      timeout_cleanup_experiment_name: selected.timeout_config?.cleanup_experiment_name ?? null,
      timeout_cleanup_experiment_path: selected.timeout_config?.cleanup_experiment_path ?? null,
      prerequisites: selected.prerequisites ?? [],
      notification_contacts: selected.notification_contacts ?? [],
    });
    setImprovedFormOpen(true);
  };

  const logRead = useRef(0);
  const handleLogsRefresh = useCallback(async () => {
    const id = ++logRead.current;
    if (user?.role !== 'admin') {
      return;
    }
    setLogsLoading(true);
    setLogsError(null);

    const params: Record<string, string | number> = { limit: 50 };
    const trimmedSchedule = appliedLogFilters.schedule.trim();
    if (trimmedSchedule) {
      params.schedule_id = trimmedSchedule;
    }
    if (appliedLogFilters.status !== 'all') {
      params.status = appliedLogFilters.status;
    }

    const result = await actions.loadNotificationLogs(params);
    if (id !== logRead.current) return;
    if (result?.error) {
      setLogsError(result.error);
    }
    setLogsLoading(false);
  }, [actions.loadNotificationLogs, appliedLogFilters, user?.role]);

  const applyLogFilters = useCallback(() => {
    setAppliedLogFilters({ schedule: logScheduleFilter, status: logStatusFilter });
  }, [logScheduleFilter, logStatusFilter]);

  const resetLogFilters = useCallback(() => {
    setLogScheduleFilter('');
    setLogStatusFilter('all');
    setAppliedLogFilters({ schedule: '', status: 'all' });
  }, []);

  const openNotificationsTab = useCallback(() => {
    if (user?.role === 'admin') {
      setCurrentTab(5);
    }
  }, [user?.role, setCurrentTab]);

  useEffect(() => {
    if (user?.role !== 'admin') {
      return;
    }
    if (currentTab !== 5 || notificationsTab !== 0) {
      return;
    }
    if (!contactsRequested) {
      setContactsRequested(true);
      actions.loadContacts(true);
    }
  }, [user?.role, currentTab, notificationsTab, contactsRequested, actions]);

  useEffect(() => {
    if (user?.role !== 'admin' || currentTab !== 5 || notificationsTab !== 1) return;
    let stopped = false;
    let timer: number;
    const poll = async () => {
      if (document.visibilityState === 'visible') await handleLogsRefresh();
      if (!stopped) timer = window.setTimeout(poll, 5000);
    };
    void poll();
    return () => { stopped = true; logRead.current++; clearTimeout(timer); };
  }, [user?.role, currentTab, notificationsTab, handleLogsRefresh]);

  useEffect(() => {
    if (user?.role !== 'admin') {
      return;
    }
    if (currentTab !== 5 || notificationsTab !== 2) {
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

  const getLogStatusTone = (status?: string): StatusTone => {
    switch ((status || '').toLowerCase()) {
      case 'sent': return 'completed';
      case 'partial': case 'unknown': case 'pending': return 'attention';
      case 'error': return 'fault';
      default: return 'neutral';
    }
  };

  // Access control - users and admins can view, only admins can control scheduler service
  if (!user) {
    return (
      <StatusDialog
        status={{ title: 'Authentication Required', message: 'Please log in to access experiment scheduling functionality.', severity: 'warning', action: { label: 'Go to Login', onClick: () => navigate('/login') } }}
        onClose={() => navigate('/login')}
      />
    );
  }

  if (!['admin', 'user'].includes(user.role)) {
    return (
      <StatusDialog
        status={{ title: 'Insufficient Permissions', message: 'Experiment scheduling requires user or administrator privileges. Contact your system administrator for access.', severity: 'warning', action: { label: 'Return to Dashboard', onClick: () => navigate('/') } }}
        onClose={() => navigate('/')}
      />
    );
  }

  const handleNotificationsTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setNotificationsTab(newValue);
  };

  const calendarData = (() => {
    const grouped: Record<string, ScheduledExperiment[]> = {};
    state.schedules.filter(schedule => schedule.next_run).forEach(schedule => {
      const day = new Date(schedule.next_run!).toDateString();
      (grouped[day] ||= []).push(schedule);
    });
    return Object.entries(grouped).sort((a, b) => new Date(a[0]).getTime() - new Date(b[0]).getTime());
  })();
  const renderCalendarView = () => {
    if (calendarData.length === 0) {
      return (
        <Alert severity="info">
          <Typography variant="h6" gutterBottom>
            No upcoming schedules
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
            Upcoming runs
          </Typography>
          <Button
            startIcon={<RefreshIcon />}
            onClick={() => void actions.loadSchedules(false)}
            size="small"
            sx={{ alignSelf: { xs: 'flex-start', sm: 'center' } }}
          >
            Refresh
          </Button>
        </Stack>

        <Grid container spacing={2}>
          {calendarData.map(([date, schedules]) => (
            <Grid item xs={12} md={6} key={date}>
              <Card component="section" aria-label={date} sx={{ height: '100%' }}>
                <Typography component="h3" variant="h6" sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider' }}>
                  {new Date(date).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                </Typography>
                {schedules.map((schedule) => (
                  <Box key={schedule.schedule_id} sx={{ display: 'grid', gridTemplateColumns: '64px minmax(0, 1fr) auto', gap: 1.5, alignItems: 'start', px: 2, py: 1.25, borderBottom: 1, borderColor: 'divider', '&:last-of-type': { borderBottom: 0 }, opacity: schedule.is_active ? 1 : 0.7 }}>
                    <Typography sx={{ fontFamily: fontMono, fontSize: 13, pt: 0.25 }}>
                      {schedule.next_run
                        ? new Date(schedule.next_run).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
                        : 'No scheduled time'}
                    </Typography>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography sx={{ fontSize: 14, fontWeight: 500, overflowWrap: 'anywhere' }}>{schedule.experiment_name}</Typography>
                      <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
                        Duration: {formatDuration(schedule.estimated_duration)} · Type: {schedule.schedule_type}
                        {schedule.interval_hours && ` (${schedule.interval_hours}h)`}
                      </Typography>
                    </Box>
                    <Stack spacing={0.5} alignItems="flex-end">
                      <StatusChip tone={schedule.is_active ? 'completed' : 'neutral'} label={schedule.is_active ? 'Active' : 'Inactive'} />
                      {schedule.prerequisites.length > 0 && <StatusChip tone="neutral" label={`${schedule.prerequisites.length} prereqs`} />}
                    </Stack>
                  </Box>
                ))}
              </Card>
            </Grid>
          ))}
        </Grid>

        <Alert severity="info" sx={{ mt: { xs: 2.5, md: 3 } }}>
          <Typography variant="body2">
            Showing {calendarData.reduce((total, [, schedules]) => total + schedules.length, 0)}
            scheduled experiments across {calendarData.length} dates.
            Next planned run for each schedule.
          </Typography>
        </Alert>
      </Box>
    );
  };

  return (
    <PageContent variant={currentTab === 5 && notificationsTab === 2 ? "task" : "inspection"}>
      <PageHeader title="Scheduling" actions={isLocalSession && <>
        <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpenCreateForm} disabled={state.loading}>Create schedule</Button>
        <Button variant="outlined" startIcon={<FolderIcon />} onClick={() => setFolderImportOpen(true)} disabled={state.loading}>Import methods</Button>
      </>} />
      <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center" sx={{ mb: `${layout.gutter}px`, px: 2, py: 0.5, minHeight: layout.row, boxSizing: 'border-box', bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: `${layout.radius}px` }} aria-label="Scheduler service summary">
        <StatusChip tone={state.schedulerRunning ? 'running' : 'neutral'} label={`Scheduler service: ${state.schedulerRunning ? 'Running' : 'Stopped'}`} />
        <StatusChip tone="neutral" label={state.queueStatus ? `${state.queueStatus.running_jobs ?? 0} running · ${state.queueStatus.queued_jobs ?? 0} queued` : 'Queue unavailable'} />
        <Button size="small" startIcon={<RefreshIcon />} onClick={() => void actions.getQueueStatus()} sx={{ ml: { sm: 'auto' } }}>Refresh queue</Button>
        {currentTab === 0 && state.queueStatus && <Button size="small" aria-expanded={queueDetailsOpen} onClick={() => setQueueDetailsOpen(value => !value)}>Queue details</Button>}
        {(state.manualRecovery?.active || state.manualRecovery?.resume_required) && <Button size="small" variant="contained" startIcon={<WarningAmber />} onClick={() => setCurrentTab(1)}
          sx={{ bgcolor: theme => theme.palette.tone.attention.bg, color: theme => theme.palette.tone.attention.fg, '&:hover': { bgcolor: theme => theme.palette.tone.attention.bg, filter: 'brightness(0.96)' } }}>Recovery required</Button>}
      </Stack>
      {state.queueError && <Alert severity="warning" sx={{ mb: 1 }}>Queue status not updated: {state.queueError}</Alert>}
      {state.schedulerError && <Alert severity="warning" sx={{ mb: 1 }}>Scheduler status not updated: {state.schedulerError}</Alert>}
      {currentTab === 0 && state.queueStatus && queueDetailsOpen && <Box sx={{ mb: `${layout.gutter}px`, bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: `${layout.radius}px` }}>
        <Stack spacing={1} sx={{ px: 2, py: 1.5 }}>
          {(state.queueStatus.running_job_details ?? []).map(item => <Typography key={`running-${item.schedule_id}`} variant="body2">Running · {item.experiment_name}</Typography>)}
          {(state.queueStatus.queued_job_details ?? []).map(item => <Typography key={`queued-${item.schedule_id}`} variant="body2">Queued · {item.experiment_name}{item.waiting_reason ? ` · ${item.waiting_reason}` : ''}</Typography>)}
          {!state.queueStatus.running_jobs && !state.queueStatus.queued_jobs && <Typography variant="body2">Queue empty</Typography>}
        </Stack>
      </Box>}
      <StatusDialog status={state.error ? { title: 'Server Error', message: state.error, severity: 'error' } : null} onClose={actions.clearError} />

      {/* Main Content */}
      <Box sx={{ minWidth: 0 }}>
        {/* Tab Panels */}
        <TabPanel value={currentTab} index={0}>
          <InspectionWorkspace label="Schedule workspace" selectorLabel="Schedules" layout="table" detailOpen={detailOpen}
            onBack={() => setDetailOpen(false)} selector={<ScheduleCollection schedules={state.schedules}
              selected={state.selectedSchedule} onSelect={schedule => { actions.selectSchedule(schedule); setDetailOpen(true); }}
              onRefresh={() => void actions.loadSchedules(false)} loading={state.loading} error={state.error} />}>
            {state.selectedSchedule ? <Box data-testid="schedule-detail" sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <Panel title="Schedule" fill inset={false} sx={{ flex: 1 }} bodySx={{ overflow: 'auto' }} actions={<StatusChip {...scheduleState(state.selectedSchedule)} />}>
              <Box sx={{ p: 2, borderBottom: 1, borderColor: 'surface.rowLine' }}>
                <DetailTitle>{state.selectedSchedule.experiment_name}</DetailTitle>
                <Typography sx={{ fontFamily: fontMono, fontSize: 12, lineHeight: '16px', color: 'text.secondary', overflowWrap: 'anywhere', mt: 0.5 }}>{state.selectedSchedule.experiment_path}</Typography>
              </Box>
              {state.selectedSchedule.recovery_required && <Alert severity="warning" sx={{ m: 2 }} action={<Button color="inherit" onClick={() => setCurrentTab(1)}>Review recovery</Button>}>Recovery required</Alert>}
              <Box component="dl" sx={{ m: 0 }}>
                {([
                  ['Status', state.selectedSchedule.is_active ? 'Active' : 'Inactive'],
                  ['Timing', repeatLabel(state.selectedSchedule)],
                  ['Next run', formatTimestamp(state.selectedSchedule.next_run)],
                  ['Duration', formatDuration(state.selectedSchedule.estimated_duration)],
                  ['Preparation', state.selectedSchedule.prerequisites.join(', ') || 'None'],
                  ['Late-start action', `${state.selectedSchedule.timeout_config?.action === 'run_cleanup_and_terminate' ? 'Run cleanup and terminate' : 'Continue'}${state.selectedSchedule.timeout_config?.timeout_minutes ? ` after ${state.selectedSchedule.timeout_config.timeout_minutes} minutes` : ''}`],
                ] as [string, string][]).map(([name, value]) => <ListRow key={name} columns="136px minmax(0, 1fr)" sx={{ height: 'auto', minHeight: layout.row, py: 1, '& > *': { whiteSpace: 'normal', overflowWrap: 'anywhere' } }}>
                  <Typography component="dt" variant="body2" color="text.secondary">{name}</Typography><Typography component="dd" variant="body2" sx={{ m: 0 }}>{value}</Typography>
                </ListRow>)}
              </Box>
              <Stack spacing={1.5} sx={{ p: 2 }}>
                <Button sx={{ alignSelf: 'flex-start' }} startIcon={<HistoryIcon />} onClick={() => setCurrentTab(3)}>Execution history</Button>
                {isLocalSession
                  ? <Stack direction="row" gap={1} flexWrap="wrap" aria-label="Schedule actions">
                    <Button variant="contained" startIcon={<EditIcon />} onClick={handleOpenEditForm} disabled={state.loading}>Edit schedule</Button>
                    <Button variant="outlined" startIcon={<ArchiveIcon />} disabled={state.loading || state.selectedSchedule.recovery_required}
                      onClick={() => state.selectedSchedule && void actions.archiveSchedule(state.selectedSchedule, !state.selectedSchedule.archived)}>
                      {state.selectedSchedule.archived ? 'Restore schedule' : 'Archive schedule'}</Button>
                    <Button variant="outlined" color="error" startIcon={<DeleteIcon />} onClick={() => setDeleteDialogOpen(true)} disabled={state.loading || state.selectedSchedule.recovery_required}>Delete schedule</Button>
                  </Stack>
                  : <Typography variant="body2" color="text.secondary">Read only · Changes require the local workstation.</Typography>}
              </Stack>
              {user?.role === 'admin' && <Box sx={{ p: 2, borderTop: 1, borderColor: 'surface.rowLine' }}>
                <PanelLabel component="p">Latest notification</PanelLabel>
                <Typography variant="body2" sx={{ mt: 0.5 }}>{latestNotificationForSelectedSchedule ? `${latestNotificationForSelectedSchedule.status} · ${formatTimestamp(latestNotificationForSelectedSchedule.triggered_at)}` : 'No notifications yet'}</Typography>
                {latestNotificationForSelectedSchedule?.error_message && <Alert severity="error" sx={{ mt: 1 }}>{latestNotificationForSelectedSchedule.error_message}</Alert>}
                <Button sx={{ mt: 1 }} onClick={openNotificationsTab}>Notification history</Button>
              </Box>}
              </Panel>
            </Box> : <EmptyPanel>Select a schedule.</EmptyPanel>}
          </InspectionWorkspace>
        </TabPanel>

        <TabPanel value={currentTab} index={1}>
          <RecoverySafetyPanel state={state.manualRecovery} isLocal={isLocalSession}
            onChanged={async () => { await actions.getQueueStatus(); await actions.loadSchedules(false); }} />
        </TabPanel>

        <TabPanel value={currentTab} index={2}>
          {renderCalendarView()}
        </TabPanel>

        <TabPanel value={currentTab} index={3}>
          <ExecutionHistory
            scheduleId={state.selectedSchedule?.schedule_id}
            maxHeight="min(65dvh, 900px)" active={currentTab === 3}
          />
        </TabPanel>

        <TabPanel value={currentTab} index={4}>
          <ScheduleList
            schedules={state.archivedSchedules}
            selectedSchedule={state.selectedSchedule}
            onScheduleSelect={actions.selectSchedule}
            onRefresh={actions.loadArchivedSchedules}
            onDeleteSchedule={
              isLocalSession
                ? (schedule) => {
                    actions.selectSchedule(schedule);
                    setDeleteDialogOpen(true);
                  }
                : undefined
            }
            loading={state.archivedLoading}
            error={state.archivedError}
            initialized={state.archivedInitialized}
            archivedView
          />
          {!isLocalSession && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mt: 1, display: 'block' }}
            >
              Archival cleanup can only be performed from the local robot control workstation.
            </Typography>
          )}
        </TabPanel>

        {user?.role === 'admin' && (
          <TabPanel value={currentTab} index={5}>
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
                          <MenuItem value="partial">Partial</MenuItem>
                          <MenuItem value="unknown">Unknown</MenuItem>
                          <MenuItem value="cancelled">Cancelled</MenuItem>
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

                    <StatusDialog
                      status={logsError ? { title: 'Notification Logs Error', message: logsError, severity: 'error', action: { label: 'Retry', onClick: handleLogsRefresh } } : null}
                      onClose={() => setLogsError(null)}
                    />

                    {logsLoading && state.notificationLogs.length === 0 ? (
                      <Box display="flex" justifyContent="center" py={4}>
                        <CircularProgress size={32} />
                      </Box>
                    ) : state.notificationLogs.length === 0 ? (
                      <Typography variant="body2" color="text.secondary">
                        No notification events recorded yet.
                      </Typography>
                    ) : (
                      <TableContainer tabIndex={0} aria-label="Notification deliveries"><Table size="small">
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
                                <StatusChip label={log.status || 'unknown'} tone={getLogStatusTone(log.status)} />
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
                      </Table></TableContainer>
                    )}
                  </CardContent>
                </Card>
              )}

              <SectionPanel active={notificationsTab === 2}>
              <NotificationEmailSettingsPanel
                  settings={state.notificationSettings}
                  loading={state.notificationSettingsLoading}
                  onRefresh={actions.loadNotificationSettings}
                  onSave={actions.updateNotificationSettings}
                  onSendTest={actions.sendNotificationTestEmail}
                  contacts={state.contacts}
                />
              </SectionPanel>
            </Stack>
          </TabPanel>
        )}
        {isLocalClient && <TabPanel value={currentTab} index={6}>
          <MethodLibraryPanel showImportAction={false} version={catalogueVersion} onChanged={() => setCatalogueVersion(value => value + 1)}
            onChangePath={setMethodToRelink}
            onImport={() => setFolderImportOpen(true)} onCreateSchedule={method => {
              handleOpenCreateForm();
              setScheduleFormInitialData({ experiment_name: method.method_name, experiment_path: method.file_path, notification_contacts: [] });
            }} />
        </TabPanel>}
      </Box>

      {/* Improved Schedule Form Dialog */}
      {methodToRelink && <MethodPathDialog method={methodToRelink} onClose={() => setMethodToRelink(null)} onChanged={() => {
        setCatalogueVersion(value => value + 1); void actions.loadSchedules();
      }} />}
      <ImprovedScheduleForm
        open={improvedFormOpen}
        onClose={handleScheduleFormClose}
        onSubmit={handleScheduleFormSubmit}
        initialData={scheduleFormInitialData}
        mode={scheduleFormMode}
        contacts={state.contacts}
        catalogueVersion={catalogueVersion}
        savedPreparation={editingPreparation.preparation}
        preparationState={editingPreparation.preparation_state}
      />

  {/* Folder Import Dialog */}
  <DeleteConfirmationDialog
    open={deleteDialogOpen}
    schedule={state.selectedSchedule}
    onClose={() => setDeleteDialogOpen(false)}
    onConfirm={async () => {
      if (!state.selectedSchedule) return;
      await actions.deleteSchedule(state.selectedSchedule);
    }}
    loading={state.operationStatus === SchedulingOperationStatus.Deleting}
  />

  <FolderImportDialog
    open={folderImportOpen}
    onClose={() => setFolderImportOpen(false)}
    onImportComplete={() => setCatalogueVersion(version => version + 1)}
    onCreateSchedule={handleOpenCreateForm}
        isLocalClient={isLocalClient}
      />
    </PageContent>
  );
};

export default SchedulingPage;
