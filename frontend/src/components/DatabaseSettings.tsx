import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { api } from '../services/api';
import ReportConnections, { Source, SourceMappings } from './ReportConnections';
import { requestMessage } from './ReportInputs';

const base = '/api/database/tools';
type Assignment = { id: string; name: string; aliases: string[]; mappings: Record<string,string>; has_operation: boolean; operation_source?: string };
type Config = { adapter: string; source_id?: string; sqlite_path?: string };
export default function DatabaseSettings({ active }: { active: boolean }) {
  const [sources, setSources] = useState<Source[]>([]), [assignments, setAssignments] = useState<Assignment[]>([]);
  const [connections, setConnections] = useState(false), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [lab, setLab] = useState<any>(), [config, setConfig] = useState<Config>({adapter:'evoyeast'});
  const [review, setReview] = useState<any>(), [binding, setBinding] = useState<Assignment>();
  const [viewer, setViewer] = useState(''), [savedViewer, setSavedViewer] = useState(''), [changeLab, setChangeLab] = useState(false);
  const load = async (signal?: AbortSignal) => {
    const [profiles, packages] = await Promise.all([api.get(`${base}/sources`, {signal}), api.get(`${base}/packages`, {signal})]);
    const bindings = await Promise.all(packages.data.map(async (p: any) => ({ id:p.id, name:p.name, ...(await api.get(`${base}/packages/${p.id}/sources`, {signal})).data })));
    if (signal?.aborted) return;
    setSources(profiles.data); setAssignments(bindings);
    const selected = await api.get(`${base}/viewer-sources`, {signal});
    if (signal?.aborted) return;
    setViewer(selected.data[0]?.id || ''); setSavedViewer(selected.data[0]?.id || '');
    try { const r = await api.get(`${base}/scheduling-settings`, {signal}); if (!signal?.aborted) { setLab(r.data); setConfig(r.data.saved); } }
    catch (e) { if (!signal?.aborted) setError(requestMessage(e)); }
  };
  useEffect(() => { if (!active) return; const c = new AbortController(); void load(c.signal).catch(e => { if (!c.signal.aborted) setError(requestMessage(e)); }); return () => c.abort(); }, [active]);
  const work = async (fn: () => Promise<void>) => { setBusy(true); setError(''); try { await fn(); } catch(e) { setError(requestMessage(e)); } finally { setBusy(false); } };
  const uses = (id: string) => assignments.filter(a => a.operation_source === id || Object.values(a.mappings).includes(id)).map(a => a.name)
    .concat(lab?.active?.source_id === id ? ['Scheduling (active)'] : [], lab?.pending && lab?.saved?.source_id === id ? ['Scheduling (after restart)'] : []);
  return <Stack spacing={2}>
    <Stack direction="row" justifyContent="space-between" flexWrap="wrap" gap={1}><Typography variant="h6">Database settings</Typography><Button disabled={busy} onClick={() => void work(() => load())}>Refresh</Button></Stack>
    {error && <Alert severity="error">{error}</Alert>}
    <Paper variant="outlined" sx={{p:2}}><Stack spacing={1}>
      <Stack direction="row" justifyContent="space-between" flexWrap="wrap"><Typography variant="h6">Connections</Typography><Button disabled={busy} onClick={() => setConnections(true)}>Manage connections</Button></Stack>
      {sources.map(s => <Box key={s.id} sx={{py:1, borderBottom:1, borderColor:'divider', overflowWrap:'anywhere'}}><Typography fontWeight={600}>{s.name}</Typography><Typography variant="body2">{s.server} / {s.database} · {s.access === 'operation' ? 'Database changes' : 'Read-only'}</Typography><Typography variant="body2" color="text.secondary">{[...(savedViewer === s.id ? ['Tables and Stored procedures'] : []), ...uses(s.id)].join(' · ') || 'Not assigned'}</Typography></Box>)}
      {!sources.length && <Typography>No connections configured.</Typography>}
    </Stack></Paper>
    <Paper variant="outlined" sx={{p:2}}><Stack spacing={2}><Typography variant="h6">Tables and Stored procedures</Typography>
      <TextField select size="small" label="Viewer database" value={viewer} disabled={busy} onChange={e => setViewer(e.target.value)}>
        {sources.filter(s => s.access !== 'operation').map(s => <MenuItem key={s.id} value={s.id}>{s.name} · {s.database}</MenuItem>)}
      </TextField><Button sx={{alignSelf:'flex-start'}} disabled={busy || !viewer || viewer === savedViewer} onClick={() => void work(async () => { await api.put(`${base}/viewer-source`, {source_id:viewer}); setSavedViewer(viewer); })}>Save viewer database</Button>
    </Stack></Paper>
    <Paper variant="outlined" sx={{p:2}}><Typography variant="h6">Package connections</Typography>
      {assignments.map(a => <Stack key={a.id} direction="row" gap={1} justifyContent="space-between" alignItems="center" sx={{py:1}}><Box><Typography>{a.name}</Typography><Typography variant="body2" color="text.secondary">{[...a.aliases.map(alias => `${alias}: ${sources.find(s => s.id === a.mappings[alias])?.name || 'Not configured'}`), ...(a.has_operation ? [`Operations: ${sources.find(s => s.id === a.operation_source)?.name || 'Not configured'}`] : [])].join(' · ') || 'No database required'}</Typography></Box><Button disabled={busy} onClick={() => setBinding({...a, mappings:{...a.mappings}})}>Assign</Button></Stack>)}
    </Paper>
    <Paper variant="outlined" sx={{p:2}}><Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between"><Typography variant="h6">Schedule preparation</Typography><Button disabled={busy} onClick={() => { setChangeLab(v => !v); setConfig(lab?.saved || {adapter:'evoyeast'}); setReview(undefined); }}>{changeLab ? 'Cancel editing' : 'Change setup'}</Button></Stack>
      {lab ? <>
        <Typography>Active now: {lab.active.adapter === 'evoyeast' ? 'EvoYeast' : 'Batch (SQLite)'} · {lab.target.server ? `${lab.target.server} / ` : ''}{lab.target.database}</Typography>
        {lab.pending && <Alert severity="info" action={<Button disabled={busy} onClick={() => void work(async () => { const r = await api.post(`${base}/scheduling-settings/cancel`, {revision:lab.revision}); setLab(r.data); setConfig(r.data.saved); setReview(undefined); })}>Cancel change</Button>}>Saved; restart required. Active settings above still apply.</Alert>}
        <Typography variant="body2" color="text.secondary">Choose the experiment and preparation steps in each schedule.</Typography>
        {changeLab && <>
        <Box component="details"><Typography component="summary">Advanced: preparation rules</Typography><TextField fullWidth sx={{mt:1}} select size="small" label="Preparation rules" value={config.adapter} disabled={busy} onChange={e => { setConfig({adapter:e.target.value}); setReview(undefined); }}>
          <MenuItem value="evoyeast">EvoYeast (SQL Server)</MenuItem><MenuItem value="batch-sqlite">Batch (SQLite)</MenuItem></TextField>
        </Box>
        {config.adapter === 'evoyeast' ? <TextField select size="small" label="Laboratory database" value={config.source_id || '__existing'} disabled={busy} onChange={e => { setConfig({adapter:'evoyeast', ...(e.target.value !== '__existing' ? {source_id:e.target.value} : {})}); setReview(undefined); }}>
          <MenuItem value="__existing">Existing laboratory connection</MenuItem>{sources.filter(s => s.access === 'operation').map(s => <MenuItem key={s.id} value={s.id}>{s.name} · {s.server} / {s.database}</MenuItem>)}</TextField>
          : <TextField size="small" label="Laboratory SQLite file" value={config.sqlite_path || ''} disabled={busy} onChange={e => { setConfig({adapter:'batch-sqlite', sqlite_path:e.target.value}); setReview(undefined); }} />}
        <Typography variant="body2" color="text.secondary">Changing the setup does not convert existing schedules.</Typography>
        <Button variant="outlined" disabled={busy} sx={{alignSelf:'flex-start'}} onClick={() => void work(async () => { const r = await api.post(`${base}/scheduling-settings/review`, config, {timeout:30000}); setReview(r.data); })}>Check and review</Button>
        </>}
      </> : <Typography>Scheduling settings are unavailable.</Typography>}
    </Stack></Paper>
    <ReportConnections open={connections} onClose={() => { setConnections(false); void work(() => load()); }} />
    <Dialog open={!!binding} onClose={() => !busy && setBinding(undefined)} fullWidth maxWidth="sm"><DialogTitle>Assign connections — {binding?.name}</DialogTitle><DialogContent><Stack spacing={2} sx={{pt:1}}>
      {error && <Alert severity="error">{error}</Alert>}
      {binding?.has_operation && <TextField select label="Operation target" value={binding.operation_source || ''} onChange={e => setBinding({...binding, operation_source:e.target.value})} disabled={busy}><MenuItem value="">Not configured</MenuItem>{sources.filter(s => s.access === 'operation').map(s => <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>)}</TextField>}
      {binding && <SourceMappings aliases={binding.aliases} sources={sources} mappings={binding.mappings} disabled={busy} onChange={mappings => setBinding({...binding,mappings})} />}
    </Stack></DialogContent><DialogActions><Button disabled={busy} onClick={() => setBinding(undefined)}>Cancel</Button><Button disabled={busy} onClick={() => void work(async () => { await api.put(`${base}/packages/${binding!.id}/sources`, {mappings:binding!.mappings, operation_source:binding!.operation_source || null}); setBinding(undefined); await load(); })}>Save assignments</Button></DialogActions></Dialog>
    <Dialog open={!!review} onClose={() => !busy && setReview(undefined)} fullWidth maxWidth="sm"><DialogTitle>Review scheduling database</DialogTitle><DialogContent><Stack spacing={2}>
      {error && <Alert severity="error">{error}</Alert>}<Typography>{review?.target?.server} {review?.target?.database}</Typography><Typography>{review?.message}</Typography>
      <Typography>Disable schedules and finish queued work or recovery before saving. After restart, review schedules for the selected database.</Typography>
      <Box sx={{maxHeight:220,overflow:'auto'}}>{review?.schedules?.map((s:any) => <Typography key={s.id} variant="body2">{s.name} · {s.active ? 'Active — disable before saving' : 'Disabled — binding retained'}</Typography>)}{!review?.schedules?.length && <Typography>No saved schedules.</Typography>}</Box>
    </Stack></DialogContent><DialogActions><Button disabled={busy} onClick={() => setReview(undefined)}>Back</Button><Button variant="contained" disabled={busy || review?.schedules?.some((s:any) => s.active)} onClick={() => void work(async () => { const r = await api.post(`${base}/scheduling-settings/apply`, {token:review.token}); setLab(r.data); setConfig(r.data.saved); setReview(undefined); })}>Save for restart</Button></DialogActions></Dialog>
  </Stack>;
}
