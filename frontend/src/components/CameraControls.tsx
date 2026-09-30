import StatusChip from './StatusChip';
import type { StatusTone } from '../theme';
import { useEffect, useRef, useState } from 'react';
import { isAxiosError } from 'axios';
import { Alert, Box, Button, Collapse, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { api } from '@/services/api';
import { useAuth } from '@/context/AuthContext';
import { useSerialPolling } from '@/hooks/useSerialPolling';

interface Health {
  device_identity: string | null;
  generation: string | null;
  capture_state: string;
  recording_state: string;
  recording_requested: boolean;
  last_frame_age_seconds: number | null;
  error: string | null;
  operation: { id: string; revision?: number; state: string; action: string; error: string | null } | null;
}
interface CameraStatus {
  cameras: { id: number; name: string; device_identity: string | null }[];
  health: Health;
}
export const cameraStateLabels: Record<string, string> = {
  no_frames: 'No frames', connected: 'Connected', disconnected: 'Disconnected', connecting: 'Connecting',
  reconnecting: 'Reconnecting', error: 'Error', recording: 'Recording', starting: 'Starting', stopped: 'Stopped',
};

export interface CameraSummary { text: string; error: string | null }

export default function CameraControls({ admin, onSourceChange, collapsible = false, active = true, onSummaryChange }: {
  admin: boolean; onSourceChange: () => void; collapsible?: boolean; active?: boolean; onSummaryChange?: (summary: CameraSummary) => void;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [status, setStatus] = useState<CameraStatus>();
  const [selection, setSelection] = useState('');
  const edited = useRef(false);
  const generation = useRef<string | null>();
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [awaitingOperation, setAwaitingOperation] = useState<{id: string; revision?: number} | null>(null);
  // Reset on a change of signed-in user, not of access token: the shared client renews
  // the token mid-request, and that must not abort the request it is retrying.
  const signIn = useAuth().user?.user_id ?? null;
  const actionRequest = useRef<AbortController>();
  useEffect(() => {
    setSubmitting(false);
    setAwaitingOperation(null);
    return () => { actionRequest.current?.abort(); actionRequest.current = undefined; };
  }, [signIn]);
  const health = status?.health;
  const pending = submitting || Boolean(awaitingOperation) || health?.operation?.state === 'pending';
  const polling = useSerialPolling({
    enabled: active, identity: signIn, interval: pending ? 1000 : 5000,
    request: async signal => {
      try {
        return (await api.get('/api/camera/control-status', { signal })).data.data as CameraStatus;
      } catch (cause) {
        if (isAxiosError(cause) && cause.response) throw new Error(`Camera status unavailable (${cause.response.status})`);
        throw cause;
      }
    },
    onSuccess: value => {
      setStatus(value);
      if (!edited.current) setSelection(value.health.device_identity ?? '');
      if (generation.current !== undefined && generation.current !== value.health.generation) onSourceChange();
      generation.current = value.health.generation;
      // The first poll after POST may have started before the operation existed.
      const operation = value.health.operation;
      // Operations are in-memory. A restarted backend has no pending operation.
      if (awaitingOperation && !operation) setAwaitingOperation(null);
      if (awaitingOperation && operation && (operation.id === awaitingOperation.id ||
        (awaitingOperation.revision !== undefined && (operation.revision ?? 0) >= awaitingOperation.revision))) {
        setAwaitingOperation(null);
      }
    },
  });
  const act = async (path: string, method = 'POST', body?: object) => {
    if (actionRequest.current) return;
    const controller = new AbortController();
    actionRequest.current = controller;
    setSubmitting(true);
    setActionError(null);
    try {
      const response = await api.request({ url: `/api/camera/${path}`, method, data: body, signal: controller.signal });
      if (controller.signal.aborted) return;
      setAwaitingOperation(response.data.data.operation);
      await polling.refresh();
    } catch (cause) {
      if (controller.signal.aborted) return;
      // Check the status first: a proxy's HTML error page has no JSON detail.
      const detail = isAxiosError(cause) ? cause.response?.data?.detail : undefined;
      const status = isAxiosError(cause) ? cause.response?.status : undefined;
      setActionError(typeof detail === 'string' ? detail
        : status ? `Camera operation failed (${status})` : cause instanceof Error ? cause.message : 'Camera operation failed');
    } finally {
      if (actionRequest.current === controller) actionRequest.current = undefined;
      if (!controller.signal.aborted) setSubmitting(false);
    }
  };
  const saved = health?.device_identity ?? '';
  const changed = selection !== saved;
  const devices = status?.cameras ?? [];
  const selectedExists = devices.some(device => device.device_identity === selection);
  const recordingRequested = Boolean(health?.recording_requested);
  const selectionLocked = recordingRequested && Boolean(saved);
  const error = actionError || health?.operation?.error || health?.error || polling.error;
  const summary = `Camera: ${cameraStateLabels[health?.capture_state ?? ''] ?? 'Checking'} · Recording: ${cameraStateLabels[health?.recording_state ?? ''] ?? 'Checking'}`;
  useEffect(() => { onSummaryChange?.({ text: summary, error: error || null }); }, [summary, error, onSummaryChange]);
  const recordingChip = { label: cameraStateLabels[health?.recording_state ?? ''] ?? 'Checking',
    tone: (health?.recording_state === 'recording' ? 'running' : health?.recording_state === 'error' ? 'fault' : 'neutral') as StatusTone };
  const cameraChip = { label: cameraStateLabels[health?.capture_state ?? ''] ?? 'Checking',
    tone: (health?.capture_state === 'connected' ? 'completed' : health?.capture_state === 'error' ? 'fault' : health?.capture_state === 'disconnected' ? 'attention' : 'neutral') as StatusTone };
  // Beside the image the two groups are cards; below it on phones they share one collapsible panel.
  const group = !collapsible ? { p: 2, bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: 2 } : {};
  const heading = (title: string, chip: { label: string; tone: StatusTone }) => <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1}>
    <Typography component="h2" variant="h6">{title}</Typography><StatusChip tone={chip.tone} label={chip.label} />
  </Stack>;
  return <Stack spacing={collapsible ? 1 : 2} sx={{ my: collapsible ? 2 : 0, '& button': { minHeight: 44 } }}>
    {collapsible && <Button aria-expanded={detailsOpen} aria-controls="camera-settings-panel" onClick={() => setDetailsOpen(value => !value)} sx={{ alignSelf: 'flex-start' }}>Camera and recording settings</Button>}
    {!onSummaryChange && <Typography aria-live="polite">{summary}</Typography>}
    {!onSummaryChange && error && <Alert severity="warning">{error}</Alert>}
    <Collapse in={!collapsible || detailsOpen} unmountOnExit={false}>
    <Stack id="camera-settings-panel" spacing={2} sx={{ p: collapsible ? 2 : 0, border: collapsible ? 1 : 0, borderColor: 'divider', borderRadius: 1 }}>
      <Stack component="section" aria-label="Recording" spacing={1.5} sx={group}>
        {heading('Recording', recordingChip)}
        {admin ? <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          <Button disabled={pending || !saved || changed || health?.recording_state === 'recording'}
            onClick={() => void act('recording/start')}>Start recording</Button>
          <Button disabled={pending || !recordingRequested} onClick={() => void act('recording/stop')}>Stop recording</Button>
        </Box> : <Typography variant="body2" color="text.secondary">An administrator can start or stop recording.</Typography>}
      </Stack>
      <Stack component="section" aria-label="Camera" spacing={1.5} sx={{ ...group, ...(collapsible && { borderTop: 1, borderColor: 'divider', pt: 2 }) }}>
        {heading('Camera', cameraChip)}
        <Typography variant="body2" color="text.secondary">Camera changes affect recording and every live viewer.</Typography>
        <TextField select fullWidth label="Selected camera" value={selection}
          disabled={!admin || pending || selectionLocked}
          onChange={event => { edited.current = true; setSelection(event.target.value); }}
          helperText={selectionLocked ? 'Stop recording before changing cameras.' : 'Save your selection before connecting.'}>
          <MenuItem value="">Select a camera</MenuItem>
          {selection && !selectedExists && <MenuItem value={selection}>Saved camera — unavailable</MenuItem>}
          {devices.filter(device => device.device_identity).map(device =>
            <MenuItem key={device.device_identity!} value={device.device_identity!}>
              {device.name} · Device {device.id + 1}
            </MenuItem>)}
        </TextField>
        {admin ? <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          <Button disabled={pending} onClick={() => void act('devices/refresh')}>Refresh cameras</Button>
          <Button disabled={pending || selectionLocked || !selection || !changed || !selectedExists}
            onClick={() => void act('selection', 'PATCH', { device_identity: selection })}>Save selection</Button>
          <Button variant="contained" disabled={pending || !saved || changed || health?.capture_state === 'connected'}
            onClick={() => void act('connect')}>Connect</Button>
          <Button disabled={pending || !saved || changed} onClick={() => void act('reconnect')}>Reconnect camera</Button>
        </Box> : <Typography variant="body2">An administrator can select, connect or reconnect the camera.</Typography>}
        <Typography variant="caption" color="text.secondary">
          Reconnect briefly interrupts all viewers and may leave the current clip incomplete.
        </Typography>
      </Stack>
      {pending && <Typography role="status">Camera operation in progress…</Typography>}
    </Stack>
    </Collapse>
  </Stack>;
}
