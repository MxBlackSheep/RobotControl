import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { api } from '../services/api';
import { requestMessage, saveBlob } from './ReportInputs';
const base = '/api/database/tools';
export type Source = { id: string; name: string; server: string; database: string; username: string; driver: string; trust_certificate: boolean; password?: string; revision?: string; access?: 'read' | 'operation' };
const trustPreferences = (): Record<string, boolean> => { try { const value = JSON.parse(localStorage.getItem('database-certificate-trust') || '{}'); return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; } catch { return {}; } };
const rememberTrust = (source: Source) => { try { localStorage.setItem('database-certificate-trust', JSON.stringify({ ...trustPreferences(), [source.server]: source.trust_certificate })); } catch { /* Saving a connection does not require browser storage. */ } };
const blank = (): Source => ({ id: 'db-' + crypto.randomUUID().slice(0, 12), name: '', server: '', database: '', username: '', password: '', driver: 'ODBC Driver 17 for SQL Server', trust_certificate: false, access: 'read' });

export default function ReportConnections({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [sources, setSources] = useState<Source[]>([]), [source, setSource] = useState<Source>(blank);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false);
  const [mode, setMode] = useState('existing'), [review, setReview] = useState<any>();
  const [authority, setAuthority] = useState({ username: '', password: '', windows_auth: false });
  const load = () => api.get(`${base}/sources`).then(r => setSources(r.data));
  useEffect(() => { if (open) { setError(''); void load().catch(e => setError(requestMessage(e))); } else { setAuthority({ username: '', password: '', windows_auth: false }); setReview(undefined); } }, [open]);
  const reset = () => { setSource(blank()); setReview(undefined); setMode('existing'); setAuthority({ username: '', password: '', windows_auth: false }); };
  const work = async (action: () => Promise<void>) => { setBusy(true); setError(''); setNotice(''); try { await action(); } catch (e) { setError(requestMessage(e)); } finally { setBusy(false); } };
  const save = () => work(async () => {
    if (mode === 'create') {
      const r = await api.post(`${base}/sources/access/review`, { ...source, password: undefined, access: 'read' }); setReview(r.data);
    } else {
      const r = await api.post(`${base}/sources`, source, { timeout: 120000 }); setNotice(r.data.message); rememberTrust(source); await load(); reset();
    }
  });
  const editing = sources.some(s => s.id === source.id);
  return <Dialog open={open} onClose={() => !busy && onClose()} fullWidth maxWidth="lg">
    <DialogTitle>Database connections</DialogTitle><DialogContent>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}{notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(220px, 1fr) minmax(0, 2fr)' }, gap: 3, pt: 1 }}>
        <Stack spacing={1}><Typography variant="subtitle1">Saved connections</Typography>
          {sources.map(item => <Box key={item.id} sx={{ p: 1, border: 1, borderColor: 'divider', borderRadius: 1 }}>
            <Typography sx={{ overflowWrap: 'anywhere' }}>{item.name}</Typography><Typography variant="caption">{item.database} · {item.access === 'operation' ? 'Operations' : 'Read-only'}</Typography>
            <Stack direction="row"><Button disabled={busy || !!review} onClick={() => { const { id, name, server, database, username, driver, trust_certificate, access } = item; setSource({ id, name, server, database, username, driver, trust_certificate, access: access || 'read' }); setMode('existing'); }}>Edit</Button>
              <Button disabled={busy || !!review} color="error" onClick={() => work(async () => { await api.delete(`${base}/sources/${item.id}`); await load(); if (source.id === item.id) reset(); })}>Remove</Button></Stack>
          </Box>)}
          <Button disabled={busy} onClick={reset}>New connection</Button>
        </Stack>
        {review ? <Stack spacing={2}>
          <Typography variant="h6">Create read-only account</Typography>
          <Typography sx={{ overflowWrap: 'anywhere' }}>Server: {review.server}<br />Database: {review.database}</Typography>
          <Typography>New read-only login: {review.account}</Typography>
          <Typography>Can read tables and view definitions. Cannot change data or run stored procedures.</Typography>
          <Box component="details"><Typography component="summary">Technical details</Typography><Typography variant="body2">{review.grants.join(' · ')}</Typography></Box>
          <Typography variant="body2">Choose an account allowed to create SQL logins. Its credentials are not saved.</Typography>
          <FormControlLabel label="Use RobotControl's Windows account" control={<Checkbox checked={authority.windows_auth} disabled={busy} onChange={(_, v) => setAuthority(a => ({ ...a, windows_auth: v }))} />} />
          {authority.windows_auth && <Typography variant="body2" color="text.secondary">Uses the Windows account running RobotControl, not the browser user. It must be allowed to create SQL logins.</Typography>}
          {!authority.windows_auth && <><TextField label="SQL administrator" autoComplete="off" value={authority.username} disabled={busy} onChange={e => setAuthority(a => ({ ...a, username: e.target.value }))} />
            <TextField label="Administrator password" type="password" autoComplete="new-password" value={authority.password} disabled={busy} onChange={e => setAuthority(a => ({ ...a, password: e.target.value }))} /></>}
          <Button onClick={() => saveBlob(new Blob([review.sql], { type: 'text/plain' }), 'create-read-only.sql')}>Download SQL for your administrator</Button>
        </Stack> : <Stack spacing={2}>
          <TextField select size="small" label="Account setup" value={mode} disabled={busy || editing} onChange={e => { setMode(e.target.value); if (e.target.value === 'create') setSource(s => ({ ...s, access: 'read' })); }}>
            <MenuItem value="existing">Use existing account</MenuItem><MenuItem value="create">Create read-only account</MenuItem></TextField>
          {mode === 'existing' && <TextField select size="small" label="Access" value={source.access || 'read'} disabled={busy || editing} onChange={e => setSource(s => ({ ...s, access: e.target.value as Source['access'] }))}>
            <MenuItem value="read">Read-only: viewers and reports</MenuItem><MenuItem value="operation">Operations: database changes</MenuItem></TextField>}
          {(['name', 'server', 'database', 'username', ...(mode === 'existing' ? ['password'] : [])] as ('name'|'server'|'database'|'username'|'password')[]).map(key => <TextField key={key} size="small" disabled={busy}
            label={{ name: 'Name', server: 'Server', database: 'Database', username: mode === 'create' ? 'New account name' : 'Account', password: 'Password' }[key]}
            type={key === 'password' ? 'password' : 'text'} value={source[key] || ''} autoComplete={key === 'password' ? 'new-password' : 'off'}
            helperText={key === 'username' && mode === 'create' ? 'A new SQL login, e.g. RobotControl_ReadOnly. Do not enter an existing administrator login.' : key === 'password' && editing ? 'Leave blank to keep the saved password.' : undefined}
            onChange={e => setSource(s => ({ ...s, [key]: key === 'password' && !e.target.value ? undefined : e.target.value, ...(key === 'server' && !editing ? { trust_certificate: trustPreferences()[e.target.value] ?? false } : {}) }))} />)}
          <Box component="details"><Typography component="summary">Details</Typography><Stack spacing={2} sx={{ mt: 2 }}>
            <TextField size="small" label="Connection ID" value={source.id} disabled={busy || editing} onChange={e => setSource(s => ({ ...s, id: e.target.value }))} />
            <TextField size="small" label="ODBC driver" value={source.driver} disabled={busy} onChange={e => setSource(s => ({ ...s, driver: e.target.value }))} />
          </Stack></Box>
          <FormControlLabel label="Trust server certificate" control={<Checkbox disabled={busy} checked={source.trust_certificate} onChange={(_, v) => setSource(s => ({ ...s, trust_certificate: v }))} />} />
          <Typography variant="caption" color="text.secondary">Encryption stays on. Trust skips certificate verification; remembered for this server after saving.</Typography>
          <Button disabled={busy} variant="contained" sx={{ alignSelf: 'flex-start' }} onClick={save}>{busy ? 'Checking…' : mode === 'create' ? 'Review access' : 'Check and save'}</Button>
        </Stack>}
      </Box>
    </DialogContent><DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
      {review && <><Button disabled={busy} onClick={() => { setReview(undefined); setAuthority({ username: '', password: '', windows_auth: false }); }}>Back</Button>
        <Button variant="contained" disabled={busy} onClick={() => work(async () => {
          try { const r = await api.post(`${base}/sources/access/create`, { token: review.token, ...authority }, { timeout: 120000 }); setNotice(r.data.message); rememberTrust(source); await load(); reset(); }
          finally { setAuthority({ username: '', password: '', windows_auth: false }); setReview(undefined); }
        })}>Create account</Button></>}
      <Button disabled={busy} onClick={onClose}>Close</Button></DialogActions>
  </Dialog>;
}

export function SourceMappings({ aliases, sources, mappings, onChange, disabled = false }: {
  aliases: string[]; sources: Source[]; mappings: Record<string, string>; onChange: (mapping: Record<string, string>) => void; disabled?: boolean;
}) {
  return <Stack spacing={2}>{aliases.map(alias => <TextField select key={alias} size="small" label={`Connection for ${alias}`} value={mappings[alias] || ''}
    disabled={disabled} onChange={e => onChange({ ...mappings, [alias]: e.target.value })}>
    {sources.filter(s => !s.access || s.access === 'read').map(s => <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>)}
  </TextField>)}</Stack>;
}
