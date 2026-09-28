import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { api } from '../services/api';
import ReportInputs, { changedInputs, ReportField, requestMessage, saveBlob } from './ReportInputs';
import ReportConnections, { Source, SourceMappings } from './ReportConnections';

const base = '/api/database/tools';
type Draft = { name: string; kind: 'report' | 'operation'; package_id: string; version: string;
  definition_file: string; files: Record<string, string>; inputs: ReportField[]; sources: string[];
  mappings: Record<string, string>; operation_source?: string; libraries: string[] };
type Saved = { id: string; revision: number; draft: Draft; base?: { sha256: string } };

export default function ToolAuthoring({ draftId, onClose }: { draftId?: string; onClose: () => void }) {
  const [saved, setSaved] = useState<Saved>(), [draft, setDraft] = useState<Draft>();
  const [sources, setSources] = useState<Source[]>([]), [connections, setConnections] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [checked, setChecked] = useState(false), [reviewed, setReviewed] = useState(false);
  const [values, setValues] = useState<Record<string, any>>({}), [job, setJob] = useState<any>(), [preview, setPreview] = useState<any>();
  const [discard, setDiscard] = useState(false), [enabled, setEnabled] = useState(false);
  const alive = useRef(true), upload = useRef<HTMLInputElement>(null);
  const replaceAll = useRef(false);
  const running = job && ['pending', 'running'].includes(job.status);
  const locked = busy || !!running || enabled;
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    api.get(`${base}/sources`, { signal: controller.signal }).then(r => setSources(r.data)).catch(e => { if (!controller.signal.aborted) setError(requestMessage(e)); });
    if (draftId) {
      setBusy(true);
      api.get(`${base}/drafts/${draftId}`, { signal: controller.signal }).then(r => { setSaved(r.data); setDraft(r.data.draft); })
        .catch(e => { if (!controller.signal.aborted) setError(requestMessage(e)); }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    }
    return () => { alive.current = false; controller.abort(); };
  }, [draftId]);
  useEffect(() => {
    if (!running) return;
    const controller = new AbortController(); let timer: number;
    const poll = async () => {
      try { const r = await api.get(`${base}/reports/${job.id}`, { signal: controller.signal }); if (!controller.signal.aborted) setJob(r.data); }
      catch(e) { if (!controller.signal.aborted) setError(requestMessage(e)); }
      if (!controller.signal.aborted) timer = window.setTimeout(poll, 1000);
    };
    timer = window.setTimeout(poll, 500);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [job?.id, running]);
  const work = async (action: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('');
    try { await action(); } catch(e) { if (alive.current) setError(requestMessage(e)); }
    finally { if (alive.current) setBusy(false); }
  };
  const invalidate = () => { setChecked(false); setReviewed(false); setJob(undefined); setPreview(undefined); setNotice(''); };
  const change = (patch: Partial<Draft>) => { if (draft) setDraft({ ...draft, ...patch }); invalidate(); setValues({}); };
  const persist = async () => {
    if (!saved || !draft) throw new Error('Add Python first.');
    if (JSON.stringify(saved.draft) === JSON.stringify(draft)) return saved;
    const r = await api.put(`${base}/drafts/${saved.id}`, { draft, revision: saved.revision });
    setSaved(r.data); setDraft(r.data.draft); return r.data as Saved;
  };
  const addFiles = (selected: FileList | null) => {
    if (!selected?.length) return;
    const incoming = Array.from(selected);
    void work(async () => {
      if (incoming.reduce((n,f) => n+f.size,0) > 3*1024*1024) throw { response:{data:{detail:'Source files must total at most 3 MiB.'}} };
      const baseline = saved ? await persist() : undefined;
      const files = replaceAll.current ? {} : { ...draft?.files };
      for (const f of incoming) files[f.name] = await f.text();
      const r = await api.post(`${base}/authoring/import`, { files, key:baseline?.id, revision:baseline?.revision || 0 });
      setSaved(r.data); setDraft(r.data.draft); invalidate(); setValues({}); setNotice('Python added. It has not been run.');
    });
  };
  const download = async (url: string, fallback: string) => {
    const r = await api.get(url, { responseType:'blob' });
    saveBlob(r.data, /filename="([^"]+)"/.exec(r.headers['content-disposition'] || '')?.[1] || fallback);
  };
  const ready = !!draft && !draft.inputs.some(f => f.required && f.type !== 'boolean' && (values[f.name] == null || values[f.name] === ''));
  const success = draft?.kind === 'report' ? job?.status === 'ready' : !!preview;
  return <Stack spacing={2}>
    <Stack direction="row" gap={1} justifyContent="space-between" alignItems="center" flexWrap="wrap">
      <Typography variant="h6" component="h2">{saved?.base ? 'Edit tool' : 'Add tool'}</Typography>
      <Stack direction="row" gap={1} flexWrap="wrap">
        {enabled ? <Button onClick={onClose}>Close</Button> : <>
          <Button disabled={busy || !!running} onClick={() => saved ? setDiscard(true) : onClose()}>Discard and close</Button>
          {saved && <Button disabled={busy || !!running} onClick={() => work(async () => { await persist(); onClose(); })}>Save and close</Button>}
        </>}
      </Stack>
    </Stack>
    {error && <Alert severity="error">{error}</Alert>}{notice && <Alert severity="success">{notice}</Alert>}{busy && <LinearProgress />}
    <Box sx={{ display:'grid', gridTemplateColumns:{xs:'minmax(0,1fr)', md:'minmax(0,2fr) minmax(0,3fr)'}, gap:2, alignItems:'start' }}>
      <Paper variant="outlined" sx={{p:2, minWidth:0}}><Stack spacing={2}>
        <Typography variant="h6">1. Python</Typography>
        <Stack direction="row" gap={1} flexWrap="wrap">
          <Button variant={draft ? 'outlined':'contained'} disabled={locked} onClick={() => {replaceAll.current=false;upload.current?.click();}}>{draft ? 'Replace or add files':'Add Python'}</Button>
          {draft && <Button disabled={locked} onClick={() => {replaceAll.current=true;upload.current?.click();}}>Replace all files</Button>}
          {saved && <Button disabled={busy} onClick={() => work(() => download(`${base}/drafts/${saved.id}/source`,'source.zip'))}>Download source</Button>}
        </Stack>
        <input ref={upload} hidden type="file" multiple accept=".py,.json,.md,.txt" aria-label="Tool Python files" onChange={e => { addFiles(e.target.files); e.target.value=''; }} />
        {!draft && <>
          <Typography variant="body2" color="text.secondary">Start with an example. Keep its TOOL definition and adapt the Python.</Typography>
          <Stack direction="row" gap={1} flexWrap="wrap">
            <Button disabled={busy} onClick={() => work(() => download(`${base}/authoring/examples/report`,'report.py'))}>Report example</Button>
            <Button disabled={busy} onClick={() => work(() => download(`${base}/authoring/examples/operation`,'operation.py'))}>Operation example</Button>
          </Stack>
        </>}
        {draft && <>
          <Typography variant="subtitle1">{draft.name}</Typography>
          <Typography variant="body2">{draft.kind === 'report' ? 'Report · Excel output' : 'Operation · changes database records'}</Typography>
          <Typography variant="body2" sx={{overflowWrap:'anywhere'}}>{Object.keys(draft.files).join(', ')}</Typography>
          <Box component="details"><Typography component="summary">Definition and libraries</Typography>
            <Typography variant="body2">Inputs: {draft.inputs.map(f=>f.label).join(', ') || 'None'}</Typography>
            <Typography variant="body2">Libraries: {draft.libraries.join(', ') || 'Python standard library'}</Typography>
            <Typography variant="body2">{draft.package_id} · {draft.version}</Typography>
          </Box>
          <Typography variant="h6">2. Connections</Typography>
          {draft.kind === 'operation' && <TextField select label="Operation database" size="small" value={draft.operation_source || ''} disabled={locked} onChange={e=>change({operation_source:e.target.value})}>
            {sources.filter(s=>s.access==='operation').map(s=><MenuItem key={s.id} value={s.id}>{s.name} · {s.database}</MenuItem>)}
          </TextField>}
          <SourceMappings aliases={draft.sources} sources={sources} mappings={draft.mappings} disabled={locked} onChange={mappings=>change({mappings})} />
          {!draft.sources.length && draft.kind==='report' && <Typography variant="body2">No database connection needed.</Typography>}
          <Button disabled={locked} sx={{alignSelf:'flex-start'}} onClick={()=>setConnections(true)}>Manage connections</Button>
          <Button disabled={locked} variant="outlined" sx={{alignSelf:'flex-start'}} onClick={()=>work(async()=>{
            const s=await persist(); await api.post(`${base}/drafts/${s.id}/check`,{}); setChecked(true); setNotice('Files, libraries and connections checked. Python has not been run.');
          })}>Check setup</Button>
        </>}
      </Stack></Paper>
      <Paper variant="outlined" sx={{p:2,minWidth:0}}><Stack spacing={2}>
        <Typography variant="h6">3. Try and enable</Typography>
        {!draft ? <Typography color="text.secondary">The tool’s form will appear here.</Typography> : <>
          {!checked && <Typography variant="body2" color="text.secondary">Check setup to try this form.</Typography>}
          <ReportInputs key={`${saved?.id}-${saved?.revision}`} fields={draft.inputs} values={values} disabled={locked || !checked}
            choiceBase={`${base}/drafts/${saved?.id}/choices`} onChange={(name,value)=>{setValues(changedInputs(draft.inputs,values,name,value));setJob(undefined);setPreview(undefined);setReviewed(false);}} />
          <Typography variant="caption" color="text.secondary">{draft.kind==='report' ? 'Trying runs the uploaded Python using the selected read-only connections.' : 'Trying runs preview only. Execution stays in Operations.'}</Typography>
          <Button variant="contained" sx={{alignSelf:'flex-start'}} disabled={locked || !checked || !ready} onClick={()=>work(async()=>{
            setReviewed(false);setJob(undefined);setPreview(undefined);
            const s=await persist(), r=await api.post(`${base}/drafts/${s.id}/try`,{inputs:values,revision:s.revision},{timeout:120000});
            if(draft.kind==='report')setJob(r.data);else setPreview(r.data);
          })}>{running ? 'Generating…' : draft.kind==='report' ? 'Try report':'Try preview'}</Button>
          {running && <LinearProgress />}
          {job?.status==='error' && <Alert severity="error">{job.error}{job.error_details && <Box component="details"><summary>Details</summary>{job.error_details}</Box>}</Alert>}
          {job?.status==='ready' && <Stack spacing={1}><Typography sx={{overflowWrap:'anywhere'}}>{job.filename}</Typography><Button sx={{alignSelf:'flex-start'}} onClick={()=>work(()=>download(`${base}/reports/${job.id}/download`,job.filename))}>Download Excel</Button></Stack>}
          {preview && <Paper variant="outlined" sx={{p:2}}><Typography>{preview.summary}</Typography><Typography variant="body2" color="text.secondary">{preview.target}</Typography>
            <Box component="dl" sx={{display:'grid',gridTemplateColumns:'minmax(0,1fr) minmax(0,1fr)',gap:1,m:0,mt:1}}>{Object.entries(preview.details || {}).map(([key,value])=><React.Fragment key={key}><Box component="dt" sx={{overflowWrap:'anywhere'}}>{key}</Box><Box component="dd" sx={{m:0,overflowWrap:'anywhere'}}>{typeof value==='object'?JSON.stringify(value):String(value)}</Box></React.Fragment>)}</Box>
            <Typography variant="caption">Preview only. Execution has not been requested.</Typography>
          </Paper>}
          {success && !enabled && <FormControlLabel control={<Checkbox checked={reviewed} disabled={locked} onChange={(_,v)=>setReviewed(v)} />} label={draft.kind==='report' ? 'I reviewed the Python and checked the output':'I reviewed the Python and expected effects'} />}
          <Stack direction="row" gap={1} flexWrap="wrap">
            <Button variant="contained" disabled={locked || !success || !reviewed} onClick={()=>work(async()=>{
              const r=await api.get(`${base}/drafts/${saved!.id}/review`);
              await api.post(`${base}/drafts/${saved!.id}/install`,{revision:saved!.revision,expected_current:r.data.current_sha256,reviewed:true});
              setEnabled(true);setNotice(`${draft.name} is available in ${draft.kind==='report'?'Data retrieval':'Operations'}.`);
            })}>{saved?.base?'Publish update':`Enable ${draft.kind}`}</Button>
            {saved && <Button disabled={busy || !!running} onClick={()=>work(async()=>{const s=await persist();await download(`${base}/drafts/${s.id}/package`,`${draft.package_id}.zip`);})}>Export package</Button>}
          </Stack>
        </>}
      </Stack></Paper>
    </Box>
    <ReportConnections open={connections} onClose={()=>{setConnections(false);invalidate();void api.get(`${base}/sources`).then(r=>setSources(r.data)).catch(e=>setError(requestMessage(e)));}} />
    <Dialog open={discard} onClose={()=>!busy&&setDiscard(false)}><DialogTitle>Discard this draft?</DialogTitle><DialogContent>The installed tool will be kept.</DialogContent><DialogActions>
      <Button disabled={busy} onClick={()=>setDiscard(false)}>Keep editing</Button><Button color="error" disabled={busy} onClick={()=>work(async()=>{await api.delete(`${base}/drafts/${saved!.id}`);onClose();})}>Discard and close</Button>
    </DialogActions></Dialog>
  </Stack>;
}
