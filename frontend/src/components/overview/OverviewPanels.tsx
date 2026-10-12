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
import { labwareApi, type TipTrackingSnapshot } from '../../services/labwareApi';

const PANEL_REFRESH_MS = 60000;
/** Rows shown in the Overview lists (the approved mock's seven). */
const LIST_ROWS = 7;
const mono = { fontFamily: fontMono, fontSize: 12, color: 'text.secondary' } as const;

/**
 * The list panels sit side by side, so their rows follow the panel's width, not the window's:
 * at 900px each is ~388px. Thresholds keep the name column at least ~140px wide. Up next's time
 * column stays 128px everywhere: the longest dayTime ("13 Jan 2027 09:00") needs ~122px.
 */
const listPanel = { containerType: 'inline-size', containerName: 'list' } as const;
const upNextDuration = '@container list (min-width: 380px)';
const upNextFull = '@container list (min-width: 500px)';
const recentStarted = '@container list (min-width: 464px)';
const recentFull = '@container list (min-width: 544px)';
const shownFrom = (query: string) => ({ display: 'none', [query]: { display: 'block' } });

// The pseudo-element gives the 20px text link a 44px-high touch target without growing the 40px band.
const headerLink = (to: string, text: string) => <MuiLink component={Link} to={to} underline="hover"
  sx={{ fontSize: 13, position: 'relative', '&::after': { content: '""', position: 'absolute', inset: '-12px -8px' } }}>{text}</MuiLink>;

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
    {/* Desktop pins the action to the panel's foot beside Now running; a phone needs no spacer. */}
    <Box sx={{ flex: 1, minHeight: 8, display: { xs: 'none', md: 'block' } }} />
    <Button variant="contained" component={Link} to="/scheduling?section=recovery"
      sx={{ alignSelf: 'flex-start', bgcolor: 'attentionSurface.action', color: 'attentionSurface.actionText', '&:hover': { bgcolor: 'attentionSurface.action', filter: 'brightness(0.94)' } }}>Review recovery</Button>
  </Panel>;
}

/** `rows`: phones show fewer so two panels fit one card; the full lists are a link away. */
export function UpNext({ canOpenScheduling, span, rows = LIST_ROWS }: { canOpenScheduling: boolean; span?: number; rows?: number }) {
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
    .slice(0, rows);
  return <Panel title="Up next" span={span} inset={false} fill sx={listPanel} actions={canOpenScheduling && headerLink('/scheduling', 'All schedules')}>
    {polling.error && <ReadProblem error="Could not load schedules." stale={!!schedules} onRetry={() => void polling.refresh()} pending={polling.pending} />}
    {schedules && !upcoming.length && <EmptyRow>No scheduled runs.</EmptyRow>}
    {upcoming.map(schedule => {
      const duration = schedule.estimated_duration > 0 ? `${schedule.estimated_duration} min` : '';
      return <ListRow key={schedule.schedule_id} columns="128px minmax(0, 1fr)"
        sx={{ [upNextDuration]: { gridTemplateColumns: '128px minmax(0, 1fr) 56px' }, [upNextFull]: { gridTemplateColumns: '128px minmax(0, 1fr) 96px 56px' } }}>
        <Box component="span" sx={mono}>{dayTime(schedule.next_run!)}</Box>
        <Box component="span" sx={{ fontWeight: 500 }}>{schedule.experiment_name}</Box>
        <Box component="span" sx={{ ...shownFrom(upNextFull), color: 'text.secondary' }}>{repeatLabel(schedule)}</Box>
        <Box component="span" sx={{ ...mono, ...shownFrom(upNextDuration), textAlign: 'right' }}>{duration}</Box>
      </ListRow>;
    })}
  </Panel>;
}

/**
 * From 600px: equal shares of a line, but never narrower than the cell's own text. On phones the
 * cells form a grid with the label above the state, three across (two on a 320px phone, whose
 * content is 288px), so the strip takes two short rows instead of one row per cell.
 */
