import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Autocomplete, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControlLabel, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { api } from '../services/api';

const base = '/api/database/tools';
type Field = { name: string; label: string; type: string; required: boolean; choices: string[] };
type Tool = { id: string; name: string; kind: string; package_version: string; inputs: Field[] };
type Preview = { token: string; confirmation: string; summary: string; details: Record<string, unknown> };
type Job = { id: string; status: string; filename?: string; error?: string };
const message = (error: any) => {
  const value = error?.response?.data?.detail || error?.message || 'Request failed.';
  return typeof value === 'string' ? value : 'The request could not be completed.';
};

function ExperimentInput({ label, value, onChange, disabled }: { label: string; value: unknown; onChange: (value: number | null) => void; disabled: boolean }) {
  const [query, setQuery] = useState('');
  const [options, setOptions] = useState<{ id: number; label: string }[]>([]);
  const [selected, setSelected] = useState<{ id: number; label: string } | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (!value) setSelected(null); }, [value]);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const { data } = await api.get(`${base}/experiments`, { params: { search: query, page }, signal: controller.signal });
        if (controller.signal.aborted) return;
        const values = data.rows.map((row: any) => ({ id: row.ExperimentID,
          label: [row.ExperimentID, row.UserDefinedID, row.Note].filter(v => v !== undefined && v !== null && v !== '').join(' · ') }));
        setOptions(old => page === 1 ? values : [...old, ...values]);
        setTotal(data.total_count); setError('');
      } catch (error) { if (!controller.signal.aborted) setError(message(error)); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, page]);
  return <Stack spacing={1}>
    <Autocomplete options={options} value={selected} disabled={disabled} loading={loading}
      filterOptions={values => values} isOptionEqualToValue={(a, b) => a.id === b.id}
      onInputChange={(_, text, reason) => { if (reason === 'input' || reason === 'clear') { setQuery(text); setPage(1); } }}
      onChange={(_, option) => { setSelected(option); onChange(option?.id ?? null); }}
      renderInput={params => <TextField {...params} label={label} required size="small" />} />
    {options.length < total && <Button disabled={disabled || loading} onClick={() => setPage(old => old + 1)}>Load more experiments</Button>}
    {error && <Alert severity="error">{error}</Alert>}
  </Stack>;
}

