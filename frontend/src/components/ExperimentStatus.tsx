/**
 * Latest experiment from the Hamilton run database, refreshed every minute.
 */
import React, { memo, useState } from 'react';
import { Box, Button, Skeleton, Stack, Typography } from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { experimentsAPI } from '../services/api';
import { useSerialPolling } from '../hooks/useSerialPolling';
import StatusChip from './StatusChip';
import { ListRow, Panel } from './PageLayout';
import { clockTime, dayTime } from '../utils/displayTime';
import { fontMono, layout, StatusTone } from '../theme';

interface ExperimentData {
  run_guid: string;
  method_name: string;
  start_time: string | null;
  end_time: string | null;
  run_state: number;
}

type Latest = { experiment: ExperimentData | null; checkedAt: Date };

// Sized by the panel, not the window. The wide row is name (~200px), ID, three 160px facts and the chip.
const wideRow = '@container latest (min-width: 1000px)';
// Below this the "Updated" time would wrap the 40px header beside the label and Refresh.
const roomyHeader = '@container latest (min-width: 400px)';

// Hamilton run-state codes and their names.
export const getRunStateDisplay = (runState: string | number): { label: string; tone: StatusTone } => {
  const state = String(runState || 'UNKNOWN').toUpperCase();
  switch (state) {
    case 'RUNNING': case 'ACTIVE': case '1': return { label: 'Running', tone: 'running' };
    case 'COMPLETED': case 'FINISHED': case '128': case '0': return { label: 'Completed', tone: 'completed' };
    case 'FAILED': case 'ERROR': case '256': case '-1': return { label: 'Failed', tone: 'fault' };
    case 'PAUSED': case '2': case 'STOPPED': return { label: 'Paused', tone: 'neutral' };
    case 'ABORTED': case '64': return { label: 'Aborted', tone: 'attention' };
    default: return { label: state.replace(/_/g, ' '), tone: 'neutral' };
  }
};

const formatTimestamp = (timestamp: string | null): string => {
  if (!timestamp) return 'Unknown';
  return Number.isNaN(new Date(timestamp).getTime()) ? 'Invalid date' : dayTime(timestamp);
};

const calculateDuration = (startTime: string | null, endTime: string | null): string => {
  if (!startTime) return 'Unknown';
  const diffMs = (endTime ? new Date(endTime) : new Date()).getTime() - new Date(startTime).getTime();
  if (Number.isNaN(diffMs)) return 'Unknown';
  const hours = Math.floor(diffMs / 3600000);
  const minutes = Math.floor((diffMs % 3600000) / 60000);
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
};

const describeError = (err: any): string => {
  const status = err?.response?.status;
  if (status === 401 || status === 403) return 'Authentication required - please log in';
  if (status === 404) return 'Experiment service not available';
  if (err?.code === 'ECONNABORTED' || err?.code === 'ETIMEDOUT') return 'Database connection timeout - check database status';
  if (err?.code === 'ECONNREFUSED' || err?.code === 'ENOTFOUND') return 'Backend service unavailable';
  return 'Experiment data temporarily unavailable';
};

const ExperimentStatus: React.FC<{ refreshInterval?: number }> = memo(({ refreshInterval = 60 }) => {
  const [latest, setLatest] = useState<Latest | null>(null);
  const polling = useSerialPolling<Latest>({
    interval: refreshInterval * 1000,
    request: async () => {
      let response;
      try { response = await experimentsAPI.getLatest(); } catch (err) { throw new Error(describeError(err)); }
      if (!response.data?.success) throw new Error(response.data?.error || 'Failed to load experiment data');
      // A successful reply without data means no experiment has run yet.
      return { experiment: response.data.data || null, checkedAt: new Date() };
    },
    onSuccess: setLatest,
  });
  const error = polling.error;
  const experiment = latest?.experiment;
  const state = experiment ? getRunStateDisplay(experiment.run_state) : null;

  const methodName = experiment ? experiment.method_name?.split('\\').pop()?.replace('.hsl', '') || 'Unknown Method' : '';
  const facts: [string, string][] = experiment ? [
    ['Started', formatTimestamp(experiment.start_time)],
    ...(experiment.end_time ? [['Ended', formatTimestamp(experiment.end_time)] as [string, string]] : []),
    ['Duration', calculateDuration(experiment.start_time, experiment.end_time)],
  ] : [];

  return <Panel title="Latest experiment" inset={false} sx={{ containerType: 'inline-size', containerName: 'latest' }}
    headerExtra={latest && !error && <Typography variant="caption" color="text.secondary"
      sx={{ fontFamily: fontMono, whiteSpace: 'nowrap', display: 'none', [roomyHeader]: { display: 'inline' } }}>Updated {clockTime(latest.checkedAt)}</Typography>}
    actions={<Button size="small" startIcon={<RefreshIcon />} onClick={() => { void polling.refresh(); }} disabled={polling.pending}>Refresh</Button>}>
    {!latest && !error && <Stack aria-label="Loading experiment" sx={{ px: 2, justifyContent: 'center', height: layout.row }}><Skeleton variant="text" width="50%" /></Stack>}

    {error && <Box role="alert" sx={{ display: 'flex', alignItems: 'center', gap: 1, minHeight: layout.row, px: 2, bgcolor: 'attentionSurface.head', color: 'attentionSurface.text', fontSize: 13, borderBottom: 1, borderColor: 'surface.rowLine' }}>
      <Box component="strong">{latest ? 'Could not refresh experiment data' : 'Experiment data is temporarily unavailable'}</Box>
      <span>· {error}{latest && ` · Showing data from ${clockTime(latest.checkedAt)}`}</span>
    </Box>}

    {latest && !experiment && <ListRow columns="minmax(0, 1fr)"><Box component="span" sx={{ color: 'text.secondary' }}>No experiments found</Box></ListRow>}

    {/* One 40px row when the panel is wide; otherwise the details wrap onto lines below the name. */}
    {experiment && <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gridTemplateRows: `${layout.row}px auto`, columnGap: `${layout.gutter}px`,
      alignItems: 'center', px: `${layout.inset}px`, fontSize: 13, '& > *, & > * > *': { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
      [wideRow]: { gridTemplateColumns: 'minmax(0, 1fr) auto auto', gridTemplateRows: `${layout.row}px` } }}>
      <Box component="span" sx={{ fontWeight: 600 }}>{methodName}</Box>
      <Box sx={{ gridColumn: '1 / -1', display: 'flex', flexWrap: 'wrap', columnGap: `${layout.inset}px`, rowGap: 0.5, lineHeight: '20px', pb: 1.5,
        [wideRow]: { gridColumn: 2, gridRow: 1, display: 'grid', gridTemplateColumns: `120px repeat(${facts.length}, 160px)`, columnGap: `${layout.gutter}px`, pb: 0 } }}>
        <Box component="span" sx={{ fontFamily: fontMono, fontSize: 12, color: 'text.secondary' }}>ID: {experiment.run_guid?.substring(0, 8) || 'Unknown'}</Box>
        {facts.map(([label, value]) => <Box key={label} component="span">
          <Box component="span" sx={{ color: 'text.secondary' }}>{label} </Box>{value}</Box>)}
      </Box>
      {state && <Box sx={{ gridColumn: 2, gridRow: 1, [wideRow]: { gridColumn: 3 } }}><StatusChip tone={state.tone} label={state.label} /></Box>}
    </Box>}
  </Panel>;
});

ExperimentStatus.displayName = 'ExperimentStatus';

export default ExperimentStatus;