const healthCell = { display: 'flex', flex: '1 1 0', px: { xs: 1.5, sm: `${layout.inset}px` }, borderRight: 1, borderBottom: 1, borderColor: 'surface.rowLine',
  flexDirection: { xs: 'column', sm: 'row' }, alignItems: { xs: 'flex-start', sm: 'center' }, justifyContent: { xs: 'center', sm: 'flex-start' },
  minWidth: { xs: 0, sm: 'max-content' }, minHeight: { xs: 52, sm: layout.row }, py: { xs: 0.75, sm: 0 } } as const;

type CameraHealth = { capture_state?: string; recording_state?: string; error?: string | null };

/** Instrument states shared by the desktop strip and the phone's fault lines; polls the camera. */
function useInstrumentStates(status: RobotStatus | null) {
  // Undefined until the first read; null when the reply carried no health.
  const [camera, setCamera] = useState<CameraHealth | null | undefined>(undefined);
  const polling = useSerialPolling<CameraHealth | null>({
    interval: PANEL_REFRESH_MS,
    request: async () => (await api.get('/api/camera/control-status')).data?.data?.health ?? null,
    onSuccess: setCamera,
  });
  const unknown: [string, StatusTone] = ['Unknown', 'neutral'];
  const cameraState: [string, StatusTone] = !camera ? unknown
    : camera.error ? ['Error', 'fault']
    : camera.recording_state === 'recording' ? ['Recording', 'running']
    : camera.capture_state === 'connected' ? ['Connected', 'completed']
    : [cameraStateLabels[camera.capture_state ?? ''] ?? 'Unknown', camera.capture_state === 'disconnected' ? 'attention' : 'neutral'];
  const cells: [string, [string, StatusTone]][] = [
    ['Scheduler', !status ? unknown : status.schedulerRunning ? ['Running', 'running'] : ['Stopped', 'neutral']],
    ['Storage', !status?.recovery ? unknown : status.recovery.storage_healthy ? ['Healthy', 'completed'] : ['Needs attention', 'attention']],
    ['HxRun', status?.hamiltonRunning === true ? ['Running', 'running'] : status?.hamiltonRunning === false ? ['Not running', 'neutral'] : unknown],
    ['Camera', cameraState],
  ];
  return { cells, polling, read: camera !== undefined };
}

/** One-line strip of instrument states across the page, like a console status bar. */
export function InstrumentHealth({ status }: { status: RobotStatus | null }) {
  const { cells, polling, read } = useInstrumentStates(status);
  return <Box component="section" aria-label="Instrument health" sx={{ gridColumn: '1 / -1', order: { xs: -2, md: 0 }, minWidth: 0, bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: `${layout.radius}px`, overflow: 'hidden' }}>
    {polling.error && <ReadProblem error="Could not check the camera." stale={read} onRetry={() => void polling.refresh()} pending={polling.pending} />}
    {/* Cells wrap by their content, so a long state ("Needs attention") moves to the next line
        instead of being clipped. Each cell draws its right and bottom line; the -1px margins push
        the lines on the outer edge under the section's border. */}
    {/* Phones: four states in a 2×2 grid, the same two rows as 3 + 1 without an empty cell. */}
    <Box sx={{ display: { xs: 'grid', sm: 'flex' }, gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
      flexWrap: 'wrap', mr: '-1px', mb: '-1px' }}>
      {cells.map(([name, [state, tone]]) => <Box key={name} sx={{ ...healthCell, columnGap: 2 }}>
        <Typography component="span" variant="overline" sx={{ textTransform: 'uppercase', color: 'surface.label', whiteSpace: 'nowrap' }}>{name}</Typography>
        <Box sx={{ ml: { xs: 0, sm: 'auto' }, '& > span': { whiteSpace: { xs: 'normal', sm: 'nowrap' } } }}><StatusDot tone={tone} label={state} /></Box>
      </Box>)}
    </Box>
  </Box>;
}

type Run = { id: string; name: string; started?: string | null; minutes: number | null; status: string };