export default function DatabaseTools({ kind, active }: { kind: 'operation' | 'report'; active: boolean }) {
  const [tools, setTools] = useState<Tool[]>([]);
  const [selected, setSelected] = useState('');
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmation, setConfirmation] = useState('');
  const [job, setJob] = useState<Job | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const generation = useRef(0);
  const tool = tools.find(item => item.id === selected);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    api.get(`${base}/catalogue`, { params: { kind }, signal: controller.signal }).then(({ data }) => {
      setTools(data); setSelected(old => data.some((item: Tool) => item.id === old) ? old : data[0]?.id || '');
    }).catch(error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [active, kind]);
  useEffect(() => () => { generation.current++; }, []);
  useEffect(() => {
    if (!active || !job || !['pending', 'running'].includes(job.status)) return;
    let stopped = false;
    let timer: number;
    const poll = async () => {
      try {
        const { data } = await api.get(`${base}/reports/${job.id}`);
        if (!stopped) { setJob(data); setError(''); }
      } catch (error) { if (!stopped) setError(message(error)); }
      if (!stopped) timer = window.setTimeout(poll, 1500);
    };
    timer = window.setTimeout(poll, 500);
    return () => { stopped = true; clearTimeout(timer); };
  }, [job?.id, job?.status, active]);
  const changeValue = (name: string, value: unknown) => {
    setValues(old => ({ ...old, [name]: value })); setJob(null); setNotice('');
  };
  const prepare = async () => {
    const id = ++generation.current;
    setBusy(true); setError(''); setNotice('');
    try {
      const inputs = { ...values };
      tool?.inputs.forEach(field => { if (field.type === 'boolean' && inputs[field.name] === undefined) inputs[field.name] = false; });
      const { data } = await api.post(kind === 'operation' ? `${base}/operations/${selected}/preview` : `${base}/reports/${selected}`, { inputs }, { timeout: 40000 });
      if (generation.current !== id) return;
      if (kind === 'operation') { setPreview(data); setConfirmation(''); setUncertain(false); }
      else setJob(data);
    } catch (error) { if (generation.current === id) setError(message(error)); }
    finally { if (generation.current === id) setBusy(false); }
  };
  const execute = async () => {
    if (!preview) return;
    setBusy(true); setError('');
    try {
      const { data } = await api.post(`${base}/operations/execute`, { token: preview.token, confirmation }, { timeout: 45000 });
      if (data.status === 'unknown') { setUncertain(true); setError(data.message); }
      else {
        setPreview(null); setUncertain(false);
        if (data.status === 'succeeded') setNotice(data.message + (data.warning ? ` ${data.warning}` : ''));
        else setError(data.message);
      }
    } catch (error) { setUncertain(true); setError(`${message(error)} Check the result before starting another operation.`); }
    finally { setBusy(false); }
  };
  const download = async () => {
    if (!job) return;
    setBusy(true);
    try {
      const { data } = await api.get(`${base}/reports/${job.id}/download`, { responseType: 'blob', timeout: 120000 });
      const url = URL.createObjectURL(data); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = job.filename || 'CultureHistory.xlsx'; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  };
  const locked = busy || !!preview || !!job && ['pending', 'running'].includes(job.status);
  return <Box sx={{ overflow: 'auto', p: .5 }}><Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, maxWidth: 900 }}>
    <Stack spacing={2}>
      <Typography variant="h6">{kind === 'operation' ? 'Operations' : 'Data retrieval'}</Typography>
      {error && !preview && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
      {notice && <Alert severity="success">{notice}</Alert>}
      <TextField select label={kind === 'operation' ? 'Operation' : 'Report'} value={selected} disabled={locked || !tools.length}
        onChange={event => { setSelected(event.target.value); setValues({}); setNotice(''); setJob(null); }}>
        {tools.map(tool => <MenuItem key={tool.id} value={tool.id}>{tool.name}</MenuItem>)}
      </TextField>
      {!tools.length && <Typography color="text.secondary">No {kind === 'operation' ? 'operations' : 'reports'} installed.</Typography>}
      {tool?.inputs.map(field => field.type === 'experiment'
        ? <ExperimentInput key={`${tool.id}/${field.name}`} label={field.label} value={values[field.name]} disabled={locked} onChange={value => changeValue(field.name, value)} />
        : field.type === 'boolean' ? <FormControlLabel key={field.name} label={field.label} control={<Checkbox disabled={locked} checked={values[field.name] === true} onChange={(_, value) => changeValue(field.name, value)} />} />
        : <TextField key={field.name} label={field.label} required={field.required} disabled={locked} select={field.type === 'choice'}
          type={['integer', 'number'].includes(field.type) ? 'number' : 'text'} value={values[field.name] ?? ''}
          onChange={event => changeValue(field.name, ['integer', 'number'].includes(field.type) && event.target.value !== '' ? Number(event.target.value) : event.target.value)}>
          {field.choices.map(choice => <MenuItem key={choice} value={choice}>{choice}</MenuItem>)}
        </TextField>)}
      {busy && <LinearProgress />}
      <Button variant="contained" disabled={!tool || locked} onClick={prepare}>{kind === 'operation' ? 'Review operation' : 'Generate Excel'}</Button>
      {job && <Stack spacing={1}>
        {['pending', 'running'].includes(job.status) && <><LinearProgress /><Typography>Preparing report…</Typography></>}
        {job.status === 'error' && <Alert severity="error">{job.error}</Alert>}
        {job.status === 'ready' && <Button variant="outlined" onClick={download} disabled={busy}>Download Excel</Button>}
      </Stack>}
    </Stack>
    <Dialog open={!!preview} onClose={() => { if (!busy && !uncertain) setPreview(null); }} fullWidth maxWidth="sm">
      <DialogTitle>Confirm {tool?.name}</DialogTitle><DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <Alert severity="warning">{preview?.summary} This cannot be undone.</Alert>
          <Box component="dl" sx={{ m: 0, overflowWrap: 'anywhere' }}>{Object.entries(preview?.details || {}).map(([key, value]) => <Box key={key} sx={{ mb: 1 }}><Typography component="dt" variant="caption" color="text.secondary">{key}</Typography><Typography component="dd" sx={{ m: 0 }}>{value == null ? '—' : String(value)}</Typography></Box>)}</Box>
          <TextField label={`Type ${preview?.confirmation ?? ''} to confirm`} value={confirmation} disabled={busy || uncertain} onChange={event => setConfirmation(event.target.value)} />
        </Stack>
      </DialogContent><DialogActions>
        <Button disabled={busy} onClick={() => setPreview(null)}>{uncertain ? 'Close' : 'Cancel'}</Button>
        <Button color="error" variant="contained" disabled={busy || confirmation !== preview?.confirmation} onClick={execute}>{uncertain ? 'Check result' : 'Confirm operation'}</Button>
      </DialogActions>
    </Dialog>
  </Paper></Box>;
}

