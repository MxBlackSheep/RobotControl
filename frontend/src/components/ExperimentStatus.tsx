/**
 * Latest experiment from the Hamilton run database, refreshed every minute.
 */
import React, { memo, useState } from 'react';
import { Box, Button, Card, Skeleton, Stack, Typography } from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { experimentsAPI } from '../services/api';
import { useSerialPolling } from '../hooks/useSerialPolling';
import StatusChip from './StatusChip';
import { PanelLabel } from './PageLayout';
import { fontMono, StatusTone } from '../theme';

interface ExperimentData {
  run_guid: string;
  method_name: string;
  start_time: string | null;
  end_time: string | null;
  run_state: number;
}

type Latest = { experiment: ExperimentData | null; checkedAt: Date };

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
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? 'Invalid date'
    : date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
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

function Fact({ label, value }: { label: string; value: string }) {
  return <Box><Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{label}</Typography><Typography sx={{ fontSize: 15 }}>{value}</Typography></Box>;
}

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

  return <Card component="section" aria-label="Latest experiment" variant="outlined" sx={{ p: { xs: 2, sm: 2.5 }, display: 'flex', flexDirection: 'column', gap: 1.75 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, flexWrap: 'wrap' }}>
      <PanelLabel>Latest experiment</PanelLabel>
      {state && <StatusChip tone={state.tone} label={state.label} />}
      <Box sx={{ flex: 1 }} />
      <Button size="small" startIcon={<RefreshIcon />} onClick={() => { void polling.refresh(); }} disabled={polling.pending}>Refresh</Button>
    </Box>

    {!latest && !error && <Stack spacing={1} aria-label="Loading experiment">
      <Skeleton variant="text" width="50%" height={32} /><Skeleton variant="text" width="30%" /><Skeleton variant="text" width="70%" />
    </Stack>}

    {error && <Box role="alert" sx={{ p: 1.5, borderRadius: 1, border: 1, borderColor: theme => theme.palette.tone.attention.fg, bgcolor: theme => theme.palette.tone.attention.bg }}>
      <Typography sx={{ fontSize: 14, fontWeight: 600, color: theme => theme.palette.tone.attention.fg }}>
        {latest ? 'Could not refresh experiment data' : 'Experiment data is temporarily unavailable'}
      </Typography>
      <Typography sx={{ fontSize: 14 }}>{error}{latest && ` · Showing data from ${latest.checkedAt.toLocaleTimeString()}`}</Typography>
    </Box>}

    {latest && !experiment && <Typography sx={{ color: 'text.secondary' }}>No experiments found</Typography>}

    {experiment && <>
      <Box>
        <Typography sx={{ fontSize: { xs: 18, sm: 22 }, fontWeight: 600 }}>
          {experiment.method_name?.split('\\').pop()?.replace('.hsl', '') || 'Unknown Method'}
        </Typography>
        <Typography sx={{ fontFamily: fontMono, fontSize: 13, color: 'text.secondary' }}>ID: {experiment.run_guid?.substring(0, 8) || 'Unknown'}</Typography>
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, max-content))' }, columnGap: 5, rowGap: 1 }}>
        <Fact label="Started" value={formatTimestamp(experiment.start_time)} />
        {experiment.end_time && <Fact label="Ended" value={formatTimestamp(experiment.end_time)} />}
        <Fact label="Duration" value={calculateDuration(experiment.start_time, experiment.end_time)} />
      </Box>
    </>}

    {latest && !error && <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>Updated: {latest.checkedAt.toLocaleTimeString()}</Typography>}
  </Card>;
});

ExperimentStatus.displayName = 'ExperimentStatus';

export default ExperimentStatus;
