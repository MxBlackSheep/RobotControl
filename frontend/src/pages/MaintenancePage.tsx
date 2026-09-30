import { ListRow, PageContent, PageGrid, PageHeader, Panel, StatusDot } from '../components/PageLayout';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import BlockIcon from '@mui/icons-material/Block';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';

import { useAuth } from '../context/AuthContext';
import { hxrunMaintenanceApi, HxRunMaintenanceState } from '../services/hxrunMaintenanceApi';
import { robotAttention, useRobotStatusContext } from '../hooks/useRobotStatus';
import { runTiming } from '../components/overview/NowRunning';
import { layout, type StatusTone } from '../theme';
import { dayTime } from '../utils/displayTime';

const formatTimestamp = (value?: string | null): string => {
  if (!value) {
    return 'N/A';
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dayTime(value);
};

const MaintenancePage: React.FC = () => {
  const { user } = useAuth();
  const [state, setState] = useState<HxRunMaintenanceState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reasonInput, setReasonInput] = useState('');
  const reasonEdited = useRef(false);
  const [hxRunRunningDialogOpen, setHxRunRunningDialogOpen] = useState(false);
  const [hxRunRunningDialogMessage, setHxRunRunningDialogMessage] = useState(
    'HxRun is running. Please close the software before entering maintenance mode.',
  );

  const isLocalSession = useMemo(() => {
    if (typeof user?.session_is_local === 'boolean') {
      return user.session_is_local;
    }
    if (typeof window === 'undefined') {
      return false;
    }
    const hostname = window.location.hostname.toLowerCase();
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1' || hostname === '0.0.0.0';
  }, [user?.session_is_local]);

  const canEdit = Boolean(state?.permissions?.can_edit ?? isLocalSession);
  // Shared robot state (no extra request): what would block or be affected by maintenance.
  const { status: robot, error: robotError } = useRobotStatusContext();
  const job = robot?.running[0];
  const timing = job ? runTiming(job.monitoring?.launched_at, job.estimated_duration, Date.now()) : null;
  const remaining = timing?.fraction != null && timing.estimate !== null && timing.elapsed !== null ? `About ${Math.max(1, timing.estimate - timing.elapsed)} min left by its estimate.`
    : timing?.overBy != null ? `It is ${timing.overBy} min past its estimate.` : '';
  const attention = robotAttention(robot);
  const scheduledHold = [state?.enabled ? 'Maintenance mode' : null, attention?.label].filter(Boolean).join(' · ');
  const scheduledUnknown = !state || loading || !!error || !!robotError || !robot?.recovery;
  const rightNow: [string, string, string, StatusTone][] = !robot ? [] : [
    ['HxRun', 'Hamilton run software on this PC', robot.hamiltonRunning === true ? 'Running' : robot.hamiltonRunning === false ? 'Not running' : 'Unknown', robot.hamiltonRunning ? 'running' : 'neutral'],
    ['Scheduler', robot.queued ? `${robot.queued} waiting` : 'Nothing waiting', robot.schedulerRunning ? 'Running' : 'Stopped', robot.schedulerRunning ? 'running' : 'neutral'],
    ['Current run', job?.experiment_name ?? 'None', job ? 'Running' : 'Idle', job ? 'running' : 'neutral'],
    ['Scheduled runs', scheduledHold || (scheduledUnknown ? 'Refresh to check the current state' : robot.schedulerRunning ? 'Not held' : 'Scheduler is stopped'),
      scheduledHold ? 'Held' : scheduledUnknown ? 'Unknown' : robot.schedulerRunning ? 'Allowed' : 'Stopped',
      scheduledHold ? 'attention' : scheduledUnknown || !robot.schedulerRunning ? 'neutral' : 'completed'],
  ];

  const loadState = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await hxrunMaintenanceApi.getState();
      if (typeof payload?.enabled !== 'boolean' || typeof payload?.permissions?.can_edit !== 'boolean') throw new Error('Maintenance state unavailable. Refresh to retry.');
      setState(payload);
      if (!reasonEdited.current) setReasonInput(payload.reason || '');
    } catch (err: any) {
      const message = err?.response?.data?.message || err?.response?.data?.detail || err?.message || 'Failed to load maintenance state';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const updateState = useCallback(
    async (enabled: boolean) => {
      if (!canEdit || !state || loading || error || saving) {
        return;
      }
      setSaving(true);
      setError(null);
      try {
        const next = await hxrunMaintenanceApi.updateState(
          enabled,
          reasonInput.trim() ? reasonInput.trim() : undefined,
        );
        if (typeof next?.enabled !== 'boolean' || typeof next?.permissions?.can_edit !== 'boolean') throw new Error('Maintenance state unavailable. Refresh to verify the change.');
        setState(next);
        reasonEdited.current = false;
        setReasonInput(next.reason || "");
      } catch (err: any) {
        const message = err?.response?.data?.message || err?.response?.data?.detail || err?.message || 'Failed to update maintenance state';
        const statusCode = err?.response?.status;
        if (enabled && statusCode === 409) {
          setHxRunRunningDialogMessage(message);
          setHxRunRunningDialogOpen(true);
          return;
        }
        setError(message);
      } finally {
        setSaving(false);
      }
    },
    [canEdit, reasonInput, state, loading, error, saving],
  );

  useEffect(() => {
    loadState();
  }, [loadState]);

  const stateTone: StatusTone = !state || error ? 'neutral' : state.enabled ? 'attention' : 'completed';
  const stateLabel = !state || error ? 'State unavailable' : state.enabled ? 'Blocked for maintenance' : 'Allowed';
  const runningNote = robot?.hamiltonRunning && !state?.enabled;

  return (
    <PageContent variant="task">
      <PageHeader title="Maintenance" actions={<Button variant="outlined" onClick={loadState} disabled={saving || loading} startIcon={<RefreshIcon />}>Refresh</Button>} />

      {error && <Alert severity="error" sx={{ mb: `${layout.gutter}px` }}>{error}</Alert>}
      {state && !canEdit && <Alert severity="info" sx={{ mb: `${layout.gutter}px` }}>Changes require a local session.</Alert>}

      <PageGrid>
        <Panel title="HxRun launches" inset={false} span={12}
          actions={state && <Typography variant="caption" color="text.secondary">Last change: {state.updated_by || 'Unknown'} · {formatTimestamp(state.updated_at)}</Typography>}>
          {loading && !state
            ? <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}><CircularProgress size={28} /></Box>
            : <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'minmax(0, 1fr) auto' }, gap: 3, alignItems: 'center', p: `${layout.inset}px` }}>
              <Stack spacing={1} sx={{ minWidth: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <Box aria-hidden sx={{ width: 12, height: 12, borderRadius: 6, flexShrink: 0, bgcolor: theme => theme.palette.tone[stateTone].dot }} />
                  <Typography component="p" sx={{ fontSize: 28, lineHeight: '36px', fontWeight: 600 }}>{stateLabel}</Typography>
                </Box>
                <Typography variant="body2" color="text.secondary">Maintenance mode stops HxRun from being launched on this PC, so you can work on the instrument safely.</Typography>
                {!state && <Typography variant="body2" color="text.secondary">Refresh to check the current state.</Typography>}
              </Stack>
              <Button
                variant="contained"
                onClick={() => updateState(!state?.enabled)}
                disabled={!canEdit || saving || loading || !state || !!error}
                startIcon={state?.enabled ? <CheckCircleOutlineIcon /> : <BlockIcon />}
                sx={{ minHeight: layout.touchRow, px: 3, justifySelf: { xs: 'stretch', sm: 'end' }, ...(!state?.enabled && {
                  bgcolor: 'attentionSurface.action', color: 'attentionSurface.actionText', '&:hover': { bgcolor: 'attentionSurface.action', filter: 'brightness(0.94)' } }) }}
              >
                {saving ? 'Saving…' : state?.enabled ? 'Allow HxRun launches' : 'Enter maintenance'}
              </Button>
            </Box>}
          {runningNote && <Box role="status" sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minHeight: layout.row, px: `${layout.inset}px`, fontSize: 13,
            borderTop: 1, borderColor: 'surface.headLine', bgcolor: theme => theme.palette.tone.running.bg, color: theme => theme.palette.tone.running.fg }}>
            <InfoOutlined fontSize="small" />
            <span><strong>HxRun is running{job ? ` ${job.experiment_name}` : ''}.</strong> You can enter maintenance once HxRun has closed.{remaining ? ` ${remaining}` : ''}</span>
          </Box>}
        </Panel>

        <Panel title="Reason" label="Maintenance details" span={robot ? 8 : 12} fill actions={<Typography variant="caption" color="text.secondary">Optional · recorded with the change</Typography>}
          bodySx={{ display: 'flex', flexDirection: 'column' }}>
          <TextField
            value={reasonInput}
            onChange={(event) => { reasonEdited.current = true; setReasonInput(event.target.value); }}
            multiline
            minRows={4}
            disabled={!canEdit || saving || !state || loading || !!error}
            placeholder="Optional maintenance note"
            inputProps={{ 'aria-label': 'Reason' }}
            fullWidth
          />
        </Panel>

        {robot && <Panel title="Right now" component="aside" span={4} inset={false}>
          {rightNow.map(([name, detail, label, tone]) => <ListRow key={name} role="group" aria-label={name} columns="112px minmax(0, 1fr) auto">
            <Box component="span" sx={{ fontWeight: 500 }}>{name}</Box>
            <Box component="span" sx={{ color: 'text.secondary' }} title={detail}>{detail}</Box>
            <StatusDot tone={tone} label={label} />
          </ListRow>)}
        </Panel>}
      </PageGrid>

      <Dialog
        open={hxRunRunningDialogOpen}
        onClose={() => setHxRunRunningDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>HxRun is running</DialogTitle>
        <DialogContent>
          <DialogContentText>{hxRunRunningDialogMessage}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHxRunRunningDialogOpen(false)} autoFocus>
            OK
          </Button>
        </DialogActions>
      </Dialog>
    </PageContent>
  );
};

export default MaintenancePage;
