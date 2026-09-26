import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, LinearProgress, List, ListItemButton, ListItemText, Menu, MenuItem, Paper, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import InspectionWorkspace from '../InspectionWorkspace';
import { labwareApi, TipTrackingSnapshot, TipTrackingUpdate } from '../../services/labwareApi';
import { useLabwareSnapshot } from './useLabwareSnapshot';

type Pending = Record<string, Record<string, string>>;
const keyFor = (rack: string, position: number) => JSON.stringify([rack, position]);
const message = (error: any) => error?.response?.data?.error?.message || error?.response?.data?.message || error?.message || 'Unable to save changes.';
const stringArray = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string');
const validSnapshot = (value: TipTrackingSnapshot) => Boolean(value &&
  typeof value.permissions?.can_update === 'boolean' && value.grid &&
  [value.grid.rows, value.grid.cols, value.grid.positions_per_rack].every(size => Number.isInteger(size) && size > 0) &&
  stringArray(value.status_order) && typeof value.unknown_status === 'string' && value.status_colors &&
  Array.isArray(value.families) && value.families.every(family => family &&
    typeof family.family_id === 'string' && typeof family.display_name === 'string' &&
    stringArray(family.left_racks) && stringArray(family.right_racks) && family.tips && typeof family.tips === 'object'));