export function DatabasePackages({ active }: { active: boolean }) {
  const [packages, setPackages] = useState<any[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [remove, setRemove] = useState<string | null>(null);
  const load = useCallback(async () => { const { data } = await api.get(`${base}/packages`); setPackages(data); }, []);
  useEffect(() => { if (active) load().catch(error => setError(message(error))); }, [active, load]);
  const change = async (action: () => Promise<unknown>) => {
    setBusy(true); setError('');
    try { await action(); setFile(null); setRemove(null); await load(); }
    catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  };
  return <Box sx={{ overflow: 'auto' }}><Stack spacing={2}>
    <Typography variant="h6">Manage packages</Typography>
    <Typography color="text.secondary">Install reviewed packages only. Packages execute code on this computer.</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      <Button component="label" disabled={busy} variant="outlined">Choose ZIP<input hidden type="file" accept=".zip" onChange={event => { setFile(event.target.files?.[0] || null); event.target.value = ''; }} /></Button>
      <Button variant="contained" disabled={busy || !file} onClick={() => change(() => { const form = new FormData(); form.append('file', file!); return api.post(`${base}/packages`, form, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 }); })}>Install package</Button>
      {file && <Typography sx={{ alignSelf: 'center', overflowWrap: 'anywhere' }}>{file.name}</Typography>}
    </Stack>
    {busy && <LinearProgress />}
    {packages.map(pkg => <Paper variant="outlined" key={pkg.id} sx={{ p: 2 }}><Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
      <Box sx={{ flex: 1, minWidth: 0 }}><Typography fontWeight={600}>{pkg.name} · {pkg.version}</Typography><Typography variant="body2" color="text.secondary">{pkg.tools.map((tool: Tool) => tool.name).join(', ')}</Typography>
        <Box component="details"><Typography component="summary" variant="body2">Details</Typography><Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>{pkg.id} · Contract {pkg.contract_version}<br />Libraries: {pkg.libraries.join(', ') || 'Standard library'}<br />SHA-256: {pkg.sha256}</Typography></Box>
      </Box><Button color="error" disabled={busy || !!pkg.running} onClick={() => setRemove(pkg.id)}>Remove</Button>
    </Stack></Paper>)}
    <Dialog open={!!remove} onClose={() => !busy && setRemove(null)}><DialogTitle>Remove package?</DialogTitle><DialogContent>Its actions and reports will no longer be available.</DialogContent><DialogActions><Button disabled={busy} onClick={() => setRemove(null)}>Cancel</Button><Button color="error" disabled={busy} onClick={() => change(() => api.delete(`${base}/packages/${remove}`))}>Remove package</Button></DialogActions></Dialog>
  </Stack></Box>;
}
