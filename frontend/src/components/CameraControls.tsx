import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { buildApiUrl } from '@/utils/apiBase';
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
const labels: Record<string, string> = {
  no_frames: 'No frames', connected: 'Connected', disconnected: 'Disconnected', connecting: 'Connecting',
  reconnecting: 'Reconnecting', error: 'Error', recording: 'Recording', starting: 'Starting', stopped: 'Stopped',
};

export default function CameraControls({ admin, onSourceChange }: {
  admin: boolean; onSourceChange: () => void;
}) {
  const [status, setStatus] = useState<CameraStatus>();
  const [selection, setSelection] = useState('');
  const edited = useRef(false);
  const generation = useRef<string | null>();
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [awaitingOperation, setAwaitingOperation] = useState<{id: string; revision?: number} | null>(null);
  const token = localStorage.getItem('access_token');
  const actionRequest = useRef<AbortController>();
  useEffect(() => {
    setSubmitting(false);
    setAwaitingOperation(null);
    return () => { actionRequest.current?.abort(); actionRequest.current = undefined; };
  }, [token]);
  const health = status?.health;
  const pending = submitting || Boolean(awaitingOperation) || health?.operation?.state === 'pending';
  const polling = useSerialPolling({
    identity: token, interval: pending ? 1000 : 5000,
    request: async signal => {
      const response = await fetch(buildApiUrl('/api/camera/control-status'), {
        headers: { Authorization: `Bearer ${token}` }, signal,
      });
      if (!response.ok) throw new Error(`Camera status unavailable (${response.status})`);
      return (await response.json()).data as CameraStatus;
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
      const response = await fetch(buildApiUrl(`/api/camera/${path}`), {
        method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      const result = await response.json();
      if (controller.signal.aborted) return;
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Camera operation failed');
      setAwaitingOperation(result.data.operation);
      await polling.refresh();
    } catch (cause) {
      if (controller.signal.aborted) return;
      setActionError(cause instanceof Error ? cause.message : 'Camera operation failed');
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
  return <Stack spacing={2} sx={{ mb: 3 }}>
    <Typography variant="h6">Camera and recording</Typography>
    <Typography aria-live="polite">
      Camera: {labels[health?.capture_state ?? ''] ?? 'Checking'} · Recording: {labels[health?.recording_state ?? ''] ?? 'Checking'}
    </Typography>
    {error && <Alert severity="warning">{error}</Alert>}
    <Typography variant="body2" color="text.secondary">
      One camera supplies recording and all live viewers. Recovery is manual. Refresh cameras after connecting a USB device.
    </Typography>
    <TextField select fullWidth label="Selected camera" value={selection}
      disabled={!admin || pending || selectionLocked}
      onChange={event => { edited.current = true; setSelection(event.target.value); }}
      helperText={selectionLocked ? 'Stop recording before changing cameras.' : 'Choose a camera, then save the selection before connecting.'}>
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
      <Button disabled={pending || !saved || changed || health?.recording_state === 'recording'}
        onClick={() => void act('recording/start')}>Start recording</Button>
      <Button disabled={pending || !recordingRequested} onClick={() => void act('recording/stop')}>Stop recording</Button>
    </Box> : <Typography variant="body2">An administrator can select, connect or reconnect the camera.</Typography>}
    {pending && <Typography role="status">Camera operation in progress…</Typography>}
    <Typography variant="caption" color="text.secondary">
      Reconnecting interrupts the camera briefly for all viewers. A forced recovery may leave the current clip incomplete; completed recordings remain available.
    </Typography>
  </Stack>;
}
