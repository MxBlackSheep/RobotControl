import { useMemo, useState } from 'react';
import { Alert, Box, Button, LinearProgress, List, ListItemButton, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { Refresh } from '@mui/icons-material';
import { ScheduledExperiment } from '../../types/scheduling';
import StatusChip from '../StatusChip';
import { Panel } from '../PageLayout';
import { columnHeading, fontMono, layout, StatusTone } from '../../theme';
import { dayTime } from '../../utils/displayTime';

export function scheduleState(schedule: ScheduledExperiment): { label: string; tone: StatusTone } {
  if (schedule.recovery_required) return { label: 'Recovery required', tone: 'attention' };
  if (schedule.archived) return { label: 'Archived', tone: 'neutral' };
  return schedule.is_active ? { label: 'Active', tone: 'completed' } : { label: 'Inactive', tone: 'neutral' };
}

export const repeatLabel = (schedule: ScheduledExperiment) => schedule.schedule_type === 'interval' && schedule.interval_hours
  ? `Every ${schedule.interval_hours} h` : schedule.schedule_type.charAt(0).toUpperCase() + schedule.schedule_type.slice(1);

type Filter = 'all' | 'active' | 'inactive' | 'recovery';
const filters: { value: Filter; label: string; match: (schedule: ScheduledExperiment) => boolean }[] = [
  { value: 'all', label: 'All', match: () => true },
  { value: 'active', label: 'Active', match: schedule => schedule.is_active && !schedule.recovery_required },
  { value: 'inactive', label: 'Inactive', match: schedule => !schedule.is_active && !schedule.recovery_required },
  { value: 'recovery', label: 'Recovery', match: schedule => schedule.recovery_required },
];

// Wide enough for the table columns; narrower panels stack each row.
const table = '@container schedules (min-width: 640px)';
// Date columns hold the longest dayTime ("13 Jan 2027 09:00", ~122px in the mono font) on one line.
const columns = 'minmax(0, 2.2fr) minmax(90px, 0.8fr) minmax(128px, 1fr) minmax(128px, 1fr) 160px';

export default function ScheduleCollection({ schedules, selected, onSelect, onRefresh, loading, error }: {
  schedules: ScheduledExperiment[]; selected: ScheduledExperiment | null;
  onSelect: (schedule: ScheduledExperiment) => void; onRefresh: () => void; loading: boolean; error: string | null;
}) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('next');
  const [filter, setFilter] = useState<Filter>('all');
  const searched = useMemo(() => schedules.filter(schedule =>
    `${schedule.experiment_name} ${schedule.experiment_path}`.toLowerCase().includes(query.toLowerCase())), [schedules, query]);
  const visible = useMemo(() => searched.filter(filters.find(item => item.value === filter)!.match)
    .sort((a, b) => sort === 'name' ? a.experiment_name.localeCompare(b.experiment_name)
      : (a.next_run || '9999').localeCompare(b.next_run || '9999')), [searched, filter, sort]);
  const muted = { color: 'text.secondary', fontSize: 13 };
  // Fills the workspace column: header band, toolbar, column headings, then a scrolling table.
  return <Box data-testid="schedule-collection" sx={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', containerType: 'inline-size', containerName: 'schedules' }}>
    <Panel title="Schedules" fill inset={false} sx={{ flex: 1 }} bodySx={{ display: 'flex', flexDirection: 'column' }}
      actions={<Button size="small" startIcon={<Refresh />} onClick={onRefresh} disabled={loading}>Refresh schedules</Button>}>
      <Stack direction="row" alignItems="center" flexWrap="wrap" gap={1} sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: 'surface.rowLine' }}>
        <TextField size="small" label="Search schedules" value={query} onChange={event => setQuery(event.target.value)} sx={{ flex: '1 1 180px', minWidth: 0, maxWidth: 320 }} />
        <ToggleButtonGroup size="small" exclusive value={filter} onChange={(_, value) => value && setFilter(value)} aria-label="Filter by status" sx={{ flexWrap: 'wrap' }}>
          {filters.map(item => <ToggleButton key={item.value} value={item.value} sx={{ gap: 0.75 }}>
            {item.label}<Box component="span" sx={{ color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}>{searched.filter(item.match).length}</Box>
          </ToggleButton>)}
        </ToggleButtonGroup>
        <TextField select SelectProps={{ native: true }} label="Sort schedules" size="small" value={sort} onChange={event => setSort(event.target.value)} sx={{ width: 128 }}>
          <option value="next">Next run</option><option value="name">Name</option>
        </TextField>
      </Stack>
      {loading && <LinearProgress aria-label="Loading schedules" />}
      {error && <Alert severity="error" sx={{ m: 2 }}>{error}</Alert>}
      <Box aria-hidden sx={{ display: 'none', [table]: { display: 'grid' }, gridTemplateColumns: columns, columnGap: 2, alignItems: 'center', height: layout.row, flexShrink: 0, px: 2,
        borderBottom: 1, borderColor: 'surface.rowLine', ...columnHeading }}>
        <span>Experiment</span><span>Repeats</span><span>Next run</span><span>Last run</span><span>Status</span>
      </Box>
      <List aria-label={`Schedules (${visible.length})`} disablePadding sx={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
        {visible.map(schedule => {
          const state = scheduleState(schedule);
          const current = selected?.schedule_id === schedule.schedule_id;
          return <ListItemButton key={schedule.schedule_id}
            aria-label={`Open ${schedule.experiment_name}`} aria-current={current ? 'true' : undefined}
            selected={current} onClick={() => onSelect(schedule)}
            sx={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', [table]: { gridTemplateColumns: columns, height: 56 },
              columnGap: 2, rowGap: 0.25, alignItems: 'center', minHeight: 56, borderBottom: 1, borderColor: 'surface.rowLine', py: 1, px: 2 }}>
            <Box sx={{ minWidth: 0 }}>
              <Typography sx={{ fontSize: 13, lineHeight: '20px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{schedule.experiment_name}</Typography>
              <Typography sx={{ fontFamily: fontMono, fontSize: 12, lineHeight: '16px', color: 'text.secondary', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{schedule.experiment_path}</Typography>
              <Typography sx={{ ...muted, mt: 0.5, [table]: { display: 'none' } }}>
                {schedule.next_run ? `Next ${dayTime(schedule.next_run)}` : 'No next run'} · {repeatLabel(schedule)}
              </Typography>
            </Box>
            <Typography sx={{ ...muted, display: 'none', [table]: { display: 'block' } }}>{repeatLabel(schedule)}</Typography>
            <Typography sx={{ ...muted, display: 'none', [table]: { display: 'block' }, fontFamily: fontMono, fontSize: 12, color: 'text.primary' }}>{schedule.next_run ? dayTime(schedule.next_run) : '—'}</Typography>
            <Typography sx={{ ...muted, display: 'none', [table]: { display: 'block' }, fontFamily: fontMono, fontSize: 12 }}>{schedule.last_run ? dayTime(schedule.last_run) : '—'}</Typography>
            <Box sx={{ gridRow: { xs: 1 }, gridColumn: { xs: 2 }, [table]: { gridRow: 'auto', gridColumn: 'auto' } }}><StatusChip tone={state.tone} label={state.label} /></Box>
          </ListItemButton>;
        })}
        {!visible.length && !loading && <Typography variant="body2" sx={{ p: 2, color: 'text.secondary' }}>No schedules found.</Typography>}
      </List>
    </Panel>
  </Box>;
}