export default function TipTrackingPanel({ active = true }: { active?: boolean }) {
  const [familyId, setFamilyId] = useState('');
  const [rack, setRack] = useState('');
  const [rackOpen, setRackOpen] = useState(false);
  const [position, setPosition] = useState(1);
  const [statusChoice, setStatusChoice] = useState('clean');
  const [scope, setScope] = useState('tip');
  const [view, setView] = useState<'map' | 'list'>(() => window.innerWidth < 900 ? 'list' : 'map');
  const [pending, setPending] = useState<Pending>({});
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [writeError, setWriteError] = useState('');
  const [notice, setNotice] = useState('');
  const [menu, setMenu] = useState<HTMLElement | null>(null);
  const map = useRef<HTMLDivElement>(null);
  const totalPending = Object.values(pending).reduce((total, entries) => total + Object.keys(entries).length, 0);
  const { snapshot, setSnapshot, pending: reading, error: readError, refresh } = useLabwareSnapshot(labwareApi.getTipTrackingSnapshot, active, busy || totalPending > 0, validSnapshot);
  const families = snapshot?.families || [];
  const family = families.find(item => item.family_id === familyId) || families[0];
  const racks = useMemo(() => family ? [...family.left_racks, ...family.right_racks] : [], [family]);
  const currentPending = pending[family?.family_id || ''] || {};
  const count = Object.keys(currentPending).length;
  const canUpdate = Boolean(snapshot?.permissions.can_update);
  const rows = snapshot?.grid.rows || 8;
  const columns = snapshot?.grid.cols || 12;
  const positions = snapshot?.grid.positions_per_rack || rows * columns;
  const statuses = snapshot?.status_order || [];
  const unknown = snapshot?.unknown_status || 'unclear';
  const savedStatus = (rackId: string, tip: number) => family?.tips[rackId]?.[String(tip)] || unknown;
  const shownStatus = (rackId: string, tip: number) => currentPending[keyFor(rackId, tip)] ?? savedStatus(rackId, tip);
  useEffect(() => {
    if (!family) return;
    if (familyId !== family.family_id) setFamilyId(family.family_id);
    if (!racks.includes(rack)) { setRack(racks[0] || ''); setPosition(1); }
    if (!statuses.includes(statusChoice)) setStatusChoice(statuses[0] || unknown);
  }, [family, familyId, rack, racks, statuses, statusChoice, unknown]);

  const selectPosition = (next: number) => {
    if (!Number.isInteger(next) || next < 1 || next > positions) return;
    setPosition(next); setStatusChoice(shownStatus(rack, next));
  };
  const apply = () => {
    if (!family || !rack || !canUpdate || busyRef.current || reading) return;
    const first = scope === 'rack' ? 1 : scope === 'column' ? Math.floor((position - 1) / rows) * rows + 1 : position;
    const length = scope === 'rack' ? positions : scope === 'column' ? rows : 1;
    setPending(previous => {
      const edits = { ...previous[family.family_id] };
      for (let tip = first; tip < Math.min(first + length, positions + 1); tip++) {
        const key = keyFor(rack, tip);
        if (statusChoice === savedStatus(rack, tip)) delete edits[key]; else edits[key] = statusChoice;
      }
      return { ...previous, [family.family_id]: edits };
    });
    setWriteError(''); setNotice('');
  };
  const save = async () => {
    if (!family || !canUpdate || !count || busyRef.current) return;
    const submittedFamily = family.family_id;
    const submitted = { ...currentPending };
    const updates: TipTrackingUpdate[] = Object.entries(submitted).map(([key, status]) => {
      const [labware_id, position_id] = JSON.parse(key) as [string, number];
      return { labware_id, position_id, status };
    });
    busyRef.current = true; setBusy(true); setWriteError(''); setNotice('');
    try {
      await labwareApi.updateTipTracking(submittedFamily, updates);
      setSnapshot(previous => previous && ({ ...previous, families: previous.families.map(item => {
        if (item.family_id !== submittedFamily) return item;
        const tips = { ...item.tips };
        updates.forEach(edit => { tips[edit.labware_id] = { ...tips[edit.labware_id], [edit.position_id]: edit.status }; });
        return { ...item, tips };
      }) }));
      setPending(previous => {
        const remaining = { ...previous[submittedFamily] };
        Object.entries(submitted).forEach(([key, value]) => { if (remaining[key] === value) delete remaining[key]; });
        return { ...previous, [submittedFamily]: remaining };
      });
      setNotice('Changes saved.');
    } catch (error) { setWriteError(message(error)); }
    finally { busyRef.current = false; setBusy(false); }
  };
  const reset = async () => {
    setMenu(null);
    if (!family || !canUpdate || busyRef.current || totalPending || !window.confirm(`Reset ${family.display_name} to its default state?`)) return;
    busyRef.current = true; setBusy(true); setWriteError(''); setNotice('');
    try { await labwareApi.resetTipTracking(family.family_id); setNotice('Family reset.'); }
    catch (error) { setWriteError(message(error)); }
    finally { busyRef.current = false; setBusy(false); }
  };
  if (!snapshot) return readError ? <Alert severity="error" action={<Button onClick={() => void refresh()}>Retry</Button>}>{readError}</Alert> : <LinearProgress aria-label="Loading tips" />;
  if (!family) return <Alert severity="info" action={<Button onClick={() => void refresh()}>Refresh</Button>}>No tip families found.</Alert>;

  const selector = <Paper variant="outlined" sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'auto' }}>
    <Typography variant="subtitle2" sx={{ p: 1.5 }}>{racks.length} racks</Typography>
    <List aria-label="Tip racks" sx={{ flex: 1, minHeight: 120, overflow: 'auto', pt: 0 }}>
      {racks.map(rackId => {
        const summary = statuses.map(status => { const total = Array.from({ length: positions }, (_, i) => shownStatus(rackId, i + 1)).filter(value => value === status).length; return total ? `${total} ${status}` : ''; }).filter(Boolean).join(' · ');
        const edits = Object.keys(currentPending).filter(key => (JSON.parse(key) as [string, number])[0] === rackId).length;
        return <ListItemButton key={rackId} selected={rack === rackId} aria-current={rack === rackId ? 'true' : undefined} aria-label={`Open rack ${rackId}`} onClick={() => { setRack(rackId); setPosition(1); setRackOpen(true); setStatusChoice(shownStatus(rackId, 1)); }}>
          <ListItemText primary={rackId} secondary={`${family.left_racks.includes(rackId) ? 'Col A' : 'Col B'} · ${summary}${edits ? ` · ${edits} unsaved` : ''}`} primaryTypographyProps={{ sx: { overflowWrap: 'anywhere' } }} />
        </ListItemButton>;
      })}
    </List>
  </Paper>;
  const editDisabled = busy || reading;
  const tipButton = (tip: number, spatial: boolean) => {
    const status = shownStatus(rack, tip);
    const unsaved = Object.prototype.hasOwnProperty.call(currentPending, keyFor(rack, tip));
    return <Button key={tip} data-tip={tip} aria-label={`Tip ${tip}, ${status}`} aria-pressed={position === tip} variant={position === tip ? 'contained' : 'outlined'} tabIndex={spatial && position !== tip ? -1 : 0} onClick={() => selectPosition(tip)} onKeyDown={event => {
      if (!spatial) return;
      if ((event.key === 'ArrowDown' && tip % rows === 0) || (event.key === 'ArrowUp' && (tip - 1) % rows === 0)) { event.preventDefault(); return; }
      const next = event.key === 'ArrowDown' ? tip + 1 : event.key === 'ArrowUp' ? tip - 1 : event.key === 'ArrowRight' ? tip + rows : event.key === 'ArrowLeft' ? tip - rows : event.key === 'Home' ? 1 : event.key === 'End' ? positions : null;
      if (next === null) return;
      event.preventDefault();
      if (next < 1 || next > positions) return;
      selectPosition(next); map.current?.querySelector<HTMLButtonElement>(`[data-tip="${next}"]`)?.focus();
    }} sx={{ minWidth: 44, minHeight: 44, px: 0.5, gap: 0.5, justifyContent: spatial ? 'center' : 'flex-start', gridColumn: spatial ? Math.floor((tip - 1) / rows) + 1 : undefined, gridRow: spatial ? ((tip - 1) % rows) + 1 : undefined, borderStyle: unsaved ? 'dashed' : 'solid' }}>
      <Box component="span" aria-hidden="true" sx={{ width: 10, height: 10, flexShrink: 0, borderRadius: '50%', bgcolor: snapshot.status_colors[status] || 'text.disabled', border: 1, borderColor: position === tip ? 'primary.contrastText' : 'divider' }} />
      {spatial ? `${tip}${unsaved ? '*' : ''}` : `Tip ${tip} · ${status}${unsaved ? ' · Unsaved' : ''}`}
    </Button>;
  };
  return <Stack spacing={1} sx={{ minWidth: 0 }}>
    <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
      <TextField select size="small" label="Tip family" value={family.family_id} disabled={busy} onChange={event => { setFamilyId(event.target.value); setRack(''); setRackOpen(false); }} sx={{ minWidth: 190, maxWidth: '100%' }}>
        {families.map(item => <MenuItem key={item.family_id} value={item.family_id}>{item.display_name}{Object.keys(pending[item.family_id] || {}).length ? ' · Unsaved' : ''}</MenuItem>)}
      </TextField>
      <Button onClick={() => void refresh()} disabled={busy || reading || totalPending > 0}>Refresh</Button>
      {canUpdate ? <>
        <Button variant="contained" onClick={() => void save()} disabled={busy || !count}>Save changes ({count})</Button>
        {count > 0 && <Button disabled={busy} onClick={() => { setPending(previous => ({ ...previous, [family.family_id]: {} })); setWriteError(''); }}>Discard</Button>}
        <Button aria-haspopup="menu" aria-label="More tip options" onClick={event => setMenu(event.currentTarget)} disabled={busy}>More</Button>
      </> : <Chip label="Read only" size="small" />}
    </Stack>
    {(readError || writeError) && <Alert severity="error" action={!totalPending && !busy ? <Button onClick={() => void refresh()}>Retry</Button> : undefined}>{writeError || readError}{readError && ' Previous data is shown.'}</Alert>}
    <Typography variant="caption" color="text.secondary" role="status">{busy ? 'Saving…' : totalPending ? `Refresh paused · ${totalPending} unsaved${totalPending > count ? ` (${totalPending - count} in other families)` : ''}` : notice || `Updated ${new Date(snapshot.refreshed_at).toLocaleTimeString()}`}</Typography>
    {reading && <LinearProgress aria-label="Refreshing tips" />}
    <InspectionWorkspace label="Tip workspace" selector={selector} selectorLabel="Racks" detailOpen={rackOpen} onBack={() => setRackOpen(false)}>
      {rack ? <Paper variant="outlined" sx={{ p: 1.5, minHeight: 0, overflow: 'auto', flex: 1, containerType: 'inline-size', containerName: 'rack' }}>
        <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" sx={{ mb: 1 }}>
          <Typography component="h2" variant="h6" sx={{ mr: 'auto', overflowWrap: 'anywhere' }}>{rack}</Typography>
          <ToggleButtonGroup size="small" exclusive value={view} onChange={(_, value) => value && setView(value)} aria-label="Tip view"><ToggleButton value="map">Map</ToggleButton><ToggleButton value="list">List</ToggleButton></ToggleButtonGroup>
        </Stack>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 1.5, '@container rack (min-width: 880px)': { gridTemplateColumns: 'minmax(0, 1fr) 250px' } }}>
          <Paper variant="outlined" sx={{ p: 1.5, minWidth: 0, '@container rack (min-width: 880px)': { gridColumn: 2, gridRow: 1 } }}>
            <Stack gap={1}>
              <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap"><TextField type="number" size="small" label="Tip position" value={position} onChange={event => selectPosition(Number(event.target.value))} inputProps={{ min: 1, max: positions }} sx={{ width: 112 }} /><Typography>{shownStatus(rack, position)}</Typography></Stack>
              {canUpdate && <>
                <TextField select size="small" label="New status" value={statusChoice} disabled={editDisabled} onChange={event => setStatusChoice(event.target.value)}>{statuses.map(status => <MenuItem key={status} value={status}>{status}</MenuItem>)}</TextField>
                <TextField select size="small" label="Apply to" value={scope} disabled={editDisabled} onChange={event => setScope(event.target.value)}><MenuItem value="tip">This tip</MenuItem><MenuItem value="column">Column ({rows} tips)</MenuItem><MenuItem value="rack">Whole rack ({positions} tips)</MenuItem></TextField>
                <Button onClick={apply} disabled={editDisabled} variant="outlined">Apply status</Button>
              </>}
            </Stack>
          </Paper>
          <Box sx={{ minWidth: 0, '@container rack (min-width: 880px)': { gridColumn: 1, gridRow: 1 } }}>
            <Box ref={map} role="group" aria-label={`${rack} tips`} sx={view === 'map' ? { overflow: 'auto', pb: 1 } : { display: 'grid', gap: 0.5, maxHeight: 420, overflow: 'auto' }}>
              {view === 'map' ? <Box sx={{ display: 'grid', gridTemplateColumns: `repeat(${columns}, minmax(44px, 1fr))`, gridTemplateRows: `repeat(${rows}, 44px)`, gap: 0.5, minWidth: columns * 48 - 4 }}>{Array.from({ length: positions }, (_, index) => tipButton(index + 1, true))}</Box> : Array.from({ length: positions }, (_, index) => tipButton(index + 1, false))}
            </Box>
            {view === 'map' && <Typography variant="caption" color="text.secondary">Arrow keys move between tips. * Unsaved</Typography>}
            <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1 }} aria-label="Tip status legend">{statuses.map(status => <Stack key={status} direction="row" gap={0.5} alignItems="center"><Box aria-hidden="true" sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: snapshot.status_colors[status] || 'text.disabled', border: 1, borderColor: 'divider' }} /><Typography variant="caption">{status}</Typography></Stack>)}</Stack>
          </Box>
        </Box>
      </Paper> : <Alert severity="info">No racks found.</Alert>}
    </InspectionWorkspace>
    <Menu anchorEl={menu} open={Boolean(menu)} onClose={() => setMenu(null)}><MenuItem disabled={busy || totalPending > 0} onClick={() => void reset()}>Reset family</MenuItem></Menu>
  </Stack>;
}
