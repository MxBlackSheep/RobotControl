import { useCallback, useEffect, useRef, useState } from 'react';
import { Box, Button, Card, CardContent, CircularProgress, FormControl, InputLabel, MenuItem, Select, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import StatusChip from '../StatusChip';
import StatusDialog from '../StatusDialog';
import { schedulingService } from '../../services/schedulingApi';
import type { NotificationLogEntry } from '../../types/scheduling';
import type { StatusTone } from '../../theme';
import { dayTime } from '../../utils/displayTime';

type LogStatus = 'all' | 'sent' | 'pending' | 'error' | 'partial' | 'unknown' | 'cancelled';

const statusTone = (status?: string): StatusTone => {
  switch ((status || '').toLowerCase()) {
    case 'sent': return 'completed';
    case 'partial': case 'unknown': case 'pending': return 'attention';
    case 'error': return 'fault';
    default: return 'neutral';
  }
};

/**
 * Notification delivery log: owns its filters, rows and 5 s poll. It stays mounted while hidden so
 * the filters survive a section switch, and polls only while `active`; a late answer never
 * replaces a newer one.
 */
export default function NotificationLogPanel({ active }: { active: boolean }) {
  const [logs, setLogs] = useState<NotificationLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scheduleFilter, setScheduleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<LogStatus>('all');
  const [applied, setApplied] = useState({ schedule: '', status: 'all' as LogStatus });
  const read = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++read.current;
    setLoading(true);
    setError(null);
    const schedule = applied.schedule.trim();
    const result = await schedulingService.getNotificationLogs({ limit: 50,
      ...(schedule ? { schedule_id: schedule } : {}), ...(applied.status !== 'all' ? { status: applied.status } : {}) });
    if (id !== read.current) return;
    if (result.error) setError(result.error);
    else setLogs(result.logs);
    setLoading(false);
  }, [applied]);

  useEffect(() => {
    if (!active) return;
    let stopped = false;
    let timer: number;
    const poll = async () => {
      if (document.visibilityState === 'visible') await refresh();
      if (!stopped) timer = window.setTimeout(poll, 5000);
    };
    void poll();
    return () => { stopped = true; read.current++; clearTimeout(timer); };
  }, [active, refresh]);

  const apply = () => setApplied({ schedule: scheduleFilter, status: statusFilter });
  const reset = () => {
    setScheduleFilter('');
    setStatusFilter('all');
    setApplied({ schedule: '', status: 'all' });
  };

  return <Card sx={{ borderRadius: 2 }}>
    <CardContent sx={{ p: 2 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ xs: 'stretch', md: 'flex-end' }} sx={{ mb: 2 }}>
        <TextField label="Schedule filter" value={scheduleFilter} onChange={event => setScheduleFilter(event.target.value)}
          onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); apply(); } }}
          size="small" sx={{ minWidth: { xs: '100%', md: 220 } }} placeholder="Schedule ID" />
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="log-status-label">Status</InputLabel>
          <Select labelId="log-status-label" label="Status" value={statusFilter} onChange={event => setStatusFilter(event.target.value as LogStatus)}>
            <MenuItem value="all">All statuses</MenuItem>
            <MenuItem value="sent">Sent</MenuItem>
            <MenuItem value="pending">Pending</MenuItem>
            <MenuItem value="error">Error</MenuItem>
            <MenuItem value="partial">Partial</MenuItem>
            <MenuItem value="unknown">Unknown</MenuItem>
            <MenuItem value="cancelled">Cancelled</MenuItem>
          </Select>
        </FormControl>
        <Stack direction="row" spacing={1}>
          <Button variant="contained" size="small" onClick={apply} disabled={loading}>Apply</Button>
          <Button variant="text" size="small" onClick={reset} disabled={loading || (scheduleFilter === '' && statusFilter === 'all')}>Reset</Button>
        </Stack>
        <Button variant="outlined" size="small" onClick={() => void refresh()} disabled={loading}>Refresh</Button>
      </Stack>

      <StatusDialog status={error ? { title: 'Notification Logs Error', message: error, severity: 'error', action: { label: 'Retry', onClick: () => void refresh() } } : null}
        onClose={() => setError(null)} />

      {loading && logs.length === 0 ? (
        <Box display="flex" justifyContent="center" py={4}><CircularProgress size={32} /></Box>
      ) : logs.length === 0 ? (
        <Typography variant="body2" color="text.secondary">No notification events recorded yet.</Typography>
      ) : (
        <TableContainer tabIndex={0} aria-label="Notification deliveries"><Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Timestamp</TableCell>
              <TableCell>Schedule</TableCell>
              <TableCell>Event</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Recipients</TableCell>
              <TableCell>Attachments</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {logs.map(log => (
              <TableRow key={log.log_id} hover>
                <TableCell>{log.triggered_at ? dayTime(log.triggered_at) : 'N/A'}</TableCell>
                <TableCell>{log.schedule_id || 'N/A'}</TableCell>
                <TableCell>{(log.event_type || 'event').replace(/_/g, ' ')}</TableCell>
                <TableCell><StatusChip label={log.status || 'unknown'} tone={statusTone(log.status)} /></TableCell>
                <TableCell>
                  {log.recipients.length ? log.recipients.join(', ') : 'N/A'}
                  {log.error_message && <Typography variant="caption" color="error" display="block">{log.error_message}</Typography>}
                </TableCell>
                <TableCell>{log.attachments.length ? `${log.attachments.length} file${log.attachments.length > 1 ? 's' : ''}` : 'N/A'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table></TableContainer>
      )}
    </CardContent>
  </Card>;
}
