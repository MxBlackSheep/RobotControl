import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress,
  Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import { LibraryMethod } from '../../types/scheduling';
import { schedulingAPI } from '../../services/schedulingApi';
import { methodError } from './HostMethodBrowser';

export const pathStatusLabel = { available: 'Available', missing: 'Missing', inaccessible: 'Inaccessible', invalid: 'Invalid path', not_checked: 'Not checked' };
export const referenceLabel = (ref: LibraryMethod['references'][number]) => ref.archived ? 'Archived schedule' : ref.busy ? 'Busy (queued, running or paused)' : ref.is_active ? 'Active schedule' : 'Inactive schedule';

export default function MethodLibraryPanel({ version, onChanged, onImport, onCreateSchedule, onChangePath }: {
  version: number; onChanged: () => void; onImport: () => void; onCreateSchedule: (method: LibraryMethod) => void;
  onChangePath?: (method: LibraryMethod) => void;
}) {
  const [methods, setMethods] = useState<LibraryMethod[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [folder, setFolder] = useState('');
  const [status, setStatus] = useState('');
  const [archiveFilter, setArchiveFilter] = useState('current');
  const [sort, setSort] = useState('name');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [detailId, setDetailId] = useState<string | null>(null);
  const [archiveAction, setArchiveAction] = useState<boolean | null>(null);
  const load = async () => {
    try {
      const response = await schedulingAPI.getMethodLibrary();
      if (!response.data.success || !response.data.data) throw new Error('Unable to load method library.');
      setMethods(response.data.data.methods);
    } catch (err) { setError(methodError(err)); }
  };
  useEffect(() => { void load(); }, [version]);
  const visible = useMemo(() => methods.filter(method =>
    `${method.method_name} ${method.file_path}`.toLowerCase().includes(query.toLowerCase()) &&
    (!folder || method.containing_folder === folder) && (!status || method.path_status === status) &&
    (archiveFilter === 'all' || Boolean(method.archived) === (archiveFilter === 'archived')))
    .sort((a, b) => (sort === 'name' ? a.method_name : sort === 'folder' ? a.containing_folder : a.path_status)
      .localeCompare(sort === 'name' ? b.method_name : sort === 'folder' ? b.containing_folder : b.path_status) || a.file_path.localeCompare(b.file_path)),
    [methods, query, folder, status, archiveFilter, sort]);
  const targets = methods.filter(method => selected.includes(method.method_id));
  const detail = methods.find(method => method.method_id === detailId);
  const clearSelection = () => setSelected([]);
  const check = async () => {
    setBusy(true); setError(''); setMessage('');
    try {
      const response = await schedulingAPI.checkMethodPaths(selected);
      const failures = response.data.data?.outcomes.filter(row => !row.success) || [];
      if (failures.length) setError(failures.map(row => row.reason).join('\n'));
      else setMessage('Path checks finished. Review the status and last checked time.');
      onChanged();
    } catch (err) { setError(methodError(err)); }
    finally { setBusy(false); }
  };
  const applyArchive = async () => {
    setBusy(true); setError(''); setMessage('');
    const failures: string[] = []; let count = 0;
    for (const method of targets.filter(row => Boolean(row.archived) !== archiveAction)) {
      try { await schedulingAPI.archiveMethod(method.method_id, archiveAction!, method.revision); count += 1; }
      catch (err) { failures.push(`${method.method_name}: ${methodError(err)}`); }
    }
    setMessage(`${count} method(s) ${archiveAction ? 'archived' : 'restored'}. Existing schedules are unchanged.`);
    setError(failures.join('\n')); setArchiveAction(null); clearSelection(); setBusy(false); onChanged();
  };
  return <Stack spacing={2}>
    <Typography variant="h6">Method library</Typography>
    <Typography variant="body2">Manage the paths available when creating schedules. Archiving a method hides it from new selections; existing schedules keep their saved paths.</Typography>
    <Stack direction="row" flexWrap="wrap" gap={1}>
      <Button variant="contained" onClick={onImport}>Import methods</Button>
      <Button disabled={busy} onClick={() => { setError(''); void load(); }}>Refresh library</Button>
      <Button disabled={busy || !targets.length} onClick={check}>Check paths</Button>
      <Button disabled={busy || !targets.some(row => !row.archived)} onClick={() => setArchiveAction(true)}>Archive selected</Button>
      <Button disabled={busy || !targets.some(row => row.archived)} onClick={() => setArchiveAction(false)}>Restore selected</Button>
    </Stack>
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
      <TextField label="Search methods or paths" value={query} onChange={e => { setQuery(e.target.value); clearSelection(); }} fullWidth size="small" />
      <TextField select SelectProps={{ native: true }} label="Folder" InputLabelProps={{ shrink: true }} value={folder} onChange={e => { setFolder(e.target.value); clearSelection(); }} size="small" sx={{ minWidth: 140, maxWidth: { md: 300 } }}>
        <option value="">All folders</option>{[...new Set(methods.map(row => row.containing_folder))].sort().map(path => <option key={path}>{path}</option>)}
      </TextField>
      <TextField select SelectProps={{ native: true }} label="Path status" value={status} InputLabelProps={{ shrink: true }} onChange={e => { setStatus(e.target.value); clearSelection(); }} size="small" sx={{ minWidth: 140 }}>
        <option value="">All statuses</option>{Object.entries(pathStatusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </TextField>
      <TextField select SelectProps={{ native: true }} label="Library view" value={archiveFilter} onChange={e => { setArchiveFilter(e.target.value); clearSelection(); }} size="small" sx={{ minWidth: 140 }}>
        <option value="current">Current</option><option value="archived">Archived</option><option value="all">All entries</option>
      </TextField>
      <TextField select SelectProps={{ native: true }} label="Sort by" value={sort} onChange={e => setSort(e.target.value)} size="small" sx={{ minWidth: 130 }}>
        <option value="name">Method name</option><option value="folder">Folder</option><option value="status">Path status</option>
      </TextField>
    </Stack>
    {!!error && <Alert severity="error" sx={{ whiteSpace: 'pre-line' }}>{error}</Alert>}
    {!!message && <Alert severity="success">{message}</Alert>}
    {busy && <LinearProgress aria-label="Updating method library" />}
    <Typography variant="caption">{visible.length} methods · {targets.length} selected. Select rows to check, archive or restore them.</Typography>
    <TableContainer sx={{ maxHeight: 550 }}><Table size="small" stickyHeader aria-label="Imported methods">
      <TableHead><TableRow>
        <TableCell padding="checkbox"><Checkbox inputProps={{ 'aria-label': 'Select all visible methods' }} disabled={busy || !visible.length}
          checked={visible.length > 0 && visible.every(row => selected.includes(row.method_id))}
          indeterminate={visible.some(row => selected.includes(row.method_id)) && !visible.every(row => selected.includes(row.method_id))}
          onChange={(_, checked) => setSelected(checked ? visible.map(row => row.method_id) : [])} /></TableCell>
        <TableCell>Method and full path</TableCell><TableCell>Path status</TableCell><TableCell>Library</TableCell><TableCell>Schedules</TableCell>
      </TableRow></TableHead>
      <TableBody>{visible.map(row => <TableRow key={row.method_id} hover>
        <TableCell padding="checkbox"><Checkbox inputProps={{ 'aria-label': `Select ${row.file_path}` }} disabled={busy} checked={selected.includes(row.method_id)}
          onChange={(_, checked) => setSelected(old => checked ? [...old, row.method_id] : old.filter(id => id !== row.method_id))} /></TableCell>
        <TableCell sx={{ minWidth: 200, maxWidth: 450, overflowWrap: 'anywhere' }}>
          <Button onClick={() => setDetailId(row.method_id)}>{row.method_name}</Button>
          <Typography variant="caption" display="block">{row.file_path}</Typography>
          <Typography variant="caption" color="text.secondary">Folder: {row.containing_folder}</Typography>
          {row.duplicate_path && <Typography color="warning.main" variant="caption" display="block">Duplicate path — review entries</Typography>}
        </TableCell>
        <TableCell><Chip size="small" label={pathStatusLabel[row.path_status]} color={row.path_status === 'available' ? 'success' : 'default'} /></TableCell>
        <TableCell>{row.archived ? 'Archived' : 'Current'}</TableCell>
        <TableCell><Button aria-label={`View schedules using ${row.method_name}`} onClick={() => setDetailId(row.method_id)}>{row.schedule_count}</Button></TableCell>
      </TableRow>)}</TableBody>
    </Table></TableContainer>
    {!visible.length && <Alert severity="info">No methods match this view. Import methods or adjust the filters.</Alert>}
    <Dialog open={!!detail} onClose={() => setDetailId(null)} maxWidth="md" fullWidth>
      <DialogTitle>Method details and schedules</DialogTitle>
      <DialogContent dividers>{detail && <Stack spacing={1.5} sx={{ overflowWrap: 'anywhere' }}>
        <Typography>{detail.method_name}</Typography><Typography>{detail.file_path}</Typography>
        <Typography>Imported from: {detail.source_folder || 'Not recorded'}</Typography>
        <Typography>Imported by {detail.imported_by || 'Unknown'} at {detail.imported_at}</Typography>
        <Typography>{pathStatusLabel[detail.path_status]} · Last checked: {detail.last_checked_at || 'Not checked'}</Typography>
        {detail.validation_reason && <Alert severity="warning">{detail.validation_reason}</Alert>}
        <Typography variant="h6">Schedules using this path</Typography>
        {!detail.references.length && <Typography>No schedules reference this path.</Typography>}
        {detail.references.map(ref => <Box key={`${ref.schedule_id}-${ref.role}`}>
          <Typography>{ref.experiment_name} — {ref.role} method</Typography>
          <Typography variant="caption">{referenceLabel(ref)} · {ref.schedule_id}</Typography>
        </Box>)}
      </Stack>}</DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap' }}>
        <Button onClick={() => setDetailId(null)}>Close</Button>
        {onChangePath && detail && <Button onClick={() => { setDetailId(null); onChangePath(detail); }}>Change path</Button>}
        <Button disabled={!detail || !!detail.archived || detail.path_status !== 'available'} onClick={() => { if (detail) { setDetailId(null); onCreateSchedule(detail); } }}>Create a schedule</Button>
      </DialogActions>
    </Dialog>
    <Dialog open={archiveAction !== null} onClose={() => { if (!busy) setArchiveAction(null); }}>
      <DialogTitle>{archiveAction ? 'Archive selected methods?' : 'Restore selected methods?'}</DialogTitle>
      <DialogContent><Typography>Hamilton files and existing schedules will remain unchanged. {archiveAction ? 'These methods will be hidden from new schedule choices.' : 'Available methods will return to new schedule choices.'}</Typography>
        {targets.filter(row => Boolean(row.archived) !== archiveAction).map(row => <Typography key={row.method_id} sx={{ mt: 1, overflowWrap: 'anywhere' }}>{row.file_path} ({row.schedule_count} schedules)</Typography>)}
      </DialogContent>
      <DialogActions><Button disabled={busy} onClick={() => setArchiveAction(null)}>Cancel</Button><Button disabled={busy} onClick={applyArchive}>{archiveAction ? 'Archive methods' : 'Restore methods'}</Button></DialogActions>
    </Dialog>
  </Stack>;
}
