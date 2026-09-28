import React, { useEffect, useRef, useState } from 'react';
import { Alert, Autocomplete, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControlLabel, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import InspectionWorkspace from './InspectionWorkspace';
import ExperimentBrowser, { Experiment } from './ExperimentBrowser';
export { default as DatabasePackages } from './DatabasePackages';
import { api } from '../services/api';

const base = '/api/database/tools';
type Field = { name: string; label: string; type: string; required: boolean; choices: string[] };
type Tool = { id: string; name: string; kind: string; package_version: string; inputs: Field[] };
type Preview = { token: string; confirmation: string; summary: string; details: Record<string, unknown> };
type Job = { id: string; status: string; filename?: string; error?: string; error_details?: string; package_version?: string };
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
  const [experiment, setExperiment] = useState<Experiment>();
  const [detailOpen, setDetailOpen] = useState(false);
  const detail = useRef<HTMLDivElement>(null);
  const selection = useRef<HTMLDivElement>(null);
  const tool = tools.find(item => item.id === selected);
  const experimentFields = tool?.inputs.filter(field => field.type === 'experiment') || [];
  const experimentField = experimentFields.length === 1 ? experimentFields[0] : undefined;
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
    setValues(old => ({ ...old, [name]: value })); setJob(null); setNotice(''); setError('');
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
  const chooseTool = (id: string) => {
    setSelected(id); setValues({}); setExperiment(undefined); setDetailOpen(false); setNotice(''); setError(''); setJob(null);
  };
  const invalid = tool?.inputs.some(field => field.required && field.type !== 'boolean' && (values[field.name] == null || values[field.name] === ''));
  return <>
    <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1, minHeight: 48 }}>
      {tools.length > 1 ? <TextField select size="small" label={kind === 'operation' ? 'Operation' : 'Report'} value={selected}
        disabled={locked} onChange={event => chooseTool(event.target.value)} sx={{ width: 420, maxWidth: '100%' }}>
        {tools.map(item => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
      </TextField> : <Typography component="h2" variant="h6">{tool?.name || (kind === 'operation' ? 'Operations' : 'Data retrieval')}</Typography>}
    </Stack>
    <InspectionWorkspace label="Database task workspace">
      <Box sx={{ display: 'grid', gridTemplateColumns: experimentField ? 'minmax(0, 2fr) minmax(0, 3fr)' : '1fr', gap: 2, height: '100%', minHeight: 0,
        '@container workspace (max-width: 899px)': { gridTemplateColumns: '1fr' } }}>
        {experimentField && <Box ref={selection} sx={{ minWidth: 0, minHeight: 0,
          '@container workspace (max-width: 899px)': { display: detailOpen ? 'none' : 'block' } }}>
          <ExperimentBrowser selected={experiment} disabled={locked} active={active} onSelect={row => {
            setExperiment(row);
            if (values[experimentField.name] !== row.ExperimentID) changeValue(experimentField.name, row.ExperimentID);
            setDetailOpen(true);
            requestAnimationFrame(() => detail.current?.focus());
          }} />
        </Box>}
        <Paper ref={detail} tabIndex={-1} variant="outlined" sx={{ p: { xs: 1.5, md: 2.5 }, minWidth: 0, minHeight: 0, overflow: 'auto', outline: 'none',
          '@container workspace (max-width: 899px)': { display: experimentField && !detailOpen ? 'none' : 'block' } }}>
          <Stack spacing={2}>
            {experimentField && <Button sx={{ display: 'none', alignSelf: 'flex-start', '@container workspace (max-width: 899px)': { display: 'inline-flex' } }}
              onClick={() => { setDetailOpen(false); requestAnimationFrame(() => selection.current?.querySelector<HTMLElement>('[aria-current="true"]')?.focus()); }}>Back to experiments</Button>}
            {error && !preview && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
            {notice && <Alert severity="success">{notice}</Alert>}
            {!tools.length && <Typography color="text.secondary">No {kind === 'operation' ? 'operations' : 'reports'} installed.</Typography>}
            {experimentField && (experiment ? <Box>
              <Typography variant="overline">Experiment {experiment.ExperimentID}</Typography>
              <Typography component="h3" variant="h6" sx={{ overflowWrap: 'anywhere' }}>{experiment.UserDefinedID || 'Unnamed experiment'}</Typography>
              {experiment.Note && <Typography color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>{experiment.Note}</Typography>}
            </Box> : <Typography color="text.secondary">Select an experiment.</Typography>)}
            {tool?.inputs.filter(field => field !== experimentField).map(field => field.type === 'experiment'
              ? <ExperimentInput key={`${tool.id}/${field.name}`} label={field.label} value={values[field.name]} disabled={locked} onChange={value => changeValue(field.name, value)} />
              : field.type === 'boolean' ? <FormControlLabel key={field.name} label={field.label} control={<Checkbox disabled={locked} checked={values[field.name] === true} onChange={(_, value) => changeValue(field.name, value)} />} />
              : <TextField key={field.name} label={field.label} required={field.required} disabled={locked} select={field.type === 'choice'}
                type={['integer', 'number'].includes(field.type) ? 'number' : 'text'} value={values[field.name] ?? ''}
                onChange={event => changeValue(field.name, ['integer', 'number'].includes(field.type) && event.target.value !== '' ? Number(event.target.value) : event.target.value)}>
                {field.choices.map(choice => <MenuItem key={choice} value={choice}>{choice}</MenuItem>)}
              </TextField>)}
            {busy && <LinearProgress />}
            <Button variant="contained" sx={{ alignSelf: 'flex-start', minHeight: 44 }} disabled={!tool || locked || invalid}
              onClick={prepare}>{kind === 'operation' ? 'Review operation' : 'Generate Excel'}</Button>
            {job && <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1}>
              {['pending', 'running'].includes(job.status) && <><Typography>Preparing report…</Typography><LinearProgress /></>}
              {job.status === 'error' && <Alert severity="error">{job.error}</Alert>}
              {job.error_details && <Box component="details"><Typography component="summary">Details</Typography><Typography sx={{ overflowWrap: 'anywhere' }}>{job.error_details}</Typography></Box>}
              {job.status === 'ready' && <><Typography sx={{ overflowWrap: 'anywhere' }}>{job.filename}</Typography><Button variant="outlined" sx={{ alignSelf: 'flex-start' }} onClick={download} disabled={busy}>Download Excel</Button></>}
              <Typography variant="caption" color="text.secondary">{tool?.name} · {job.package_version}</Typography>
            </Stack></Paper>}
          </Stack>
        </Paper>
      </Box>
    </InspectionWorkspace>
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
  </>;
}
