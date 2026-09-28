import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Checkbox, FormControlLabel, LinearProgress, MenuItem, Paper, Stack, Step, StepLabel, Stepper, TextField, Typography } from '@mui/material';
import { api } from '../services/api';
import ReportInputs, { changedInputs, ReportField, requestMessage, saveBlob } from './ReportInputs';
import ReportConnections, { Source, SourceMappings } from './ReportConnections';
const base = '/api/database/tools';
type Draft = { name: string; package_id: string; version: string; libraries: string[]; original: string; handler: string;
  sources: string[]; mappings: Record<string, string>; inputs: ReportField[]; step: number };
type Saved = { id: string; revision: number; draft: Draft };
const empty = (): Draft => ({ name: 'New report', package_id: 'my-report', version: '1.0.0', libraries: ['openpyxl'],
  original: '', handler: '', sources: ['primary'], mappings: {}, inputs: [], step: 0 });

function LookupEditor({ field, fields, aliases, change }: { field: ReportField; fields: ReportField[]; aliases: string[]; change: (f: ReportField) => void }) {
  const [table, setTable] = useState(''), [value, setValue] = useState(''), [label, setLabel] = useState('');
  const lookup = field.lookup!;
  const update = (patch: any) => change({ ...field, lookup: { ...lookup, ...patch } });
  const quote = (x: string) => '[' + x.replace(/]/g, ']]') + ']';
  return <Stack spacing={2}>
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
      <TextField select fullWidth size="small" label="Source" value={lookup.source || ''} onChange={e => update({ source: e.target.value })}>{aliases.map(x => <MenuItem key={x} value={x}>{x}</MenuItem>)}</TextField>
      <TextField select fullWidth size="small" label="Value type" value={lookup.value_type} onChange={e => update({ value_type: e.target.value })}>{['text', 'integer', 'number'].map(x => <MenuItem key={x} value={x}>{x}</MenuItem>)}</TextField>
    </Stack>
    <Box component="details"><Typography component="summary">Build from columns</Typography><Stack spacing={1} sx={{ mt: 1 }}>
      <TextField size="small" label="Table or view (schema.table)" value={table} onChange={e => setTable(e.target.value)} />
      <TextField size="small" label="Value column" value={value} onChange={e => setValue(e.target.value)} />
      <TextField size="small" label="Label column" value={label} onChange={e => setLabel(e.target.value)} />
      <Button disabled={!table || !value || !label} onClick={() => update({ query: `SELECT ${quote(value)} AS [value], ${quote(label)} AS [label] FROM ${table.split('.').map(quote).join('.')}` })}>Use columns</Button>
    </Stack></Box>
    <TextField size="small" multiline minRows={3} label="Choice query" value={lookup.query || ''} onChange={e => update({ query: e.target.value })}
      helperText="Return value and label columns. Use ? for each dependent input, in order." />
    <TextField select size="small" label="Depends on (parameter order)" SelectProps={{ multiple: true }} value={lookup.parameters}
      onChange={e => update({ parameters: typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value })}>
      {fields.filter(x => x.name !== field.name).map(x => <MenuItem key={x.name} value={x.name}>{x.label || x.name}</MenuItem>)}
    </TextField>
  </Stack>;
}

