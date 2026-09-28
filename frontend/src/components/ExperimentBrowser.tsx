import React, { useEffect, useState } from 'react';
import { Alert, Box, LinearProgress, List, ListItemButton, ListItemText, Paper, TablePagination, TextField, Typography } from '@mui/material';
import { api } from '../services/api';

export type Experiment = { ExperimentID: number; UserDefinedID?: string; Note?: string };

export default function ExperimentBrowser({ selected, onSelect, disabled, active, reportId }: {
  selected?: Experiment; onSelect: (row: Experiment) => void; disabled: boolean; active: boolean; reportId?: string;
}) {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState<Experiment[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const { data } = await api.get('/api/database/tools/experiments', { params: { search: query, page: page + 1, report_id: reportId }, signal: controller.signal });
        if (controller.signal.aborted) return;
        setRows(data.rows); setTotal(data.total_count); setError('');
      } catch {
        if (!controller.signal.aborted) setError('Experiments could not be loaded. Change the search to try again.');
      } finally { if (!controller.signal.aborted) setLoading(false); }
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, page, active, reportId]);
  return <Paper variant="outlined" sx={{ display: 'flex', flexDirection: 'column', minHeight: 0, height: '100%' }}>
    <Box sx={{ p: 2 }}>
      <Typography component="h2" variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Experiments</Typography>
      <TextField fullWidth size="small" label="Search experiments" placeholder="ID, name or note" value={query}
        onChange={event => { setQuery(event.target.value); setPage(0); }} disabled={disabled} />
    </Box>
    <Box sx={{ height: 4 }}>{loading && <LinearProgress />}</Box>
    {error && <Alert severity="error">{error}</Alert>}
    <List aria-label="Experiments" sx={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
      {rows.map(row => <ListItemButton key={row.ExperimentID} selected={row.ExperimentID === selected?.ExperimentID}
        aria-current={row.ExperimentID === selected?.ExperimentID ? 'true' : undefined}
        disabled={disabled || loading} onClick={() => onSelect(row)} sx={{ minHeight: 64 }}>
        <ListItemText primary={`${row.ExperimentID} · ${row.UserDefinedID || 'Unnamed experiment'}`} secondary={row.Note || undefined}
          primaryTypographyProps={{ sx: { overflowWrap: 'anywhere' } }} secondaryTypographyProps={{ sx: { overflowWrap: 'anywhere' } }} />
      </ListItemButton>)}
      {!loading && !error && !rows.length && <Typography sx={{ p: 2 }} color="text.secondary">No matching experiments.</Typography>}
    </List>
    <TablePagination component="div" count={total} page={page} onPageChange={(_, value) => setPage(value)}
      rowsPerPage={25} rowsPerPageOptions={[]} showFirstButton showLastButton
      slotProps={{ actions: { nextButton: { disabled: disabled || loading || (page + 1) * 25 >= total },
        previousButton: { disabled: disabled || loading || page === 0 }, firstButton: { disabled: disabled || loading || page === 0 },
        lastButton: { disabled: disabled || loading || (page + 1) * 25 >= total } } }}
      sx={{ flexShrink: 0, '& .MuiTablePagination-toolbar': { px: 1, flexWrap: 'wrap' }, '& .MuiTablePagination-actions': { ml: 1 } }} />
  </Paper>;
}
