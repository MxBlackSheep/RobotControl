import React, { useMemo, useState } from 'react';
import { Alert, Box, Button, Chip, LinearProgress, List, ListItemButton, Stack, TextField, Typography } from '@mui/material';
import { Refresh } from '@mui/icons-material';
import { ScheduledExperiment } from '../../types/scheduling';

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
  return <Stack data-testid="schedule-collection" spacing={1} sx={{ minHeight: 0, height: '100%' }}>
    <Stack direction="row" alignItems="center" justifyContent="space-between">
      <Typography variant="subtitle1">Schedules ({visible.length})</Typography>
      <Button aria-label="Refresh schedules" startIcon={<Refresh />} onClick={onRefresh} disabled={loading}>Refresh</Button>
    </Stack>
    <TextField size="small" label="Search schedules" value={query} onChange={event => setQuery(event.target.value)} />
    <TextField select SelectProps={{ native: true }} label="Sort schedules" size="small" value={sort} onChange={event => setSort(event.target.value)}>
      <option value="next">Next run</option><option value="name">Name</option>
    </TextField>
    {loading && <LinearProgress aria-label="Loading schedules" />}
    {error && <Alert severity="error">{error}</Alert>}
    <List disablePadding sx={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
      {visible.map(schedule => <ListItemButton key={schedule.schedule_id}
        aria-label={`Open ${schedule.experiment_name}`} aria-current={selected?.schedule_id === schedule.schedule_id ? 'true' : undefined}
        selected={selected?.schedule_id === schedule.schedule_id} onClick={() => onSelect(schedule)}
        sx={{ alignItems: 'flex-start', borderBottom: 1, borderColor: 'divider', py: 1.5 }}>
        <Box sx={{ minWidth: 0, width: '100%' }}>
          <Typography variant="body1" fontWeight={600} sx={{ overflowWrap: 'anywhere' }}>{schedule.experiment_name}</Typography>
          <Stack direction="row" gap={.5} flexWrap="wrap" sx={{ my: .5 }}>
            <Chip size="small" label={schedule.recovery_required ? 'Recovery required' : schedule.archived ? 'Archived' : schedule.is_active ? 'Active' : 'Inactive'}
              color={schedule.recovery_required ? 'error' : schedule.is_active ? 'success' : 'default'} />
            <Typography variant="body2" color="text.secondary">{schedule.schedule_type}</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary">{schedule.next_run ? `Next ${new Date(schedule.next_run).toLocaleString()}` : 'No next run'}</Typography>
        </Box>
      </ListItemButton>)}
      {!visible.length && !loading && <Typography sx={{ p: 2 }}>No schedules found.</Typography>}
    </List>
  </Stack>;
}
