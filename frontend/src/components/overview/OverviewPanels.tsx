import React, { useState } from 'react';
import { Box, Button, Link as MuiLink, Stack, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
import StatusChip from '../StatusChip';
import { ListRow, Panel, StatusDot } from '../PageLayout';
import { cameraStateLabels } from '../CameraControls';
import { api } from '../../services/api';
import { schedulingService, schedulingAPI } from '../../services/schedulingApi';
import { useSerialPolling } from '../../hooks/useSerialPolling';
import { robotAttention, type RobotStatus } from '../../hooks/useRobotStatus';
import type { ScheduledExperiment } from '../../types/scheduling';
import { fontMono, layout, type StatusTone } from '../../theme';
import { clockTime, dayTime } from '../../utils/displayTime';
import { repeatLabel } from '../scheduling/ScheduleCollection';
import { executionTone } from '../scheduling/executionStatus';

const PANEL_REFRESH_MS = 60000;
/** Rows shown in the Overview lists (the approved mock's seven). */
const LIST_ROWS = 7;
const mono = { fontFamily: fontMono, fontSize: 12, color: 'text.secondary' } as const;

const headerLink = (to: string, text: string) => <MuiLink component={Link} to={to} underline="hover" sx={{ fontSize: 13 }}>{text}</MuiLink>;

/** A panel's read failed: keep what was shown and offer a retry, without blanking the page. */
function ReadProblem({ error, stale, onRetry, pending }: { error: string; stale: boolean; onRetry: () => void; pending: boolean }) {
  return <Stack direction="row" alignItems="center" gap={1} role="alert" sx={{ minHeight: layout.row, px: `${layout.inset}px`, fontSize: 13, color: 'attentionSurface.text', borderBottom: 1, borderColor: 'surface.rowLine' }}>
    <span>{stale ? 'Could not refresh. Showing earlier data.' : error}</span>
    <Button size="small" onClick={onRetry} disabled={pending}>Retry</Button>
  </Stack>;
}

function EmptyRow({ children }: { children: React.ReactNode }) {
  return <Typography variant="body2" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', height: layout.row, px: `${layout.inset}px` }}>{children}</Typography>;
}

/** Shown only while the scheduler is holding runs for an operator. */
export function NeedsAttention({ status, span }: { status: RobotStatus | null; span?: number }) {
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
  // On phones the hold comes first, right after the status strip: it blocks every other run.
  return <Panel title="Needs attention" tone="attention" span={span} actions={<StatusChip tone="attention" label={chip} />} sx={{ order: { xs: -1, md: 0 } }}
    bodySx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
    <Typography sx={{ fontSize: 16, lineHeight: '24px', fontWeight: 600, overflowWrap: 'anywhere' }}>{heading}</Typography>
    {note && <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>{note}</Typography>}
    <Typography variant="body2" color="text.secondary">{body}</Typography>
    <Box sx={{ flex: 1, minHeight: 8 }} />
    <Button variant="contained" component={Link} to="/scheduling?section=recovery"
      sx={{ alignSelf: 'flex-start', bgcolor: 'attentionSurface.action', color: 'attentionSurface.actionText', '&:hover': { bgcolor: 'attentionSurface.action', filter: 'brightness(0.94)' } }}>Review recovery</Button>
  </Panel>;
}

export function UpNext({ canOpenScheduling, span }: { canOpenScheduling: boolean; span?: number }) {
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
    .slice(0, LIST_ROWS);
  return <Panel title="Up next" span={span} inset={false} fill actions={canOpenScheduling && headerLink('/scheduling', 'All schedules')}>
    {polling.error && <ReadProblem error="Could not load schedules." stale={!!schedules} onRetry={() => void polling.refresh()} pending={polling.pending} />}
    {schedules && !upcoming.length && <EmptyRow>No scheduled runs.</EmptyRow>}
    {upcoming.map(schedule => {
      const duration = schedule.estimated_duration > 0 ? `${schedule.estimated_duration} min` : '';
      return <ListRow key={schedule.schedule_id} columns={{ xs: '104px minmax(0, 1fr) 48px', sm: '128px minmax(0, 1fr) 96px 56px' }}>
        <Box component="span" sx={mono}>{dayTime(schedule.next_run!)}</Box>
        <Box component="span" sx={{ fontWeight: 500 }}>{schedule.experiment_name}</Box>
        <Box component="span" sx={{ display: { xs: 'none', sm: 'block' }, color: 'text.secondary' }}>{repeatLabel(schedule)}</Box>
        <Box component="span" sx={{ ...mono, textAlign: 'right' }}>{duration}</Box>
      </ListRow>;
    })}
  </Panel>;
}

type CameraHealth = { capture_state?: string; recording_state?: string; error?: string | null };
type Health = { database: boolean | null; camera: CameraHealth | null };

/** One-line strip of instrument states across the page, like a console status bar. */
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
  const cells: [string, [string, StatusTone]][] = [
    ['Scheduler', !status ? unknown : status.schedulerRunning ? ['Running', 'running'] : ['Stopped', 'neutral']],
    ['Storage', !status?.recovery ? unknown : status.recovery.storage_healthy ? ['Healthy', 'completed'] : ['Needs attention', 'attention']],
    ['SQL Server', health?.database === true ? ['Connected', 'completed'] : health?.database === false ? ['Disconnected', 'fault'] : unknown],
    ['HxRun', status?.hamiltonRunning === true ? ['Running', 'running'] : status?.hamiltonRunning === false ? ['Not running', 'neutral'] : unknown],
    ['Camera', cameraState],
  ];
  return <Box component="section" aria-label="Instrument health" sx={{ gridColumn: '1 / -1', order: { xs: -2, md: 0 }, minWidth: 0, bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: `${layout.radius}px`, overflow: 'hidden' }}>
    {polling.error && <ReadProblem error="Could not check the database and camera." stale={!!health} onRetry={() => void polling.refresh()} pending={polling.pending} />}
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(5, minmax(0, 1fr)) auto' } }}>
      {cells.map(([name, [state, tone]]) => <Box key={name} sx={{ display: 'flex', alignItems: 'center', gap: 1, height: layout.row, px: `${layout.inset}px`, minWidth: 0,
        borderRight: 1, borderBottom: { xs: 1, md: 0 }, borderColor: 'surface.rowLine' }}>
        <Typography component="span" variant="overline" sx={{ textTransform: 'uppercase', color: 'surface.label', whiteSpace: 'nowrap' }}>{name}</Typography>
        <Box sx={{ ml: 'auto', minWidth: 0 }}><StatusDot tone={tone} label={state} /></Box>
      </Box>)}
      <Box sx={{ display: 'flex', alignItems: 'center', height: layout.row, px: `${layout.inset}px` }}>{headerLink('/system-status', 'System status')}</Box>
    </Box>
  </Box>;
}

