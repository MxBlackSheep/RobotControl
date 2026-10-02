import { useEffect, useState } from 'react';
import { Alert, Box, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { api } from '../services/api';
import ReportConnections, { AssignConnections, PackageBinding, readingLabel, Source } from './ReportConnections';
import { requestMessage } from './ReportInputs';

const base = '/api/database/tools';
export default function DatabaseSettings({ active }: { active: boolean }) {
  const [sources, setSources] = useState<Source[]>([]), [assignments, setAssignments] = useState<PackageBinding[]>([]);
  const [connections, setConnections] = useState(false), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [binding, setBinding] = useState<PackageBinding>();
  const [viewer, setViewer] = useState(''), [savedViewer, setSavedViewer] = useState('');
  const load = async (signal?: AbortSignal) => {
    const [profiles, packages] = await Promise.all([api.get(`${base}/sources`, {signal}), api.get(`${base}/packages`, {signal})]);
    const bindings = await Promise.all(packages.data.map(async (p: any) => ({ id:p.id, name:p.name, ...(await api.get(`${base}/packages/${p.id}/sources`, {signal})).data })));
    if (signal?.aborted) return;
    setSources(profiles.data); setAssignments(bindings);
    const selected = await api.get(`${base}/viewer-sources`, {signal});
    if (signal?.aborted) return;
    setViewer(selected.data[0]?.id || ''); setSavedViewer(selected.data[0]?.id || '');
  };
  useEffect(() => { if (!active) return; const c = new AbortController(); void load(c.signal).catch(e => { if (!c.signal.aborted) setError(requestMessage(e)); }); return () => c.abort(); }, [active]);
  const work = async (fn: () => Promise<void>) => { setBusy(true); setError(''); try { await fn(); } catch(e) { setError(requestMessage(e)); } finally { setBusy(false); } };
  const uses = (id: string) => assignments.filter(a => a.operation_source === id || Object.values(a.mappings).includes(id)).map(a => a.name);
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
      {assignments.map(a => <Stack key={a.id} direction="row" gap={1} justifyContent="space-between" alignItems="center" sx={{py:1}}><Box><Typography>{a.name}</Typography><Typography variant="body2" color="text.secondary">{[...a.aliases.map(alias => `${readingLabel(a.aliases, alias)}: ${sources.find(s => s.id === a.mappings[alias])?.name || 'Not configured'}`), ...(a.has_operation ? [`Writing connection: ${sources.find(s => s.id === a.operation_source)?.name || 'Not configured'}`] : [])].join(' · ') || 'No database required'}</Typography></Box><Button disabled={busy} onClick={() => setBinding({...a, mappings:{...a.mappings}})}>Assign</Button></Stack>)}
    </Paper>
    <ReportConnections open={connections} onClose={() => { setConnections(false); void work(() => load()); }} />
    <AssignConnections binding={binding} sources={sources} onChange={setBinding} onClose={() => setBinding(undefined)} onManage={() => setConnections(true)}
      onSaved={() => { setBinding(undefined); void work(() => load()); }} />
  </Stack>;
}
