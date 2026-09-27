import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, Dialog, DialogContent, DialogTitle, LinearProgress, Menu, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { labwareApi, TipTrackingSnapshot, TipTrackingUpdate } from '../../services/labwareApi';
import { useLabwareSnapshot } from './useLabwareSnapshot';
import { useLabwareWorkspace } from './useLabwareWorkspace';
import TipDeckOverview from './TipDeckOverview';
import TipRackEditor from './TipRackEditor';

type Pending = Record<string, Record<string, string>>;
type Stroke = Record<string, string | undefined>;
const keyFor = (rack: string, position: number) => JSON.stringify([rack, position]);
const message = (error: any) => error?.response?.data?.error?.message || error?.response?.data?.message || error?.message || 'Unable to save changes.';
const stringArray = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string');
const validSnapshot = (value: TipTrackingSnapshot) => Boolean(value &&
  typeof value.permissions?.can_update === 'boolean' && value.grid &&
  [value.grid.rows, value.grid.cols, value.grid.positions_per_rack].every(size => Number.isInteger(size) && size > 0) &&
  value.grid.rows * value.grid.cols === value.grid.positions_per_rack &&
  stringArray(value.status_order) && typeof value.unknown_status === 'string' && value.status_colors &&
  Array.isArray(value.families) && value.families.every(family => family &&
    typeof family.family_id === 'string' && typeof family.display_name === 'string' &&
    stringArray(family.left_racks) && stringArray(family.right_racks) && family.tips && typeof family.tips === 'object'));

