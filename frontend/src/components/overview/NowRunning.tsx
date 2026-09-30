import { useEffect, useState } from 'react';
import { Box, Button, Card, LinearProgress, Skeleton, Stack, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
import StatusChip from '../StatusChip';
import { PanelLabel } from '../PageLayout';
import { fontMono } from '../../theme';
import { clockTime } from '../../utils/displayTime';
import type { RobotStatus } from '../../hooks/useRobotStatus';
import type { RunningJobDetail } from '../../types/scheduling';


export type RunTiming = { started: Date | null; elapsed: number | null; estimate: number | null; fraction: number | null; overBy: number | null };

/**
 * Elapsed time is measured; the estimate is what the user typed into the schedule, so a run
 * may legitimately take longer. Past the estimate there is no percentage to show: the bar
 * stops claiming progress and the text says by how much the estimate was exceeded.
 */
export function runTiming(launchedAt: string | null | undefined, estimateMinutes: number | null | undefined, now: number): RunTiming {
  const startedMs = launchedAt ? new Date(launchedAt).getTime() : NaN;
  const started = Number.isFinite(startedMs) ? new Date(startedMs) : null;
  const elapsed = started ? Math.max(0, Math.floor((now - startedMs) / 60000)) : null;
  const estimate = typeof estimateMinutes === 'number' && estimateMinutes > 0 ? estimateMinutes : null;
  if (elapsed === null || estimate === null) return { started, elapsed, estimate, fraction: null, overBy: null };
  return elapsed <= estimate
    ? { started, elapsed, estimate, fraction: elapsed / estimate, overBy: null }
    : { started, elapsed, estimate, fraction: null, overBy: elapsed - estimate };
}

function timingText(t: RunTiming) {
  const parts = [t.started ? `Started ${clockTime(t.started)}` : 'Start time unknown'];
  if (t.elapsed !== null && t.estimate !== null) {
    parts.push(t.overBy === null ? `${t.elapsed} min of about ${t.estimate} min` : `${t.elapsed} min · ${t.overBy} min past the ${t.estimate} min estimate`);
  } else if (t.elapsed !== null) parts.push(`${t.elapsed} min`);
  else if (t.estimate !== null) parts.push(`estimate ${t.estimate} min`);
  return parts.join(' · ');
}

function seconds(value: number) {
  const s = Math.max(0, Math.round(value));
  return s < 60 ? `${s} s` : `${Math.round(s / 60)} min`;
}

function LogActivity({ job, heldFor }: { job: RunningJobDetail; heldFor: number }) {
  const monitoring = job.monitoring;
  if (!monitoring) return null;
  const threshold = monitoring.threshold_minutes;
  const [dot, text] = monitoring.state === 'monitoring'
    ? ['success.main', `Log active ${seconds(monitoring.inactivity_seconds + heldFor)} ago · alert after ${threshold} min silent`]
    : monitoring.state === 'log_inactive' ? ['warning.main', `No log activity for ${seconds(monitoring.inactivity_seconds + heldFor)}`]
    : monitoring.state === 'waiting' ? ['text.disabled', 'Waiting for the run log']
    : monitoring.state === 'monitoring_unavailable' ? ['warning.main', monitoring.reason || 'Log monitoring unavailable']
    : ['text.disabled', 'Run finishing'];
  return <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
    <Box component="span" aria-hidden sx={{ width: 8, height: 8, borderRadius: 4, bgcolor: dot, flexShrink: 0 }} />{text}
  </Box>;
}

/** The scheduler's current run, with elapsed time against the user's estimate. */
export default function NowRunning({ status, error }: { status: RobotStatus | null; error: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 15000); return () => clearInterval(timer); }, []);
  const job = status?.running[0];
  const timing = job ? runTiming(job.monitoring?.launched_at, job.estimated_duration, now) : null;

  return <Card component="section" aria-label="Now running" variant="outlined" sx={{ p: { xs: 2, sm: 2.5 }, display: 'flex', flexDirection: 'column', gap: 1.75, minWidth: 0 }}>
    <Stack direction="row" alignItems="center" gap={1.25} flexWrap="wrap">
      <PanelLabel>Now running</PanelLabel>
      {status && (job ? <StatusChip tone="running" label="Running" />
        : <StatusChip tone="neutral" label={status.schedulerRunning ? 'Idle' : 'Scheduler stopped'} />)}
    </Stack>

    {!status && (error
      ? <Typography sx={{ color: 'text.secondary' }}>Robot status is unavailable. The banner above retries it.</Typography>
      : <Stack spacing={1} aria-label="Loading robot status"><Skeleton variant="text" width="45%" height={32} /><Skeleton variant="text" width="70%" /></Stack>)}

    {status && !job && <Box>
      <Typography sx={{ fontSize: { xs: 18, sm: 20 }, fontWeight: 600 }}>Nothing running</Typography>
      <Typography sx={{ fontSize: 14, color: 'text.secondary' }}>
        {status.schedulerRunning ? 'The scheduler starts the next run when it is due.' : 'The scheduler is stopped, so scheduled runs will not start.'}
        {status.queued > 0 && ` ${status.queued} waiting in the queue.`}
      </Typography>
    </Box>}

    {job && timing && <>
      <Box sx={{ minWidth: 0 }}>
        <Typography sx={{ fontSize: { xs: 18, sm: 22 }, fontWeight: 600, overflowWrap: 'anywhere' }}>{job.experiment_name}</Typography>
        {job.experiment_path && <Typography sx={{ fontFamily: fontMono, fontSize: 13, color: 'text.secondary', overflowWrap: 'anywhere' }}>{job.experiment_path}</Typography>}
      </Box>
      <Box>
        {timing.fraction !== null
          ? <LinearProgress variant="determinate" value={timing.fraction * 100} aria-label="Elapsed time against the estimate" sx={{ height: 8, borderRadius: 4 }} />
          : timing.overBy !== null && <LinearProgress variant="indeterminate" color="inherit" aria-label="Running past the estimate" sx={{ height: 8, borderRadius: 4, color: 'text.disabled' }} />}
        <Stack direction={{ xs: 'column', sm: 'row' }} columnGap={2} rowGap={0.5} justifyContent="space-between" sx={{ mt: 1, fontSize: 13, color: 'text.secondary' }}>
          <span>{timingText(timing)}</span>
          <LogActivity job={job} heldFor={(now - status!.receivedAt) / 1000} />
        </Stack>
      </Box>
    </>}

    {status && <Stack direction="row" gap={1} flexWrap="wrap">
      {job && <Button variant="outlined" size="small" component={Link} to="/logfile?section=hamilton">View run log</Button>}
      <Button variant="outlined" size="small" component={Link} to="/camera">Open camera</Button>
      {status.queued > 0 && job && <Typography sx={{ alignSelf: 'center', fontSize: 13, color: 'text.secondary' }}>{status.queued} waiting</Typography>}
    </Stack>}
  </Card>;
}
