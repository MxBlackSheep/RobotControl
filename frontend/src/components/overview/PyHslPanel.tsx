import { Stack, Typography } from '@mui/material';
import StatusChip from '../StatusChip';
import { DetailTitle, Panel } from '../PageLayout';
import { fontMono } from '../../theme';
import type { PyHslStatus } from '../../hooks/usePyHslStatus';

const label = (text: string) => text.charAt(0).toUpperCase() + text.slice(1).replace(/_/g, ' ');

/** Shown only while Run Control has something to report: an active run, a review or an unknown state. */
export default function PyHslPanel({ status, span }: { status: PyHslStatus | null; span?: number }) {
  if (!status) return null;
  const { run, reviews, state } = status;
  if (!run && !reviews.blocked && state !== 'unknown') return null;
  return <Panel title="PyHSL" span={span} tone={reviews.blocked ? 'attention' : undefined}
    headerExtra={run ? <StatusChip tone="running" label={label(run.status)} />
      : reviews.blocked ? <StatusChip tone="attention" label="Review needed" />
      : <StatusChip tone="neutral" label="Unknown" />}
    bodySx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
    {run && <>
      <DetailTitle component="p">{run.protocol}</DetailTitle>
      <Stack direction="row" columnGap={2} flexWrap="wrap" sx={{ fontFamily: fontMono, fontSize: 12, color: 'text.secondary' }}>
        {run.mode && <span>{label(run.mode)}</span>}
        {typeof run.completed_count === 'number' && <span>{run.completed_count} done</span>}
        {run.origin === 'machine' && <span>Scheduled</span>}
      </Stack>
      {run.error && <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>{run.error}</Typography>}
    </>}
    {reviews.blocked && <Typography variant="body2">Record the Run review in Run Control on the robot PC.</Typography>}
    {!run && !reviews.blocked && <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>{status.reason}</Typography>}
  </Panel>;
}
