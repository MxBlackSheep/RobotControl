import React, { useState } from 'react';
import { Box, Button, Card, Link as MuiLink, Stack, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
import StatusChip from '../StatusChip';
import { PanelLabel } from '../PageLayout';
import { cameraStateLabels } from '../CameraControls';
import { api } from '../../services/api';
import { schedulingService, schedulingAPI } from '../../services/schedulingApi';
import { useSerialPolling } from '../../hooks/useSerialPolling';
import { robotAttention, type RobotStatus } from '../../hooks/useRobotStatus';
import type { ScheduledExperiment } from '../../types/scheduling';
import type { StatusTone } from '../../theme';
import { clockTime, dayTime } from '../../utils/displayTime';
import { repeatLabel } from '../scheduling/ScheduleCollection';
import { executionTone } from '../scheduling/executionStatus';

const PANEL_REFRESH_MS = 60000;

function Panel({ title, link, children }: { title: string; link?: { to: string; text: string } | null; children: React.ReactNode }) {
  return <Card component="section" aria-label={title} variant="outlined" sx={{ p: { xs: 2, sm: 2.5 }, minWidth: 0 }}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1} sx={{ mb: 1 }}>
      <Typography component="h2" variant="h6">{title}</Typography>
      {link && <MuiLink component={Link} to={link.to} sx={{ fontSize: 14 }}>{link.text}</MuiLink>}
    </Stack>
    {children}
  </Card>;
}

function Rows({ children }: { children: React.ReactNode }) {
  return <Box sx={{ '& > *': { py: 1.25, borderTop: 1, borderColor: 'divider', minWidth: 0 }, '& > *:first-of-type': { borderTop: 0 } }}>{children}</Box>;
}

/** A panel's read failed: keep what was shown and offer a retry, without blanking the page. */
function ReadProblem({ error, stale, onRetry, pending }: { error: string; stale: boolean; onRetry: () => void; pending: boolean }) {
  return <Stack direction="row" alignItems="center" gap={1} role="alert" sx={{ fontSize: 13, color: theme => theme.palette.tone.attention.fg, mb: 0.5 }}>
    <span>{stale ? 'Could not refresh. Showing earlier data.' : error}</span>
    <Button size="small" onClick={onRetry} disabled={pending}>Retry</Button>
  </Stack>;
}

/** Shown only while the scheduler is holding runs for an operator. */
export function NeedsAttention({ status }: { status: RobotStatus | null }) {
  const attention = robotAttention(status);
  if (!attention || !status?.recovery) return null;
  const recovery = status.recovery;
  const first = recovery.pending_recoveries?.[0];
  const note = attention.kind === 'recovery' ? first?.note || recovery.note : null;
  const [chip, heading, body] = attention.kind === 'storage'
    ? ['Storage unavailable', 'Scheduler storage', `No runs are dispatched until scheduler storage is healthy again.${recovery.storage_error ? ` ${recovery.storage_error}` : ''}`]
    : attention.kind === 'recovery'
      ? ['Recovery required', first?.experiment_name || recovery.experiment_name || 'A scheduled run',
          `${first?.triggered_at ? `Stopped at ${clockTime(new Date(first.triggered_at))}. ` : ''}New runs are held until someone checks the deck and resolves this.${attention.count > 1 ? ` ${attention.count - 1} more waiting.` : ''}`]
      : ['Waiting for Resume', 'Queued jobs are paused', 'Recovery is acknowledged. Queued jobs stay paused until someone chooses Resume queued jobs.'];
  return <Card component="section" aria-label="Needs attention" variant="outlined"
    sx={{ p: { xs: 2, sm: 2.5 }, minWidth: 0, borderColor: theme => theme.palette.tone.attention.fg, display: 'flex', flexDirection: 'column', gap: 1.25 }}>
    <Stack direction="row" alignItems="center" gap={1.25} flexWrap="wrap"><PanelLabel>Needs attention</PanelLabel><StatusChip tone="attention" label={chip} /></Stack>
    <Typography sx={{ fontSize: 18, fontWeight: 600, overflowWrap: 'anywhere' }}>{heading}</Typography>
    {note && <Typography sx={{ fontSize: 14, overflowWrap: 'anywhere' }}>{note}</Typography>}
    <Typography sx={{ fontSize: 14, color: 'text.secondary' }}>{body}</Typography>
    <Box sx={{ flex: 1 }} />
    <Button variant="contained" color="warning" component={Link} to="/scheduling?section=recovery" sx={{ alignSelf: 'flex-start' }}>Review recovery</Button>
  </Card>;
}