export default function ReportWizard({ draftId, onClose }: { draftId?: string; onClose: () => void }) {
  const [saved, setSaved] = useState<Saved>(), [draft, setDraft] = useState<Draft>(empty);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [sources, setSources] = useState<Source[]>([]), [connectionsOpen, setConnectionsOpen] = useState(false);
  const [values, setValues] = useState<Record<string, any>>({}), [job, setJob] = useState<any>(), [review, setReview] = useState<any>();
  const loadSources = () => api.get(`${base}/sources`).then(r => setSources(r.data));
  useEffect(() => {
    const controller = new AbortController();
    if (draftId) {
      setBusy(true);
      api.get(`${base}/drafts/${draftId}`, { signal: controller.signal }).then(r => { if (!controller.signal.aborted) { setSaved(r.data); setDraft(r.data.draft); } })
        .catch(e => { if (!controller.signal.aborted) setError(requestMessage(e)); })
        .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    }
    void loadSources().catch(e => setError(requestMessage(e)));
    return () => controller.abort();
  }, [draftId]);
  useEffect(() => {
    if (!job || !['pending', 'running'].includes(job.status)) return;
    const controller = new AbortController(); let timer: number;
    const poll = async () => {
      try { const r = await api.get(`${base}/reports/${job.id}`, { signal: controller.signal }); if (!controller.signal.aborted) setJob(r.data); }
      catch (e) { if (!controller.signal.aborted) setError(requestMessage(e)); }
      if (!controller.signal.aborted) timer = window.setTimeout(poll, 1000);
    };
    timer = window.setTimeout(poll, 500);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [job?.id, job?.status]);
  const running = !!job && ['pending', 'running'].includes(job.status);
  const update = (patch: Partial<Draft>) => { setDraft(d => ({ ...d, ...patch })); setReview(undefined); setJob(undefined); setValues({}); setNotice(''); };
  const persist = async (value = draft) => {
    value = { ...value, mappings: Object.fromEntries(value.sources.filter(x => value.mappings[x]).map(x => [x, value.mappings[x]])) };
    const r = saved ? await api.put(`${base}/drafts/${saved.id}`, { draft: value, revision: saved.revision })
      : await api.post(`${base}/drafts`, { draft: value, revision: 0 });
    setSaved(r.data); setDraft(r.data.draft); return r.data as Saved;
  };
  const action = async (work: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('');
    try { await work(); } catch (e) { setError(requestMessage(e)); } finally { setBusy(false); }
  };
  const navigate = (step: number) => action(async () => { await persist({ ...draft, step }); setReview(undefined); });
  const upload = (which: 'original' | 'handler', file?: File) => {
    if (!file) return;
    void action(async () => {
      if (file.size > 1024 * 1024) throw { response: { data: { detail: 'Python files must be under 1 MiB.' } } };
      const next = { ...draft, [which]: await file.text() }; await persist(next); setJob(undefined); setReview(undefined);
      setNotice(which === 'original' ? 'Original script saved.' : 'Handler saved.');
    });
  };
  const download = async (url: string, name: string) => { const r = await api.get(url, { responseType: 'blob' }); saveBlob(r.data, name); };
  const fieldChange = (index: number, f: ReportField) => update({ inputs: draft.inputs.map((x, i) => i === index ? f : x) });
  const ready = !draft.inputs.some(f => f.required && f.type !== 'boolean' && (values[f.name] == null || values[f.name] === ''));
  return <Stack spacing={2}>
    <Stack direction="row" justifyContent="space-between" alignItems="center"><Typography variant="h6">Create report</Typography>
      <Button disabled={busy || running} onClick={() => action(async () => { await persist(); onClose(); })}>Save and close</Button></Stack>
    <Stepper activeStep={draft.step} alternativeLabel>{['Script', 'Data and inputs', 'Try report', 'Install or export'].map(x => <Step key={x}><StepLabel>{x}</StepLabel></Step>)}</Stepper>
    {error && <Alert severity="error">{error}</Alert>}{notice && <Alert severity="success">{notice}</Alert>}{busy && <LinearProgress />}
    <Paper variant="outlined" sx={{ p: { xs: 1.5, md: 3 } }}><Box component="fieldset" disabled={busy || running} sx={{ border: 0, p: 0, m: 0, minWidth: 0 }}>
      {draft.step === 0 && <Stack spacing={2}>
        <TextField label="Report name" value={draft.name} onChange={e => update({ name: e.target.value })} />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}><TextField fullWidth label="Package ID" value={draft.package_id} onChange={e => update({ package_id: e.target.value })} />
          <TextField fullWidth label="Version" value={draft.version} onChange={e => update({ version: e.target.value })} /></Stack>
        <TextField select label="Bundled libraries" SelectProps={{ multiple: true }} value={draft.libraries} onChange={e => update({ libraries: typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value })}>
          {['pandas', 'openpyxl', 'pyodbc', 'numpy'].map(x => <MenuItem key={x} value={x}>{x}</MenuItem>)}</TextField>
        <Button component="label" variant="outlined">Upload original Python<input hidden type="file" accept=".py" aria-label="Original Python" onChange={e => { upload('original', e.target.files?.[0]); e.target.value = ''; }} /></Button>
        {draft.original && <Typography variant="body2">Original saved as reference. It has not been run.</Typography>}
        {draft.original && <Button onClick={() => saveBlob(new Blob([draft.original], { type: 'text/x-python' }), 'original.py')}>Download original</Button>}
      </Stack>}
      {draft.step === 1 && <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between"><Typography variant="subtitle1">Sources</Typography><Button onClick={() => setConnectionsOpen(true)}>Configure connections</Button></Stack>
        <TextField label="Names used in Python (comma separated)" value={draft.sources.join(', ')} onChange={e => update({ sources: e.target.value.split(',').map(x => x.trim()) })} />
        <SourceMappings aliases={draft.sources.filter(Boolean)} sources={sources} mappings={draft.mappings} onChange={mappings => update({ mappings })} />
        {!sources.length && <Alert severity="info">Configure a read-only connection to try this report.</Alert>}
        <Typography variant="subtitle1">Inputs</Typography>
        {draft.inputs.map((field, i) => <Paper key={i} variant="outlined" sx={{ p: 2 }}><Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField fullWidth size="small" label="Input name in Python" value={field.name} onChange={e => fieldChange(i, { ...field, name: e.target.value })} />
            <TextField fullWidth size="small" label="Label" value={field.label} onChange={e => fieldChange(i, { ...field, label: e.target.value })} />
            <TextField select fullWidth size="small" label="Input type" value={field.type} onChange={e => fieldChange(i, { ...field, type: e.target.value,
              lookup: e.target.value === 'lookup' ? { source: draft.sources[0], query: '', parameters: [], value_type: 'text' } : null })}>
              {Object.entries({ text: 'Text', integer: 'Integer', number: 'Number', date: 'Date', boolean: 'Checkbox', choice: 'Fixed choices', lookup: 'Database choices' }).map(([v, label]) => <MenuItem key={v} value={v}>{label}</MenuItem>)}
            </TextField></Stack>
          {field.type === 'choice' && <TextField multiline label="Choices (one per line)" value={field.choices.join('\n')} onChange={e => fieldChange(i, { ...field, choices: e.target.value.split('\n') })} />}
          {field.type === 'lookup' && <LookupEditor field={field} fields={draft.inputs} aliases={draft.sources} change={f => fieldChange(i, f)} />}
          <Stack direction="row" justifyContent="space-between"><FormControlLabel label="Required" control={<Checkbox checked={field.required} onChange={(_, required) => fieldChange(i, { ...field, required })} />} />
            <Button color="error" onClick={() => update({ inputs: draft.inputs.filter((_, n) => n !== i) })}>Remove input</Button></Stack>
        </Stack></Paper>)}
        <Button onClick={() => update({ inputs: [...draft.inputs, { name: `input_${draft.inputs.length + 1}`, label: 'Input', type: 'text', required: true, choices: [] }] })}>Add input</Button>
      </Stack>}
      {draft.step === 2 && <Stack spacing={2}>
        <Typography variant="subtitle1">Finish your Python</Typography>
        <Typography variant="body2">Download a starter, add your calculations, then upload the completed handler.</Typography>
        <Stack direction="row" flexWrap="wrap" gap={1}>
          <Button variant="outlined" onClick={() => action(async () => { const s = await persist(); await download(`${base}/drafts/${s.id}/handler`, 'handler.py'); })}>Download starter</Button>
          <Button component="label" variant="outlined">Upload handler.py<input hidden type="file" accept=".py" aria-label="Completed handler" onChange={e => { upload('handler', e.target.files?.[0]); e.target.value = ''; }} /></Button>
          {draft.handler && <Button onClick={() => saveBlob(new Blob([draft.handler], { type: 'text/x-python' }), 'handler.py')}>Download saved handler</Button>}
          {/^[ \t]*def run\(/m.test(draft.original) && <Button title="Original already defines run(context, inputs)" onClick={() => action(async () => {
            await persist({ ...draft, handler: draft.original }); setJob(undefined); setReview(undefined); setNotice('Original selected as handler.');
          })}>Use original as handler</Button>}
        </Stack>
        {draft.handler && <Typography variant="body2">Handler saved · {draft.handler.split('\n').length} lines</Typography>}
        <Typography variant="subtitle1">Try report</Typography>
        {saved && <ReportInputs fields={draft.inputs} values={values} disabled={busy || running} choiceBase={`${base}/drafts/${saved.id}/choices`}
          onChange={(name, v) => { setValues(old => changedInputs(draft.inputs, old, name, v)); setJob(undefined); }} />}
        <Button variant="contained" sx={{ alignSelf: 'flex-start' }} disabled={!draft.handler || !ready || busy || running} onClick={() => action(async () => {
          const s = await persist(); const inputs = { ...values }; draft.inputs.forEach(f => { if (f.type === 'boolean' && inputs[f.name] == null) inputs[f.name] = false; });
          const r = await api.post(`${base}/drafts/${s.id}/try`, { inputs }); setJob(r.data);
        })}>Try report</Button>
      </Stack>}
      {draft.step === 3 && <Stack spacing={2}>
        <Typography variant="h6">{draft.name} · {draft.version}</Typography>
        <Typography variant="body2">Install here, or export a package for another RobotControl installation.</Typography>
        <Button variant="outlined" sx={{ alignSelf: 'flex-start' }} onClick={() => action(async () => { const s = await persist(); await download(`${base}/drafts/${s.id}/package`, `${draft.package_id}-${draft.version}.zip`); })}>Export package</Button>
        {!review && <Button variant="contained" sx={{ alignSelf: 'flex-start' }} onClick={() => action(async () => { const s = await persist(); const r = await api.get(`${base}/drafts/${s.id}/review`); setReview(r.data); })}>Review installation</Button>}
        {review && <><Typography>{review.current_version ? `${review.current_version} → ${draft.version}` : 'New package'}</Typography>
          {review.current_version && <Alert severity="warning">This replaces the installed package. Check the version and Excel output first.</Alert>}
          <Button variant="contained" sx={{ alignSelf: 'flex-start' }} onClick={() => action(async () => {
            await api.post(`${base}/drafts/${saved!.id}/install`, { expected_current: review.current_sha256, revision: saved!.revision });
            setNotice('Report installed. It is available in Data retrieval.'); setReview(undefined);
          })}>Install report</Button></>}
      </Stack>}
    </Box></Paper>
    {running && <LinearProgress />}{job?.status === 'error' && <Alert severity="error">{job.error}</Alert>}
    {job?.status === 'ready' && <Alert severity="success" action={<Button onClick={() => action(() => download(`${base}/reports/${job.id}/download`, job.filename))}>Download Excel</Button>}>Report ready</Alert>}
    <Stack direction="row" justifyContent="space-between"><Button disabled={!draft.step || busy || running} onClick={() => navigate(draft.step - 1)}>Back</Button>
      <Button disabled={busy || running} onClick={() => action(async () => { await persist(); setNotice('Draft saved.'); })}>Save draft</Button>
      <Button disabled={draft.step === 3 || busy || running} onClick={() => navigate(draft.step + 1)}>Next</Button></Stack>
    <ReportConnections open={connectionsOpen} onClose={() => { setConnectionsOpen(false); void loadSources(); }} />
  </Stack>;
}
