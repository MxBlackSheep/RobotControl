import React, { useRef, useState } from 'react';
import { Alert, Box, Button, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import StatusChip from '../StatusChip';
import { CytomatRowState, CytomatSnapshot, labwareApi } from '../../services/labwareApi';
import { useLabwareSnapshot } from './useLabwareSnapshot';
import { useLabwareWorkspace } from './useLabwareWorkspace';
import { clockTime } from '../../utils/displayTime';

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
  const [editing, setEditing] = useState<string | null>(null);
  const editButtons = useRef(new Map<string, HTMLButtonElement>());
  const otherPositionsRef = useRef<HTMLDivElement>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [writeError, setWriteError] = useState('');
  const [notice, setNotice] = useState('');
  const count = Object.keys(pending).length;
  const { snapshot, setSnapshot, pending: reading, error: readError, refresh, suspend } = useLabwareSnapshot(labwareApi.getCytomatSnapshot, active, saving || count > 0 || editing !== null, validSnapshot);
  const workspace = useLabwareWorkspace(active, Boolean(snapshot));
  const bounded = workspace.width >= 900 && workspace.height >= 480;
  const rows = snapshot?.rows || [];
  const groups = new Map<string, CytomatRowState[]>();
  rows.forEach(row => groups.set(row.cytomat_pos, [...(groups.get(row.cytomat_pos) || []), row]));
  const byPosition = new Map([...groups].filter(([, entries]) => entries.length === 1).map(([position, entries]) => [position, entries[0]]));
  const canUpdate = Boolean(snapshot?.permissions.can_update);
  const options = [...new Set(['', ...(snapshot?.plate_options || []), ...rows.map(row => row.plate_id)])];
  const closeEditor = (position: string) => {
    if (savingRef.current) return;
    setEditing(null);
    editButtons.current.get(position)?.focus({ preventScroll: true });
  };
  const openEditor = (position: string) => {
    if (!active || !byPosition.has(position) || unusedPositions.includes(position) || !canUpdate || savingRef.current) return;
    suspend();
    setEditing(position);
  };
  const queue = (position: string, plate: string) => {
    const row = byPosition.get(position);
    if (!active || editing !== position || !row || unusedPositions.includes(position) || !canUpdate || savingRef.current) return;
    setPending(previous => {
      const next = { ...previous };
      if (plate === row.plate_id) delete next[position]; else next[position] = plate;
      return next;
    });
    setNotice(''); setWriteError('');
  };
  const save = async () => {
    if (!active || !canUpdate || !count || savingRef.current) return;
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

  const focusStyle = { '&.Mui-focusVisible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: 2 } };
  const columns = { xs: '76px minmax(0, 1fr) auto', sm: 'clamp(100px, 10cqw, 180px) minmax(0, 1fr) auto' };
  // Only the independently sized scroll viewport is a query container. Rows
  // may grow for text or editing without feeding their size back into the fit.
  const summaryHeight = bounded ? 'max(48px, calc((100cqh - 8px) / 9))' : '48px';
  const rowFont = bounded ? 'clamp(14px, 1cqw, 22px)' : '14px';
  const renderPosition = (position: string, unused = false) => {
    const row = byPosition.get(position);
    const unsaved = Object.prototype.hasOwnProperty.call(pending, position);
    const plate = pending[position] ?? row?.plate_id ?? '';
    const open = editing === position && canUpdate && row && !unused;
    return <Box role="group" aria-label={'Position ' + position} data-testid={'cytomat-position-' + position}
      onKeyDown={event => { if (open && event.key === 'Escape') { event.preventDefault(); closeEditor(position); } }}
      sx={{ minWidth: 0, px: { xs: 1.25, sm: 2 }, bgcolor: open ? 'action.selected' : undefined, borderBottom: 1, borderColor: 'divider', '&:last-child': { borderBottom: 0 } }}>
      <Box sx={{ display: 'grid', gridTemplateColumns: columns, alignItems: 'center', gap: 1, minHeight: configuredPositions.has(position) ? summaryHeight : 48, py: 0.25 }}>
        <Typography component="h3" variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere', fontSize: rowFont }}>Position {position}</Typography>
        <Stack gap={0.25} sx={{ minWidth: 0 }}>
          <Typography variant="body2" color={!row || !plate ? 'text.secondary' : 'text.primary'} sx={{ overflowWrap: 'anywhere', fontSize: rowFont }}>
            {!row ? (groups.get(position)?.length || 0) > 1 ? 'Unavailable · duplicate position' : 'Unavailable' : plate || 'Empty'}
          </Typography>
          {unsaved && <Typography variant="caption" color="warning.main">Unsaved</Typography>}
        </Stack>
        {unused ? <Typography variant="caption" color="text.secondary" sx={{ fontSize: rowFont }}>Unused</Typography> : row && canUpdate ?
          <Button size="small" disableRipple ref={element => { if (element) editButtons.current.set(position, element); else editButtons.current.delete(position); }}
            aria-label={(open ? 'Done editing position ' : 'Edit position ') + position} aria-expanded={Boolean(open)}
            disabled={saving} onClick={() => open ? closeEditor(position) : openEditor(position)} sx={{ minWidth: 44, minHeight: 44, fontSize: bounded ? 'clamp(14px, 1cqw, 20px)' : 14, ...focusStyle }}>{open ? 'Done' : 'Edit'}</Button> : null}
      </Box>
      {open && <Box sx={{ pb: 1.5, pl: { xs: 0, sm: 'calc(clamp(100px, 10cqw, 180px) + 8px)' } }}>
          <TextField select fullWidth autoFocus size="small" label={'Plate at ' + position} value={plate}
            onChange={event => queue(position, event.target.value)} disabled={saving}
            InputLabelProps={{ shrink: true }} SelectProps={{ displayEmpty: true, SelectDisplayProps: { 'aria-label': 'Plate at ' + position, 'aria-labelledby': undefined }, renderValue: value => <Box component="span" sx={{ display: 'block', whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{String(value) || 'Empty'}</Box> }}>
            {options.map(option => <MenuItem key={option || '__empty__'} value={option} sx={{ whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{option || 'Empty'}</MenuItem>)}
          </TextField>
      </Box>}
    </Box>;
  };
  const otherPositions = [...groups.keys()].filter(position => !configuredPositions.has(position));
  return <Stack ref={workspace.ref} data-testid="cytomat-workspace" spacing={1} sx={{ minWidth: 0, width: '100%', height: bounded ? workspace.height : 'auto' }}>
    <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" sx={{ flexShrink: 0 }}>
      <Button disableRipple aria-busy={reading} onClick={() => { if (!reading) void refresh(); }} disabled={saving || count > 0 || editing !== null} sx={focusStyle}>Refresh</Button>
      {canUpdate ? <><Button variant="contained" onClick={() => void save()} disabled={saving || !count}>Save changes ({count})</Button>{count > 0 && <Button disabled={saving} onClick={() => { setPending({}); setWriteError(''); }}>Discard</Button>}</> : <StatusChip tone="neutral" label="Read only" />}
      {otherPositions.length > 0 && <Button disableRipple onClick={() => { otherPositionsRef.current?.scrollIntoView({ block: 'nearest' }); otherPositionsRef.current?.focus({ preventScroll: true }); }} sx={{ ml: 'auto', ...focusStyle }}>Other positions ({otherPositions.length})</Button>}
    </Stack>
    {(readError || writeError) && <Alert severity="error" sx={{ flexShrink: 0 }} action={!count && !saving && editing === null ? <Button onClick={() => void refresh()}>Retry</Button> : undefined}>{writeError || readError}{readError && ' Previous data is shown.'}</Alert>}
    <Typography variant="caption" color="text.secondary" role="status" sx={{ minHeight: 20, flexShrink: 0 }}>{saving ? 'Saving…' : count ? count + ' unsaved' : reading ? 'Updating…' : notice || 'Updated ' + clockTime(new Date(snapshot.refreshed_at))}</Typography>
    <Paper data-cytomat-register variant="outlined" sx={{ overflow: 'hidden', display: 'flex', flexDirection: 'column', flex: bounded ? '1 1 0%' : 'none', minHeight: 0 }}>
      <Box sx={{ display: 'grid', gridTemplateColumns: columns, gap: 1, px: { xs: 1.25, sm: 2 }, py: 1.25, bgcolor: 'action.hover', borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}>
        <Typography variant="caption" color="text.secondary">Position</Typography><Typography variant="caption" color="text.secondary">Plate</Typography>
      </Box>
      <Box data-testid="cytomat-register-body" role="region" aria-label="Cytomat register" tabIndex={bounded ? 0 : undefined}
        sx={{ flex: bounded ? '1 1 0%' : undefined, minHeight: 0, overflowY: bounded ? 'auto' : 'visible', containerType: bounded ? 'size' : undefined,
          '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: -2 } }}>
      <Box component="ol" aria-label="Cytomat shelves" sx={{ m: 0, p: 0, listStyle: 'none' }}>
        {shelves.map(position => <Box component="li" key={position} data-position={position} sx={{ '&:not(:last-child)': { borderBottom: 1, borderColor: 'divider' } }}>{renderPosition(position)}</Box>)}
      </Box>
      <Box component="section" aria-label="Unused positions" sx={{ borderTop: 1, borderColor: 'divider', bgcolor: 'action.hover' }}>
        {unusedPositions.map(position => <React.Fragment key={position}>{renderPosition(position, true)}</React.Fragment>)}
      </Box>
      {otherPositions.length > 0 && <Box ref={otherPositionsRef} component="section" aria-label="Other positions" tabIndex={-1} sx={{ borderTop: 1, borderColor: 'divider', '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: -2 } }}>
        <Typography component="h2" variant="subtitle2" sx={{ px: { xs: 1.25, sm: 2 }, py: 1.25, bgcolor: 'action.hover', borderBottom: 1, borderColor: 'divider' }}>Other positions</Typography>
        {otherPositions.map(position => <React.Fragment key={position}>{renderPosition(position)}</React.Fragment>)}
      </Box>}
      </Box>
    </Paper>
  </Stack>;
}
