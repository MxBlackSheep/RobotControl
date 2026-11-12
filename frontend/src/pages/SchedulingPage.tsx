import { DetailTitle, EmptyPanel, ListRow, PageContent, PageHeader, Panel, PanelLabel } from '../components/PageLayout';
import { useSchedulingSection, isLocalUser } from '../components/navigation';
import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { Box, Typography, Button, Alert, Stack, Grid, Card, Tab, Tabs } from '@mui/material';
import { Refresh as RefreshIcon } from '@mui/icons-material';
import { useAuth } from '../context/AuthContext';
import { useRobotStatusContext } from '../hooks/useRobotStatus';
import ScheduleCollection, { repeatLabel, scheduleState, scheduleTarget } from '../components/scheduling/ScheduleCollection';
import StatusChip from '../components/StatusChip';
import { preparationSummary, stateChip } from '../components/scheduling/PreparationStepField';
import { fontMono, layout } from '../theme';
import { dayTime } from '../utils/displayTime';
import WarningAmber from '@mui/icons-material/WarningAmber';
import InspectionWorkspace, { pinnedBarSx, usePhoneWorkspace } from '../components/InspectionWorkspace';
import PhoneRuns from '../components/scheduling/PhoneRuns';
import SectionPanel from '../components/SectionPanel';
import RecoverySafetyPanel from '../components/scheduling/RecoverySafetyPanel';
import ImprovedScheduleForm from '../components/scheduling/ImprovedScheduleForm';
import NotificationContactsPanel from '../components/scheduling/NotificationContactsPanel';
import NotificationEmailSettingsPanel from '../components/scheduling/NotificationEmailSettingsPanel';
import NotificationLogPanel from '../components/scheduling/NotificationLogPanel';
import FolderImportDialog from '../components/scheduling/FolderImportDialog';
import MethodLibraryPanel from '../components/scheduling/MethodLibraryPanel';
import MethodPathDialog from '../components/scheduling/MethodPathDialog';
import ExecutionHistory from '../components/ExecutionHistory';
import useScheduling from '../hooks/useScheduling';
import { formatDuration, LibraryMethod, SCHEDULE_MODE_LABELS, ScheduledExperiment } from '../types/scheduling';
import StatusDialog from '../components/StatusDialog';
import { DeleteConfirmationDialog } from '../components/ScheduleActions';

/** The open schedule form: the stored schedule to edit, or a new one (from a library method). */
type OpenForm = { schedule?: ScheduledExperiment; method?: LibraryMethod };

// Not Active: a stored next_run is not a run that will happen.
const notRunning: Record<string, string> = { 'Needs review': 'No run until reviewed', 'Recovery required': 'No run until recovery is resolved',
  Archived: 'No run while archived', Inactive: 'No run while inactive' };

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

