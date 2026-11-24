import Details from './Details';
import InspectionWorkspace from './InspectionWorkspace';
import { Panel, EmptyPanel, DetailTitle, ListRow } from './PageLayout';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress, TextField, Stack, Typography, ListItemButton, Menu, MenuItem } from '@mui/material';
import { api } from '../services/api';
import { saveBlob, toolsBase } from './ReportInputs';
import ToolAuthoring from './ToolAuthoring';
import StatusChip from './StatusChip';
import { packageState, type PackageState } from '../types/packageState';
import ReviewReason from './ReviewReason';
import ReportConnections, { AssignConnections, PackageBinding, Source } from './ReportConnections';

type Package = { id: string; name: string; version: string; sha256: string; running: number;
  state: PackageState; reason: string;
  libraries: string[]; tools: { id: string; name: string; kind: string }[] };
type Review = { package: Package; sha256: string; current_version: string | null; current_sha256: string; running: number; changelog: string };
type Change = { version:string; previous_version?:string; at:string; actor?:string; note:string; files:{added:string[];changed:string[];removed:string[]} };
const message = (error: any) => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : 'The request could not be completed. Try again.';
const kindLabel = (kind:string) => ({report:'Report', operation:'Operation', preparation:'Preparation step', experiment:'Experiment type'}[kind] ?? kind);
const toolSummary = (tools:Package['tools']) => tools.map(tool => `${tool.name} (${kindLabel(tool.kind)})`).join(', ');
const hasPython = (pkg: Package) => pkg.tools.some(tool => tool.kind !== 'experiment');
const reviewScope = (pkg: Package) => hasPython(pkg)
  ? 'Package structure and declared libraries checked. Python code has not been run.'
  : 'Package structure checked. No Python code.';
const recoveryNote = 'Keep the previous ZIP before updating. Reinstalling it does not undo database changes.';
const older = (a: string, b: string) => {
  const left = a.split('.').map(Number), right = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) if (left[i] !== right[i]) return left[i] < right[i];
  return false;
};

