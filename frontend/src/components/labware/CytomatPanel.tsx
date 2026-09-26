import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Chip, LinearProgress, List, ListItemButton, ListItemText, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import InspectionWorkspace from '../InspectionWorkspace';
import { CytomatSnapshot, labwareApi } from '../../services/labwareApi';
import { useLabwareSnapshot } from './useLabwareSnapshot';

const validSnapshot = (value: CytomatSnapshot) => Boolean(value &&
  typeof value.permissions?.can_update === 'boolean' &&
  Array.isArray(value.rows) && value.rows.every(row => row && typeof row.cytomat_pos === 'string' && typeof row.plate_id === 'string') &&
  Array.isArray(value.plate_options) && value.plate_options.every(plate => typeof plate === 'string'));

export default function CytomatPanel({ active = true }: { active?: boolean }) {
  const [selected, setSelected] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [pending, setPending] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [writeError, setWriteError] = useState('');
  const [notice, setNotice] = useState('');
  const count = Object.keys(pending).length;
  const { snapshot, setSnapshot, pending: reading, error: readError, refresh } = useLabwareSnapshot(labwareApi.getCytomatSnapshot, active, saving || count > 0, validSnapshot);
  const rows = snapshot?.rows || [];
  const canUpdate = Boolean(snapshot?.permissions.can_update);
  const row = rows.find(item => item.cytomat_pos === selected);
  const plateAt = (position: string) => pending[position] ?? rows.find(item => item.cytomat_pos === position)?.plate_id ?? '';
  const options = [...new Set(['', ...(snapshot?.plate_options || []), ...rows.map(item => item.plate_id)])];
  useEffect(() => {
    if (selected && snapshot && !rows.some(item => item.cytomat_pos === selected)) { setSelected(''); setDetailOpen(false); }
  }, [selected, snapshot, rows]);
  const queue = (plate: string) => {
    if (!row || !canUpdate || savingRef.current || reading) return;
    setPending(previous => {
      const next = { ...previous };
      if (plate === row.plate_id) delete next[row.cytomat_pos]; else next[row.cytomat_pos] = plate;
      return next;
    });
    setNotice(''); setWriteError('');
  };
  const save = async () => {
    if (!canUpdate || !count || savingRef.current) return;
    const submitted = { ...pending };
    savingRef.current = true; setSaving(true); setWriteError(''); setNotice('');
    try {
      await labwareApi.updateCytomat(Object.entries(submitted).map(([cytomat_pos, plate_id]) => ({ cytomat_pos, plate_id })));
      setSnapshot(previous => previous && ({ ...previous, rows: previous.rows.map(item => Object.prototype.hasOwnProperty.call(submitted, item.cytomat_pos) ? { ...item, plate_id: submitted[item.cytomat_pos] } : item) }));
      setPending(previous => {
        const remaining = { ...previous };
        Object.entries(submitted).forEach(([position, plate]) => { if (remaining[position] === plate) delete remaining[position]; });
        return remaining;
      });
      setNotice('Changes saved.');
    } catch (error: any) { setWriteError(error?.response?.data?.error?.message || error?.response?.data?.message || error?.message || 'Unable to save changes.'); }
    finally { savingRef.current = false; setSaving(false); }
  };
  if (!snapshot) return readError ? <Alert severity="error" action={<Button onClick={() => void refresh()}>Retry</Button>}>{readError}</Alert> : <LinearProgress aria-label="Loading positions" />;
  const filtered = rows.filter(item => `${item.cytomat_pos} ${plateAt(item.cytomat_pos)}`.toLowerCase().includes(search.toLowerCase()));
  const selector = <Paper variant="outlined" sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'auto' }}>
    <TextField size="small" label="Find a position or plate" value={search} onChange={event => setSearch(event.target.value)} sx={{ m: 1.5 }} />
    <List aria-label="Cytomat positions" sx={{ flex: 1, minHeight: 120, overflow: 'auto', pt: 0 }}>
      {filtered.map(item => <ListItemButton key={item.cytomat_pos} selected={selected === item.cytomat_pos} aria-current={selected === item.cytomat_pos ? 'true' : undefined} aria-label={`Position ${item.cytomat_pos}, ${plateAt(item.cytomat_pos) || 'Empty'}`} onClick={() => { setSelected(item.cytomat_pos); setDetailOpen(true); }}>
        <ListItemText primary={item.cytomat_pos} secondary={`${plateAt(item.cytomat_pos) || 'Empty'}${Object.prototype.hasOwnProperty.call(pending, item.cytomat_pos) ? ' · Unsaved' : ''}`} primaryTypographyProps={{ sx: { overflowWrap: 'anywhere' } }} secondaryTypographyProps={{ sx: { overflowWrap: 'anywhere' } }} />
      </ListItemButton>)}
      {!filtered.length && <Typography sx={{ p: 1.5 }}>{rows.length ? 'No matching positions.' : 'No positions found.'}</Typography>}
    </List>
  </Paper>;
  return <Stack spacing={1} sx={{ minWidth: 0 }}>
    <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
      <Typography variant="body2">{rows.length} positions · {rows.filter(item => !plateAt(item.cytomat_pos)).length} empty</Typography>
      <Button onClick={() => void refresh()} disabled={saving || reading || count > 0}>Refresh</Button>
      {canUpdate ? <><Button variant="contained" onClick={() => void save()} disabled={saving || !count}>Save changes ({count})</Button>{count > 0 && <Button disabled={saving} onClick={() => { setPending({}); setWriteError(''); }}>Discard</Button>}</> : <Chip label="Read only" size="small" />}
    </Stack>
    {(readError || writeError) && <Alert severity="error" action={!count && !saving ? <Button onClick={() => void refresh()}>Retry</Button> : undefined}>{writeError || readError}{readError && ' Previous data is shown.'}</Alert>}
    <Typography variant="caption" color="text.secondary" role="status">{saving ? 'Saving…' : count ? `Refresh paused · ${count} unsaved` : notice || `Updated ${new Date(snapshot.refreshed_at).toLocaleTimeString()}`}</Typography>
    {reading && <LinearProgress aria-label="Refreshing positions" />}
    <InspectionWorkspace label="Cytomat workspace" selector={selector} selectorLabel="Positions" detailOpen={detailOpen} onBack={() => setDetailOpen(false)}>
      {row ? <Paper variant="outlined" sx={{ p: 2, flex: 1, minHeight: 0, overflow: 'auto' }}>
        <Stack spacing={2} sx={{ maxWidth: 420 }}>
          <Typography variant="h6" component="h2">Position {row.cytomat_pos}</Typography>
          <Typography color="text.secondary">Saved plate: {row.plate_id || 'Empty'}</Typography>
          {canUpdate ? <TextField select fullWidth size="small" label={`Plate at ${row.cytomat_pos}`} value={plateAt(row.cytomat_pos)} onChange={event => queue(event.target.value)} disabled={saving || reading} InputLabelProps={{ shrink: true }} SelectProps={{ displayEmpty: true, renderValue: value => String(value) || 'Empty' }}>
            {options.map(plate => <MenuItem key={plate || '__empty__'} value={plate}>{plate || 'Empty'}</MenuItem>)}
          </TextField> : <Typography>{row.plate_id || 'Empty'}</Typography>}
          {Object.prototype.hasOwnProperty.call(pending, row.cytomat_pos) && <Typography color="warning.main">Unsaved change</Typography>}
        </Stack>
      </Paper> : <Alert severity="info">Choose a position.</Alert>}
    </InspectionWorkspace>
  </Stack>;
}