export default function TipTrackingPanel({ active = true }: { active?: boolean }) {
  const [familyId, setFamilyId] = useState('');
  const [selectedRacks, setSelectedRacks] = useState<Record<string, string>>({});
  const [selectedTips, setSelectedTips] = useState<Record<string, number>>({});
  const [rackOpen, setRackOpen] = useState(false);
  const [paint, setPaint] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending>({});
  const [history, setHistory] = useState<Record<string, Stroke[]>>({});
  const [gesture, setGesture] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [writeError, setWriteError] = useState('');
  const [notice, setNotice] = useState('');
  const [menu, setMenu] = useState<HTMLElement | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const totalPending = Object.values(pending).reduce((total, entries) => total + Object.keys(entries).length, 0);
  const { snapshot, setSnapshot, pending: reading, error: readError, refresh, suspend } = useLabwareSnapshot(labwareApi.getTipTrackingSnapshot, active, busy || totalPending > 0 || gesture, validSnapshot);
  const workspace = useLabwareWorkspace(active, Boolean(snapshot));
  const families = snapshot?.families || [];
  const family = families.find(item => item.family_id === familyId) || families[0];
  const racks = useMemo(() => family ? [...family.left_racks, ...family.right_racks] : [], [family]);
  const rack = family && racks.includes(selectedRacks[family.family_id]) ? selectedRacks[family.family_id] : racks[0] || '';
  const position = selectedTips[`${family?.family_id}:${rack}`] || 1;
  const currentPending = pending[family?.family_id || ''] || {};
  const count = Object.keys(currentPending).length;
  const canUpdate = Boolean(snapshot?.permissions.can_update);
  const rows = snapshot?.grid.rows || 8;
  const columns = snapshot?.grid.cols || 12;
  const editorMinimum = columns * 44 + (columns - 1) * 4 + 24;
  const narrow = workspace.width < 320 + editorMinimum;
  const statuses = snapshot?.status_order || [];
  const unknown = snapshot?.unknown_status || 'unclear';
  const savedStatus = (rackId: string, tip: number) => family?.tips[rackId]?.[String(tip)] || unknown;
  const shownStatus = (rackId: string, tip: number) => currentPending[keyFor(rackId, tip)] ?? savedStatus(rackId, tip);

  useEffect(() => {
    if (family && familyId !== family.family_id) setFamilyId(family.family_id);
    if (paint && !statuses.includes(paint)) setPaint(null);
  }, [family, familyId, paint, statuses]);
  useEffect(() => { setGesture(false); }, [familyId, rack, active, narrow, rackOpen]);

  const apply = (tips: number[], status: string) => {
    if (!active || (narrow && !rackOpen) || !family || !rack || !canUpdate || busyRef.current || !statuses.includes(status)) return;
    const edits = { ...currentPending };
    const before: Stroke = {};
    tips.forEach(tip => {
      if (!Number.isInteger(tip) || tip < 1 || tip > rows * columns) return;
      const key = keyFor(rack, tip);
      const next = status === savedStatus(rack, tip) ? undefined : status;
      if (edits[key] === next) return;
      before[key] = edits[key];
      if (next === undefined) delete edits[key]; else edits[key] = next;
    });
    if (!Object.keys(before).length) return;
    suspend();
    setPending(previous => ({ ...previous, [family.family_id]: edits }));
    setHistory(previous => ({ ...previous, [family.family_id]: [...(previous[family.family_id] || []), before] }));
    setWriteError(''); setNotice('');
  };
  const undo = () => {
    if (!family || busyRef.current || gesture || !canUpdate) return;
    const strokes = history[family.family_id] || [];
    const last = strokes[strokes.length - 1]; if (!last) return;
    suspend();
    const restored = { ...currentPending };
    Object.entries(last).forEach(([key, value]) => { if (value === undefined) delete restored[key]; else restored[key] = value; });
    setPending(previous => ({ ...previous, [family.family_id]: restored }));
    setHistory(previous => ({ ...previous, [family.family_id]: strokes.slice(0, -1) }));
    setWriteError(''); setNotice('Last change undone.');
  };
  const save = async () => {
    if (!family || !canUpdate || !count || busyRef.current || gesture) return;
    const submittedFamily = family.family_id;
    const submitted = { ...currentPending };
    const updates: TipTrackingUpdate[] = Object.entries(submitted).map(([key, status]) => {
      const [labware_id, position_id] = JSON.parse(key) as [string, number];
      return { labware_id, position_id, status };
    });
    suspend(); busyRef.current = true; setBusy(true); setWriteError(''); setNotice('');
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
      setHistory(previous => ({ ...previous, [submittedFamily]: [] })); setNotice('Changes saved.');
    } catch (error) { setWriteError(message(error)); }
    finally { busyRef.current = false; setBusy(false); }
  };
  const reset = async () => {
    setMenu(null);
    if (!family || !canUpdate || busyRef.current || totalPending || gesture || !window.confirm(`Reset ${family.display_name} to its default state?`)) return;
    suspend(); busyRef.current = true; setBusy(true); setWriteError(''); setNotice('');
    try { await labwareApi.resetTipTracking(family.family_id); setHistory(previous => ({ ...previous, [family.family_id]: [] })); setNotice('Family reset.'); }
    catch (error) { setWriteError(message(error)); }
    finally { busyRef.current = false; setBusy(false); }
  };

  if (!snapshot) return readError ? <Alert severity="error" action={<Button onClick={() => void refresh()}>Retry</Button>}>{readError}</Alert> : <LinearProgress aria-label="Loading tips" />;
  if (!family) return <Alert severity="info" action={<Button onClick={() => void refresh()}>Refresh</Button>}>No tip families found.</Alert>;

  const actions = <Stack gap={0.5}>
    <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
      <TextField select size="small" label="Tip family" value={family.family_id} disabled={busy} onChange={event => { setFamilyId(event.target.value); setRackOpen(false); }} SelectProps={{ SelectDisplayProps: { 'aria-label': 'Tip family', 'aria-labelledby': undefined } }} sx={{ minWidth: 160, maxWidth: '100%' }}>
        {families.map(item => <MenuItem key={item.family_id} value={item.family_id}>{item.display_name}{Object.keys(pending[item.family_id] || {}).length ? ' · Unsaved' : ''}</MenuItem>)}
      </TextField>
      <Button onClick={() => void refresh()} disabled={busy || totalPending > 0 || gesture}>Refresh</Button>
      {canUpdate ? <>
        <Button variant="contained" onClick={() => void save()} disabled={busy || !count || gesture}>Save changes ({count})</Button>
        <Button onClick={undo} disabled={busy || gesture || !(history[family.family_id]?.length)}>Undo</Button>
        {count > 0 && <Button disabled={busy || gesture} onClick={() => { setPending(previous => ({ ...previous, [family.family_id]: {} })); setHistory(previous => ({ ...previous, [family.family_id]: [] })); setWriteError(''); }}>Discard</Button>}
        <Button aria-haspopup="menu" aria-label="More tip options" onClick={event => setMenu(event.currentTarget)} disabled={busy || gesture}>More</Button>
      </> : <Chip label="Read only" size="small" />}
    </Stack>
    {(readError || writeError) && <Alert severity="error" action={!totalPending && !busy && !gesture ? <Button onClick={() => void refresh()}>Retry</Button> : undefined}>{writeError || readError}{readError && ' Previous data is shown.'}</Alert>}
    <Typography variant="caption" color="text.secondary" role="status" sx={{ minHeight: 20 }}>{busy ? 'Saving…' : gesture ? 'Selection in progress' : totalPending ? `${totalPending} unsaved${totalPending > count ? ` (${totalPending - count} in other families)` : ''}` : reading ? 'Updating…' : notice || `Updated ${new Date(snapshot.refreshed_at).toLocaleTimeString()}`}</Typography>
  </Stack>;
  const editor = rack ? <TipRackEditor rack={rack} headingId="selected-tip-rack-heading" joined={!narrow} side={family.left_racks.includes(rack) ? 'Col A' : 'Col B'} rows={rows} columns={columns} position={position} statuses={statuses} colors={snapshot.status_colors}
    statusAt={tip => shownStatus(rack, tip)} pendingAt={tip => Object.prototype.hasOwnProperty.call(currentPending, keyFor(rack, tip))}
    canUpdate={canUpdate} disabled={busy} active={active && (!narrow || rackOpen)} paint={paint} onPaintChange={setPaint}
    onSelect={tip => setSelectedTips(previous => ({ ...previous, [`${family.family_id}:${rack}`]: tip }))} onApply={apply} onGestureChange={selecting => { if (selecting) suspend(); setGesture(selecting); }} /> : <Alert severity="info">No racks found.</Alert>;

  return <Box ref={container} sx={{ minWidth: 0, width: '100%' }}>
    <Stack gap={1}>
      {actions}
      <Paper ref={workspace.ref} data-tip-workspace variant="outlined" sx={{ width: '100%', minWidth: 0, height: narrow ? 'auto' : Math.max(240, workspace.height), borderRadius: 2, overflowX: 'hidden', overflowY: narrow ? 'visible' : 'auto' }}>
        <Box sx={{ display: 'grid', minHeight: narrow ? undefined : '100%', gridTemplateColumns: narrow ? 'minmax(0, 1fr)' : `clamp(320px, calc(100% - ${editorMinimum}px), 40%) minmax(0, 1fr)`, gridTemplateRows: 'auto minmax(min-content, 1fr) auto' }}>
        <TipDeckOverview family={family} joined={!narrow} rows={rows} columns={columns} selected={rack} statuses={statuses} colors={snapshot.status_colors} statusAt={shownStatus}
          pendingAt={rackId => Object.keys(currentPending).filter(key => (JSON.parse(key) as [string, number])[0] === rackId).length}
          onOpen={rackId => { setSelectedRacks(previous => ({ ...previous, [family.family_id]: rackId })); setRackOpen(true); }} />
        {!narrow && editor}
        </Box>
      </Paper>
    </Stack>
    <Dialog open={narrow && rackOpen && active} fullScreen aria-labelledby="selected-tip-rack-heading" onClose={() => setRackOpen(false)} PaperProps={{ sx: { height: '100dvh', maxHeight: '100dvh' } }} TransitionProps={{ onExited: () => container.current?.querySelector<HTMLButtonElement>('[aria-current="true"]')?.focus({ preventScroll: true }) }}>
      <DialogTitle id="tip-rack-dialog-actions" sx={{ p: 1 }}><Stack direction="row" gap={1} justifyContent="space-between" flexWrap="wrap"><Button onClick={() => setRackOpen(false)}>Back to deck</Button>{canUpdate && <Button variant="contained" onClick={() => void save()} disabled={busy || !count || gesture}>Save changes ({count})</Button>}</Stack></DialogTitle>
      <DialogContent sx={{ p: 1, minWidth: 0, overflow: 'auto' }}><Stack gap={1}>
        {canUpdate && <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap"><Button onClick={undo} disabled={busy || gesture || !(history[family.family_id]?.length)}>Undo</Button>{count > 0 && <Button disabled={busy || gesture} onClick={() => { setPending(previous => ({ ...previous, [family.family_id]: {} })); setHistory(previous => ({ ...previous, [family.family_id]: [] })); setWriteError(''); }}>Discard</Button>}<Typography variant="caption" color="text.secondary" role="status">{busy ? 'Saving…' : gesture ? 'Selection in progress' : totalPending ? `${totalPending} unsaved${totalPending > count ? ` (${totalPending - count} in other families)` : ''}` : reading ? 'Updating…' : notice}</Typography></Stack>}
        {(readError || writeError) && <Alert severity="error">{writeError || readError}{readError && ' Previous data is shown.'}</Alert>}
        {editor}
      </Stack></DialogContent>
    </Dialog>
    <Menu anchorEl={menu} open={Boolean(menu)} onClose={() => setMenu(null)}><MenuItem disabled={busy || totalPending > 0 || gesture} onClick={() => void reset()}>Reset family</MenuItem></Menu>
  </Box>;
}