export default function DatabasePackages({ active }: { active: boolean }) {
  const [selected, setSelected] = useState<string>();
  const [detailOpen, setDetailOpen] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [packages, setPackages] = useState<Package[]>([]);
  const [file, setFile] = useState<File>();
  const [review, setReview] = useState<Review>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [changeNote, setChangeNote] = useState('');
  const [history, setHistory] = useState<{name:string;tools:Package['tools'];changes:Change[]}>();
  const [remove, setRemove] = useState<Package>();
  const [toolEditor, setToolEditor] = useState<string>();
  const [drafts, setDrafts] = useState<{ id: string; name: string; review_reason?: string | null; openable?: boolean }[]>([]);
  const [removeDraft, setRemoveDraft] = useState<{ id: string; name: string }>();
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [binding, setBinding] = useState<PackageBinding>();
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    const { data } = await api.get(`${toolsBase}/packages`, { signal });
    if (!signal?.aborted) setPackages(data);
    const saved = await api.get(`${toolsBase}/drafts`, { signal });
    if (!signal?.aborted) setDrafts(saved.data);
  }, []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    load(controller.signal).catch(error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [active, load]);
  const inspect = async (incoming: File) => {
    setBusy(true); setError(''); setNotice(''); setReview(undefined); setFile(undefined); setChangeNote('');
    try {
      const form = new FormData(); form.append('file', incoming);
      const { data } = await api.post(`${toolsBase}/packages/inspect`, form, { headers: { 'Content-Type': 'multipart/form-data' } });
      // Prefilled once, as the review opens: later typing is never replaced.
      setFile(incoming); setReview(data); setChangeNote(data.changelog || '');
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
      form.append('change_note',changeNote);
      await api.post(`${toolsBase}/packages`, form, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 });
      setNotice(`${review.package.name} ${review.package.version} installed.`);
      setReview(undefined); setFile(undefined);
      await load();
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  };
  const removePackage = async () => {
    if (!remove) return;
    setBusy(true); setError('');
    try { await api.delete(`${toolsBase}/packages/${remove.id}`); setRemove(undefined); await load(); }
    catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  };
  const pkg = packages.find(pkg => pkg.id === selected);
  const unchanged = review?.sha256 === review?.current_sha256;
  const downgrade = !!review?.current_version && older(review.package.version, review.current_version);
  const action = !review?.current_version ? 'Install package' : downgrade ? 'Install older version' : review.current_version === review.package.version ? 'Replace version' : 'Update package';
  const finished = (notice?:string) => {setToolEditor(undefined);setError('');if(notice)setNotice(notice);void load().catch(e=>setError(message(e)));};
  if (toolEditor !== undefined) return <ToolAuthoring draftId={toolEditor || undefined} onClose={finished} />;
  return <Stack spacing={2}>
    <Stack direction="row" gap={1} flexWrap="wrap">
      <Button variant="contained" disabled={busy} onClick={() => input.current?.click()}>Import package ZIP</Button>
      <Button disabled={busy} onClick={() => setToolEditor('')}>Add tool</Button>
    </Stack>
    <input ref={input} hidden type="file" accept=".zip" onChange={event => {
      const selected = event.target.files?.[0]; event.target.value = ''; if (selected) void inspect(selected);
    }} />
    {error && !review && !remove && <Alert severity="error">{error}</Alert>}
    {notice && <Alert severity="success">{notice}</Alert>}
    {busy && <LinearProgress />}
    <InspectionWorkspace label="Manage packages" layout="table" selectorLabel="Packages" detailOpen={detailOpen && !!pkg} onBack={() => setDetailOpen(false)}
      selector={<Panel title="Packages" fill inset={false} sx={{ height: '100%' }} bodySx={{ overflow: 'auto' }}>
        {!packages.length && !busy && <Typography sx={{ p: 2 }}>No packages installed.</Typography>}
        {([['report', 'Reports'], ['operation', 'Operations'], ['preparation', 'Preparation steps'], ['experiment', 'Experiment types']] as const).map(([kind, label]) => {
          const group = packages.filter(pkg => pkg.tools[0]?.kind === kind);
          return <Box component="details" open key={kind} sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Box component="summary" sx={{ p: 2, cursor: 'pointer' }}>{label} ({group.length})</Box>
            {group.map(pkg => <ListItemButton key={pkg.id} aria-label={`Details for ${pkg.name}`} aria-current={selected === pkg.id ? 'true' : undefined}
              selected={selected === pkg.id} onClick={() => { setSelected(pkg.id); setDetailOpen(true); }} sx={{ display: 'block', p: 0, transition: 'none',
                '&.Mui-selected, &.Mui-selected:hover': { bgcolor: 'action.selected', boxShadow: theme => `inset 3px 0 0 ${theme.palette.primary.main}` } }}>
              <ListRow columns="minmax(0, 1fr) auto auto"><Typography title={pkg.name} noWrap>{pkg.name}</Typography><span>{pkg.version}</span><StatusChip {...packageState[pkg.state]} /></ListRow>
            </ListItemButton>)}
          </Box>;
        })}
      </Panel>}>
      {pkg ? <Panel title="Details" fill sx={{ height: '100%' }} bodySx={{ overflow: 'auto' }}>
        <Stack spacing={2} alignItems="flex-start">
          <DetailTitle>{pkg.name}</DetailTitle>
          <StatusChip {...packageState[pkg.state]} />
          {pkg.reason && <Alert severity="warning">{pkg.reason}</Alert>}
          {pkg.state === 'ready' && <Typography variant="body2" color="text.secondary">{pkg.running > 0 ? 'In use. Update, Connections and Remove wait until it finishes.' : 'Available to use.'}</Typography>}
          <Button id="package-more" aria-haspopup="menu" aria-controls={menuAnchor ? 'package-actions' : undefined}
            aria-expanded={!!menuAnchor} onClick={event => setMenuAnchor(event.currentTarget)}>More</Button>
          <Menu id="package-actions" anchorEl={menuAnchor} open={!!menuAnchor} onClose={() => setMenuAnchor(null)} MenuListProps={{ 'aria-labelledby': 'package-more' }}>
            <MenuItem disabled={busy || pkg.running > 0} onClick={() => { setMenuAnchor(null); input.current?.click(); }}>Update package</MenuItem>
            {pkg.tools.some(tool => tool.kind === 'experiment') && <MenuItem component={Link} to="/database?section=settings" onClick={() => setMenuAnchor(null)}>Experiments connection</MenuItem>}
            {pkg.tools.filter(tool => ['report', 'operation'].includes(tool.kind)).map(tool => <MenuItem key={tool.id} disabled={busy} onClick={async () => { setMenuAnchor(null);
              setBusy(true); setError('');
              try { const r = await api.post(`${toolsBase}/authoring/${tool.kind}/${tool.id}/edit`, {}); setToolEditor(r.data.id); }
              catch(e) { setError(message(e)); } finally { setBusy(false); }
            }}>{pkg.tools.length === 1 ? `Edit ${tool.kind}` : `Edit ${tool.name}`}</MenuItem>)}
            <MenuItem disabled={busy} onClick={async () => { setMenuAnchor(null); try { const r = await api.get(`${toolsBase}/packages/${pkg.id}/export`, { responseType: 'blob' }); saveBlob(r.data, /filename="([^"]+)"/.exec(r.headers['content-disposition'] || '')?.[1] || `${pkg.id}-${pkg.version}.zip`); } catch (e) { setError(message(e)); } }}>Download package</MenuItem>
            {hasPython(pkg) && <MenuItem disabled={busy || pkg.running > 0} onClick={async () => { setMenuAnchor(null);
              try {
                const [mapping, profiles] = await Promise.all([api.get(`${toolsBase}/packages/${pkg.id}/sources`), api.get(`${toolsBase}/sources`)]);
                setSources(profiles.data); setBinding({ id: pkg.id, name: pkg.name, ...mapping.data });
              } catch (e) { setError(message(e)); }
            }}>Connections</MenuItem>}
            <MenuItem disabled={busy} aria-label={`History for ${pkg.name}`} onClick={async()=>{ setMenuAnchor(null);
              setBusy(true);setError('');try{const r=await api.get(`${toolsBase}/packages/${pkg.id}/history`);setHistory({name:pkg.name,tools:pkg.tools,changes:r.data});}
              catch(e){setError(message(e));}finally{setBusy(false);}
            }}>History</MenuItem>
            <MenuItem sx={{ color: 'error.main' }} disabled={busy || pkg.running > 0} aria-label={`Remove ${pkg.name}`} onClick={() => { setMenuAnchor(null); setError(''); setRemove(pkg); }}>Remove</MenuItem>
          </Menu>
          <Details key={pkg.id}>
            <Stack spacing={1}>
              <Typography>Version {pkg.version}</Typography>
              <Typography variant="body2">{toolSummary(pkg.tools)}</Typography>
              <Typography variant="body2">{reviewScope(pkg)}</Typography>
              <Typography variant="body2">{recoveryNote}</Typography>
              <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>{pkg.id}<br />
                {hasPython(pkg) && <>Libraries: {pkg.libraries.join(', ') || 'Standard library'}<br /></>}
                SHA-256: {pkg.sha256}</Typography>
            </Stack>
          </Details>
        </Stack>
      </Panel> : <EmptyPanel>Select a package.</EmptyPanel>}
    </InspectionWorkspace>
    {!!drafts.length && <Box component="details"><Typography component="summary" sx={{ cursor: 'pointer' }}>Saved drafts ({drafts.length})</Typography>
      {drafts.map(d => <Stack key={d.id} direction="row" alignItems="center" gap={1}><Box sx={{ flex: 1, minWidth: 0 }}><Typography>{d.name}</Typography>
        {d.review_reason && <ReviewReason reason={d.review_reason} />}</Box>
        {d.review_reason && <StatusChip tone="attention" label="Needs review" />}
        {d.openable && <Button onClick={() => setToolEditor(d.id)}>Resume</Button>}
        <Button color="error" onClick={() => setRemoveDraft(d)}>Remove draft</Button></Stack>)}
    </Box>}
    <Dialog open={!!review} onClose={() => { if (!busy) { setReview(undefined); setFile(undefined); } }} fullWidth maxWidth="sm">
      <DialogTitle>{review?.current_version ? 'Review update' : 'Review package'}</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
        {error && <Alert severity="error">{error}</Alert>}
        <Typography variant="h6">{review?.package.name}</Typography>
        <Typography>{review?.current_version ? `${review.current_version} → ${review.package.version}` : `Version ${review?.package.version}`}</Typography>
        <Typography>{review && toolSummary(review.package.tools)}</Typography>
        <Typography variant="body2" color="text.secondary">{review && reviewScope(review.package)}</Typography>
        {review?.package.reason && <Alert severity="warning">{review.package.state === 'needs_review'
          ? 'This package will install as Needs review. It cannot run until you import a copy that declares min_robotcontrol_version.'
          : review.package.reason}</Alert>}
        {review?.current_version && <Typography variant="body2">{recoveryNote}</Typography>}
        <TextField label="What changed? (optional)" multiline maxRows={4} inputProps={{maxLength:2000}} value={changeNote} onChange={e=>setChangeNote(e.target.value)} disabled={busy} />
        {unchanged && <Alert severity="info">This package is already installed.</Alert>}
        {downgrade && <Alert severity="warning">This replaces the installed code with an older version.</Alert>}
        {!unchanged && review?.current_version === review?.package.version && <Alert severity="warning">A different package file uses the same version number. Ask the author to increase the version.</Alert>}
        {!!review?.running && <Alert severity="warning">This package is in use. Wait until it finishes, then review the update again.</Alert>}
      </Stack></DialogContent>
      <DialogActions><Button disabled={busy} onClick={() => { setReview(undefined); setFile(undefined); }}>Cancel</Button>
        <Button variant="contained" disabled={busy || unchanged || !!review?.running || review?.package.state === 'needs_newer'} onClick={install}>{action}</Button>
      </DialogActions>
    </Dialog>
    <Dialog open={!!history} onClose={()=>setHistory(undefined)} fullWidth maxWidth="sm"><DialogTitle>{history?.name} · History</DialogTitle>
      <DialogContent><Stack spacing={2}>
        {history && <Typography>Installed: {toolSummary(history.tools)}</Typography>}
        {!history?.changes.length && <Typography>No history was recorded for this installation.</Typography>}
        {!!history?.changes[history.changes.length-1]?.previous_version && <Typography variant="body2" color="text.secondary">Earlier changes were not recorded.</Typography>}
        {history?.changes.map((change,index)=><Box key={index} sx={{borderBottom:1,borderColor:'divider',pb:2}}>
          <Typography fontWeight={600}>{change.previous_version?`${change.previous_version} → ${change.version}`:`Version ${change.version}`}</Typography>
          <Typography variant="body2" color="text.secondary">{new Date(change.at).toLocaleString()} · {change.actor?`Published by ${change.actor}`:'Bundled installation'}</Typography>
          <Typography sx={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{change.note || 'No change note provided.'}</Typography>
          {(['added','changed','removed'] as const).map(kind=>!!change.files[kind].length&&<Typography key={kind} variant="body2" sx={{overflowWrap:'anywhere'}}>{kind[0].toUpperCase()+kind.slice(1)} files: {change.files[kind].join(', ')}</Typography>)}
        </Box>)}
      </Stack></DialogContent><DialogActions><Button onClick={()=>setHistory(undefined)}>Close</Button></DialogActions>
    </Dialog>
    <ReportConnections open={connectionsOpen} onClose={() => { setConnectionsOpen(false); if (binding) void api.get(`${toolsBase}/sources`).then(r => setSources(r.data)); }} />
    <Dialog open={!!removeDraft} onClose={() => !busy && setRemoveDraft(undefined)}>
      <DialogTitle>Remove draft?</DialogTitle><DialogContent>{removeDraft?.name}: its saved scripts and input settings will be deleted. Installed reports are kept.</DialogContent>
      <DialogActions><Button disabled={busy} onClick={() => setRemoveDraft(undefined)}>Cancel</Button><Button disabled={busy} color="error" onClick={async () => {
        if (!removeDraft) return; setBusy(true);
        try { await api.delete(`${toolsBase}/drafts/${removeDraft.id}`); setRemoveDraft(undefined); await load(); }
        catch (e) { setError(message(e)); } finally { setBusy(false); }
      }}>Remove draft</Button></DialogActions>
    </Dialog>
    <AssignConnections binding={binding} sources={sources} onChange={setBinding} onClose={() => setBinding(undefined)}
      onSaved={() => setBinding(undefined)} onManage={() => setConnectionsOpen(true)} />
    <Dialog open={!!remove} onClose={() => !busy && setRemove(undefined)}>
      <DialogTitle>Remove {remove?.name}?</DialogTitle><DialogContent>
        {error && <Alert severity="error">{error}</Alert>}
        {remove && <Typography>{toolSummary(remove.tools)}</Typography>}
        <Typography>Its tools will no longer be available.</Typography>
        <Typography>Removing deletes this package's history. Database changes already made are not undone; an older ZIP is needed to go back.</Typography>
      </DialogContent>
      <DialogActions><Button disabled={busy} onClick={() => setRemove(undefined)}>Cancel</Button><Button color="error" disabled={busy} onClick={removePackage}>Remove package</Button></DialogActions>
    </Dialog>
  </Stack>;
}