export function RecentRuns({ canOpenScheduling, span, rows = LIST_ROWS }: { canOpenScheduling: boolean; span?: number; rows?: number }) {
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
  return <Panel title="Recent runs" span={span} inset={false} fill sx={listPanel} actions={canOpenScheduling && headerLink('/scheduling?section=history', 'History')}>
    {polling.error && <ReadProblem error="Could not load recent runs." stale={!!runs} onRetry={() => void polling.refresh()} pending={polling.pending} />}
    {runs && !runs.length && <EmptyRow>No runs yet.</EmptyRow>}
    {(runs ?? []).slice(0, rows).map(run => {
      const [label, tone] = executionTone(run.status);
      return <ListRow key={run.id} columns="minmax(0, 1fr) auto" sx={{ [recentStarted]: { gridTemplateColumns: 'minmax(0, 1fr) 128px 136px' }, [recentFull]: { gridTemplateColumns: 'minmax(0, 1fr) 128px 56px 136px' } }}>
        <Box component="span" sx={{ fontWeight: 500 }}>{run.name}</Box>
        <Box component="span" sx={{ ...mono, ...shownFrom(recentStarted) }}>{run.started ? dayTime(run.started) : '—'}</Box>
        <Box component="span" sx={{ ...mono, ...shownFrom(recentFull), textAlign: 'right' }}>{run.minutes !== null ? `${run.minutes} min` : '—'}</Box>
        <Box component="span" sx={{ justifySelf: 'end' }}><StatusChip tone={tone} label={label} /></Box>
      </ListRow>;
    })}
  </Panel>;
}

/**
 * Phones: instrument states only when one needs a look (a fault, an attention state or a stopped
 * scheduler), each linking to System status; otherwise one quiet line. Unknown is never "OK".
 */
export function InstrumentProblems({ status }: { status: RobotStatus | null }) {
  const { cells, polling, read } = useInstrumentStates(status);
  const problems = cells.filter(([name, [state, tone]]) => tone === 'fault' || tone === 'attention' || (name === 'Scheduler' && state === 'Stopped'));
  const known = read && !polling.error && cells.every(([, [state]]) => state !== 'Unknown');
  if (!problems.length) return known
    ? <Typography role="status" variant="body2" sx={{ textAlign: 'center', color: theme => theme.palette.tone.completed.fg }}>All systems OK</Typography>
    : null;
  return <Panel title="Needs a look" inset={false}>
    {problems.map(([name, [state, tone]]) => <ListRow key={name} component={Link} to="/system-status" columns="minmax(0, 1fr) auto"
      sx={{ height: 48, fontSize: 15, color: 'text.primary', textDecoration: 'none' }}>
      <span>{name}</span><StatusDot tone={tone} label={state} />
    </ListRow>)}
  </Panel>;
}

/** Clean tips per tip size (read-only); the racks are a tap away. Hidden if the deck has no "clean" state. */
export function CleanTips() {
  const [snapshot, setSnapshot] = useState<TipTrackingSnapshot | null>(null);
  const polling = useSerialPolling<TipTrackingSnapshot>({ interval: PANEL_REFRESH_MS, request: labwareApi.getTipTrackingSnapshot, onSuccess: setSnapshot });
  if (!snapshot || !snapshot.status_order?.includes('clean')) return null;
  const counts = snapshot.families.map(family => [family.display_name, [...family.left_racks, ...family.right_racks]
    .reduce((sum, rack) => sum + Object.values(family.tips?.[rack] ?? {}).filter(state => state === 'clean').length, 0)] as const);
  return <Panel title="Clean tips" inset={false} actions={headerLink('/labware', 'Tip racks')}>
    {polling.error && <ReadProblem error="Could not load tips." stale onRetry={() => void polling.refresh()} pending={polling.pending} />}
    {counts.map(([name, count]) => <ListRow key={name} columns="minmax(0, 1fr) auto" sx={{ height: 44, fontSize: 15 }}>
      <span>{name}</span><Box component="span" sx={{ fontFamily: fontMono, fontWeight: 600 }}>{count}</Box>
    </ListRow>)}
  </Panel>;
}
