import { useState } from 'react';
import { Alert, Button, Card, CardContent, Checkbox, FormControlLabel, Stack, TextField, Typography } from '@mui/material';
import { ManualRecoveryState } from '../../types/scheduling';
import { api } from '../../services/api';
import StatusChip from '../StatusChip';
import { fontMono } from '../../theme';

interface Props {
  state: ManualRecoveryState | null;
  isLocal: boolean;
  onChanged: () => Promise<void>;
}

export default function RecoverySafetyPanel({ state, isLocal, onChanged }: Props) {
  const [note, setNote] = useState('');
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const healthy = state?.storage_healthy === true;
  const pending = state?.pending_recoveries ?? [];

  const submit = async (scheduleId?: string | null) => {
    if (!isLocal || !healthy || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (scheduleId === undefined) {
        if (!window.confirm('Resume queued jobs? Due jobs may start immediately.')) return;
        await api.post('/api/scheduling/dispatch/resume', { expected_revision: state?.safety_revision });
      } else {
        await api.post('/api/scheduling/recovery/resolve', {
          schedule_id: scheduleId, expected_revision: state?.safety_revision, robot_ready: ready, note: note.trim() || null,
        });
        setReady(false);
        setNote('');
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Recovery action failed');
    } finally {
      try { await onChanged(); } finally { setBusy(false); }
    }
  };

  return <Stack spacing={2} sx={{ maxWidth: 880 }}>
    <Alert severity={!healthy ? 'error' : state?.active || state?.resume_required ? 'warning' : 'info'}>
      {!healthy ? state?.storage_error || 'Scheduler safety state unavailable. Refresh status or review SQLite storage health.'
        : state?.active ? 'Automatic scheduling is paused. Acknowledge each recovery issue, then use Resume queued jobs.'
        : state?.resume_required ? 'Recovery is acknowledged. Queued jobs remain paused until you choose Resume queued jobs.'
        : 'No manual recovery is currently required.'}
    </Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {isLocal && state?.active && <>
      <TextField label="Recovery note" multiline value={note} onChange={event => setNote(event.target.value)} disabled={busy}
        helperText="Required when the original schedule is missing. Acknowledgement does not resume jobs." />
      <FormControlLabel control={<Checkbox checked={ready} onChange={event => setReady(event.target.checked)} disabled={busy} />}
        label="I have checked the robot, completed manual recovery, and closed HxRun." />
    </>}
    {pending.map((item, index) => <Card key={item.schedule_id ?? `missing-${index}`}><CardContent>
      <Stack spacing={1}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1}>
          <Typography component="h3" sx={{ fontSize: 18, fontWeight: 600 }}>{item.experiment_name || 'Unknown schedule'}</Typography>
          <StatusChip tone="attention" label="Recovery required" />
        </Stack>
        <Typography sx={{ fontFamily: fontMono, fontSize: 13, color: 'text.secondary' }}>Schedule ID: {item.schedule_id || 'Unavailable'}</Typography>
        <Typography>{item.note || 'Manual recovery required'}</Typography>
        <Typography variant="body2" color="text.secondary">Triggered by {item.triggered_by || 'unknown'} at {item.triggered_at || 'unknown time'}</Typography>
        {item.schedule_missing && <Alert severity="warning">The original schedule is missing. You can still acknowledge recovery here; a note is required.</Alert>}
        {item.archived && <Typography>This schedule is archived.</Typography>}
        {isLocal && <Button variant="contained" disabled={busy || !healthy || !ready || (item.schedule_missing && !note.trim())}
          onClick={() => void submit(item.schedule_id)}>Acknowledge recovery</Button>}
      </Stack>
    </CardContent></Card>)}
    {isLocal && state?.resume_required && <>
      {state.resume_block_reason && <Typography>{state.resume_block_reason}</Typography>}
      <Button variant="contained" disabled={busy || !healthy || state.active || Boolean(state.resume_block_reason)} onClick={() => void submit()}>
        Resume queued jobs
      </Button>
      <Typography variant="body2">Due jobs may start immediately. The failed schedule remains inactive.</Typography>
    </>}
    {!isLocal && <Typography>Recovery and Resume controls are available only on the local robot control workstation.</Typography>}
  </Stack>;
}
