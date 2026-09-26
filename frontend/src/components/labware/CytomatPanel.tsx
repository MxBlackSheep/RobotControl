import React, { useRef, useState } from 'react';
import { Alert, Box, Button, Chip, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { CytomatRowState, CytomatSnapshot, labwareApi } from '../../services/labwareApi';
import { useLabwareSnapshot } from './useLabwareSnapshot';

// These positions describe the operator-confirmed layout, not database sort order.
const shelves = ['1', '2', '3', '4', '5', '6', '7'];
const unusedPositions = ['8', '9'];
const configuredPositions = new Set([...shelves, ...unusedPositions]);
const validSnapshot = (value: CytomatSnapshot) => Boolean(value &&
  typeof value.permissions?.can_update === 'boolean' &&
  Array.isArray(value.rows) && value.rows.every(row => row && typeof row.cytomat_pos === 'string' && typeof row.plate_id === 'string') &&
  Array.isArray(value.plate_options) && value.plate_options.every(plate => typeof plate === 'string'));

export default function CytomatPanel({ active = true }: { active?: boolean }) {
  const [pending, setPending] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [writeError, setWriteError] = useState('');
  const [notice, setNotice] = useState('');
  const count = Object.keys(pending).length;
  const { snapshot, setSnapshot, pending: reading, error: readError, refresh } = useLabwareSnapshot(labwareApi.getCytomatSnapshot, active, saving || count > 0, validSnapshot);
  const rows = snapshot?.rows || [];
  const groups = new Map<string, CytomatRowState[]>();
  rows.forEach(row => groups.set(row.cytomat_pos, [...(groups.get(row.cytomat_pos) || []), row]));
  const byPosition = new Map([...groups].filter(([, entries]) => entries.length === 1).map(([position, entries]) => [position, entries[0]]));
  const canUpdate = Boolean(snapshot?.permissions.can_update);
  const options = [...new Set(['', ...(snapshot?.plate_options || []), ...rows.map(row => row.plate_id)])];
  const queue = (position: string, plate: string) => {
    const row = byPosition.get(position);
    if (!active || !row || unusedPositions.includes(position) || !canUpdate || savingRef.current || reading) return;
    setPending(previous => {
      const next = { ...previous };
      if (plate === row.plate_id) delete next[position]; else next[position] = plate;
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
      setSnapshot(previous => previous && ({ ...previous, rows: previous.rows.map(row => Object.prototype.hasOwnProperty.call(submitted, row.cytomat_pos) ? { ...row, plate_id: submitted[row.cytomat_pos] } : row) }));
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

  const renderPosition = (position: string, unused = false) => {
    const row = byPosition.get(position);
    const unsaved = Object.prototype.hasOwnProperty.call(pending, position);
    const plate = pending[position] ?? row?.plate_id ?? '';
    return <Paper variant="outlined" role="group" aria-label={'Position ' + position} data-testid={'cytomat-position-' + position}
      sx={{ p: 1, minWidth: 0, borderBottomWidth: unused ? 1 : 3, borderStyle: unsaved ? 'dashed' : 'solid', bgcolor: unused ? 'action.hover' : 'background.paper' }}>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(76px, 1fr) minmax(0, 3fr)', alignItems: 'center', gap: 1 }}>
        <Stack gap={0.5} alignItems="flex-start" sx={{ minWidth: 0 }}>
          <Typography component="h3" variant="subtitle2" sx={{ overflowWrap: 'anywhere' }}>Position {position}</Typography>
          {unused && <Chip label="Unused" size="small" />}
          {unsaved && <Typography variant="caption" color="warning.main">Unsaved</Typography>}
        </Stack>
        {!row ? <Typography color="text.secondary">{(groups.get(position)?.length || 0) > 1 ? 'Unavailable · duplicate position' : 'Unavailable'}</Typography>
          : canUpdate && !unused ? <TextField select fullWidth size="small" label={'Plate at ' + position} value={plate}
            onChange={event => queue(position, event.target.value)} disabled={saving || reading}
            InputLabelProps={{ shrink: true }} SelectProps={{ displayEmpty: true, SelectDisplayProps: { 'aria-label': 'Plate at ' + position, 'aria-labelledby': undefined }, renderValue: value => <Box component="span" sx={{ display: 'block', whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{String(value) || 'Empty'}</Box> }}>
            {options.map(option => <MenuItem key={option || '__empty__'} value={option} sx={{ whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{option || 'Empty'}</MenuItem>)}
          </TextField>
            : <Typography sx={{ overflowWrap: 'anywhere' }}>{plate || 'Empty'}</Typography>}
      </Box>
    </Paper>;
  };
  const otherPositions = [...groups.keys()].filter(position => !configuredPositions.has(position));
  return <Stack spacing={1} sx={{ minWidth: 0, maxWidth: 800 }}>
    <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
      <Button onClick={() => void refresh()} disabled={saving || reading || count > 0}>Refresh</Button>
      {canUpdate ? <><Button variant="contained" onClick={() => void save()} disabled={saving || !count}>Save changes ({count})</Button>{count > 0 && <Button disabled={saving} onClick={() => { setPending({}); setWriteError(''); }}>Discard</Button>}</> : <Chip label="Read only" size="small" />}
    </Stack>
    {(readError || writeError) && <Alert severity="error" action={!count && !saving ? <Button onClick={() => void refresh()}>Retry</Button> : undefined}>{writeError || readError}{readError && ' Previous data is shown.'}</Alert>}
    <Typography variant="caption" color="text.secondary" role="status">{saving ? 'Saving…' : count ? count + ' unsaved' : notice || 'Updated ' + new Date(snapshot.refreshed_at).toLocaleTimeString()}</Typography>
    {reading && <LinearProgress aria-label="Refreshing positions" />}
    <Stack component="ol" aria-label="Cytomat shelves" spacing={0.75} sx={{ m: 0, p: 0, listStyle: 'none' }}>
      {shelves.map(position => <Box component="li" key={position} data-position={position}>{renderPosition(position)}</Box>)}
    </Stack>
    <Stack component="section" aria-label="Unused positions" spacing={0.75}>
      {unusedPositions.map(position => <Box key={position}>{renderPosition(position, true)}</Box>)}
    </Stack>
    {otherPositions.length > 0 && <Stack component="section" aria-label="Other positions" spacing={0.75}>
      <Typography component="h2" variant="subtitle1" sx={{ pt: 1 }}>Other positions</Typography>
      {otherPositions.map(position => <Box key={position}>{renderPosition(position)}</Box>)}
    </Stack>}
  </Stack>;
}