/** Schedules, archive, calendar, history, recovery, notifications and the method library. The route admits only admin and user. */
const SchedulingPage: React.FC = () => {
  const { user } = useAuth();
  const [currentTab, setCurrentTab] = useSchedulingSection(user);
  const [form, setForm] = useState<OpenForm | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [queueDetailsOpen, setQueueDetailsOpen] = useState(false);
  const [catalogueVersion, setCatalogueVersion] = useState(0);
  const [methodToRelink, setMethodToRelink] = useState<LibraryMethod | null>(null);
  const [folderImportOpen, setFolderImportOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [notificationsTab, setNotificationsTab] = useState(0);
  const [contactsRequested, setContactsRequested] = useState(false);
  const [emailSettingsRequested, setEmailSettingsRequested] = useState(false);

  const { state, actions } = useScheduling();
  // The frame owns the one status read; the page shows it and asks it to refresh.
  const robot = useRobotStatusContext();
  const status = robot.status;
  const isLocal = isLocalUser(user);
  const phone = usePhoneWorkspace();
  const workspaceTop = useRef<HTMLDivElement>(null);
  const detailHeading = useRef<HTMLDivElement>(null);
  const openScheduleId = detailOpen ? state.selectedSchedule?.schedule_id : undefined;

  // Phones: an opened schedule starts at the top of the screen, not where the list was scrolled.
  // Runs after InspectionWorkspace focuses its detail, so the heading takes focus. Only opening a
  // schedule triggers it; rotating or resizing with one open must not scroll or move focus.
  const phoneNow = useRef(phone);
  phoneNow.current = phone;
  useLayoutEffect(() => {
    if (!phoneNow.current || !openScheduleId) return;
    workspaceTop.current?.scrollIntoView({ block: 'start' });
    const heading = detailHeading.current?.querySelector<HTMLElement>('h2');
    if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
  }, [openScheduleId]);

  const openNotificationsTab = () => setCurrentTab(5);

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

  const handleNotificationsTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setNotificationsTab(newValue);
  };

  const calendarData = (() => {
    const grouped: Record<string, ScheduledExperiment[]> = {};
    // A record under review never runs, whatever time it holds.
    state.schedules.filter(schedule => schedule.next_run && !schedule.review_reason).forEach(schedule => {
      const day = new Date(schedule.next_run!).toDateString();
      (grouped[day] ||= []).push(schedule);
    });
    return Object.entries(grouped).sort((a, b) => new Date(a[0]).getTime() - new Date(b[0]).getTime());
  })();
  const renderCalendarView = () => {
    if (calendarData.length === 0) {
      return (
        <Typography variant="body2" color="text.secondary">
          No upcoming runs.
        </Typography>
      );
    }

    return (
      <Box>
        <Stack direction="row" justifyContent="flex-end" sx={{ mb: { xs: 2.5, md: 3 } }}>
          <Button onClick={() => void actions.loadSchedules()} size="small">
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
                      {/* Inactive schedules still have a next_run, so they must not read as runs that will happen. */}
                      {scheduleState(schedule).label !== 'Active' && <StatusChip {...scheduleState(schedule)} />}
                      {schedule.preparation_state && schedule.preparation_state !== 'ready' && <StatusChip {...stateChip[schedule.preparation_state]} />}
                      {schedule.mode !== 'real' && <StatusChip tone="neutral" label={SCHEDULE_MODE_LABELS[schedule.mode]} />}
                    </Stack>
                  </Box>
                ))}
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  };

  const renderScheduleDetail = (schedule: ScheduledExperiment) => {
    const scheduleStatus = scheduleState(schedule);
    const statusChip = <StatusChip {...scheduleStatus} />;
    const facts = ([
      ['Timing', repeatLabel(schedule)],
      ...(phone ? [] : [['Next run', schedule.next_run && !schedule.review_reason ? dayTime(schedule.next_run) : notRunning[scheduleStatus.label] ?? 'Not scheduled']]),
      ['Last run', schedule.last_run ? dayTime(schedule.last_run) : 'Never'],
      ['Duration', formatDuration(schedule.estimated_duration)],
      ...(schedule.runner === 'pyhsl' ? [['Protocol', schedule.protocol_id ?? '']] : []),
      ['Mode', SCHEDULE_MODE_LABELS[schedule.mode]],
      ['Before this run', preparationSummary(schedule)],
      ['Late-start action', `${schedule.timeout_config?.action === 'run_cleanup_and_terminate' ? 'Run cleanup and terminate' : 'Continue'}${schedule.timeout_config?.timeout_minutes ? ` after ${schedule.timeout_config.timeout_minutes} minutes` : ''}`],
      ['Created by', schedule.created_by],
      ['Created', dayTime(schedule.created_at)],
    ] as [string, string][]);
    // Phones show the visible words; the accessible names stay the full action names.
    const actionLabel = (full: string) => phone ? { 'aria-label': full, children: full.split(' ')[0] } : { children: full };
    const archiveLabel = schedule.archived ? 'Restore schedule' : 'Archive schedule';
    // Archived: restore before editing. Under review: edit or delete only (the server refuses the rest).
    const scheduleActions = isLocal
      ? <Stack direction="row" gap={1} flexWrap={phone ? 'nowrap' : 'wrap'} aria-label="Schedule actions" sx={phone ? { '& > *': { flex: '1 1 0', minHeight: 44 } } : undefined}>
        {!schedule.archived && <Button variant="contained" onClick={() => setForm({ schedule })} disabled={state.loading} {...actionLabel('Edit schedule')} />}
        {!schedule.review_reason && <Button variant={schedule.archived ? 'contained' : 'outlined'} disabled={state.loading || schedule.recovery_required}
          onClick={() => void actions.archiveSchedule(schedule, !schedule.archived)} {...actionLabel(archiveLabel)} />}
        <Button variant="outlined" color="error" onClick={() => setDeleteDialogOpen(true)} disabled={state.loading || schedule.recovery_required} {...actionLabel('Delete schedule')} />
      </Stack>
      : <Typography variant="body2" color="text.secondary">Read only · Changes require the local workstation.</Typography>;
    const nextRun = schedule.next_run ? new Date(schedule.next_run) : null;
    const validNextRun = nextRun && !Number.isNaN(nextRun.getTime()) ? nextRun : null;
    const waitingReason = status?.queuedJobs.find(item => item.schedule_id === schedule.schedule_id)?.waiting_reason;
    return <Box data-testid="schedule-detail" sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <Panel title="Schedule" fill inset={false} sx={{ flex: 1 }} bodySx={{ overflow: phone ? 'visible' : 'auto' }} actions={phone ? undefined : statusChip}>
        <Box ref={detailHeading} sx={{ p: 2, borderBottom: 1, borderColor: 'surface.rowLine' }}>
          <Stack direction="row" gap={1} alignItems="flex-start" justifyContent="space-between">
            <DetailTitle>{schedule.experiment_name}</DetailTitle>
            {phone && <Box sx={{ flexShrink: 0, pt: 0.25 }}>{statusChip}</Box>}
          </Stack>
          <Typography sx={{ fontFamily: fontMono, fontSize: 12, lineHeight: '16px', color: 'text.secondary', overflowWrap: 'anywhere', mt: 0.5 }}>{scheduleTarget(schedule)}</Typography>
        </Box>
        {phone && <Box component="section" aria-label="Next run" sx={{ p: 2, borderBottom: 1, borderColor: 'surface.rowLine' }}>
          <PanelLabel component="p">Next run</PanelLabel>
          {scheduleStatus.label !== 'Active'
            ? <>
              <Typography sx={{ fontSize: 20, fontWeight: 600, lineHeight: '28px', mt: 0.5 }}>{notRunning[scheduleStatus.label] ?? scheduleStatus.label}</Typography>
              {schedule.next_run && !schedule.review_reason && <Typography variant="body2" color="text.secondary">Stored time: {dayTime(schedule.next_run)}</Typography>}
            </>
            : validNextRun
              ? <>
                <Typography sx={{ fontFamily: fontMono, fontSize: 36, fontWeight: 500, lineHeight: '44px', mt: 0.5 }}>
                  {validNextRun.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </Typography>
                <Typography variant="body2">{validNextRun.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</Typography>
                {/* A time already past is a missed or late run, never an upcoming one. */}
                {validNextRun.getTime() < Date.now() && <Typography variant="body2" sx={{ color: 'warning.dark', fontWeight: 600 }}>Overdue</Typography>}
              </>
              : <Typography sx={{ fontSize: 20, fontWeight: 600, lineHeight: '28px', mt: 0.5 }}>{schedule.next_run ? dayTime(schedule.next_run) : 'Not scheduled'}</Typography>}
          <Typography variant="body2" color="text.secondary">Expected duration {formatDuration(schedule.estimated_duration)}</Typography>
        </Box>}
        {schedule.review_reason && <Alert severity="warning" sx={{ m: 2 }}>Needs review: {schedule.review_reason}</Alert>}
        {schedule.recovery_required && <Alert severity="warning" sx={{ m: 2 }} action={<Button color="inherit" onClick={() => setCurrentTab(1)}>Review recovery</Button>}>Recovery required</Alert>}
        {waitingReason && <Alert severity="warning" sx={{ m: 2 }}>Waiting: {waitingReason}</Alert>}
        <Box component="dl" sx={{ m: 0 }}>
          {facts.map(([name, value]) => <ListRow key={name} columns="136px minmax(0, 1fr)" sx={{ height: 'auto', minHeight: layout.row, py: 1, '& > *': { whiteSpace: 'normal', overflowWrap: 'anywhere' } }}>
            <Typography component="dt" variant="body2" color="text.secondary">{name}</Typography><Typography component="dd" variant="body2" sx={{ m: 0 }}>{value}</Typography>
          </ListRow>)}
        </Box>
        {!phone && <Stack spacing={1.5} sx={{ p: 2 }}>{scheduleActions}</Stack>}
        {user?.role === 'admin' && <Box sx={{ px: 2, pb: 2, pt: phone ? 2 : 0 }}>
          <Button onClick={openNotificationsTab}>Notification history</Button>
        </Box>}
        {phone && <Box sx={[{ px: 2, py: 1 }, pinnedBarSx]}>{scheduleActions}</Box>}
      </Panel>
    </Box>;
  };

  // Schedules and Archived share the list and the detail; each shows the selection only when it lists it.
  const scheduleWorkspace = (title: string, schedules: ScheduledExperiment[], onRefresh: () => void, loading: boolean, error: string | null, statusFilter: boolean) => {
    const selected = schedules.find(schedule => schedule.schedule_id === state.selectedSchedule?.schedule_id) ?? null;
    return <InspectionWorkspace label={`${title} workspace`} selectorLabel={title} layout="table" detailOpen={detailOpen && Boolean(selected)}
      onBack={() => setDetailOpen(false)} selector={<ScheduleCollection title={title} statusFilter={statusFilter} schedules={schedules}
        selected={selected} onSelect={schedule => { actions.selectSchedule(schedule); setDetailOpen(true); }}
        onRefresh={onRefresh} loading={loading} error={error} />}>
      {selected ? renderScheduleDetail(selected) : <EmptyPanel>Select a schedule.</EmptyPanel>}
    </InspectionWorkspace>;
  };

  const recovery = status?.recovery;
  return (
    <PageContent variant={currentTab === 5 && notificationsTab === 2 ? "task" : "inspection"}>
      <PageHeader title="Scheduling" actions={isLocal && <>
        <Button variant="contained" onClick={() => setForm({})} disabled={state.loading}>Create schedule</Button>
        <Button variant="outlined" onClick={() => setFolderImportOpen(true)} disabled={state.loading}>Import methods</Button>
      </>} />
      <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center" sx={{ mb: `${layout.gutter}px`, px: 2, py: 0.5, minHeight: layout.row, boxSizing: 'border-box', bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: `${layout.radius}px` }} aria-label="Scheduler service summary">
        <StatusChip tone={status?.schedulerRunning ? 'running' : 'neutral'} label={`Scheduler service: ${!status ? 'Unknown' : status.schedulerRunning ? 'Running' : 'Stopped'}`} />
        <StatusChip tone="neutral" label={status ? `${status.running.length} running · ${status.queued} queued` : 'Queue unavailable'} />
        <Button size="small" startIcon={<RefreshIcon />} onClick={() => void robot.refresh()} sx={{ ml: { sm: 'auto' } }}>Refresh queue</Button>
        {currentTab === 0 && status && <Button size="small" aria-expanded={queueDetailsOpen} onClick={() => setQueueDetailsOpen(value => !value)}>Queue details</Button>}
        {(recovery?.active || recovery?.resume_required) && <Button size="small" variant="contained" startIcon={<WarningAmber />} onClick={() => setCurrentTab(1)}
          sx={{ bgcolor: theme => theme.palette.tone.attention.bg, color: theme => theme.palette.tone.attention.fg, '&:hover': { bgcolor: theme => theme.palette.tone.attention.bg, filter: 'brightness(0.96)' } }}>Recovery required</Button>}
      </Stack>
      {robot.error && <Alert severity="warning" sx={{ mb: 1 }}>Status not updated: {robot.error}</Alert>}
      {currentTab === 0 && status && queueDetailsOpen && <Box sx={{ mb: `${layout.gutter}px`, bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: `${layout.radius}px` }}>
        <Stack spacing={1} sx={{ px: 2, py: 1.5 }}>
          {status.running.map(item => <Typography key={`running-${item.schedule_id}`} variant="body2">Running · {item.experiment_name}</Typography>)}
          {status.queuedJobs.map(item => <Typography key={`queued-${item.schedule_id}`} variant="body2">Queued · {item.experiment_name}{item.waiting_reason ? ` · ${item.waiting_reason}` : ''}</Typography>)}
          {!status.running.length && !status.queued && <Typography variant="body2">Queue empty</Typography>}
        </Stack>
      </Box>}
      <StatusDialog status={state.error ? { title: 'Server Error', message: state.error, severity: 'error' } : null} onClose={actions.clearError} />

      {/* Main Content */}
      <Box ref={workspaceTop} sx={{ minWidth: 0 }}>
        <TabPanel value={currentTab} index={0}>
          {scheduleWorkspace('Schedules', state.schedules, () => void actions.loadSchedules(), state.loading, state.error, true)}
        </TabPanel>

        <TabPanel value={currentTab} index={1}>
          <RecoverySafetyPanel state={recovery ?? null} isLocal={isLocal}
            onChanged={async () => { await robot.refresh(); await actions.loadSchedules(); }} />
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
          {scheduleWorkspace('Archived', state.archivedSchedules, () => void actions.loadArchivedSchedules(), state.archivedLoading, state.archivedError, false)}
          {!isLocal && (
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

              <SectionPanel active={notificationsTab === 1}>
                <NotificationLogPanel active={currentTab === 5 && notificationsTab === 1} />
              </SectionPanel>

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
        <TabPanel value={currentTab} index={6}>
          <MethodLibraryPanel showImportAction={false} version={catalogueVersion} onChanged={() => setCatalogueVersion(value => value + 1)}
            onChangePath={setMethodToRelink}
            onImport={() => setFolderImportOpen(true)} onCreateSchedule={method => setForm({ method })} />
        </TabPanel>
      </Box>

      {methodToRelink && <MethodPathDialog method={methodToRelink} onClose={() => setMethodToRelink(null)} onChanged={() => {
        setCatalogueVersion(value => value + 1); void actions.loadSchedules();
      }} />}
      {/* Mounted per opening: the draft is a snapshot of the schedule as it was opened. */}
      {form && <ImprovedScheduleForm schedule={form.schedule} method={form.method} contacts={state.contacts} catalogueVersion={catalogueVersion}
        onClose={() => setForm(null)}
        onSubmit={values => form.schedule
          ? actions.updateSchedule(form.schedule.schedule_id, values, form.schedule.updated_at)
          : actions.createSchedule(values)} />}

      <DeleteConfirmationDialog
        open={deleteDialogOpen}
        schedule={state.selectedSchedule}
        onClose={() => setDeleteDialogOpen(false)}
        onConfirm={async () => {
          if (state.selectedSchedule) await actions.deleteSchedule(state.selectedSchedule);
        }}
        loading={state.deleting}
      />

      <FolderImportDialog
        open={folderImportOpen}
        onClose={() => setFolderImportOpen(false)}
        onImportComplete={() => setCatalogueVersion(version => version + 1)}
        onCreateSchedule={() => setForm({})}
        isLocalClient={isLocal}
      />
    </PageContent>
  );
};

/**
 * A remote session on a phone gets the Runs monitor for Schedules and History (the server refuses
 * schedule changes through the tunnel); other sections, reached by link, keep the full page. The
 * workstation's own browser is local, so narrowing its window never unmounts an open draft.
 */
function SchedulingRoute() {
  const { user } = useAuth();
  const phone = usePhoneWorkspace();
  const [section] = useSchedulingSection(user);
  return phone && !isLocalUser(user) && (section === 0 || section === 3) ? <PhoneRuns /> : <SchedulingPage />;
}

export default SchedulingRoute;