export function UpNext({ canOpenScheduling }: { canOpenScheduling: boolean }) {
  const [schedules, setSchedules] = useState<ScheduledExperiment[] | null>(null);
  const polling = useSerialPolling<ScheduledExperiment[]>({
    interval: PANEL_REFRESH_MS,
    request: async () => {
      const result = await schedulingService.getAllSchedules(true, false);
      if (result.error) throw new Error(result.error);
      return result.schedules;
    },
    onSuccess: setSchedules,
  });
  const upcoming = (schedules ?? [])
    .filter(schedule => schedule.is_active && !schedule.archived && schedule.next_run && !Number.isNaN(new Date(schedule.next_run).getTime()))
    .sort((a, b) => new Date(a.next_run!).getTime() - new Date(b.next_run!).getTime())
    .slice(0, 4);
  return <Panel title="Up next" link={canOpenScheduling ? { to: '/scheduling', text: 'All schedules' } : null}>
    {polling.error && <ReadProblem error="Could not load schedules." stale={!!schedules} onRetry={() => void polling.refresh()} pending={polling.pending} />}
    {schedules && !upcoming.length && <Typography sx={{ fontSize: 14, color: 'text.secondary', py: 1 }}>No scheduled runs.</Typography>}
    <Rows>{upcoming.map(schedule => {
      const duration = schedule.estimated_duration > 0 ? `${schedule.estimated_duration} min` : '';
      return <Box key={schedule.schedule_id} sx={{ display: 'grid', gridTemplateColumns: { xs: 'minmax(0,1fr)', sm: '130px minmax(0,1fr) auto 64px' }, columnGap: 2, rowGap: 0.25, alignItems: 'baseline', fontSize: 14 }}>
        <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' }, color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}>{dayTime(schedule.next_run!)}</Box>
        <Box component="span" sx={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{schedule.experiment_name}</Box>
        <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' }, color: 'text.secondary' }}>{repeatLabel(schedule)}</Box>
        <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' }, color: 'text.secondary', textAlign: 'right' }}>{duration}</Box>
        <Box component="span" sx={{ display: { xs: 'inline', sm: 'none' }, color: 'text.secondary', fontSize: 13 }}>{[dayTime(schedule.next_run!), repeatLabel(schedule), duration].filter(Boolean).join(' · ')}</Box>
      </Box>;
    })}</Rows>
  </Panel>;
}

type CameraHealth = { capture_state?: string; recording_state?: string; error?: string | null };
type Health = { database: boolean | null; camera: CameraHealth | null };

export function InstrumentHealth({ status }: { status: RobotStatus | null }) {
  const [health, setHealth] = useState<Health | null>(null);
  const polling = useSerialPolling<Health>({
    interval: PANEL_REFRESH_MS,
    request: async () => {
      // One failing source must not hide the other.
      const [database, camera] = await Promise.allSettled([api.get('/api/monitoring/system-health'), api.get('/api/camera/control-status')]);
      if (database.status === 'rejected' && camera.status === 'rejected') throw new Error('Instrument health unavailable');
      const connected = database.status === 'fulfilled' ? database.value.data?.data?.database?.is_connected : undefined;
      return {
        database: typeof connected === 'boolean' ? connected : null,
        camera: camera.status === 'fulfilled' ? camera.value.data?.data?.health ?? null : null,
      };
    },
    onSuccess: setHealth,
  });
  const unknown: [string, StatusTone] = ['Unknown', 'neutral'];
  const camera = health?.camera;
  const cameraState: [string, StatusTone] = !camera ? unknown
    : camera.error ? ['Error', 'fault']
    : camera.recording_state === 'recording' ? ['Recording', 'running']
    : camera.capture_state === 'connected' ? ['Connected', 'completed']
    : [cameraStateLabels[camera.capture_state ?? ''] ?? 'Unknown', camera.capture_state === 'disconnected' ? 'attention' : 'neutral'];
  const rows: [string, [string, StatusTone]][] = [
    ['Scheduler', !status ? unknown : status.schedulerRunning ? ['Running', 'running'] : ['Stopped', 'neutral']],
    ['Scheduler storage', !status?.recovery ? unknown : status.recovery.storage_healthy ? ['Healthy', 'completed'] : ['Needs attention', 'attention']],
    ['SQL Server database', health?.database === true ? ['Connected', 'completed'] : health?.database === false ? ['Disconnected', 'fault'] : unknown],
    ['HxRun', status?.hamiltonRunning === true ? ['Running', 'running'] : status?.hamiltonRunning === false ? ['Not running', 'neutral'] : unknown],
    ['Camera', cameraState],
  ];
  return <Panel title="Instrument health" link={{ to: '/system-status', text: 'System status' }}>
    {polling.error && <ReadProblem error="Could not check the database and camera." stale={!!health} onRetry={() => void polling.refresh()} pending={polling.pending} />}
    <Rows>{rows.map(([name, [state, tone]]) => <Stack key={name} direction="row" alignItems="center" justifyContent="space-between" gap={1} sx={{ fontSize: 14 }}>
      <span>{name}</span><StatusChip tone={tone} label={state} />
    </Stack>)}</Rows>
  </Panel>;
}

type Run = { id: string; name: string; started?: string | null; minutes: number | null; status: string };

export function RecentRuns() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const polling = useSerialPolling<Run[]>({
    interval: PANEL_REFRESH_MS,
    request: async () => {
      const { data } = await schedulingAPI.getExecutionHistory(undefined, 5);
      if (!data?.success || !Array.isArray(data.data)) throw new Error(data?.message || 'Could not load recent runs');
      return data.data.map((record: Record<string, any>) => ({
        id: String(record.execution_id),
        name: record.experiment_name_snapshot || record.experiment_name || 'Archived schedule',
        started: record.start_time,
        minutes: typeof record.duration_minutes === 'number' ? record.duration_minutes
          : typeof record.calculated_duration_minutes === 'number' ? Math.round(record.calculated_duration_minutes) : null,
        status: String(record.status ?? ''),
      }));
    },
    onSuccess: setRuns,
  });
  return <Panel title="Recent runs">
    {polling.error && <ReadProblem error="Could not load recent runs." stale={!!runs} onRetry={() => void polling.refresh()} pending={polling.pending} />}
    {runs && !runs.length && <Typography sx={{ fontSize: 14, color: 'text.secondary', py: 1 }}>No runs yet.</Typography>}
    <Rows>{(runs ?? []).map(run => {
      const [label, tone] = executionTone(run.status);
      return <Box key={run.id} sx={{ display: 'grid', gridTemplateColumns: { xs: 'minmax(0,1fr) auto', sm: 'minmax(0,1fr) 140px 80px 170px' }, columnGap: 2, rowGap: 0.5, alignItems: 'center', fontSize: 14 }}>
        <Box component="span" sx={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{run.name}</Box>
        <Box component="span" sx={{ color: 'text.secondary', display: { xs: 'none', sm: 'inline' } }}>{run.started ? new Date(run.started).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }) : '—'}</Box>
        <Box component="span" sx={{ color: 'text.secondary', display: { xs: 'none', sm: 'inline' } }}>{run.minutes !== null ? `${run.minutes} min` : '—'}</Box>
        <Box component="span" sx={{ justifySelf: { xs: 'end', sm: 'start' } }}><StatusChip tone={tone} label={label} /></Box>
      </Box>;
    })}</Rows>
  </Panel>;
}
