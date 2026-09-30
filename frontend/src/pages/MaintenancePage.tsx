import { PageContent, PageHeader, PanelHeader } from '../components/PageLayout';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
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
import StatusChip from '../components/StatusChip';
import BlockIcon from '@mui/icons-material/Block';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';

import { useAuth } from '../context/AuthContext';
import { hxrunMaintenanceApi, HxRunMaintenanceState } from '../services/hxrunMaintenanceApi';
import { robotAttention, useRobotStatusContext } from '../hooks/useRobotStatus';
import { runTiming } from '../components/overview/NowRunning';
import { panelPadding, type StatusTone } from '../theme';
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

  return (
    <PageContent variant="task">
      <PageHeader title="Maintenance" actions={<Button onClick={loadState} disabled={saving || loading} startIcon={<RefreshIcon />}>Refresh</Button>} />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {state && !canEdit && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Changes require a local session.
        </Alert>
      )}

      <Box sx={{ display: 'grid', gap: 2, alignItems: 'start', gridTemplateColumns: 'minmax(0, 1fr)', '@container workspace (min-width: 900px)': { gridTemplateColumns: 'minmax(0, 2fr) minmax(280px, 1fr)' } }}>
      <Card variant="outlined">
        <CardContent>
          {loading && !state ? (
            <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}>
              <CircularProgress size={28} />
            </Box>
          ) : (
            <Stack spacing={2}>
              <PanelHeader title="HxRun launches" actions={<StatusChip tone={!state || error ? 'neutral' : state.enabled ? 'attention' : 'completed'}
                label={!state || error ? 'State unavailable' : state.enabled ? 'Blocked for maintenance' : 'Allowed'} />} />

              <Typography sx={{ fontSize: 15, lineHeight: 1.6, color: 'text.secondary' }}>
                Maintenance mode stops HxRun from being launched on this PC, so you can work on the instrument safely.
              </Typography>

              {robot?.hamiltonRunning && !state?.enabled && <Alert severity="info">
                <strong>HxRun is running{job ? ` ${job.experiment_name}` : ''}.</strong> You can enter maintenance once HxRun has closed.{remaining ? ` ${remaining}` : ''}
              </Alert>}

              <Typography variant="body2" color="text.secondary">
                {state ? `Last change: ${state.updated_by || 'Unknown'} · ${formatTimestamp(state.updated_at)}` : 'Refresh to check the current state.'}
              </Typography>

              <TextField
                label="Reason"
                value={reasonInput}
                onChange={(event) => { reasonEdited.current = true; setReasonInput(event.target.value); }}
                multiline
                minRows={2}
                disabled={!canEdit || saving || !state || loading || !!error}
                placeholder="Optional maintenance note"
                fullWidth
              />

              <Button
                variant="contained"
                color={state?.enabled ? 'primary' : 'warning'}
                onClick={() => updateState(!state?.enabled)}
                disabled={!canEdit || saving || loading || !state || !!error}
                startIcon={state?.enabled ? <CheckCircleOutlineIcon /> : <BlockIcon />}
                sx={{ alignSelf: { xs: 'stretch', sm: 'flex-start' } }}
              >
                {saving ? 'Saving…' : state?.enabled ? 'Allow HxRun launches' : 'Enter maintenance'}
              </Button>
            </Stack>
          )}
        </CardContent>
      </Card>
      {robot && <Card component="aside" aria-label="Right now" variant="outlined" sx={{ p: panelPadding }}>
        <PanelHeader title="Right now" />
        <Box sx={{ mt: 2 }}>{rightNow.map(([name, detail, label, tone]) => <Stack key={name} direction="row" alignItems="center" justifyContent="space-between" gap={1.5}
          sx={{ py: 1.25, borderTop: 1, borderColor: 'divider', '&:first-of-type': { borderTop: 0 } }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ fontSize: 14, fontWeight: 500 }}>{name}</Typography>
            <Typography sx={{ fontSize: 13, color: 'text.secondary', overflowWrap: 'anywhere' }}>{detail}</Typography>
          </Box>
          <Box sx={{ flexShrink: 0 }}><StatusChip tone={tone} label={label} /></Box>
        </Stack>)}</Box>
      </Card>}
      </Box>

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
