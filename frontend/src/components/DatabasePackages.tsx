import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress, MenuItem, TextField, Paper, Stack, Typography } from '@mui/material';
import { api } from '../services/api';
import ReportWizard from './ReportWizard';
import ReportConnections, { Source, SourceMappings } from './ReportConnections';

type Package = { id: string; name: string; version: string; sha256: string; running: number;
  libraries: string[]; tools: { id: string; name: string; kind: string }[] };
type Review = { package: Package; sha256: string; current_version: string | null; current_sha256: string; running: number };
const message = (error: any) => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : 'The request could not be completed. Try again.';
const older = (a: string, b: string) => {
  const left = a.split('.').map(Number), right = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) if (left[i] !== right[i]) return left[i] < right[i];
  return false;
};

export default function DatabasePackages({ active }: { active: boolean }) {
  const [packages, setPackages] = useState<Package[]>([]);
  const [file, setFile] = useState<File>();
  const [review, setReview] = useState<Review>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [remove, setRemove] = useState<Package>();
  const [wizard, setWizard] = useState<string>();
  const [drafts, setDrafts] = useState<{ id: string; name: string }[]>([]);
  const [removeDraft, setRemoveDraft] = useState<{ id: string; name: string }>();
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [binding, setBinding] = useState<{ id: string; aliases: string[]; mappings: Record<string, string>; operation_source?: string; has_operation?: boolean }>();
  const input = useRef<HTMLInputElement>(null);
  const target = useRef<string>();
  const load = useCallback(async (signal?: AbortSignal) => {
    const { data } = await api.get('/api/database/tools/packages', { signal });
    if (!signal?.aborted) setPackages(data);
    const saved = await api.get('/api/database/tools/drafts', { signal });
    if (!signal?.aborted) setDrafts(saved.data);
  }, []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    load(controller.signal).catch(error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [active, load]);
  const inspect = async (incoming: File) => {
    setBusy(true); setError(''); setNotice(''); setReview(undefined); setFile(undefined);
    try {
      const form = new FormData(); form.append('file', incoming);
      const { data } = await api.post('/api/database/tools/packages/inspect', form, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (target.current && target.current !== data.package.id) throw { response: { data: { detail: 'This file belongs to another package. Choose the matching update.' } } };
      setFile(incoming); setReview(data);
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  };
  const install = async () => {
    if (!file || !review) return;
    setBusy(true); setError('');
    try {
      const form = new FormData(); form.append('file', file);
      form.append('expected_package', review.package.id);
      form.append('expected_current', review.current_sha256 || 'absent');
      await api.post('/api/database/tools/packages', form, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 });
      setNotice(`${review.package.name} ${review.package.version} installed.`);
      setReview(undefined); setFile(undefined);
      await load();
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  };
  const removePackage = async () => {
    if (!remove) return;
    setBusy(true); setError('');
    try { await api.delete(`/api/database/tools/packages/${remove.id}`); setRemove(undefined); await load(); }
    catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  };
  const unchanged = review?.sha256 === review?.current_sha256;
  const downgrade = !!review?.current_version && older(review.package.version, review.current_version);
  const action = !review?.current_version ? 'Install package' : downgrade ? 'Install older version' : review.current_version === review.package.version ? 'Replace version' : 'Update package';
  if (wizard !== undefined) return <ReportWizard draftId={wizard || undefined} onClose={() => { setWizard(undefined); void load(); }} />;
  return <Stack spacing={2}>
    <Stack direction="row" justifyContent="space-between" gap={2} alignItems="center" flexWrap="wrap">
      <Typography component="h2" variant="h6">Manage packages</Typography>
      <Stack direction="row" gap={1} flexWrap="wrap">
        <Button disabled={busy} onClick={() => setConnectionsOpen(true)}>Database connections</Button>
        <Button variant="outlined" disabled={busy} onClick={() => setWizard('')}>Create report</Button>
        <Button variant="contained" disabled={busy} onClick={() => { target.current = undefined; input.current?.click(); }}>Add package</Button>
      </Stack>
    </Stack>
    <input ref={input} hidden type="file" accept=".zip" onChange={event => {
      const selected = event.target.files?.[0]; event.target.value = ''; if (selected) void inspect(selected);
    }} />
    <Typography color="text.secondary" variant="body2">Install reviewed code only. Updating RobotControl does not replace installed packages.</Typography>
    {error && !review && <Alert severity="error">{error}</Alert>}
    {notice && <Alert severity="success">{notice}</Alert>}
    {busy && <LinearProgress />}
    {!!drafts.length && <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="subtitle1">Saved drafts</Typography>
      {drafts.map(d => <Stack key={d.id} direction="row" alignItems="center"><Typography sx={{ flex: 1 }}>{d.name}</Typography>
        <Button onClick={() => setWizard(d.id)}>Resume</Button><Button color="error" onClick={() => setRemoveDraft(d)}>Remove draft</Button></Stack>)}
    </Paper>}
    {!packages.length && !busy && <Typography>No packages installed.</Typography>}
    <Paper variant="outlined">
      {packages.map(pkg => <Box key={pkg.id} sx={{ p: 2, borderBottom: 1, borderColor: 'divider', '&:last-child': { borderBottom: 0 } }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} gap={2} alignItems={{ sm: 'center' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography fontWeight={600}>{pkg.name} · {pkg.version}</Typography>
            <Typography color="text.secondary">{pkg.tools.map(tool => tool.name).join(', ')}</Typography>
            <Box component="details"><Typography component="summary" variant="body2">Details</Typography>
              <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>{pkg.id}<br />Libraries: {pkg.libraries.join(', ') || 'Standard library'}<br />SHA-256: {pkg.sha256}</Typography>
            </Box>
          </Box>
          {pkg.running > 0 && <Typography variant="body2">In use</Typography>}
          <Stack direction="row" spacing={1}>
            {<Button disabled={busy || pkg.running > 0} onClick={async () => {
              try {
                const [mapping, profiles] = await Promise.all([api.get(`/api/database/tools/packages/${pkg.id}/sources`), api.get('/api/database/tools/sources')]);
                setSources(profiles.data); setBinding({ id: pkg.id, ...mapping.data });
              } catch (e) { setError(message(e)); }
            }}>Connections</Button>}
            <Button variant="outlined" disabled={busy || pkg.running > 0} aria-label={`Update ${pkg.name}`}
              onClick={() => { target.current = pkg.id; input.current?.click(); }}>Update</Button>
            <Button color="error" disabled={busy || pkg.running > 0} aria-label={`Remove ${pkg.name}`} onClick={() => setRemove(pkg)}>Remove</Button>
          </Stack>
        </Stack>
      </Box>)}
    </Paper>
    <Dialog open={!!review} onClose={() => { if (!busy) { setReview(undefined); setFile(undefined); } }} fullWidth maxWidth="sm">
      <DialogTitle>{review?.current_version ? 'Review update' : 'Review package'}</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
        {error && <Alert severity="error">{error}</Alert>}
        <Typography variant="h6">{review?.package.name}</Typography>
        <Typography>{review?.current_version ? `${review.current_version} → ${review.package.version}` : `Version ${review?.package.version}`}</Typography>
        <Typography>{review?.package.tools.map(tool => tool.name).join(', ')}</Typography>
        <Typography variant="body2" color="text.secondary">Package structure and declared libraries checked. Python code has not been run.</Typography>
        {unchanged && <Alert severity="info">This package is already installed.</Alert>}
        {downgrade && <Alert severity="warning">This replaces the installed code with an older version.</Alert>}
        {!unchanged && review?.current_version === review?.package.version && <Alert severity="warning">A different package file uses the same version number. Ask the author to increase the version.</Alert>}
        {!!review?.running && <Alert severity="warning">This package is in use. Wait until it finishes, then review the update again.</Alert>}
      </Stack></DialogContent>
      <DialogActions><Button disabled={busy} onClick={() => { setReview(undefined); setFile(undefined); }}>Cancel</Button>
        <Button variant="contained" disabled={busy || unchanged || !!review?.running} onClick={install}>{action}</Button>
      </DialogActions>
    </Dialog>
    <ReportConnections open={connectionsOpen} onClose={() => { setConnectionsOpen(false); if (binding) void api.get('/api/database/tools/sources').then(r => setSources(r.data)); }} />
    <Dialog open={!!removeDraft} onClose={() => !busy && setRemoveDraft(undefined)}>
      <DialogTitle>Remove draft?</DialogTitle><DialogContent>{removeDraft?.name}: its saved scripts and input settings will be deleted. Installed reports are kept.</DialogContent>
      <DialogActions><Button disabled={busy} onClick={() => setRemoveDraft(undefined)}>Cancel</Button><Button disabled={busy} color="error" onClick={async () => {
        if (!removeDraft) return; setBusy(true);
        try { await api.delete(`/api/database/tools/drafts/${removeDraft.id}`); setRemoveDraft(undefined); await load(); }
        catch (e) { setError(message(e)); } finally { setBusy(false); }
      }}>Remove draft</Button></DialogActions>
    </Dialog>
    <Dialog open={!!binding} onClose={() => !busy && setBinding(undefined)} fullWidth maxWidth="sm">
      <DialogTitle>Assign connections</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
        {error && <Alert severity="error">{error}</Alert>}
        <Button onClick={() => setConnectionsOpen(true)}>Configure connections</Button>
        {binding?.has_operation && <TextField select label="Operation target" value={binding.operation_source || ''} disabled={busy} onChange={e => setBinding({ ...binding, operation_source: e.target.value })}>
          <MenuItem value="">Not configured</MenuItem>{sources.filter(s => s.access === 'operation').map(s => <MenuItem key={s.id} value={s.id}>{s.name} · {s.database}</MenuItem>)}
        </TextField>}
        {binding && <SourceMappings aliases={binding.aliases} sources={sources} mappings={binding.mappings}
          onChange={mappings => setBinding({ ...binding, mappings })} disabled={busy} />}
      </Stack></DialogContent><DialogActions><Button onClick={() => setBinding(undefined)} disabled={busy}>Cancel</Button>
        <Button disabled={busy} onClick={async () => {
          if (!binding) return; setBusy(true); setError('');
          try { await api.put(`/api/database/tools/packages/${binding.id}/sources`, { mappings: Object.fromEntries(binding.aliases.map(x => [x, binding.mappings[x]])), operation_source: binding.operation_source || null }); setBinding(undefined); }
          catch (e) { setError(message(e)); } finally { setBusy(false); }
        }}>Save connections</Button></DialogActions>
    </Dialog>
    <Dialog open={!!remove} onClose={() => !busy && setRemove(undefined)}>
      <DialogTitle>Remove {remove?.name}?</DialogTitle><DialogContent>Its operations and reports will no longer be available.</DialogContent>
      <DialogActions><Button disabled={busy} onClick={() => setRemove(undefined)}>Cancel</Button><Button color="error" disabled={busy} onClick={removePackage}>Remove package</Button></DialogActions>
    </Dialog>
  </Stack>;
}