type Run = { id: string; name: string; started?: string | null; minutes: number | null; status: string };

export function RecentRuns({ canOpenScheduling, span }: { canOpenScheduling: boolean; span?: number }) {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const polling = useSerialPolling<Run[]>({
    interval: PANEL_REFRESH_MS,
    request: async () => {
      const { data } = await schedulingAPI.getExecutionHistory(undefined, LIST_ROWS);
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
  return <Panel title="Recent runs" span={span} inset={false} fill actions={canOpenScheduling && headerLink('/scheduling?section=history', 'History')}>
    {polling.error && <ReadProblem error="Could not load recent runs." stale={!!runs} onRetry={() => void polling.refresh()} pending={polling.pending} />}
    {runs && !runs.length && <EmptyRow>No runs yet.</EmptyRow>}
    {(runs ?? []).map(run => {
      const [label, tone] = executionTone(run.status);
      return <ListRow key={run.id} columns={{ xs: 'minmax(0, 1fr) auto', sm: 'minmax(0, 1fr) 128px 56px 136px' }}>
        <Box component="span" sx={{ fontWeight: 500 }}>{run.name}</Box>
        <Box component="span" sx={{ ...mono, display: { xs: 'none', sm: 'block' } }}>{run.started ? dayTime(run.started) : '—'}</Box>
        <Box component="span" sx={{ ...mono, display: { xs: 'none', sm: 'block' }, textAlign: 'right' }}>{run.minutes !== null ? `${run.minutes} min` : '—'}</Box>
        <Box component="span" sx={{ justifySelf: 'end' }}><StatusChip tone={tone} label={label} /></Box>
      </ListRow>;
    })}
  </Panel>;
}
