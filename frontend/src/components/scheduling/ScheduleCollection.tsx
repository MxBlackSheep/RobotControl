import { useMemo, useState } from 'react';
import { Alert, Box, Button, LinearProgress, List, ListItemButton, Stack, TextField, Typography } from '@mui/material';
import { Refresh } from '@mui/icons-material';
import { ScheduledExperiment } from '../../types/scheduling';
import StatusChip from '../StatusChip';
import { fontMono, StatusTone } from '../../theme';

export function scheduleState(schedule: ScheduledExperiment): { label: string; tone: StatusTone } {
  if (schedule.recovery_required) return { label: 'Recovery required', tone: 'attention' };
  if (schedule.archived) return { label: 'Archived', tone: 'neutral' };
  return schedule.is_active ? { label: 'Active', tone: 'completed' } : { label: 'Inactive', tone: 'neutral' };
}

export default function ScheduleCollection({ schedules, selected, onSelect, onRefresh, loading, error }: {
  schedules: ScheduledExperiment[]; selected: ScheduledExperiment | null;
  onSelect: (schedule: ScheduledExperiment) => void; onRefresh: () => void; loading: boolean; error: string | null;
}) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('next');
  const visible = useMemo(() => schedules.filter(schedule =>
    `${schedule.experiment_name} ${schedule.experiment_path}`.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => sort === 'name' ? a.experiment_name.localeCompare(b.experiment_name)
      : (a.next_run || '9999').localeCompare(b.next_run || '9999')), [schedules, query, sort]);
  return <Stack data-testid="schedule-collection" sx={{ minHeight: 0, height: '100%', bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}>
    <Stack spacing={1.25} sx={{ p: 1.5 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography component="h2" sx={{ fontSize: 15, fontWeight: 600 }}>Schedules ({visible.length})</Typography>
        <Button size="small" aria-label="Refresh schedules" startIcon={<Refresh />} onClick={onRefresh} disabled={loading}>Refresh</Button>
      </Stack>
      <Stack direction="row" gap={1}>
        <TextField size="small" label="Search schedules" value={query} onChange={event => setQuery(event.target.value)} sx={{ flex: 1, minWidth: 0 }} />
        <TextField select SelectProps={{ native: true }} label="Sort schedules" size="small" value={sort} onChange={event => setSort(event.target.value)} sx={{ width: 128 }}>
          <option value="next">Next run</option><option value="name">Name</option>
        </TextField>
      </Stack>
    </Stack>
    {loading && <LinearProgress aria-label="Loading schedules" />}
    {error && <Alert severity="error" sx={{ mx: 1.5, mb: 1 }}>{error}</Alert>}
    <List disablePadding sx={{ overflow: 'auto', flex: 1, minHeight: 0, borderTop: 1, borderColor: 'divider' }}>
      {visible.map(schedule => {
        const state = scheduleState(schedule);
        const current = selected?.schedule_id === schedule.schedule_id;
        return <ListItemButton key={schedule.schedule_id}
          aria-label={`Open ${schedule.experiment_name}`} aria-current={current ? 'true' : undefined}
          selected={current} onClick={() => onSelect(schedule)}
          sx={{ alignItems: 'flex-start', gap: 1.5, borderBottom: 1, borderColor: 'divider', py: 1.25, px: 1.5 }}>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography sx={{ fontSize: 14, fontWeight: 500, overflowWrap: 'anywhere' }}>{schedule.experiment_name}</Typography>
            <Typography sx={{ fontFamily: fontMono, fontSize: 12, color: 'text.secondary', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{schedule.experiment_path}</Typography>
            <Typography sx={{ fontSize: 13, color: 'text.secondary', mt: 0.5 }}>
              {schedule.next_run ? `Next ${new Date(schedule.next_run).toLocaleString()}` : 'No next run'} · {schedule.schedule_type}
            </Typography>
          </Box>
          <StatusChip tone={state.tone} label={state.label} />
        </ListItemButton>;
      })}
      {!visible.length && !loading && <Typography sx={{ p: 2, color: 'text.secondary' }}>No schedules found.</Typography>}
    </List>
  </Stack>;
}
