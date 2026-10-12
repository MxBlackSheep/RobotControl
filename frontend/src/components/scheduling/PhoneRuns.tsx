import React, { useId, useState } from 'react';
import { Box, Button, ButtonBase, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import StatusChip from '../StatusChip';
import { ListRow, PageContent, PageHeader, Panel } from '../PageLayout';
import { useAuth } from '../../context/AuthContext';
import { useModuleSection } from '../navigation';
import { schedulingService, schedulingAPI } from '../../services/schedulingApi';
import { useSerialPolling } from '../../hooks/useSerialPolling';
import { useRobotStatusContext } from '../../hooks/useRobotStatus';
import type { ScheduledExperiment } from '../../types/scheduling';
import { fontMono, layout } from '../../theme';
import { clockTime, dayTime } from '../../utils/displayTime';
import { repeatLabel } from './ScheduleCollection';
import { executionTone } from './executionStatus';

/*
 * The phone Runs tab: a read-only monitor of what will run and what has run. Editing stays on the
 * workstation, because the server refuses schedule edits through the tunnel.
 */

const REFRESH_MS = 60000;
const AGENDA = 0;
const HISTORY = 3;
const DAY_MS = 86400000;
const mono = { fontFamily: fontMono, fontSize: 13, color: 'text.secondary' } as const;
const rowSx = { height: 48, fontSize: 15 } as const;
const listBox = { bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: `${layout.radius}px`, overflow: 'clip' } as const;

const dayStart = (date: Date) => new Date(date).setHours(0, 0, 0, 0);
const validTime = (value?: string | null) => (value && !Number.isNaN(new Date(value).getTime()) ? new Date(value).getTime() : null);
const methodName = (path: string) => (path.split(/[\\/]/).pop() ?? path).replace(/\.[^.]+$/, '');

/** A read failed: keep what was shown and offer a retry (the Overview panels' pattern). */
function ReadProblem({ error, stale, onRetry, pending }: { error: string; stale: boolean; onRetry: () => void; pending: boolean }) {
  return <Stack direction="row" alignItems="center" gap={1} role="alert" sx={{ minHeight: layout.row, px: `${layout.inset}px`, fontSize: 13, color: 'attentionSurface.text', borderBottom: 1, borderColor: 'surface.rowLine' }}>
    <span>{stale ? 'Could not refresh. Showing earlier data.' : error}</span>
    <Button size="small" onClick={onRetry} disabled={pending} sx={{ minHeight: 44 }}>Retry</Button>
  </Stack>;
}

function EmptyRow({ children }: { children: React.ReactNode }) {
  return <Typography variant="body2" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', minHeight: 48, px: `${layout.inset}px`, borderBottom: 1, borderColor: 'surface.rowLine' }}>{children}</Typography>;
}

/** A list row; with `details` it is a button that opens them inline below it. */
function RunRow({ id, columns, open, onToggle, details, children }: {
  id: string; columns: string; open: boolean; onToggle: () => void; details?: React.ReactNode; children: React.ReactNode;
}) {
  const baseId = useId();
  if (!details) return <ListRow columns={columns} sx={rowSx}>{children}</ListRow>;
  const detailId = `${baseId}-${id}`;
  return <>
    <ListRow component={ButtonBase} columns={columns} aria-expanded={open} aria-controls={detailId} onClick={onToggle}
      sx={{ ...rowSx, width: '100%', textAlign: 'left', font: 'inherit', fontSize: 15, color: 'text.primary', ...(open && { borderBottom: 0, bgcolor: 'action.selected' }) }}>
      {children}
    </ListRow>
    <Box id={detailId} hidden={!open} sx={{ px: `${layout.inset}px`, pb: 1.5, pt: 0.5, fontSize: 14, borderBottom: 1, borderColor: 'surface.rowLine', bgcolor: 'action.selected' }}>
      {open && details}
    </Box>
  </>;
}

function Facts({ items, note }: { items: [string, React.ReactNode][]; note?: string }) {
  return <>
    <Box component="dl" sx={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr)', columnGap: 2, rowGap: 0.5, m: 0 }}>
      {items.map(([label, value]) => <React.Fragment key={label}>
        <Box component="dt" sx={{ color: 'text.secondary' }}>{label}</Box>
        <Box component="dd" sx={{ m: 0, overflowWrap: 'anywhere' }}>{value}</Box>
      </React.Fragment>)}
    </Box>
    {note && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{note}</Typography>}
  </>;
}

const name = (text: string) => <Box component="span" sx={{ fontWeight: 500 }}>{text}</Box>;

function Agenda() {
  const [schedules, setSchedules] = useState<ScheduledExperiment[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const { status } = useRobotStatusContext();
  const polling = useSerialPolling<ScheduledExperiment[]>({
    interval: REFRESH_MS,
    request: async () => {
      const result = await schedulingService.getAllSchedules(false, false);
      if (result.error) throw new Error(result.error);
      return result.schedules;
    },
    onSuccess: setSchedules,
  });
  const running = status?.running[0];
  const runningSchedule = running && schedules?.find(schedule => schedule.schedule_id === running.schedule_id);
  const today = dayStart(new Date());
  // Inactive schedules will not run; a held one stays listed so a hold is never hidden.
  const candidates = (schedules ?? []).filter(schedule => !schedule.archived && (schedule.is_active || schedule.recovery_required)
    && schedule.schedule_id !== running?.schedule_id);
  const byTime = (a: ScheduledExperiment, b: ScheduledExperiment) => (validTime(a.next_run) ?? -Infinity) - (validTime(b.next_run) ?? -Infinity);
  const dayOf = (schedule: ScheduledExperiment) => { const time = validTime(schedule.next_run); return time === null ? null : dayStart(new Date(time)); };
  const todayRuns = candidates.filter(schedule => {
    const day = dayOf(schedule);
    return schedule.recovery_required ? day === null || day <= today : day === today;
  }).sort(byTime);
  const tomorrowRuns = candidates.filter(schedule => !todayRuns.includes(schedule) && dayOf(schedule) === today + DAY_MS).sort(byTime);
  const later = candidates.filter(schedule => (dayOf(schedule) ?? -Infinity) > today + DAY_MS).sort(byTime)[0];
  const toggle = (id: string) => setOpen(current => (current === id ? null : id));

  const details = (schedule: ScheduledExperiment) => {
    const items: [string, React.ReactNode][] = [['Repeats', repeatLabel(schedule)], ['Method', methodName(schedule.experiment_path)]];
    if (schedule.estimated_duration > 0) items.push(['About', `${schedule.estimated_duration} min`]);
    if (schedule.last_run) items.push(['Last run', dayTime(schedule.last_run)]);
    if (schedule.recovery_required && schedule.recovery_note) items.push(['Held', schedule.recovery_note]);
    return <Facts items={items} note="Edit on the workstation." />;
  };
  const row = (schedule: ScheduledExperiment) => {
    const time = validTime(schedule.next_run);
    return <RunRow key={schedule.schedule_id} id={schedule.schedule_id} columns="52px minmax(0, 1fr) auto" open={open === schedule.schedule_id}
      onToggle={() => toggle(schedule.schedule_id)} details={details(schedule)}>
      <Box component="span" sx={mono}>{time === null ? '—' : clockTime(new Date(time))}</Box>
      {name(schedule.experiment_name)}
      <span>{schedule.recovery_required && <StatusChip tone="attention" label="Held" />}</span>
    </RunRow>;
  };

  if (!schedules && !polling.error) return null;
  const nothing = !running && !todayRuns.length && !tomorrowRuns.length;
  return <Stack gap={`${layout.gutter}px`}>
    <Panel title="Today" inset={false}>
      {polling.error && <ReadProblem error="Could not load schedules." stale={!!schedules} onRetry={() => void polling.refresh()} pending={polling.pending} />}
      {running && (runningSchedule
        ? <RunRow id={runningSchedule.schedule_id} columns="auto minmax(0, 1fr)" open={open === runningSchedule.schedule_id}
            onToggle={() => toggle(runningSchedule.schedule_id)} details={details(runningSchedule)}>
            <StatusChip tone="running" label="Running" />{name(runningSchedule.experiment_name)}
          </RunRow>
        : <RunRow id="running" columns="auto minmax(0, 1fr)" open={false} onToggle={() => {}}>
            <StatusChip tone="running" label="Running" />{name(running.experiment_name)}
          </RunRow>)}
      {todayRuns.map(row)}
      {schedules && nothing && <EmptyRow>Nothing scheduled today or tomorrow.</EmptyRow>}
      {schedules && nothing && later && <EmptyRow>Next: {later.experiment_name}, {dayTime(later.next_run!)}</EmptyRow>}
    </Panel>
    {tomorrowRuns.length > 0 && <Panel title="Tomorrow" inset={false}>{tomorrowRuns.map(row)}</Panel>}
  </Stack>;
}

type Run = { id: string; name: string; started?: string | null; minutes: number | null; status: string; error: string | null };

function History() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const polling = useSerialPolling<Run[]>({
    interval: REFRESH_MS,
    request: async () => {
      const { data } = await schedulingAPI.getExecutionHistory(undefined, 50);
      if (!data?.success || !Array.isArray(data.data)) throw new Error(data?.message || 'Could not load run history');
      return data.data.map((record: Record<string, any>) => ({
        id: String(record.execution_id),
        name: record.experiment_name_snapshot || record.experiment_name || 'Archived schedule',
        started: record.start_time,
        minutes: typeof record.duration_minutes === 'number' ? record.duration_minutes
          : typeof record.calculated_duration_minutes === 'number' ? Math.round(record.calculated_duration_minutes) : null,
        status: String(record.status ?? ''),
        error: record.error_message ? String(record.error_message) : null,
      }));
    },
    onSuccess: setRuns,
  });
  const days = new Map<number, { label: string; runs: Run[] }>();
  [...(runs ?? [])].sort((a, b) => (validTime(b.started) ?? -Infinity) - (validTime(a.started) ?? -Infinity)).forEach(run => {
    const time = validTime(run.started);
    const key = time === null ? -Infinity : dayStart(new Date(time));
    const label = time === null ? 'Date unknown' : dayTime(run.started!).split(' ').slice(0, -1).join(' ');
    if (!days.has(key)) days.set(key, { label, runs: [] });
    days.get(key)!.runs.push(run);
  });

  return <Stack gap={`${layout.gutter}px`}>
    {(polling.error || (runs && !runs.length)) && <Box sx={listBox}>
      {polling.error && <ReadProblem error="Could not load run history." stale={!!runs} onRetry={() => void polling.refresh()} pending={polling.pending} />}
      {runs && !runs.length && <EmptyRow>No runs yet.</EmptyRow>}
    </Box>}
    {[...days.values()].map(day => <Panel key={day.label} title={day.label} inset={false}>
      {day.runs.map(run => {
        const [label, tone] = executionTone(run.status);
        const time = validTime(run.started);
        return <RunRow key={run.id} id={run.id} columns="52px minmax(0, 1fr) auto" open={open === run.id}
          onToggle={() => setOpen(current => (current === run.id ? null : run.id))}
          details={run.error && <Typography variant="body2" sx={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{run.error}</Typography>}>
          <Box component="span" sx={mono}>{time === null ? '—' : clockTime(new Date(time))}</Box>
          {name(run.name)}
          {/* Only problems get colour: a completed run shows its length instead of a chip. */}
          {tone === 'completed'
            ? <Box component="span" sx={{ ...mono, textAlign: 'right' }}>{run.minutes !== null ? `${run.minutes} min` : '—'}</Box>
            : <span><StatusChip tone={tone} label={label} /></span>}
        </RunRow>;
      })}
    </Panel>)}
  </Stack>;
}

export default function PhoneRuns() {
  const { user } = useAuth();
  const [section, setSection] = useModuleSection('/scheduling', user);
  const view = section === HISTORY ? HISTORY : AGENDA;
  return <PageContent>
    <PageHeader title="Runs" sectionMenu={false} />
    <ToggleButtonGroup exclusive fullWidth size="small" aria-label="Runs view" value={view}
      onChange={(_, value: number | null) => { if (value !== null) setSection(value); }} sx={{ mb: `${layout.gutter}px`, '& .MuiToggleButton-root': { minHeight: 44 } }}>
      <ToggleButton value={AGENDA}>Agenda</ToggleButton>
      <ToggleButton value={HISTORY}>History</ToggleButton>
    </ToggleButtonGroup>
    {/* Only the shown view is mounted, so only it polls. */}
    {view === HISTORY ? <History /> : <Agenda />}
  </PageContent>;
}
