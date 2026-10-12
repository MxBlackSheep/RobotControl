import React, { useState } from 'react';
import { Box, Button, Link as MuiLink, Stack, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
import { DetailTitle, PageContent, PageHeader, Panel } from '../components/PageLayout';
import StatusChip from '../components/StatusChip';
import { isLocalUser } from '../components/navigation';
import { useAuth } from '../context/AuthContext';
import { robotAttention, useRobotStatusContext } from '../hooks/useRobotStatus';
import { useSerialPolling } from '../hooks/useSerialPolling';
import { logFileApi } from '../services/logFileApi';
import type { PendingRecovery } from '../types/scheduling';
import { fontMono, layout } from '../theme';
import { clockTime, dayTime } from '../utils/displayTime';

const TRACE_REFRESH_MS = 30000;
const TRACE_LINES = 20;
const TRACE_BYTES = 16384;
const mono = { fontFamily: fontMono, fontSize: 12, color: 'text.secondary' } as const;
const attentionButton = { bgcolor: 'attentionSurface.action', color: 'attentionSurface.actionText', '&:hover': { bgcolor: 'attentionSurface.action', filter: 'brightness(0.94)' } } as const;

// The pseudo-element gives the text link a 44px-high touch target without growing the 40px band.
const headerLink = (to: string, text: string) => <MuiLink component={Link} to={to} underline="hover"
  sx={{ fontSize: 13, position: 'relative', '&::after': { content: '""', position: 'absolute', inset: '-12px -8px' } }}>{text}</MuiLink>;

/** A read failed: keep what was shown and offer a retry, without blanking the page. */
function ReadProblem({ error, stale, onRetry, pending }: { error: string; stale: boolean; onRetry: () => void; pending: boolean }) {
  return <Stack direction="row" alignItems="center" gap={1} role="alert" sx={{ minHeight: layout.row, px: `${layout.inset}px`, fontSize: 13, color: 'attentionSurface.text', borderBottom: 1, borderColor: 'surface.rowLine' }}>
    <span>{stale ? 'Could not refresh. Showing earlier data.' : error}</span>
    <Button size="small" onClick={onRetry} disabled={pending}>Retry</Button>
  </Stack>;
}

function ago(date: Date) {
  const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  return hours < 48 ? `${hours} h ago` : `${Math.floor(hours / 24)} days ago`;
}

// The backend records a username, 'unknown' when the session had none, or 'scheduler' for its own stops.
function markedBy(value?: string | null) {
  const actor = value?.trim();
  if (!actor || actor.toLowerCase() === 'unknown') return null;
  return actor === 'scheduler' ? 'Marked by the scheduler' : `Marked by ${actor}`;
}

function HeldRun({ hold }: { hold: PendingRecovery }) {
  const parsed = hold.triggered_at ? new Date(hold.triggered_at) : null;
  const since = parsed && !Number.isNaN(parsed.getTime()) ? parsed : null;
  const by = markedBy(hold.triggered_by);
  return <Panel title="Held" label="Held run" tone="attention" bodySx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
    <DetailTitle>{hold.experiment_name || 'A scheduled run'}</DetailTitle>
    {since && <Typography variant="body2" color="text.secondary">Held since {clockTime(since)} · {ago(since)}</Typography>}
    {hold.note && <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>{hold.note}</Typography>}
    {by && <Typography variant="body2" color="text.secondary">{by}</Typography>}
  </Panel>;
}

type Trace = { name: string; modified?: string; lines: string[] } | 'none';

/** Mounted only while a run is held, so the trace is read only then. */
function NewestTrace() {
  const [trace, setTrace] = useState<Trace | null>(null);
  const polling = useSerialPolling<Trace>({
    interval: TRACE_REFRESH_MS,
    request: async signal => {
      const listing = await logFileApi.browse('hamilton_logfiles', '', { file_type: 'traces', sort_by: 'modified', sort_direction: 'desc', limit: 1 }, signal);
      const item = listing.items?.find(entry => !entry.is_directory);
      if (!item) return 'none';
      // `path` is absolute; the browser joins the listed folder (here the source root) and the name.
      const preview = await logFileApi.preview('hamilton_logfiles', item.name, 'tail', TRACE_BYTES, signal);
      if (preview.content === null) throw new Error('No readable text');
      const lines = preview.content.split(/\r?\n/).filter(line => line.trim()).slice(-TRACE_LINES);
      return { name: item.name, modified: item.modified_date ?? preview.modified_date, lines };
    },
    onSuccess: setTrace,
  });
  return <Panel title="Newest Hamilton trace" inset={false} actions={headerLink('/logfile?section=hamilton', 'Run logs')}>
    {polling.error && <ReadProblem error="Could not read the newest trace." stale={trace !== null} onRetry={() => void polling.refresh()} pending={polling.pending} />}
    {!trace && !polling.error && <Typography variant="body2" color="text.secondary" sx={{ p: `${layout.inset}px` }}>Reading the newest trace…</Typography>}
    {trace === 'none' && <Typography variant="body2" color="text.secondary" sx={{ p: `${layout.inset}px` }}>No Hamilton trace files found.</Typography>}
    {trace && trace !== 'none' && <>
      <Box sx={{ px: `${layout.inset}px`, pt: 1.5, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <Box sx={{ ...mono, overflowWrap: 'anywhere' }}>{trace.name}{trace.modified ? ` · ${dayTime(trace.modified)}` : ''}</Box>
        <Typography variant="body2" color="text.secondary">New runs are held, so this is usually the stopped run.</Typography>
      </Box>
      <Box component="pre" sx={{ fontFamily: fontMono, fontSize: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', m: 0, p: 2 }}>
        {trace.lines.join('\n')}
      </Box>
    </>}
  </Panel>;
}

export default function HeldRunPage() {
  const { status, error } = useRobotStatusContext();
  const { user } = useAuth();
  const local = isLocalUser(user);
  const recovery = status?.recovery;
  const attention = robotAttention(status);
  // An older reply carries one active recovery and no list.
  const holds: PendingRecovery[] = recovery?.pending_recoveries?.length ? recovery.pending_recoveries
    : recovery?.active ? [{ schedule_id: recovery.schedule_id ?? null, experiment_name: recovery.experiment_name, note: recovery.note,
        triggered_at: recovery.triggered_at, triggered_by: recovery.triggered_by, schedule_missing: !!recovery.schedule_missing, archived: false }] : [];

  let body: React.ReactNode;
  if (!recovery) {
    // Unknown is never "nothing held".
    body = <Typography variant="body2" color={error ? 'attentionSurface.text' : 'text.secondary'} role={error ? 'alert' : undefined}>
      {error ? 'Could not read the scheduler state.' : 'Reading the scheduler state…'}
    </Typography>;
  } else if (!attention) {
    body = <Panel title="Nothing is held" bodySx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Typography variant="body2">No run is waiting for recovery.</Typography>
      <Button variant="outlined" component={Link} to="/" sx={{ alignSelf: 'flex-start' }}>Back to Now</Button>
    </Panel>;
  } else {
    const remoteNote = attention.kind === 'recovery' ? 'Acknowledge and resume on the workstation, after checking the deck.'
      : attention.kind === 'resume' ? 'Resume queued jobs on the workstation.' : null;
    body = <>
      {attention.kind === 'recovery' ? holds.map((hold, index) => <HeldRun key={hold.schedule_id ?? index} hold={hold} />)
        : <Panel title={attention.kind === 'storage' ? 'Scheduler storage' : 'Queued jobs are paused'} tone="attention"
            actions={<StatusChip tone="attention" label={attention.kind === 'storage' ? 'Storage unavailable' : 'Waiting for Resume'} />}>
          <Typography variant="body2" color="text.secondary">
            {attention.kind === 'storage'
              ? `No runs are dispatched until scheduler storage is healthy again.${recovery.storage_error ? ` ${recovery.storage_error}` : ''}`
              : 'Recovery is acknowledged. Queued jobs stay paused until someone chooses Resume queued jobs.'}
          </Typography>
        </Panel>}
      <Stack direction="row" alignItems="center" gap={1.5} flexWrap="wrap">
        <Button variant="outlined" component={Link} to="/camera">Live camera</Button>
        {local
          ? <Button variant="contained" component={Link} to="/scheduling?section=recovery" sx={attentionButton}>Open recovery</Button>
          : remoteNote && <Typography variant="body2" color="text.secondary">{remoteNote}</Typography>}
      </Stack>
      {attention.kind === 'recovery' && <NewestTrace />}
    </>;
  }

  return <PageContent reading>
    <PageHeader title="What happened" />
    <Stack gap={`${layout.gutter}px`} sx={{ minWidth: 0 }}>{body}</Stack>
  </PageContent>;
}
